import sys, os
import unittest
import time
import customtkinter as ctk
import ctypes

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app
from ui.theme import bring_to_front_absolute
from ui.dialogs import ConfirmExitDialog
from ui.dropdowns import FloatingGlassMenu

_windll = getattr(ctypes, "windll", None)
user32 = _windll.user32 if _windll else None

from unittest.mock import patch

@unittest.skipUnless(os.name == "nt", "Win32 Z-Order HWND tests solo disponibles en Windows")
class TestZOrderAndMiniRules(unittest.TestCase):
    def setUp(self):
        self._patchers = [
            patch("app.ensure_watcher_running"),
            patch("app.ensure_gamebar_nexus_disabled"),
        ]
        for p in self._patchers:
            p.start()
        self.root = app.App()
        self.root.deiconify()
        time.sleep(0.12)
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

    def _get_zorder(self, h1, h2):
        curr = user32.GetTopWindow(0)
        order = {}
        i = 0
        while curr and i < 50:
            if curr == h1:
                order['h1'] = i
            elif curr == h2:
                order['h2'] = i
            curr = user32.GetWindow(curr, 2)
            i += 1
        return order

    def test_01_menu_never_opens_in_mini_mode(self):
        # Set mini mode
        self.root.set_mini_mode()
        self.assertTrue(self.root.is_mini_mode)

        # Attempt to toggle menu
        self.root.toggle_top_menu()
        self.assertFalse(hasattr(self.root, "glass_menu") and self.root.glass_menu is not None, "El menú NO debe abrirse en modo mini/transparente")

    def test_02_exit_dialog_in_mini_mode_is_on_top(self):
        self.root.set_mini_mode()
        self.root.update()

        self.root.open_exit_dialog()
        dlg = self.root.exit_dialog
        self.assertIsNotNone(dlg)
        self.assertTrue(dlg.winfo_exists())
        dlg.update()

        root_hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        dlg_hwnd = user32.GetParent(dlg.winfo_id()) or dlg.winfo_id()

        order = self._get_zorder(dlg_hwnd, root_hwnd)
        self.assertIn('h1', order)
        self.assertIn('h2', order)
        self.assertLess(order['h1'], order['h2'], "ConfirmExitDialog DEBE estar por delante de App en modo mini/transparente!")
        dlg.destroy()

    def test_03_menu_and_exit_dialog_in_fullscreen_big_picture_are_on_top(self):
        self.root.set_full_mode()
        self.assertFalse(self.root.is_mini_mode)
        self.root.update()

        # 1. Menu in Big Picture
        self.root.toggle_top_menu()
        menu = getattr(self.root, "glass_menu", None)
        self.assertIsNotNone(menu, "El menú SÍ debe abrirse en modo Big Picture")
        menu._disable_focus_out_close = True
        menu.update()

        root_hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        menu_hwnd = user32.GetParent(menu.winfo_id()) or menu.winfo_id()

        order_menu = self._get_zorder(menu_hwnd, root_hwnd)
        self.assertIn('h1', order_menu)
        self.assertIn('h2', order_menu)
        self.assertLess(order_menu['h1'], order_menu['h2'], "FloatingGlassMenu DEBE estar por delante de App en Big Picture!")
        self.root.toggle_top_menu()

        # 2. Exit dialog in Big Picture
        self.root.open_exit_dialog()
        dlg = self.root.exit_dialog
        self.assertIsNotNone(dlg)
        dlg.update()

        dlg_hwnd = user32.GetParent(dlg.winfo_id()) or dlg.winfo_id()
        order_dlg = self._get_zorder(dlg_hwnd, root_hwnd)
        self.assertIn('h1', order_dlg)
        self.assertIn('h2', order_dlg)
        self.assertLess(order_dlg['h1'], order_dlg['h2'], "ConfirmExitDialog DEBE estar por delante de App en Big Picture!")
        dlg.destroy()

if __name__ == "__main__":
    unittest.main()
