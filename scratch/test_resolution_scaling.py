"""
Test Suite: Verificación de Escalado Dinámico y Adaptabilidad de Resolución
Verifica que GameFlow Launcher se adapte matemáticamente y visualmente a cualquier resolución
desde pantallas compactas (720p / 800p) hasta 1080p, 1440p (2K) y 4K (UHD).
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import customtkinter as ctk

# Añadir raíz al sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ui.display_scale import (
    get_display_scale_factor,
    scale_value,
    calculate_dialog_bounds,
    set_active_display_scale,
    get_active_display_scale
)
from ui.theme import font_title, font_body, font_button
from ui.controller_hud import (
    render_controller_hud_strip,
    render_big_picture_top_hud,
    render_launch_button_pill
)


class TestResolutionScaling(unittest.TestCase):
    """Pruebas unitarias para la arquitectura de escalado de resolución."""

    @classmethod
    def setUpClass(cls):
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

    def test_display_scale_factors_by_resolution(self):
        """Verifica que el factor de escala lógico y físico sea armónico (sin doble escalado con CustomTkinter)."""
        resolutions = [
            # (name, work_w, work_h, ctk_scale, expected_min_log, expected_max_log, expected_min_phys, expected_max_phys)
            ("720p Handheld (Steam Deck)", 1280, 720, 1.0, 0.70, 0.85, 0.70, 0.85),
            ("800p Handheld (ROG Ally / Legion Go)", 1280, 800, 1.0, 0.72, 0.85, 0.72, 0.85),
            ("1080p Full HD (Baseline 100%)", 1920, 1040, 1.0, 0.95, 1.05, 0.95, 1.05),
            ("1440p QHD / 2K (100%)", 2560, 1400, 1.0, 1.25, 1.40, 1.25, 1.40),
            ("4K UHD TV (100% DPI)", 3840, 2120, 1.0, 1.90, 2.05, 1.90, 2.05),
            ("4K UHD High DPI (200% DPI - CTk 2.0x)", 3840, 2120, 2.0, 0.95, 1.05, 1.90, 2.10),
        ]

        for name, ww, wh, ctk_sc, min_l, max_l, min_p, max_p in resolutions:
            with self.subTest(resolution=name):
                with patch("ui.display_scale.get_monitor_work_area_for_window", return_value=(ww, wh, (0, 0, ww, wh))):
                    with patch("ui.display_scale.get_ctk_window_scaling", return_value=ctk_sc):
                        scale = get_display_scale_factor(None)
                        phys_scale = scale * ctk_sc
                        self.assertGreaterEqual(scale, min_l, f"Escala lógica muy baja en {name}: {scale}")
                        self.assertLessEqual(scale, max_l, f"Escala lógica muy alta en {name}: {scale}")
                        self.assertGreaterEqual(phys_scale, min_p, f"Escala física muy baja en {name}: {phys_scale}")
                        self.assertLessEqual(phys_scale, max_p, f"Escala física muy alta en {name}: {phys_scale}")

    def test_calculate_dialog_bounds_clamping(self):
        """Verifica que ningún diálogo desborde los límites de pantalla ni se vuelva microscópico."""
        # Probar diálogo grande (1140x860) en 720p (100% DPI)
        with patch("ui.display_scale.get_monitor_work_area_for_window", return_value=(1280, 720, (0, 0, 1280, 720))):
            with patch("ui.display_scale.get_ctk_window_scaling", return_value=1.0):
                w, h, scale = calculate_dialog_bounds(1140, 860, None)
                self.assertLessEqual(w, int(1280 * 0.92))
                self.assertLessEqual(h, int(720 * 0.90))
                self.assertGreaterEqual(w, 700)
                self.assertGreaterEqual(h, 500)

        # Probar diálogo grande en 4K @ 100% DPI (3840x2160)
        with patch("ui.display_scale.get_monitor_work_area_for_window", return_value=(3840, 2160, (0, 0, 3840, 2160))):
            with patch("ui.display_scale.get_ctk_window_scaling", return_value=1.0):
                w, h, scale = calculate_dialog_bounds(1140, 860, None)
                self.assertGreaterEqual(w, 2000)
                self.assertGreaterEqual(h, 1500)
                self.assertLessEqual(w, int(3840 * 0.92))
                self.assertLessEqual(h, int(2160 * 0.90))
                self.assertGreaterEqual(scale, 1.90)

        # Probar diálogo grande en 4K @ 200% DPI (3840x2160, CTk multiplica x2)
        with patch("ui.display_scale.get_monitor_work_area_for_window", return_value=(3840, 2160, (0, 0, 3840, 2160))):
            with patch("ui.display_scale.get_ctk_window_scaling", return_value=2.0):
                w, h, scale = calculate_dialog_bounds(1140, 860, None)
                # En unidades lógicas CTk es ~1140x860 -> en píxeles físicos en pantalla (x2) es ~2280x1720
                self.assertEqual(w, 1140)
                self.assertEqual(h, 860)
                self.assertLessEqual(w * 2, int(3840 * 0.92))
                self.assertLessEqual(h * 2, int(2160 * 0.90))

    def test_theme_fonts_scale_dynamically(self):
        """Verifica que font_title, font_body y font_button respondan al active scale."""
        if not self.root:
            self.skipTest("Tkinter no inicializado")

        set_active_display_scale(1.0)
        f_norm = font_title(20)
        self.assertEqual(f_norm.cget("size"), 20)

        set_active_display_scale(2.0)  # 4K
        f_4k = font_title(20)
        self.assertEqual(f_4k.cget("size"), 40)

        set_active_display_scale(0.8)  # 720p
        f_720 = font_title(20)
        self.assertEqual(f_720.cget("size"), 16)

        # Restaurar baseline
        set_active_display_scale(1.0)

    def test_vector_hud_rendering_scaled(self):
        """Verifica que las píldoras y botones vectoriales rendericen nítidamente a diferentes alturas."""
        # 1. Big Picture Top HUD a 1080p (h=36) y 4K (h=72)
        img_1080, boxes_1080 = render_big_picture_top_hud(family="xbox", height=36)
        self.assertEqual(img_1080.height, 36)
        self.assertGreater(len(boxes_1080), 0)

        img_4k, boxes_4k = render_big_picture_top_hud(family="xbox", height=72)
        self.assertEqual(img_4k.height, 72)
        self.assertGreater(img_4k.width, img_1080.width)
        self.assertGreater(len(boxes_4k), 0)

        # 2. Launch button pill a 1080p (248x48) y 4K (496x96)
        pill_1080 = render_launch_button_pill(family="xbox", width=248, height=48)
        self.assertEqual(pill_1080.size, (248, 48))

        pill_4k = render_launch_button_pill(family="xbox", width=496, height=96)
        self.assertEqual(pill_4k.size, (496, 96))

    def test_alphabetical_jump_and_steamgriddb(self):
        """Verifica el salto alfabético con gatillos LT/RT y la presencia del scraper SteamGridDB."""
        from core.library_service import GameLibraryService
        from core.cover_downloader import search_steamgriddb_covers
        self.assertTrue(callable(search_steamgriddb_covers))

        svc = GameLibraryService()
        svc.games = [
            {"name": "Assassins Creed"},
            {"name": "Alan Wake 2"},
            {"name": "Black Myth Wukong"},
            {"name": "Cyberpunk 2077"},
            {"name": "Split Fiction"}
        ]
        # Desde índice 0 ('A'), RT (direction=1) debe saltar a 'Black Myth Wukong' (índice 2)
        idx_next = svc.find_alphabetical_jump(0, direction=1)
        self.assertEqual(idx_next, 2)
        # Desde índice 2 ('B'), LT (direction=-1) debe saltar a 'Alan Wake 2' (índice 1, letra 'A')
        idx_prev = svc.find_alphabetical_jump(2, direction=-1)
        self.assertEqual(idx_prev, 1)


if __name__ == "__main__":
    unittest.main()
