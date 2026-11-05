import sys
import os
import unittest
from unittest.mock import MagicMock, patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import customtkinter as ctk
from core.cover_downloader import fetch_steamgriddb_best_assets, download_and_apply_steamgriddb_media
from ui.dialogs.batch_steamgriddb_dialog import BatchSteamGridDBDialog


class TestBatchSteamGridDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ctk.CTk()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_1_fetch_steamgriddb_best_assets_live(self):
        """Verifica que la API pública oficial de SteamGridDB resuelve carátulas (grids) y wallpapers (heroes)."""
        res = fetch_steamgriddb_best_assets("Black Myth Wukong")
        self.assertIsNotNone(res, "SteamGridDB no devolvió resultados para 'Black Myth Wukong'")
        self.assertIn("Black Myth", res.get("matched_name", ""))
        self.assertTrue(res.get("grid_url", "").startswith("https://cdn2.steamgriddb.com/grid/"))
        self.assertTrue(res.get("hero_url", "").startswith("https://cdn2.steamgriddb.com/hero/"))

    def test_2_batch_dialog_initialization_and_gamepad(self):
        """Verifica que el diálogo de descarga masiva se crea correctamente con sus controles y navegación con mando."""
        mock_games = [
            {"name": "Game One", "path": "C:/Games/One/game.exe", "cover": "", "wallpaper": ""},
            {"name": "Game Two", "path": "C:/Games/Two/game.exe", "cover": "", "wallpaper": ""}
        ]
        on_done = MagicMock()
        dlg = BatchSteamGridDBDialog(self.app, mock_games, on_complete_callback=on_done)
        try:
            self.assertEqual(len(dlg._game_rows), 2)
            self.assertTrue(dlg.opt_covers_var.get())
            self.assertTrue(dlg.opt_wallpapers_var.get())
            self.assertTrue(dlg.opt_overwrite_var.get())
            self.assertIsNotNone(dlg.progress_bar)

            # Comprobar navegación con mando
            self.assertEqual(dlg._focused_nav_idx, 3)  # Inicia en btn_start
            dlg.handle_gamepad_input({"down": True}, {"down": False})
            self.assertEqual(dlg._focused_nav_idx, 4)  # Mueve a btn_cancel

            dlg.handle_gamepad_input({"up": True}, {"up": False})
            self.assertEqual(dlg._focused_nav_idx, 3)  # Vuelve a btn_start
        finally:
            dlg.destroy()

    def test_3_top_menu_includes_steamgriddb_option(self):
        """Verifica que el menú desplegable principal contiene la opción de SteamGridDB."""
        from app import App
        from unittest.mock import patch

        with patch.object(App, "mainloop"):
            with patch.object(App, "_start_gamepad_loop"):
                # Inspeccionar directamente la lista de items en toggle_top_menu leyendo el código o simulando
                import inspect
                src = inspect.getsource(App.toggle_top_menu)
                self.assertIn("open_batch_steamgriddb_dialog", src)
                self.assertIn("SteamGridDB", src)


if __name__ == "__main__":
    unittest.main()
