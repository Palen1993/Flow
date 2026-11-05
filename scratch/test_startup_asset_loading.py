import sys
import os
import unittest
import time
from unittest.mock import MagicMock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import customtkinter as ctk
from core.config import load_games_data
from ui.coverflow_canvas import CoverFlowCanvas


class TestStartupAssetLoading(unittest.TestCase):
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

    def test_all_games_covers_and_wallpapers_loaded_despite_rapid_resize(self):
        """
        Verifica que al iniciar y producirse eventos rápidos de redimensionamiento
        o cambio a modo mini, el cargador de fondo NO se cancela y todos los juegos
        (incluidos los lejanos al índice 0) cargan sus carátulas y wallpapers.
        """
        canvas = CoverFlowCanvas(self.app)
        games = load_games_data()
        self.assertGreaterEqual(len(games), 5, "Debe haber al menos 5 juegos para probar la carga perezosa")

        # 1. Cargar juegos inicialmente con target 0
        canvas.set_games(games, target_index=0)

        # 2. Simular inmediatamente un <Configure> (que antes incrementaba _cache_generation y mataba el cargador)
        canvas._on_resize(type("Event", (), {"width": 800, "height": 600})())
        canvas._on_resize(type("Event", (), {"width": 640, "height": 480})())

        # Esperar un instante para que el hilo de fondo complete la carga
        time.sleep(0.35)

        # 3. Comprobar que todos los juegos tienen jewel y wallpaper cargados en RAM
        for i, g in enumerate(games):
            key = canvas._get_key(g)
            self.assertIn(
                key, canvas.raw_jewels,
                f"El juego #{i} ({g['name']}) no tiene raw_jewels cargado tras resize"
            )
            if g.get("wallpaper") and os.path.isfile(g["wallpaper"]):
                self.assertIn(
                    key, canvas.raw_wallpapers,
                    f"El juego #{i} ({g['name']}) no tiene raw_wallpapers cargado tras resize"
                )

        # 4. Comprobar que get_rendered_cover NUNCA devuelve None para ningún juego
        for i, g in enumerate(games):
            key = canvas._get_key(g)
            w_img, w_w = canvas.get_rendered_cover(key, 0.0)
            self.assertIsNotNone(w_img, f"La carátula 3D del juego #{i} ({g['name']}) es None (invisible)")
            self.assertGreater(w_w, 0, f"El ancho de la carátula #{i} es 0")

        # 5. Comprobar el fallback bajo demanda si se simula vaciado accidental de raw_jewels
        canvas.raw_jewels.clear()
        canvas.flat_covers.clear()
        canvas.rendered_cache.clear()

        # Debe cargarlo on-demand automáticamente sin fallar
        test_g = games[-1]
        test_key = canvas._get_key(test_g)
        fallback_img, fallback_w = canvas.get_rendered_cover(test_key, 0.0)
        self.assertIsNotNone(fallback_img, "El fallback on-demand de get_rendered_cover falló")
        self.assertGreater(fallback_w, 0)
        self.assertIn(test_key, canvas.raw_jewels, "El fallback no guardó el jewel en raw_jewels")

        # 6. Comprobar el fallback bajo demanda para wallpapers
        canvas.raw_wallpapers.clear()
        canvas.wallpaper_bg_cache.clear()
        if test_g.get("wallpaper") and os.path.isfile(test_g["wallpaper"]):
            bg_res = canvas.get_background_for_game(test_g, 800, 600, 500)
            self.assertIsNotNone(bg_res)
            self.assertIn(test_key, canvas.raw_wallpapers, "El fallback no cargó el wallpaper on-demand")

        canvas.destroy()


if __name__ == "__main__":
    unittest.main()
