import os
import sys
import unittest
from unittest.mock import patch
import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from core.cover_downloader import (
    _is_candidate_relevant,
    search_cover_candidates,
    search_wallpaper_candidates,
)
from ui.display_scale import get_monitor_work_area_for_window, get_ctk_window_scaling
from ui.dialogs.base_dialog import BaseGlassDialog
from ui.dialogs.cover_picker_dialog import CoverPickerDialog
from ui.dialogs.glass_folder_browser import GlassFolderBrowserDialog
from ui.gamepad_service import GamepadNavigationService


class DummyApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._modal_stack = []
        self.gamepad_config = {"selected_controller_id": "any", "enable_controller_nav": True}
        self._current_controller_family = "xbox"
        self.gamepad_service = GamepadNavigationService(self)
        self.tick_count = 0

    def _sync_controller_family_ui(self):
        pass

    def on_gamepad_connected(self, dev_name: str):
        pass

    def push_modal(self, modal):
        if modal not in self._modal_stack:
            self._modal_stack.append(modal)

    def pop_modal(self, modal):
        if modal in self._modal_stack:
            try:
                self._modal_stack.remove(modal)
            except ValueError:
                pass
        top = self._get_topmost_active_modal()
        if top is not None:
            try:
                top.grab_set()
                top.focus_force()
            except Exception:
                pass

    def _get_topmost_active_modal(self):
        while self._modal_stack:
            top = self._modal_stack[-1]
            try:
                if top.winfo_exists():
                    return top
            except Exception:
                pass
            self._modal_stack.pop()
        return None

    def _gamepad_tick(self):
        if self.winfo_exists():
            self.after(20, self._gamepad_tick)
        self.tick_count += 1
        self.gamepad_service.tick(target_id="any", enable_nav=True)


class TestLiveBugfixes3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = DummyApp()
        cls.app.geometry("900x600+100+100")
        cls.app.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.app.destroy()
        except Exception:
            pass

    def test_1_gamepad_works_inside_nested_wait_window_roms_browser(self):
        """
        Verifica que cuando un modal padre (ExternalImportDialog) abre el selector de carpetas ROMs
        con wait_window() desde dentro de handle_gamepad_input(), el bucle de mando a 40 Hz sigue vivo
        y navega/cierra el GlassFolderBrowserDialog sin bloquearse.
        """
        parent_modal = BaseGlassDialog(self.app, title="Parent Import Modal", width=820, height=620)
        rom_browser_navigated = {"down": False, "closed": False, "selected": None}

        def parent_gamepad_handler(inputs, prev):
            if inputs.get("y") and not prev.get("y"):
                dlg = GlassFolderBrowserDialog(parent=parent_modal, title="Seleccionar Carpeta de ROMs")
                # Programar pulsaciones simuladas de mando MIENTRAS wait_window() está bloqueado
                self.app.after(60, lambda: setattr(self, "_sim_inputs", {"down": True}))
                self.app.after(120, lambda: setattr(self, "_sim_inputs", {"down": False, "b": True}))
                dlg.wait_window()
                rom_browser_navigated["closed"] = True
                return True
            return False

        parent_modal.handle_gamepad_input = parent_gamepad_handler
        self._sim_inputs = {"y": True}

        def fake_poll(_target_id="any"):
            return True, "Xbox Controller", dict(getattr(self, "_sim_inputs", {}))

        with patch("ui.gamepad_service.poll_active_gamepad", side_effect=fake_poll):
            self.app._gamepad_tick()

        self.assertTrue(rom_browser_navigated["closed"], "El selector de carpetas ROMs debe cerrarse con el botón B del mando durante wait_window()")
        self.assertEqual(self.app._get_topmost_active_modal(), parent_modal, "Al cerrar el selector de ROMs, el modal padre debe recuperar la cima de la pila")
        parent_modal.destroy()

    def test_2_cover_picker_centered_on_monitor_when_parent_is_smaller_dialog(self):
        """
        Verifica que CoverPickerDialog (1140x860) quede centrado exactamente en el monitor activo
        incluso cuando se abre desde un diálogo padre más pequeño como AddEditGameDialog (650x560).
        """
        small_parent = BaseGlassDialog(self.app, title="Editar Juego", width=650, height=560)
        small_parent.update_idletasks()

        with patch.object(CoverPickerDialog, "_start_search", lambda s: None):
            picker = CoverPickerDialog(small_parent, initial_query="LEGO Batman Legacy of the Dark Knight")
            picker.update_idletasks()

            work_w, work_h, rc = get_monitor_work_area_for_window(small_parent)
            ctk_scale = get_ctk_window_scaling(picker)
            phys_w = int(round(picker.dialog_width * ctk_scale))
            phys_h = int(round(picker.dialog_height * ctk_scale))

            expected_x = rc[0] + max(0, (work_w - phys_w) // 2)
            expected_y = rc[1] + max(0, (work_h - phys_h) // 2)

            geom = picker.geometry()  # e.g. '883x614+1037+446'
            pos_part = geom.split("+", 1)[1]
            actual_x, actual_y = [int(v) for v in pos_part.split("+")]

            self.assertAlmostEqual(actual_x, expected_x, delta=5)
            self.assertAlmostEqual(actual_y, expected_y, delta=5)

            picker.destroy()
        small_parent.destroy()

    def test_3_cover_search_strict_game_relevance_and_hd_1080p_candidates(self):
        """
        Verifica que el filtro de relevancia rechace sets físicos de LEGO y otros juegos genéricos,
        y que search_cover_candidates devuelva tanto carátulas como Key Art 1080p HD del juego exacto.
        """
        q = "LEGO Batman Legacy of the Dark Knight"
        # Juguetes físicos de LEGO o juegos sin relación deben ser rechazados al 100%
        self.assertFalse(_is_candidate_relevant(
            "Modern House 31153 | Creator 3-in-1 | Official LEGO Shop",
            "https://www.lego.com/cdn/cs/set/assets/31153.png",
            "",
            q
        ))
        self.assertFalse(_is_candidate_relevant(
            "THE KING OF FIGHTERS 2003",
            "https://images.gog-statics.com/kof2003.jpg",
            "",
            q
        ))
        self.assertFalse(_is_candidate_relevant(
            "Dark LEGO Wallpapers - Top Free Dark LEGO Backgrounds",
            "https://wallpaperaccess.com/full/26576297.png",
            "",
            q
        ))
        # Títulos reales del juego (en inglés o español) deben ser aceptados
        self.assertTrue(_is_candidate_relevant(
            "LEGO® Batman™: El Legado del Caballero Oscuro",
            "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/221/library_600x900_2x.jpg",
            "",
            q
        ))
        self.assertTrue(_is_candidate_relevant(
            "Lego Batman: Legacy of the Dark Knight Wallpaper 4K, Key Art",
            "https://4kwallpapers.com/images/wallpapers/lego-batman-legacy-1920x1080.jpg",
            "",
            q
        ))

        covs = search_cover_candidates(q)
        self.assertGreater(len(covs), 5)
        sources = {c.get("source") for c in covs}
        self.assertIn("Key Art 1080p HD", sources, "search_cover_candidates debe incluir imágenes 1080p HD / Key Art del juego")
        for c in covs:
            combined = f"{c.get('name', '')} {c.get('poster_url', '')}".lower()
            self.assertIn("lego", combined)
            self.assertIn("batman", combined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
