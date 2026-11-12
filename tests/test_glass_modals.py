"""Prueba integral de los modales GlassMessageBox y GlassFolderBrowserDialog."""
import os
import sys
import unittest
import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ui.dialogs.glass_message_box import GlassMessageBox
from ui.dialogs.glass_folder_browser import GlassFolderBrowserDialog


class TestGlassModals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = ctk.CTk()
        cls.app.geometry("400x300")
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_glass_message_box_info_and_confirm_and_folder_browser(self):
        # 1. Probar GlassMessageBox tipo info
        dlg_info = GlassMessageBox(self.app, "Prueba Info", "Este es un mensaje de prueba informativo.", kind="info")
        self.app.update()
        self.assertTrue(dlg_info.winfo_exists())
        dlg_info.handle_gamepad_input({"a": True}, {"a": False})
        self.app.update()
        self.assertFalse(dlg_info.winfo_exists(), "GlassMessageBox info debió cerrarse con A")

        # 2. Probar GlassMessageBox tipo confirm
        dlg_conf = GlassMessageBox(self.app, "Confirmar Acción", "¿Deseas continuar?", kind="confirm", is_destructive=True)
        self.app.update()
        self.assertEqual(dlg_conf._focused_btn, 0)
        dlg_conf.handle_gamepad_input({"right": True}, {"right": False})
        self.assertEqual(dlg_conf._focused_btn, 1)
        dlg_conf.handle_gamepad_input({"a": True}, {"a": False})
        self.app.update()
        self.assertTrue(dlg_conf.result, "GlassMessageBox debió confirmar")

        # 3. Probar GlassFolderBrowserDialog
        dlg_fb = GlassFolderBrowserDialog(self.app, title="Escanear", select_mode="folder")
        self.app.update()
        self.assertTrue(dlg_fb.winfo_exists())
        dlg_fb.handle_gamepad_input({"down": True}, {"down": False})
        dlg_fb.handle_gamepad_input({"x": True}, {"x": False})
        self.app.update()
        self.assertIsNotNone(dlg_fb.selected_path, "GlassFolderBrowserDialog debió seleccionar la ruta actual con X")


if __name__ == "__main__":
    unittest.main()
