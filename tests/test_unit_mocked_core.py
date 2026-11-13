"""
Suite de pruebas unitarias con mocks (sin red real ni efectos sobre datos del usuario).
Verifica los módulos críticos de seguridad, concurrencia, sincronización e IPC.
"""
import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import _thread_lock_state, config_lock, sanitize_game_filename
from core.cover_downloader import (
    _is_safe_http_url,
    _safe_read_response,
    fetch_steamgriddb_best_assets,
    search_steamgriddb_covers,
)
from core.library_service import GameLibraryService
from core.steamgriddb_client import search_steamgriddb_covers_impl
from scripts.sync_to_player import stop_running_player_processes
from ui.display_scale import get_active_display_scale, set_active_display_scale


class TestSanitizeGameFilename(unittest.TestCase):
    def test_strips_invalid_ntfs_and_traversal_chars(self):
        self.assertEqual(sanitize_game_filename("The Witcher 3: Wild Hunt"), "The Witcher 3_ Wild Hunt")
        self.assertEqual(sanitize_game_filename("../../evil/path\\game*?\"<>|"), "evil_path_game")

    def test_blocks_windows_reserved_device_names(self):
        for reserved in ("CON", "prn", "Aux", "NUL", "COM1", "lpt9"):
            res = sanitize_game_filename(reserved)
            self.assertTrue(res.startswith("_"), f"Expected '{reserved}' to be prefixed, got '{res}'")

    def test_empty_or_symbols_fallback(self):
        self.assertEqual(sanitize_game_filename("...:::..."), "game")
        self.assertEqual(sanitize_game_filename("", default="custom_default"), "custom_default")


class TestReentrantConfigLock(unittest.TestCase):
    def test_reentrant_depth_tracking(self):
        initial_depth = getattr(_thread_lock_state, "depth", 0)
        self.assertEqual(initial_depth, 0)
        with config_lock(timeout_ms=1000):
            self.assertEqual(_thread_lock_state.depth, 1)
            with config_lock(timeout_ms=1000):
                self.assertEqual(_thread_lock_state.depth, 2)
            self.assertEqual(_thread_lock_state.depth, 1)
        self.assertEqual(_thread_lock_state.depth, 0)


class TestLibraryServiceRefresh(unittest.TestCase):
    @patch("core.library_service.get_games_file_mtime")
    @patch("core.library_service.load_games_data")
    def test_refresh_if_modified_detects_playtime_addition_and_empty(self, mock_load, mock_mtime):
        mock_mtime.return_value = 100.0
        mock_load.return_value = [
            {"name": "Game A", "path": "C:/Games/A.exe", "playtime_minutes": 10, "last_played": 1000}
        ]
        svc = GameLibraryService()
        svc.load()
        self.assertEqual(len(svc.games), 1)

        # 1. Sin cambio de mtime -> False
        self.assertFalse(svc.refresh_if_modified())

        # 2. Cambio en playtime_minutes desde sentinel_process -> True y actualiza in-place
        mock_mtime.return_value = 200.0
        mock_load.return_value = [
            {"name": "Game A", "path": "C:/Games/A.exe", "playtime_minutes": 45, "last_played": 2000}
        ]
        self.assertTrue(svc.refresh_if_modified())
        self.assertEqual(svc.games[0]["playtime_minutes"], 45)
        self.assertEqual(svc._file_mtime, 200.0)

        # 3. Adición externa de un juego nuevo -> True
        mock_mtime.return_value = 300.0
        mock_load.return_value = [
            {"name": "Game A", "path": "C:/Games/A.exe", "playtime_minutes": 45, "last_played": 2000},
            {"name": "Game B", "path": "C:/Games/B.exe", "playtime_minutes": 0, "last_played": 0},
        ]
        self.assertTrue(svc.refresh_if_modified())
        self.assertEqual(len(svc.games), 2)

        # 4. Vaciado externo de biblioteca -> True y actualiza _file_mtime sin quedar en bucle
        mock_mtime.return_value = 400.0
        mock_load.return_value = []
        self.assertTrue(svc.refresh_if_modified())
        self.assertEqual(len(svc.games), 0)
        self.assertEqual(svc._file_mtime, 400.0)
        self.assertFalse(svc.refresh_if_modified())


class TestCoverDownloaderSecurityAndMocks(unittest.TestCase):
    def test_is_safe_http_url(self):
        self.assertTrue(_is_safe_http_url("https://cdn2.steamgriddb.com/grid/abc.png"))
        self.assertTrue(_is_safe_http_url("http://example.com/image.jpg"))
        self.assertFalse(_is_safe_http_url("file:///C:/Windows/System32/cmd.exe"))
        self.assertFalse(_is_safe_http_url("ftp://example.com/file"))
        self.assertFalse(_is_safe_http_url(""))

    def test_safe_read_response_enforces_max_bytes(self):
        small_resp = io.BytesIO(b"hello world")
        self.assertEqual(_safe_read_response(small_resp, max_bytes=100), b"hello world")

        oversized_resp = io.BytesIO(b"x" * 250)
        with self.assertRaises(ValueError):
            _safe_read_response(oversized_resp, max_bytes=100)

    @patch("core.steamgriddb_client.urllib.request.urlopen")
    def test_steamgriddb_module_reexport_and_mocked_search(self, mock_urlopen):
        self.assertIsNotNone(fetch_steamgriddb_best_assets)
        self.assertIsNotNone(search_steamgriddb_covers)

        def fake_urlopen(req, timeout=1.8):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "/search/autocomplete/" in url:
                payload = {"success": True, "data": [{"id": 42, "name": "Hades"}]}
            elif "/grids/game/42" in url:
                payload = {
                    "success": True,
                    "data": [
                        {
                            "url": "https://cdn2.steamgriddb.com/grid/hades_full.png",
                            "thumb": "https://cdn2.steamgriddb.com/thumb/hades_thumb.png",
                            "width": 600,
                            "height": 900,
                        }
                    ],
                }
            else:
                payload = {"success": False, "data": []}
            cm = MagicMock()
            cm.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")
            return cm

        mock_urlopen.side_effect = fake_urlopen
        with patch.dict(os.environ, {"STEAMGRIDDB_API_KEY": "dummy_test_key"}):
            results = search_steamgriddb_covers_impl(
                "Hades",
                max_results=5,
                browser_headers={"User-Agent": "Test"},
                relevance_fn=lambda title, snippet, url, q: True,
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Hades")
        self.assertEqual(results[0]["source"], "SteamGridDB")
        self.assertTrue(results[0]["is_vertical"])


class TestSyncToPlayerStopProcesses(unittest.TestCase):
    @patch("scripts.sync_to_player.psutil.wait_procs")
    @patch("scripts.sync_to_player.psutil.process_iter")
    def test_stops_only_processes_inside_player_dir(self, mock_iter, mock_wait):
        proc_inside = MagicMock()
        proc_inside.info = {
            "pid": 1234,
            "name": "GameFlow_Launcher.exe",
            "exe": r"C:\Users\jorge\Documents\Programas\GameFlow\GameFlow_Launcher.exe",
        }
        proc_outside = MagicMock()
        proc_outside.info = {
            "pid": 5678,
            "name": "explorer.exe",
            "exe": r"C:\Windows\explorer.exe",
        }
        mock_iter.return_value = [proc_inside, proc_outside]
        mock_wait.return_value = ([proc_inside], [])

        stopped = stop_running_player_processes(r"C:\Users\jorge\Documents\Programas\GameFlow")
        self.assertEqual(stopped, 1)
        proc_inside.terminate.assert_called_once()
        proc_outside.terminate.assert_not_called()


class TestDisplayScaleRestored(unittest.TestCase):
    def test_set_and_restore_display_scale(self):
        original = get_active_display_scale()
        try:
            set_active_display_scale(1.25)
            self.assertAlmostEqual(get_active_display_scale(), 1.25)
            prev = get_active_display_scale()
            set_active_display_scale(0.85)
            self.assertAlmostEqual(get_active_display_scale(), 0.85)
            set_active_display_scale(prev)
            self.assertAlmostEqual(get_active_display_scale(), 1.25)
        finally:
            set_active_display_scale(original)


class TestGamepadHidAndCropEngineModules(unittest.TestCase):
    def test_gamepad_hid_dualsense_and_ds4_decoding(self):
        from core.gamepad_hid import decode_playstation_hid_report
        import gamepad_manager

        self.assertIs(gamepad_manager.decode_playstation_hid_report, decode_playstation_hid_report)

        # DualSense Bluetooth report (0x31), byte 54: charging=1 (0x10), level=8 (80%)
        ds_bt = bytearray(78)
        ds_bt[0] = 0x31
        ds_bt[54] = 0x18
        res = decode_playstation_hid_report(0x0CE6, bytes(ds_bt))
        self.assertIsNotNone(res)
        self.assertTrue(res["is_charging"])
        self.assertEqual(res["percent"], 80)

    def test_cover_crop_engine_prepare_and_compose(self):
        from PIL import Image
        from ui.dialogs.cover_crop_engine import (
            compose_cover_preview_stage,
            prepare_card_and_preview_images,
        )

        raw = Image.new("RGBA", (800, 1200), (20, 80, 160, 255))
        prev_im, card_th, orig_sz = prepare_card_and_preview_images(raw, is_wp=False, card_w=200)
        self.assertEqual(orig_sz, (800, 1200))
        self.assertLessEqual(max(prev_im.size), 600)
        self.assertLessEqual(max(card_th.size), 132)

        stage = compose_cover_preview_stage(
            base_im=prev_im,
            game_name="Test Game",
            fit_mode="auto",
            crop_anchor="center",
            crop_offset=0.5,
            box_size=186,
        )
        self.assertEqual(stage.size, (240, 248))


class TestTkImageCacheAcrossRoots(unittest.TestCase):
    def test_ctk_image_caches_survive_root_destroy_and_recreation(self):
        import customtkinter as ctk
        from ui.controller_hud import get_button_icon_ctk
        from ui.dialogs.select_game_to_edit import get_game_thumbnail_ctk

        sample_game = {"name": "Regression Test Game"}

        for _ in range(2):
            root = ctk.CTk()
            try:
                root.withdraw()
                icon = get_button_icon_ctk("x", family="xbox", size=18, scale=1.0)
                thumb = get_game_thumbnail_ctk(sample_game, size=32)
                btn1 = ctk.CTkButton(root, text="Icon", image=icon)
                btn2 = ctk.CTkButton(root, text="Thumb", image=thumb)
                btn1.pack()
                btn2.pack()
                root.update_idletasks()
            finally:
                root.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
