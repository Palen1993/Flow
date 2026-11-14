import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app


class TestBigPictureEditCurrentGameMenu(unittest.TestCase):
    def setUp(self):
        fake_monitors = [{
            "id": 0,
            "device": "\\\\.\\DISPLAY1",
            "name": "CI Display (Principal)",
            "raw_name": "CI Display",
            "is_primary": True,
            "rect": (0, 0, 1920, 1080),
        }]
        self._patchers = [
            patch("app.ensure_watcher_running"),
            patch("app.ensure_gamebar_nexus_disabled"),
            patch("app.force_foreground_window", return_value=True),
            patch("app.get_monitors", return_value=fake_monitors),
            patch.object(app.App, "_start_gamepad_loop", lambda s: None),
            patch.object(app.App, "_poll_battery_status", lambda s: None),
        ]
        for p in self._patchers:
            p.start()
        self.root = app.App()
        self.root.is_mini_mode = False
        self.root.update_idletasks()

    def tearDown(self):
        try:
            self.root.close_active_menu()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        for p in reversed(getattr(self, "_patchers", [])):
            try:
                p.stop()
            except Exception:
                pass

    def test_first_menu_item_is_edit_current_game_and_targets_selected_game(self):
        g_alpha = {"name": "Alpha", "path": "C:/alpha.exe", "favorite": False}
        g_beta = {"name": "Beta Fav", "path": "C:/beta.exe", "favorite": True}
        g_gamma = {"name": "Gamma", "path": "C:/gamma.exe", "favorite": False}
        self.root.library.games = [g_alpha, g_beta, g_gamma]

        # Simular que estamos viendo una estantería filtrada (solo Favoritos), donde el índice local es 0 pero en library.games es 1
        self.root.games = [g_beta]
        self.root.selected_index = 0

        captured = {}

        class _DummyMenu:
            def __init__(self, parent, anchor, items):
                captured["items"] = items

            def winfo_exists(self):
                return True

            def destroy(self):
                pass

        with patch("app.FloatingGlassMenu", _DummyMenu):
            self.root.toggle_top_menu()

        items = captured.get("items", [])
        self.assertGreater(len(items), 0)
        first_icon, first_label, first_action = items[0]
        self.assertIn("Editar Juego", first_label)
        self.assertIn("Beta Fav", first_label)
        self.assertEqual(first_action, self.root.open_edit_current_game_dialog)

        # Al pulsar la primera opción, debe abrir AddEditGameDialog directamente con index=1 (g_beta), no SelectGameToEditDialog
        with patch.object(self.root, "open_edit_for_game_index") as mock_edit_idx, \
             patch.object(self.root, "open_select_game_dialog") as mock_select_dlg:
            first_action()
            mock_edit_idx.assert_called_once_with(1)
            mock_select_dlg.assert_not_called()


if __name__ == "__main__":
    unittest.main()
