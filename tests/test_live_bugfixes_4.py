import unittest
import os
import sys
import tkinter as tk
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.coverflow_engine import compose_big_picture_wallpaper_bg
from ui.coverflow_canvas import CoverFlowCanvas
from ui.window_manager import WindowStateService

class TestLiveBugfixes4(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.canvas = CoverFlowCanvas(self.root, width=1920, height=1080)
        self.service = WindowStateService(self.root)

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_1_wallpaper_hd_sharpness_no_downscale(self):
        """Verifica que compose_big_picture_wallpaper_bg a resolución completa conserva los bordes nítidos 1080p sin reescalados intermedios a 640px."""
        # Creamos una imagen 1920x1080 dividida mitad izquierda blanca (255) y mitad derecha negra (0)
        test_pattern = Image.new("RGB", (1920, 1080), (255, 255, 255))
        for x in range(960, 1920):
            for y in range(1080):
                test_pattern.putpixel((x, y), (0, 0, 0))

        # En modo nítido (blur_radius=0.0): la frontera en x=959 y x=960 debe ser un salto directo sin emborronado
        composed = compose_big_picture_wallpaper_bg(test_pattern, 1920, 1080, floor_y=680, opacity=0.8, blur_radius=0.0)
        self.assertEqual(composed.size, (1920, 1080))
        
        # Al no haber blur ni reducción a 640px, el salto entre x=950 y x=970 es nítido y categórico
        left_val = composed.getpixel((950, 540))[0]
        right_val = composed.getpixel((970, 540))[0]
        print(f"\n[NITIDEZ] Modo Nítido en 1080p: pixel izq (blanco): {left_val}, pixel der (negro): {right_val}")
        self.assertGreater(left_val, 180, "La zona blanca debe mantener su alta luminosidad")
        self.assertLess(right_val, 40, "La zona negra debe mantener su tono oscuro")

    def test_2_big_picture_covers_vertically_centered(self):
        """Verifica que el suelo de las carátulas (floor_y) se ubica en el centro estético (~63% de altura) y no pegado arriba."""
        mock_game = {"title": "Test Game", "name": "Test Game", "path": "test.exe"}
        self.canvas.games = [mock_game]
        key = self.canvas._get_key(mock_game)
        self.canvas.raw_jewels[key] = Image.new("RGBA", (300, 300), (255, 100, 50, 255))
        self.canvas.is_transparent_mode = False
        self.canvas.last_w = 1920
        self.canvas.last_h = 1080
        self.canvas.base_size = int(1080 * 0.44) # 475px
        self.canvas.display_scale = 1.0
        self.canvas._rebuild_rendered_cache()

        # En 1080p, floor_y debe estar alrededor de 670-690px para que el centro de la carátula esté alrededor de y=440-460px
        self.canvas.redraw(force_w=1920, force_h=1080)
        self.assertTrue(len(self.canvas.hitboxes) > 0, "Debe haber una hitbox para la carátula central")
        hx1, hy1, hx2, hy2, _ = self.canvas.hitboxes[0]
        cover_center_y = (hy1 + hy2) // 2
        print(f"[LAYOUT] Altura pantalla: 1080 | Caja 3D top: {hy1}, bottom: {hy2}, centro: {cover_center_y}")
        self.assertGreater(hy1, 180, "La parte superior de la carátula no debe estar pegada al techo (hy1 > 180)")
        self.assertGreater(cover_center_y, 400, "El centro de la carátula debe estar centrado confortablemente (centro > 400)")

    def test_3_mini_mode_redraw_exact_dimensions_no_clipping(self):
        """Verifica que al pasar a mini mode se redibuja con las dimensiones exactas del widget y no queda cortado a 1920."""
        mock_game = {"title": "Test Game", "name": "Test Game", "path": "test.exe"}
        self.canvas.games = [mock_game]
        key = self.canvas._get_key(mock_game)
        self.canvas.raw_jewels[key] = Image.new("RGBA", (300, 300), (255, 100, 50, 255))
        
        self.service.set_mini_mode(self.canvas)
        self.assertTrue(self.service.is_mini_mode)
        self.assertTrue(self.canvas.is_transparent_mode)
        
        # El canvas debe haber redibujado con ancho y alto de modo widget exactamente
        self.assertEqual(self.canvas._photo_w, self.canvas.last_w)
        self.assertEqual(self.canvas._photo_h, self.canvas.last_h)
        self.assertLess(self.canvas._photo_h, 800)

if __name__ == "__main__":
    unittest.main()
