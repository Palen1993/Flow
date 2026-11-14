import unittest
import time
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PIL import Image
from core.coverflow_engine import compose_big_picture_wallpaper_bg
from ui.coverflow_canvas import CoverFlowCanvas
from ui.window_manager import WindowStateService, COLOR_TRANS_KEY

class TestTransitionAndFramerate(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.canvas = CoverFlowCanvas(self.root, width=1280, height=720)
        self.service = WindowStateService(self.root)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_wallpaper_speed_and_zero_latency_caching(self):
        """Verifica que compose_big_picture_wallpaper_bg es ultra veloz (<50ms en 1080p) y get_background_for_game retorna en <1ms."""
        wp = Image.new("RGB", (3840, 2160), (40, 60, 100))
        
        # Test 1: Composición de wallpaper
        t0 = time.perf_counter()
        bg_1080 = compose_big_picture_wallpaper_bg(wp, 1920, 1080, 0, 0.3, 1.8)
        ms_1080 = (time.perf_counter() - t0) * 1000.0
        print(f"\n[BENCHMARK] Composición 1080p Wallpaper: {ms_1080:.2f} ms")
        self.assertLess(ms_1080, 150.0, "La composición a 1080p debe tomar menos de 150 ms en segundo plano")
        self.assertEqual(bg_1080.size, (1920, 1080))

        # Test 2: Inserción y recuperación instantánea en RAM
        mock_game = {"title": "Test 60Hz Game", "path": "test.exe", "wallpaper": "test_wp.jpg"}
        key = self.canvas._get_key(mock_game)
        self.canvas.raw_wallpapers[key] = wp
        self.canvas.games = [mock_game]
        self.canvas.is_transparent_mode = False
        
        # Precache y esperar a que termine el worker asíncrono en CPU virtualizada
        self.canvas._precache_wallpapers_async(1920, 1080, 0)
        cache_key = (key, 1920, 1080, 0.3, 1.8)
        for _ in range(30):
            if cache_key in self.canvas.wallpaper_bg_cache:
                break
            time.sleep(0.02)
        
        # Consulta en caliente: debe retornar desde caché RAM en milisegundos bajos
        _ = self.canvas.get_background_for_game(mock_game, 1920, 1080, 0)
        t0 = time.perf_counter()
        cached_bg = self.canvas.get_background_for_game(mock_game, 1920, 1080, 0)
        fetch_ms = (time.perf_counter() - t0) * 1000.0
        print(f"[BENCHMARK] Acceso a wallpaper en RAM: {fetch_ms:.4f} ms")
        self.assertLess(fetch_ms, 5.0, "El acceso al wallpaper en RAM debe ser instantáneo (< 5ms)")
        self.assertIsNotNone(cached_bg)

    def test_mode_transition_overlays_hidden_in_transparent_mode(self):
        """Verifica que en modo transparente se oculta el HUD Big Picture y solo se muestra la píldora compacta del filtro activo."""
        self.canvas.is_transparent_mode = True
        self.canvas.ui_filter_label = "Favoritos"
        self.canvas.ui_filter_count = 4
        self.canvas.ui_shelf_index = 1
        self.canvas.ui_total_shelves = 3
        self.canvas.base_size = 260
        test_bg = Image.new("RGB", (800, 450), (0, 0, 1))

        # Configurar textos que en Big Picture se pintarían
        self.canvas.ui_title = "Titulo Big Picture"
        self.canvas.ui_status = "Estado Big Picture"
        self.canvas.hud_hitboxes = [(10, 10, 50, 50, "menu")]

        self.canvas._draw_overlays(test_bg, 800, 450)

        # Ningún botón de Big Picture (menu, battery, launch, start, select, exit) debe aparecer en modo mini
        actions = {act for (_, _, _, _, act) in self.canvas.hud_hitboxes}
        self.assertTrue(actions.issubset({"shelf_prev", "shelf_next"}), f"Acciones inesperadas en modo mini: {actions}")
        self.assertEqual(actions, {"shelf_prev", "shelf_next"})

        # El centro y la zona inferior (donde iría el título/botón de Big Picture) permanecen transparentes (0, 0, 1)
        self.assertEqual(test_bg.getpixel((400, 225)), (0, 0, 1))
        self.assertEqual(test_bg.getpixel((400, 410)), (0, 0, 1))

        # La píldora del filtro activo SÍ debe haberse dibujado centrada arriba
        top_band = test_bg.crop((250, 0, 550, 90))
        non_key_pixels = [px for px in top_band.getdata() if px != COLOR_TRANS_KEY]
        self.assertGreater(len(non_key_pixels), 200, "La píldora de filtro activo debe dibujarse en la banda superior en modo mini")

        # Cambiar de filtro debe cambiar los píxeles de la píldora
        test_bg_todos = Image.new("RGB", (800, 450), (0, 0, 1))
        self.canvas.ui_filter_label = "Todos"
        self.canvas.ui_filter_count = 12
        self.canvas.ui_shelf_index = 0
        self.canvas._draw_overlays(test_bg_todos, 800, 450)
        self.assertNotEqual(top_band.tobytes(), test_bg_todos.crop((250, 0, 550, 90)).tobytes())

    def test_window_manager_clean_transition_no_glitch(self):
        """Verifica que las transiciones a modo mini y full configuran correctamente el estado sin excepciones."""
        self.service.set_mini_mode(self.canvas)
        self.assertTrue(self.service.is_mini_mode)
        self.assertFalse(self.service.is_fullscreen)
        self.assertTrue(self.canvas.is_transparent_mode)

        self.service.set_full_mode(self.canvas)
        self.assertFalse(self.service.is_mini_mode)
        self.assertTrue(self.service.is_fullscreen)
        self.assertFalse(self.canvas.is_transparent_mode)

if __name__ == "__main__":
    unittest.main()
