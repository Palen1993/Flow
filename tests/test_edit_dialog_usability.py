import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure root directory is in sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import customtkinter as ctk
from PIL import Image

from ui.controller_hud import render_button_icon_pil, get_button_icon_ctk
from ui.dialogs.add_edit_game import AddEditGameDialog
from ui.dialogs.cover_picker_dialog import CoverPickerDialog


class TestEditDialogUsability(unittest.TestCase):
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

    def test_1_controller_lt_rt_icons_rendered(self):
        """Verifica que los glifos de LT y RT (Xbox y PS) se dibujan correctamente sin ser transparentes."""
        for fam in ("xbox", "playstation"):
            img_lt = render_button_icon_pil("lt", family=fam, size=20)
            img_rt = render_button_icon_pil("rt", family=fam, size=20)
            self.assertIsNotNone(img_lt.getbbox(), f"LT icon for {fam} is empty/transparent")
            self.assertIsNotNone(img_rt.getbbox(), f"RT icon for {fam} is empty/transparent")
            
            ctk_lt = get_button_icon_ctk("lt", family=fam, size=18)
            ctk_rt = get_button_icon_ctk("rt", family=fam, size=18)
            self.assertIsNotNone(ctk_lt)
            self.assertIsNotNone(ctk_rt)

    def test_2_add_edit_game_button_widths_and_margins(self):
        """Verifica que 'btn_online' y 'btn_cover' tienen el mismo ancho exacto de 180px."""
        mock_monitors = [{"id": 0, "name": "Mon", "rect": [0, 0, 1920, 1080]}]
        mock_game = {
            "name": "Halo Infinite",
            "path": "C:/Games/Halo/game.exe",
            "monitor": 0,
            "high_priority": True,
            "cover": ""
        }
        
        dlg = AddEditGameDialog(
            self.app,
            monitors=mock_monitors,
            game_data=mock_game,
            delete_callback=MagicMock()
        )
        try:
            # Comprobar anchuras de ambos botones del panel izquierdo
            self.assertEqual(dlg.btn_online.cget("width"), 180)
            self.assertEqual(dlg.btn_cover.cget("width"), 180)
            self.assertEqual(dlg.cover_canvas.winfo_reqwidth(), 180)
        finally:
            dlg.destroy()

    def test_3_delete_button_gamepad_navigation_and_activation(self):
        """Verifica la navegación espacial hacia el botón 'Eliminar Juego' y que solo con A encima se activa."""
        mock_monitors = [{"id": 0, "name": "Mon", "rect": [0, 0, 1920, 1080]}]
        del_mock = MagicMock()
        mock_game = {
            "name": "Gears 5",
            "path": "C:/Games/Gears/game.exe",
            "monitor": 0,
            "high_priority": True,
            "cover": ""
        }
        
        dlg = AddEditGameDialog(
            self.app,
            monitors=mock_monitors,
            game_data=mock_game,
            delete_callback=del_mock
        )
        try:
            self.assertIsNotNone(dlg.btn_delete)
            del_idx = next(i for i, c in enumerate(dlg._nav_controls) if c[1] == dlg.btn_delete)
            save_idx = next(i for i, c in enumerate(dlg._nav_controls) if c[1] == dlg.btn_save)
            
            # Inicialmente está en 0 (btn_online)
            self.assertEqual(dlg._focused_idx, 0)
            
            # Presionar 'A' en btn_online NO debe llamar a confirm_delete
            with patch.object(dlg, "confirm_delete") as mock_confirm:
                with patch.object(dlg, "download_online_hd_cover") as mock_dl:
                    dlg.handle_gamepad_input({"a": True}, {"a": False})
                    mock_confirm.assert_not_called()
                    mock_dl.assert_called_once()

            # Navegar hacia abajo: 0 -> 1 (btn_cover) -> 2 (btn_auto_wallpaper) -> del_idx (btn_delete)
            dlg.handle_gamepad_input({"down": True}, {"down": False})
            self.assertEqual(dlg._focused_idx, 1)
            dlg.handle_gamepad_input({"down": True}, {"down": False})
            self.assertEqual(dlg._focused_idx, 2)
            dlg.handle_gamepad_input({"down": True}, {"down": False})
            self.assertEqual(dlg._focused_idx, del_idx)
            
            # Verificar estilo de foco de peligro de alto contraste en btn_delete
            self.assertEqual(dlg.btn_delete.cget("border_color"), "#ffffff")
            self.assertEqual(dlg.btn_delete.cget("border_width"), 3)
            self.assertEqual(dlg.btn_delete.cget("fg_color"), "#ff1744")

            # Estando encima de btn_delete, presionar 'A' SÍ llama a confirm_delete
            with patch.object(dlg, "confirm_delete") as mock_confirm:
                dlg.handle_gamepad_input({"a": True}, {"a": False})
                mock_confirm.assert_called_once()

            # Moverse a la derecha desde btn_delete -> save_idx (btn_save)
            dlg.handle_gamepad_input({"right": True}, {"right": False})
            self.assertEqual(dlg._focused_idx, save_idx)
            
            # Desde btn_save, moverse a la izquierda -> vuelve a del_idx (btn_delete)
            dlg.handle_gamepad_input({"left": True}, {"left": False})
            self.assertEqual(dlg._focused_idx, del_idx)

            # Desde btn_delete, subir -> va a la última fila de la columna derecha
            dlg.handle_gamepad_input({"up": True}, {"up": False})
            self.assertEqual(dlg._focused_idx, save_idx - 1)
        finally:
            dlg.destroy()

    def test_4_cover_picker_lt_rt_tab_switching(self):
        """Verifica que LT y RT alternan entre 'Carátula (Caja 3D)' y 'Wallpaper 16:9'."""
        with patch.object(CoverPickerDialog, "_start_search"):
            dlg = CoverPickerDialog(
                self.app,
                initial_query="Test Game",
                game_name="Test Game",
                initial_mode="cover"
            )
            try:
                self.assertEqual(dlg.asset_mode, "cover")
                self.assertIsNotNone(dlg.btn_mode_cover.cget("image"))
                self.assertIsNotNone(dlg.btn_mode_wallpaper.cget("image"))

                # Presionar RT cambia a Wallpaper 16:9
                res = dlg.handle_gamepad_input({"rt": True}, {"rt": False})
                self.assertTrue(res)
                self.assertEqual(dlg.asset_mode, "wallpaper")

                # Presionar LT cambia de regreso a Carátula 3D
                res = dlg.handle_gamepad_input({"lt": True}, {"lt": False})
                self.assertTrue(res)
                self.assertEqual(dlg.asset_mode, "cover")
            finally:
                dlg.destroy()

    def test_5_all_dialogs_high_contrast_focus(self):
        """Verifica que todos los botones y controles en diálogos muestran un foco de alto contraste (3px blanco/cian + cambio LED de fondo)."""
        from ui.dialogs.confirm_exit import ConfirmExitDialog
        from ui.dialogs.glass_message_box import GlassMessageBox
        from ui.dialogs.gamepad_config_dialog import GamepadConfigDialog

        # 1. ConfirmExitDialog
        dlg_exit = ConfirmExitDialog(self.app)
        try:
            # Inicialmente en btn_exit (index 1, danger)
            self.assertEqual(dlg_exit._focused_btn, 1)
            self.assertEqual(dlg_exit.btn_exit.cget("border_color"), "#ffffff")
            self.assertEqual(dlg_exit.btn_exit.cget("border_width"), 3)
            self.assertEqual(dlg_exit.btn_exit.cget("fg_color"), "#ff1744")
            self.assertEqual(dlg_exit.btn_cancel.cget("border_width"), 1)
            self.assertEqual(dlg_exit.btn_cancel.cget("fg_color"), "#1c212d")

            # Cambiar a btn_cancel (index 0, secondary)
            dlg_exit.handle_gamepad_input({"left": True}, {"left": False})
            self.assertEqual(dlg_exit._focused_btn, 0)
            self.assertEqual(dlg_exit.btn_cancel.cget("border_color"), "#ffffff")
            self.assertEqual(dlg_exit.btn_cancel.cget("border_width"), 3)
            self.assertEqual(dlg_exit.btn_cancel.cget("fg_color"), "#0284c7")
            self.assertEqual(dlg_exit.btn_exit.cget("border_width"), 1)
            self.assertEqual(dlg_exit.btn_exit.cget("fg_color"), "#7f1d1d")
        finally:
            dlg_exit.destroy()

        # 2. GlassMessageBox (confirm)
        dlg_msg = GlassMessageBox(self.app, "Test", "¿Confirmar acción?", kind="confirm")
        try:
            # Foco inicial en btn_confirm (index 1)
            self.assertEqual(dlg_msg._focused_btn, 1)
            self.assertEqual(dlg_msg.btn_confirm.cget("border_color"), "#ffffff")
            self.assertEqual(dlg_msg.btn_confirm.cget("border_width"), 3)
            self.assertEqual(dlg_msg.btn_confirm.cget("fg_color"), "#007aff")
            self.assertEqual(dlg_msg.btn_cancel.cget("border_width"), 1)

            dlg_msg.handle_gamepad_input({"left": True}, {"left": False})
            self.assertEqual(dlg_msg._focused_btn, 0)
            self.assertEqual(dlg_msg.btn_cancel.cget("border_color"), "#ffffff")
            self.assertEqual(dlg_msg.btn_cancel.cget("border_width"), 3)
            self.assertEqual(dlg_msg.btn_cancel.cget("fg_color"), "#0284c7")
            self.assertEqual(dlg_msg.btn_confirm.cget("border_width"), 1)
            self.assertEqual(dlg_msg.btn_confirm.cget("fg_color"), "#1e3a8a")
        finally:
            dlg_msg.destroy()

        # 3. GamepadConfigDialog
        dlg_gp = GamepadConfigDialog(self.app)
        try:
            # Mover al botón Guardar (índice 11)
            dlg_gp._focused_idx = 11
            dlg_gp._update_focus_highlight()
            self.assertEqual(dlg_gp.btn_save.cget("border_color"), "#ffffff")
            self.assertEqual(dlg_gp.btn_save.cget("border_width"), 3)
            self.assertEqual(dlg_gp.btn_save.cget("fg_color"), "#007aff")
            self.assertEqual(dlg_gp.btn_cancel.cget("border_width"), 1)

            # Mover al botón Cancelar (índice 12)
            dlg_gp._focused_idx = 12
            dlg_gp._update_focus_highlight()
            self.assertEqual(dlg_gp.btn_cancel.cget("border_color"), "#ffffff")
            self.assertEqual(dlg_gp.btn_cancel.cget("border_width"), 3)
            self.assertEqual(dlg_gp.btn_cancel.cget("fg_color"), "#0284c7")
            self.assertEqual(dlg_gp.btn_save.cget("border_width"), 1)
            self.assertEqual(dlg_gp.btn_save.cget("fg_color"), "#1e3a8a")
        finally:
            dlg_gp.destroy()


if __name__ == "__main__":
    unittest.main()
