import os
import sys
import unittest
import customtkinter as ctk
import ctypes

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app
from ui.dropdowns import FloatingGlassMenu, FloatingGlassDropdown
from ui.dialogs import ConfirmExitDialog

_windll = getattr(ctypes, "windll", None)
user32 = _windll.user32 if _windll else None
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

from unittest.mock import patch

@unittest.skipUnless(os.name == "nt", "Win32 taskbar HWND styles solo disponibles en Windows")
class TestTaskbarAndModalFix(unittest.TestCase):
    def setUp(self):
        fake_monitors = [{"id": 0, "device": "\\\\.\\DISPLAY1", "name": "CI Display (Principal)", "raw_name": "CI Display", "is_primary": True, "rect": (0, 0, 1920, 1080)}]
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
        self.root.deiconify()
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        for p in reversed(getattr(self, "_patchers", [])):
            try:
                p.stop()
            except Exception:
                pass

    def test_01_push_and_pop_modal(self):
        dummy = ctk.CTkFrame(self.root)
        self.assertEqual(len(self.root._modal_stack), 0)
        self.root.push_modal(dummy)
        self.assertEqual(len(self.root._modal_stack), 1)
        self.assertIn(dummy, self.root._modal_stack)
        self.root.pop_modal(dummy)
        self.assertEqual(len(self.root._modal_stack), 0)

    def test_02_floating_glass_menu_toggle_and_taskbar_hidden(self):
        import time
        self.root.update()
        time.sleep(0.12)
        self.root.update()
        # Ensure Big Picture mode since menu is only allowed in Big Picture
        self.root.set_full_mode()
        self.root.update()
        # Open menu
        self.root.toggle_top_menu()
        m = self.root.glass_menu
        self.assertIsNotNone(m)
        self.assertTrue(m.winfo_exists())
        self.assertEqual(m.title(), "GameFlow Menu")
        self.assertIn(m, self.root._modal_stack)
        self.assertEqual(self.root._get_topmost_active_modal(), m)

        # Verify Windows Window Extended Style
        hwnd = user32.GetParent(m.winfo_id()) or m.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        self.assertTrue(bool(style & WS_EX_TOOLWINDOW), "Menu MUST have WS_EX_TOOLWINDOW to hide from taskbar")
        self.assertFalse(bool(style & WS_EX_APPWINDOW), "Menu MUST NOT have WS_EX_APPWINDOW")

        # Toggle to close
        self.root.toggle_top_menu()
        self.assertIsNone(self.root.glass_menu)
        self.assertNotIn(m, self.root._modal_stack)

    def test_03_base_glass_dialog_taskbar_hidden_and_modal_stack(self):
        dlg = ConfirmExitDialog(self.root)
        dlg.update()
        self.assertIn(dlg, self.root._modal_stack)
        self.assertEqual(self.root._get_topmost_active_modal(), dlg)

        hwnd = user32.GetParent(dlg.winfo_id()) or dlg.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        self.assertTrue(bool(style & WS_EX_TOOLWINDOW), "Dialog MUST have WS_EX_TOOLWINDOW")
        self.assertFalse(bool(style & WS_EX_APPWINDOW), "Dialog MUST NOT have WS_EX_APPWINDOW")

        dlg.destroy()
        self.assertNotIn(dlg, self.root._modal_stack)

if __name__ == "__main__":
    unittest.main()
