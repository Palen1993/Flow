import unittest
from unittest import mock
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.library_service import GameLibraryService
from ui.coverflow_canvas import CoverFlowCanvas

class TestMassiveLibraryOptimization(unittest.TestCase):
    def setUp(self):
        self.service = GameLibraryService()
        # Generar 600 juegos simulados
        self.mock_games = []
        statuses = ["Por jugar", "Jugando", "Completado", "Abandonado"]
        platforms = ["Steam", "GOG", "Epic Games", "PC"]
        genres = ["Acción", "Aventura", "RPG", "Estrategia", "Indie"]

        for i in range(600):
            letter = chr(65 + (i % 26))
            self.mock_games.append({
                "name": f"{letter} Game {i:04d}",
                "path": f"C:\\Games\\game_{i}.exe",
                "monitor": i % 3,
                "favorite": (i % 5 == 0),
                "status": statuses[i % len(statuses)],
                "platform": platforms[i % len(platforms)],
                "genre": genres[i % len(genres)],
                "playtime_minutes": i * 15,
                "cover": f"C:\\Games\\covers\\game_{i}.png",
                "wallpaper": f"C:\\Games\\wallpapers\\game_{i}.jpg"
            })
        self.service.games = self.mock_games

    def test_memoized_filters_performance(self):
        # Primera llamada calcula y almacena en caché
        t0 = time.perf_counter()
        favs1 = self.service.filter_games("favorite")
        t_calc = time.perf_counter() - t0

        # Segunda llamada debe ser instantánea (memoizada en RAM)
        t1 = time.perf_counter()
        favs2 = self.service.filter_games("favorite")
        t_cache = time.perf_counter() - t1

        self.assertEqual(len(favs1), 120)
        self.assertEqual(len(favs2), 120)
        self.assertLess(t_cache, t_calc + 0.001)

    def test_alphabetical_jump_o1_lookup(self):
        # Buscar salto a la letra 'M'
        target_idx = self.service.find_alphabetical_jump(current_index=0, char="M")
        self.assertIsNotNone(target_idx)
        target_game = self.service.games[target_idx]
        self.assertTrue(target_game["name"].lower().startswith("m game"))

    def test_cache_invalidation_on_mutation(self):
        self.service.filter_games("favorite")
        self.assertIn("favorite", self.service._filter_cache)

        # Mutación
        self.service.invalidate_caches()
        self.assertEqual(len(self.service._filter_cache), 0)
        self.assertEqual(len(self.service._alpha_jump_cache), 0)

    def test_prune_memory_caches_bounds(self):
        # Probar la lógica de acotación de memoria LRU
        canvas = CoverFlowCanvas.__new__(CoverFlowCanvas)
        canvas.games = self.mock_games
        canvas.raw_jewels = {f"k_{i}": f"jewel_{i}" for i in range(150)}
        canvas.raw_wallpapers = {f"k_{i}": f"wp_{i}" for i in range(50)}
        canvas.rendered_cache = {f"k_{i}": {-1.0: (None, 100), 0.0: (None, 100), 1.0: (None, 100)} for i in range(100)}
        canvas.flat_covers = {f"k_{i}": (None, 100, 100) for i in range(100)}
        canvas.wallpaper_bg_cache = {(f"k_{i}", 1920, 1080, 0.3, 1.8): None for i in range(30)}
        canvas._cache_lock = mock.MagicMock()
        canvas._cache_lock.__enter__ = mock.MagicMock()
        canvas._cache_lock.__exit__ = mock.MagicMock()
        canvas.current_pos = 10.0
        canvas._get_key = lambda g: g.get("path")

        # Mock keys to correspond to games
        for i in range(150):
            canvas.games[i]["path"] = f"k_{i}"

        canvas._prune_memory_caches(center_idx=10)

        # Verificar que ninguna caché exceda sus límites máximos
        self.assertLessEqual(len(canvas.raw_jewels), 64)
        self.assertLessEqual(len(canvas.raw_wallpapers), 12)
        self.assertLessEqual(len(canvas.rendered_cache), 36)
        self.assertLessEqual(len(canvas.wallpaper_bg_cache), 6)

if __name__ == "__main__":
    unittest.main()
