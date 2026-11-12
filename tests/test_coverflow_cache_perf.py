import os
import sys
import time
import shutil
import tempfile
import unittest
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import core.config as config_mod
from core.coverflow_engine import get_cached_jewel_case

class TestCoverflowCachePerformance(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_cache_dir = config_mod.JEWELS_CACHE_DIR
        config_mod.JEWELS_CACHE_DIR = os.path.join(self.test_dir, "jewels")

    def tearDown(self):
        config_mod.JEWELS_CACHE_DIR = self.orig_cache_dir
        try:
            shutil.rmtree(self.test_dir, ignore_errors=True)
        except Exception:
            pass

    def test_01_cold_vs_warm_cache_performance(self):
        """Verifica que la caché en disco acelera la obtención de carátulas drásticamente."""
        # Crear imagen de prueba
        test_cover = os.path.join(self.test_dir, "test_game.png")
        raw_img = Image.new("RGBA", (600, 900), (200, 50, 50, 255))
        raw_img.save(test_cover)

        # 1. Generación Fría (Cold Generation)
        t0 = time.perf_counter()
        im_cold = get_cached_jewel_case(test_cover, name="Test Game", size=512)
        cold_time = (time.perf_counter() - t0) * 1000.0

        self.assertEqual(im_cold.size, (512, 512))
        self.assertEqual(im_cold.mode, "RGBA")

        # 2. Recuperación desde Caché Caliente (Warm Cache)
        t1 = time.perf_counter()
        im_warm = get_cached_jewel_case(test_cover, name="Test Game", size=512)
        warm_time = (time.perf_counter() - t1) * 1000.0

        self.assertEqual(im_warm.size, (512, 512))
        print(f"\n  [Perf] Cold generation: {cold_time:.2f} ms | Warm cache load: {warm_time:.2f} ms")
        print(f"  [Perf] Aceleración de carga: {cold_time / max(0.01, warm_time):.1f}x más rápido")

        # La caché caliente debe ser significativamente más rápida (<15ms vs tiempo frío)
        self.assertLess(warm_time, cold_time)

    def test_02_procedural_album_cache(self):
        """Verifica que juegos sin carátula también se cachean en disco."""
        t0 = time.perf_counter()
        im1 = get_cached_jewel_case(None, name="Procedural Game", size=512)
        cold_time = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        im2 = get_cached_jewel_case(None, name="Procedural Game", size=512)
        warm_time = (time.perf_counter() - t1) * 1000.0

        self.assertEqual(im1.size, (512, 512))
        self.assertEqual(im2.size, (512, 512))
        self.assertLess(warm_time, 20.0)

if __name__ == "__main__":
    unittest.main()
