"""
Test suite completo para el Sistema de Filtros y Colecciones de GameFlow Launcher.
Verifica persistencia, cálculo de conteos, filtrado, salto alfabético y renderizado de píldora HUD.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.library_service import GameLibraryService
from ui.controller_hud import render_filter_capsule


class TestCollectionsAndFilters(unittest.TestCase):
    def setUp(self):
        self.service = GameLibraryService()
        self.service.games = [
            {
                "name": "The Witcher 3",
                "path": "C:/Games/Witcher3/witcher3.exe",
                "monitor": 0,
                "high_priority": True,
                "cover": "",
                "favorite": True,
                "status": "Jugando",
                "genre": "RPG, Aventura",
                "platform": "GOG Galaxy",
                "playtime_minutes": 180
            },
            {
                "name": "Cyberpunk 2077",
                "path": "C:/Games/Cyberpunk/cp2077.exe",
                "monitor": 1,
                "high_priority": True,
                "cover": "",
                "favorite": True,
                "status": "Completado",
                "genre": "RPG, Acción",
                "platform": "Steam",
                "playtime_minutes": 5400
            },
            {
                "name": "DOOM Eternal",
                "path": "C:/Games/Doom/doom.exe",
                "monitor": 0,
                "high_priority": True,
                "cover": "",
                "favorite": False,
                "status": "Por jugar",
                "genre": "Acción, Shooter",
                "platform": "Steam",
                "playtime_minutes": 0
            },
            {
                "name": "Hades",
                "path": "C:/Games/Hades/hades.exe",
                "monitor": 0,
                "high_priority": False,
                "cover": "",
                "favorite": False,
                "status": "Por jugar",
                "genre": "Roguelike, Acción",
                "platform": "Epic Games",
                "playtime_minutes": 45
            },
            {
                "name": "RetroArch NES Pack",
                "path": "C:/Emulators/RetroArch/retroarch.exe",
                "monitor": 0,
                "high_priority": False,
                "cover": "",
                "favorite": False,
                "status": "Abandonado",
                "genre": "Retro",
                "platform": "RetroArch",
                "playtime_minutes": 15
            }
        ]

    def test_available_filters_generation(self):
        filters = self.service.get_available_filters()
        f_map = {f["id"]: f for f in filters}

        # Comprobar colecciones principales
        self.assertIn("all", f_map)
        self.assertEqual(f_map["all"]["count"], 5)

        self.assertIn("favorite", f_map)
        self.assertEqual(f_map["favorite"]["count"], 2)

        # Comprobar estados
        self.assertIn("status:Por jugar", f_map)
        self.assertEqual(f_map["status:Por jugar"]["count"], 2)

        self.assertIn("status:Jugando", f_map)
        self.assertEqual(f_map["status:Jugando"]["count"], 1)

        self.assertIn("status:Completado", f_map)
        self.assertEqual(f_map["status:Completado"]["count"], 1)

        self.assertIn("status:Abandonado", f_map)
        self.assertEqual(f_map["status:Abandonado"]["count"], 1)

        # Comprobar plataformas
        self.assertIn("platform:Steam", f_map)
        self.assertEqual(f_map["platform:Steam"]["count"], 2)

        self.assertIn("platform:GOG Galaxy", f_map)
        self.assertEqual(f_map["platform:GOG Galaxy"]["count"], 1)

        self.assertIn("platform:Epic Games", f_map)
        self.assertEqual(f_map["platform:Epic Games"]["count"], 1)

        # Comprobar géneros
        self.assertIn("genre:RPG", f_map)
        self.assertEqual(f_map["genre:RPG"]["count"], 2)

        self.assertIn("genre:Acción", f_map)
        self.assertEqual(f_map["genre:Acción"]["count"], 3)

    def test_filter_games_queries(self):
        # 1. Todos
        all_games = self.service.filter_games("all")
        self.assertEqual(len(all_games), 5)

        # 2. Favoritos
        favs = self.service.filter_games("favorite")
        self.assertEqual(len(favs), 2)
        self.assertTrue(all(g["favorite"] for g in favs))

        # 3. Estado: Por jugar
        pj = self.service.filter_games("status:Por jugar")
        self.assertEqual(len(pj), 2)
        self.assertTrue(all(g["name"] in ("DOOM Eternal", "Hades") for g in pj))

        # 4. Plataforma: Steam
        steam_games = self.service.filter_games("platform:Steam")
        self.assertEqual(len(steam_games), 2)
        self.assertTrue(all(g["name"] in ("Cyberpunk 2077", "DOOM Eternal") for g in steam_games))

        # 5. Género: RPG
        rpg_games = self.service.filter_games("genre:RPG")
        self.assertEqual(len(rpg_games), 2)
        self.assertTrue(all(g["name"] in ("The Witcher 3", "Cyberpunk 2077") for g in rpg_games))

    @patch("core.library_service.save_games_data")
    def test_toggle_favorite(self, mock_save):
        self.assertTrue(self.service.games[0]["favorite"])
        # Alternar The Witcher 3 de favorito a no favorito
        new_val = self.service.toggle_favorite(0)
        self.assertFalse(new_val)
        self.assertFalse(self.service.games[0]["favorite"])
        mock_save.assert_called_once()

        # Volver a alternar
        new_val2 = self.service.toggle_favorite(0)
        self.assertTrue(new_val2)
        self.assertTrue(self.service.games[0]["favorite"])

    @patch("core.library_service.save_games_data")
    def test_set_game_status(self, mock_save):
        self.assertEqual(self.service.games[2]["status"], "Por jugar")
        res = self.service.set_game_status(2, "Completado")
        self.assertTrue(res)
        self.assertEqual(self.service.games[2]["status"], "Completado")
        mock_save.assert_called_once()

    def test_format_subtitle_badges(self):
        witcher = self.service.games[0]
        sub = self.service.format_subtitle(witcher)
        self.assertIn("★ Favorito", sub)
        self.assertIn("Jugando", sub)
        self.assertIn("GOG Galaxy", sub)
        self.assertIn("RPG, Aventura", sub)
        self.assertIn("3.0 h jugadas", sub)

    def test_alphabetical_jump_on_filtered_subset(self):
        # Subset de solo juegos de Steam (Cyberpunk 2077, DOOM Eternal)
        steam_games = self.service.filter_games("platform:Steam")
        # Cyberpunk (C) -> salto adelante -> DOOM (D)
        idx = self.service.find_alphabetical_jump(0, direction=1, games_list=steam_games)
        self.assertEqual(idx, 1)
        self.assertEqual(steam_games[idx]["name"], "DOOM Eternal")

    def test_render_filter_capsule_xbox_and_ps(self):
        # Renderizado multi-estantería (total_shelves > 1: flechas y 3 zonas interactivas)
        img_xb, boxes_xb = render_filter_capsule("Favoritos", 4, family="xbox", height=36, shelf_index=0, total_shelves=3)
        self.assertIsNotNone(img_xb)
        self.assertEqual(len(boxes_xb), 3)
        self.assertIn(boxes_xb[0][4], ("filter_prev", "shelf_prev"))
        self.assertEqual(boxes_xb[1][4], "filter_menu")
        self.assertIn(boxes_xb[2][4], ("filter_next", "shelf_next"))

        # Renderizado para PlayStation
        img_ps, boxes_ps = render_filter_capsule("Por Jugar", 8, family="playstation", height=36, shelf_index=1, total_shelves=3)
        self.assertIsNotNone(img_ps)
        self.assertEqual(len(boxes_ps), 3)

        # Renderizado mono-estantería (total_shelves = 1: sin flechas, 1 sola zona para abrir menú de filtros)
        img_single, boxes_single = render_filter_capsule("Todos", 10, total_shelves=1)
        self.assertEqual(len(boxes_single), 1)
        self.assertEqual(boxes_single[0][4], "filter_menu")


if __name__ == "__main__":
    unittest.main()
