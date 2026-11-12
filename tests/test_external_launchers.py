import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import customtkinter as ctk

from core.external_launchers import (
    get_steam_games, get_epic_games, get_gog_games,
    scan_emulator_roms, get_all_external_games, EMULATOR_PROFILES
)
from ui.dialogs.external_import_dialog import ExternalImportDialog


class TestExternalLaunchers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import core.cover_resolver as cover_res_mod
        cls._tmp_covers = tempfile.mkdtemp(prefix="gf_ext_covers_")
        cls._covers_patcher = patch.object(cover_res_mod, "COVERS_DIR", cls._tmp_covers)
        cls._covers_patcher.start()
        try:
            cls.root = ctk.CTk()
            cls.root.withdraw()
        except Exception:
            cls.root = None

    @classmethod
    def tearDownClass(cls):
        if cls.root:
            try:
                cls.root.destroy()
            except Exception:
                pass
        try:
            cls._covers_patcher.stop()
        except Exception:
            pass
        shutil.rmtree(cls._tmp_covers, ignore_errors=True)

    def test_01_real_installed_launchers_scan(self):
        # Must execute cleanly on host Windows without crashing
        games = get_all_external_games()
        self.assertIsInstance(games, list)
        for g in games:
            self.assertIn("name", g)
            self.assertIn("path", g)
            self.assertIn("platform", g)
            if g["platform"] == "Steam":
                self.assertIn("cover_url", g)
                self.assertIn("wallpaper_url", g)
                self.assertTrue(g["cover_url"].startswith("https://cdn.cloudflare.steamstatic.com/steam/apps/"))

    def test_02_emulator_roms_scanner(self):
        # Create a mock ROM directory structure
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy emulator exe and ROMs
            dummy_emu = os.path.join(tmpdir, "retroarch.exe")
            with open(dummy_emu, "wb") as f:
                f.write(b"MZ")

            rom1 = os.path.join(tmpdir, "Super Mario World (USA).sfc")
            rom2 = os.path.join(tmpdir, "Chrono Trigger [SNES].smc")
            txt_file = os.path.join(tmpdir, "readme.txt")
            for r in (rom1, rom2, txt_file):
                with open(r, "wb") as f:
                    f.write(b"DUMMY_ROM")

            res = scan_emulator_roms(
                emulator_exe=dummy_emu,
                roms_dir=tmpdir,
                profile_name="RetroArch"
            )
            # Must detect exactly 2 ROMs and ignore readme.txt
            self.assertEqual(len(res), 2)
            names = [g["name"] for g in res]
            self.assertIn("Super Mario World", names)
            self.assertIn("Chrono Trigger", names)
            self.assertEqual(res[0]["path"], dummy_emu)
            self.assertIn(dummy_emu, res[0]["path"])
            self.assertTrue(len(res[0]["launch_args"]) > 0)

    def test_03_external_import_dialog_instantiation(self):
        if not self.root:
            self.skipTest("No GUI display available")

        mock_candidates = [
            {
                "name": "Portal 2",
                "path": "C:\\Games\\Portal2\\portal2.exe",
                "platform": "Steam",
                "cover": "",
                "already_added": False
            },
            {
                "name": "Hades",
                "path": "C:\\Games\\Hades\\Hades.exe",
                "platform": "Epic Games",
                "cover": "",
                "already_added": True
            }
        ]

        dlg = ExternalImportDialog(self.root, existing_games=[])
        dlg._populate_candidates(mock_candidates)
        self.assertEqual(len(dlg.items_vars), 2)

        # First item (new) should be checked by default
        self.assertTrue(dlg.items_vars[0][0].get())
        # Second item (already added) should be unchecked by default
        self.assertFalse(dlg.items_vars[1][0].get())

        # Test gamepad input simulation
        # D-pad Down -> step row
        dlg.handle_gamepad_input({"down": True}, {})
        self.assertEqual(dlg._focused_row_idx, 1)

        # (A) -> toggle checkbox
        dlg.handle_gamepad_input({"a": True}, {})
        self.assertTrue(dlg.items_vars[1][0].get())

        # (X) -> toggle all (solo afecta a los nuevos por defecto)
        dlg.handle_gamepad_input({"x": True}, {})
        self.assertFalse(dlg.items_vars[0][0].get())
        self.assertTrue(dlg.items_vars[1][0].get())

        dlg.close()


if __name__ == "__main__":
    unittest.main()
