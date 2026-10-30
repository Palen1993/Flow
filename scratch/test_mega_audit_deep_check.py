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
from ui.dialogs import (
    AddEditGameDialog, ConfirmExitDialog, ControllerInfoDialog,
    CoverPickerDialog, ExternalImportDialog, GamepadConfigDialog,
    GlassFolderBrowserDialog, GlassMessageBox, OnScreenKeyboardDialog,
    ScanResultsDialog, SelectGameToEditDialog
)

user32 = ctypes.windll.user32
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

class TestMegaAuditDeepCheck(unittest.TestCase):
    def setUp(self):
        self.root = app.App()
        self.root.deiconify()
        self.root.update()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def _check_window_styles(self, widget, name: str):
        self.assertTrue(widget.winfo_exists(), f"{name} debe existir.")
        hwnd = user32.GetParent(widget.winfo_id()) or widget.winfo_id()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        self.assertTrue(
            bool(style & WS_EX_TOOLWINDOW),
            f"{name} DEBE tener WS_EX_TOOLWINDOW para jamás aparecer en la barra de tareas de Windows."
        )
        self.assertFalse(
            bool(style & WS_EX_APPWINDOW),
            f"{name} NO debe tener WS_EX_APPWINDOW."
        )
        # Verificar que CustomTkinter no puede sobreescribir el icono de la ventana
        self.assertTrue(
            hasattr(widget, "_windows_set_titlebar_icon"),
            f"{name} debe tener _windows_set_titlebar_icon."
        )
        self.assertTrue(
            hasattr(widget, "_windows_set_titlebar_color"),
            f"{name} debe tener _windows_set_titlebar_color."
        )

    def test_01_all_13_modals_have_taskbar_protection(self):
        # 1. FloatingGlassMenu
        self.root.toggle_top_menu()
        m = self.root.glass_menu
        self.assertIsNotNone(m)
        m._disable_focus_out_close = True
        self._check_window_styles(m, "FloatingGlassMenu")
        self.root.toggle_top_menu()

        # 2. AddEditGameDialog
        dlg1 = AddEditGameDialog(self.root, monitors=self.root.monitors)
        self._check_window_styles(dlg1, "AddEditGameDialog")
        dlg1.destroy()

        # 3. ConfirmExitDialog
        dlg2 = ConfirmExitDialog(self.root)
        self._check_window_styles(dlg2, "ConfirmExitDialog")
        dlg2.destroy()

        # 4. ControllerInfoDialog
        dlg3 = ControllerInfoDialog(self.root, family="xbox")
        self._check_window_styles(dlg3, "ControllerInfoDialog")
        dlg3.destroy()

        # 5. CoverPickerDialog
        dlg4 = CoverPickerDialog(self.root, initial_query="Test")
        self._check_window_styles(dlg4, "CoverPickerDialog")
        dlg4.destroy()

        # 6. ExternalImportDialog
        dlg5 = ExternalImportDialog(self.root, on_import_callback=None, existing_games=[])
        self._check_window_styles(dlg5, "ExternalImportDialog")
        dlg5.destroy()

        # 7. GamepadConfigDialog
        dlg6 = GamepadConfigDialog(self.root)
        self._check_window_styles(dlg6, "GamepadConfigDialog")
        dlg6.destroy()

        # 8. GlassFolderBrowserDialog
        dlg7 = GlassFolderBrowserDialog(self.root, title="Test Browser")
        self._check_window_styles(dlg7, "GlassFolderBrowserDialog")
        dlg7.destroy()

        # 9. GlassMessageBox
        dlg8 = GlassMessageBox(self.root, title="Info", message="Testing")
        self._check_window_styles(dlg8, "GlassMessageBox")
        dlg8.destroy()

        # 10. OnScreenKeyboardDialog
        dlg9 = OnScreenKeyboardDialog(self.root, title="OSK")
        self._check_window_styles(dlg9, "OnScreenKeyboardDialog")
        dlg9.destroy()

        # 11. ScanResultsDialog
        dlg10 = ScanResultsDialog(self.root, scanned_folder="C:/", candidates=[])
        self._check_window_styles(dlg10, "ScanResultsDialog")
        dlg10.destroy()

        # 12. SelectGameToEditDialog
        dlg11 = SelectGameToEditDialog(self.root, games=[])
        self._check_window_styles(dlg11, "SelectGameToEditDialog")
        dlg11.destroy()

        # 13. FloatingGlassDropdown
        dlg12 = FloatingGlassDropdown(self.root, anchor_widget=self.root.btn_menu, values=["A", "B"])
        self._check_window_styles(dlg12, "FloatingGlassDropdown")
        dlg12.destroy()

    def test_02_single_instance_guards_in_app(self):
        # Probar que invocar dos veces open_add_dialog no crea 2 instancias
        self.root.open_add_dialog()
        inst1 = getattr(self.root, "_add_dialog", None)
        self.assertIsNotNone(inst1)
        self.root.open_add_dialog()
        inst2 = getattr(self.root, "_add_dialog", None)
        self.assertIs(inst1, inst2, "open_add_dialog debe reutilizar la instancia existente")
        inst1.destroy()

        # Probar open_gamepad_config_dialog
        self.root.open_gamepad_config_dialog()
        gp1 = getattr(self.root, "_gamepad_dialog", None)
        self.assertIsNotNone(gp1)
        self.root.open_gamepad_config_dialog()
        gp2 = getattr(self.root, "_gamepad_dialog", None)
        self.assertIs(gp1, gp2, "open_gamepad_config_dialog debe reutilizar la instancia")
        gp1.destroy()

        # Probar open_select_game_dialog
        self.root.open_select_game_dialog()
        sel1 = getattr(self.root, "_select_dialog", None)
        self.assertIsNotNone(sel1)
        self.root.open_select_game_dialog()
        sel2 = getattr(self.root, "_select_dialog", None)
        self.assertIs(sel1, sel2, "open_select_game_dialog debe reutilizar la instancia")
        sel1.destroy()

        # Probar open_external_import_dialog
        self.root.open_external_import_dialog()
        ext1 = getattr(self.root, "_external_import_dialog", None)
        self.assertIsNotNone(ext1)
        self.root.open_external_import_dialog()
        ext2 = getattr(self.root, "_external_import_dialog", None)
        self.assertIs(ext1, ext2, "open_external_import_dialog debe reutilizar la instancia")
        ext1.destroy()

if __name__ == "__main__":
    unittest.main()
