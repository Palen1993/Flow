"""
Suite de Pruebas E2E de Flujos de Usuario Reales para GameFlow Launcher.
Valida el circuito completo: Diálogos UI -> App -> GameLibraryService -> Disco (games.json) -> Recarga,
incluyendo estanterías filtradas, colisiones por nombre, errores de lanzamiento, recuperación .bak,
modo Mini <-> Big Picture y navegación híbrida ratón/teclado.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import app as app_mod
import core.collections_service as coll_mod
import core.config as cfg_mod
from core.library_service import GameLibraryService
from ui.dialogs.add_edit_game import AddEditGameDialog
from ui.dialogs.cover_picker_dialog import CoverPickerDialog
from ui.dialogs.external_import_dialog import ExternalImportDialog
from ui.dialogs.scan_results import ScanResultsDialog
from ui.dialogs.select_game_to_edit import SelectGameToEditDialog


class TestE2EUserFlows(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="gf_e2e_")
        self.games_file = os.path.join(self.tmp_dir, "games.json")
        self.covers_dir = os.path.join(self.tmp_dir, "covers")
        self.wallpapers_dir = os.path.join(self.tmp_dir, "wallpapers")
        self.gamepad_cfg_file = os.path.join(self.tmp_dir, "gamepad_config.json")
        self.backups_dir = os.path.join(self.tmp_dir, "backups")
        os.makedirs(self.covers_dir, exist_ok=True)
        os.makedirs(self.wallpapers_dir, exist_ok=True)
        os.makedirs(self.backups_dir, exist_ok=True)

        self.fake_monitors = [
            {
                "id": 0,
                "device": "\\\\.\\DISPLAY1",
                "name": "Test Display 1",
                "raw_name": "Test Display 1",
                "is_primary": True,
                "rect": (0, 0, 1920, 1080),
            },
            {
                "id": 1,
                "device": "\\\\.\\DISPLAY2",
                "name": "Test Display 2",
                "raw_name": "Test Display 2",
                "is_primary": False,
                "rect": (1920, 0, 3840, 1080),
            },
        ]

        self._patchers = [
            patch.object(cfg_mod, "CONFIG_FILE", self.games_file),
            patch.object(cfg_mod, "COVERS_DIR", self.covers_dir),
            patch.object(cfg_mod, "WALLPAPERS_DIR", self.wallpapers_dir),
            patch.object(cfg_mod, "GAMEPAD_CONFIG_FILE", self.gamepad_cfg_file),
            patch.object(cfg_mod, "BACKUPS_DIR", self.backups_dir),
            patch.object(coll_mod, "get_storage_dir", lambda: self.tmp_dir),
            patch("app.ensure_watcher_running"),
            patch("app.ensure_gamebar_nexus_disabled"),
            patch("app.force_foreground_window", return_value=True),
            patch("app.poll_active_gamepad", return_value=(False, None, "")),
            patch("app.get_monitors", return_value=self.fake_monitors),
            patch("ui.dialogs.select_game_to_edit.get_monitors", return_value=self.fake_monitors),
            patch.object(app_mod.App, "_start_gamepad_loop", lambda s: None),
            patch.object(app_mod.App, "_poll_battery_status", lambda s: None),
            patch.object(CoverPickerDialog, "_start_search", lambda s: None),
            patch.object(ExternalImportDialog, "_start_scan_thread", lambda s: None),
        ]
        for p in self._patchers:
            p.start()

        self._apps = []

    def tearDown(self):
        for a in reversed(self._apps):
            try:
                if a.winfo_exists():
                    a.destroy()
            except Exception:
                pass
        for p in reversed(self._patchers):
            try:
                p.stop()
            except Exception:
                pass
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _boot_app(self, initial_games=None) -> app_mod.App:
        if initial_games is not None:
            with open(self.games_file, "w", encoding="utf-8") as f:
                json.dump(initial_games, f, indent=2, ensure_ascii=False)
        instance = app_mod.App()
        instance.withdraw()
        instance.update()
        self._apps.append(instance)
        return instance

    def _reload_games_from_disk(self):
        svc = GameLibraryService()
        svc.load()
        return svc.games

    def test_01_empty_library_state_and_admin_prompt(self):
        app = self._boot_app([])
        self.assertEqual(app.library.games, [])
        self.assertEqual(app.games, [])
        self.assertEqual(app.btn_launch.cget("state"), "disabled")

        with patch("app.show_info") as mock_info:
            app.open_select_game_dialog()
            mock_info.assert_called_once()
            _, msg = mock_info.call_args[0][:2]
            self.assertIn("Importar Juegos", msg)

    def test_02_admin_all_games_preserves_full_library_across_edit_and_delete_on_filtered_shelf(self):
        initial = [
            {"name": "Alpha Fav", "path": r"C:\Games\alpha.exe", "monitor": 0, "favorite": True, "status": "Jugando"},
            {"name": "Beta Normal", "path": r"C:\Games\beta.exe", "monitor": 0, "favorite": False, "status": "Por jugar"},
            {"name": "Gamma Normal", "path": r"C:\Games\gamma.exe", "monitor": 0, "favorite": False, "status": "Por jugar"},
        ]
        app = self._boot_app(initial)

        # Situar al usuario en una estantería filtrada ("favorites", solo 1 juego)
        app.apply_filter("favorites")
        app.update()
        self.assertEqual(app.current_filter_id, "favorites")
        self.assertEqual(len(app.games), 1)
        self.assertEqual(len(app.library.games), 3)

        # Abrir "Administrar Todos los Juegos..."
        app.open_select_game_dialog()
        app.update()
        sel_dlg = app._select_dialog
        self.assertIsInstance(sel_dlg, SelectGameToEditDialog)
        self.assertEqual(len(sel_dlg.games), 3)

        # Editar "Beta Normal" (índice 1 en library.games) y simular regreso al listado
        sel_dlg._select_game(1)
        app.update()
        app.on_specific_game_edited(
            1,
            "Beta Remastered",
            r"C:\Games\beta.exe",
            1,
            False,
            "",
            genre="RPG",
            platform="Steam",
            favorite=False,
            status="Completado",
            collections=[],
        )
        sel_dlg._on_edit_finished()
        app.update()

        # Regresión clave: tras editar desde estantería filtrada, SelectGameToEditDialog sigue mostrando los 3 juegos
        self.assertTrue(sel_dlg.winfo_exists())
        self.assertEqual(len(sel_dlg.games), 3)
        self.assertIn("Beta Remastered", [g["name"] for g in sel_dlg.games])

        # Eliminar el único juego de Favoritos ("Alpha Fav", índice 0) y volver al diálogo
        app.delete_specific_game(0, confirm=False)
        sel_dlg._on_edit_finished()
        app.update()

        # Aunque Favoritos quedó vacío, siguen quedando 2 juegos en library.games: NO debe cerrarse ni vaciarse
        self.assertTrue(sel_dlg.winfo_exists())
        self.assertEqual(len(sel_dlg.games), 2)
        self.assertEqual([g["name"] for g in sel_dlg.games], ["Beta Remastered", "Gamma Normal"])

        # Verificar persistencia real tras recarga desde disco
        reloaded = self._reload_games_from_disk()
        self.assertEqual([g["name"] for g in reloaded], ["Beta Remastered", "Gamma Normal"])
        self.assertEqual(reloaded[0]["monitor"], 1)
        self.assertEqual(reloaded[0]["genre"], "RPG")

    def test_03_add_manual_and_scan_import_persist_and_deduplicate(self):
        app = self._boot_app([])

        # 1. Alta manual real mediante AddEditGameDialog -> App.on_game_added -> games.json
        app.open_add_dialog()
        app.update()
        add_dlg = app._add_dialog
        self.assertIsInstance(add_dlg, AddEditGameDialog)
        add_dlg.name_entry.insert(0, "Delta Quest")
        add_dlg.path_entry.insert(0, r"C:\Games\Delta\delta.exe")
        add_dlg.save()
        app.update()

        self.assertEqual(len(app.library.games), 1)
        self.assertEqual(app.games[app.selected_index]["name"], "Delta Quest")

        # 2. Importar mediante ScanResultsDialog + ruta equivalente en distinta capitalización (sin duplicar)
        candidates = [
            {"name": "Delta Quest Dup", "path": r"c:/Games/Delta/delta.exe", "cover": ""},
            {"name": "Epsilon Scanned", "path": r"C:\Games\Epsilon\eps.exe", "cover": ""},
        ]
        scan_dlg = ScanResultsDialog(app, r"C:\Games", candidates, on_import_callback=app.on_games_imported)
        app.update()
        scan_dlg.import_selected()
        app.update()

        self.assertEqual(len(app.library.games), 2)
        reloaded = self._reload_games_from_disk()
        self.assertEqual(len(reloaded), 2)
        self.assertEqual({g["name"] for g in reloaded}, {"Delta Quest Dup", "Epsilon Scanned"})

        # 3. Administrar Todos los Juegos debe reflejar ambos inmediatamente
        app.open_select_game_dialog()
        app.update()
        self.assertEqual(len(app._select_dialog.games), 2)

    def test_04_same_name_different_path_resolves_exact_game_index(self):
        initial = [
            {"name": "Hollow Knight", "path": r"C:\PCGames\HollowKnight\hk.exe", "favorite": False},
            {"name": "Hollow Knight", "path": r"C:\ROMs\Switch\hk.nsp", "favorite": False, "is_rom": True},
        ]
        app = self._boot_app(initial)

        idx_rom = app._get_library_index_for_game(app.library.games[1])
        self.assertEqual(idx_rom, 1)

        # Seleccionar el segundo (ROM) en el carrusel y marcarlo como favorito
        rom_idx_in_shelf = next(i for i, g in enumerate(app.games) if g["path"] == initial[1]["path"])
        app.selected_index = rom_idx_in_shelf
        with patch("core.feedback.feedback_click"):
            app.toggle_current_game_favorite()

        reloaded = self._reload_games_from_disk()
        self.assertFalse(reloaded[0]["favorite"])
        self.assertTrue(reloaded[1]["favorite"])

    def test_05_unfavorite_and_delete_last_game_on_filtered_shelf(self):
        initial = [
            {"name": "Only Fav", "path": r"C:\Games\fav.exe", "favorite": True},
            {"name": "Normal A", "path": r"C:\Games\a.exe", "favorite": False},
            {"name": "Normal B", "path": r"C:\Games\b.exe", "favorite": False},
        ]
        app = self._boot_app(initial)
        app.apply_filter("favorites")
        app.update()
        self.assertEqual(app.current_filter_id, "favorites")
        self.assertEqual(len(app.games), 1)

        # Quitar favorito estando dentro de la propia estantería de Favoritos
        with patch("core.feedback.feedback_click"):
            app.toggle_current_game_favorite()
        app.update()

        self.assertGreaterEqual(app.selected_index, 0)
        if app.games:
            self.assertLess(app.selected_index, len(app.games))

        reloaded = self._reload_games_from_disk()
        self.assertFalse(reloaded[0]["favorite"])

        # Borrar el último elemento seleccionado sin quedar fuera de rango
        app.apply_filter("all")
        app.selected_index = len(app.games) - 1
        app.delete_current_game(confirm=False)
        app.update()
        self.assertEqual(len(app.library.games), 2)
        self.assertGreaterEqual(app.selected_index, 0)
        self.assertLess(app.selected_index, len(app.games))

    def test_06_details_save_and_corrupted_json_recovers_from_bak(self):
        initial = [
            {"name": "Starfield", "path": r"C:\Games\starfield.exe", "playtime_minutes": 45}
        ]
        app = self._boot_app(initial)

        # Primera escritura para generar games.json y rotar a .bak en el segundo guardado
        app.library.games[0]["power_profile"] = "high_performance"
        app.save_games()
        app.library.games[0]["steam_app_id"] = "1716740"
        app.save_games()
        self.assertTrue(os.path.exists(f"{self.games_file}.bak"))

        # Corromper el games.json principal y comprobar restauración automática desde .bak
        with open(self.games_file, "w", encoding="utf-8") as f:
            f.write("{corrupted_json!!")

        recovered = self._reload_games_from_disk()
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["name"], "Starfield")
        self.assertEqual(recovered[0]["power_profile"], "high_performance")

    def test_07_launch_error_recovery_and_sentinel_playtime_sync(self):
        import time

        initial = [
            {"name": "Missing Exe", "path": os.path.join(self.tmp_dir, "missing_game.exe"), "playtime_minutes": 10}
        ]
        app = self._boot_app(initial)
        app.gamepad_config["close_on_game_launch"] = True

        # Ejecutar el hilo real de GameExecutionService contra un .exe inexistente
        with patch("core.execution_service.feedback_launch"), \
             patch("core.power_service.apply_game_performance_profile"), \
             patch("app.show_error") as mock_err:
            app.launch_current_game()
            deadline = time.time() + 3.0
            while not mock_err.called and time.time() < deadline:
                app.update()
                time.sleep(0.02)

            mock_err.assert_called_once()
            self.assertFalse(app.execution_service.is_launching)
            self.assertEqual(app.btn_launch.cget("state"), "normal")

        # Simular actualización externa de playtime en disco por el centinela y regreso al lanzador
        with open(self.games_file, "r", encoding="utf-8") as f:
            disk_games = json.load(f)
        disk_games[0]["playtime_minutes"] = 95
        with open(self.games_file, "w", encoding="utf-8") as f:
            json.dump(disk_games, f)
        os.utime(self.games_file, (os.path.getatime(self.games_file), os.path.getmtime(self.games_file) + 5))

        app.restore_window()
        app.update()
        self.assertEqual(app.library.games[0]["playtime_minutes"], 95)

    def test_08_mini_full_mode_and_mouse_keyboard_2d_navigation(self):
        initial = [
            {"name": "Celeste", "path": r"C:\Games\celeste.exe", "favorite": True},
            {"name": "Doom Eternal", "path": r"C:\Games\doom.exe", "favorite": False},
            {"name": "Zelda BOTW", "path": r"C:\Games\zelda.exe", "favorite": True},
        ]
        app = self._boot_app(initial)
        app.update()
        self.assertGreaterEqual(len(app.active_shelves), 2)

        # Navegación horizontal por teclado y salto rápido por letra
        app.cover_stage.select_index(0)
        app._on_quick_letter_jump(SimpleNamespace(char="z"))
        self.assertEqual(app.games[app.selected_index]["name"], "Zelda BOTW")

        # Navegación vertical por ratón (Shift+Rueda y arrastre vertical)
        start_shelf = app.current_shelf_idx
        app.cover_stage._on_shift_mouse_wheel(SimpleNamespace(delta=-120))
        self.assertNotEqual(app.current_shelf_idx, start_shelf)

        prev_shelf = app.current_shelf_idx
        app.cover_stage._on_mouse_down(SimpleNamespace(x=500, y=320))
        app.cover_stage._on_mouse_drag(SimpleNamespace(x=504, y=220))
        app.cover_stage._on_mouse_up(SimpleNamespace(x=504, y=210))
        self.assertNotEqual(app.current_shelf_idx, prev_shelf)

        # Transición Big Picture -> Modo Mini -> Big Picture preservando navegación 2D
        app.set_mini_mode()
        app.update()
        self.assertTrue(app.is_mini_mode)
        self.assertTrue(app.cover_stage.is_transparent_mode)

        mini_shelf = app.current_shelf_idx
        app.cover_stage._on_shift_mouse_wheel(SimpleNamespace(delta=-120))
        self.assertNotEqual(app.current_shelf_idx, mini_shelf)

        app.set_full_mode()
        app.update()
        self.assertFalse(app.is_mini_mode)
        self.assertFalse(app.cover_stage.is_transparent_mode)


if __name__ == "__main__":
    unittest.main()
