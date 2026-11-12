import unittest
import os
import sys
import tempfile
import shutil
import json
from unittest.mock import MagicMock

# Añadir raíz del proyecto al sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.collections_service import (
    canonicalize_genre,
    load_collections_config,
    save_collections_config,
    get_available_shelf_definitions,
    get_active_shelves,
    filter_games_by_shelf,
    get_game_collections,
    set_game_collections,
    CANONICAL_GENRES,
    DEFAULT_CONFIG
)


class TestCollectionsService(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.tmp_dir, "collections_config.json")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_canonicalize_genre(self):
        # Mapeos válidos
        self.assertEqual(canonicalize_genre("Action / Adventure"), "Acción y Aventura")
        self.assertEqual(canonicalize_genre("JRPG"), "Rol (RPG)")
        self.assertEqual(canonicalize_genre("First-Person Shooter"), "Shooter y Disparos")
        self.assertEqual(canonicalize_genre("Metroidvania 2D"), "Plataformas y Metroidvania")
        self.assertEqual(canonicalize_genre("4X Turn Based Strategy"), "Estrategia y Táctica")
        self.assertEqual(canonicalize_genre("Flight Simulator"), "Simulación y Gestión")
        self.assertEqual(canonicalize_genre("Formula 1 Racing"), "Carreras y Deportes")
        self.assertEqual(canonicalize_genre("2D Fighting"), "Lucha y Combate")
        self.assertEqual(canonicalize_genre("Survival Horror"), "Terror y Suspenso")
        self.assertEqual(canonicalize_genre("Logic Puzzle"), "Puzles y Casual")

        # Entrada vacía o desconocida
        self.assertEqual(canonicalize_genre(""), "Otros")
        self.assertEqual(canonicalize_genre(None), "Otros")
        self.assertEqual(canonicalize_genre("Género Inventado Extraño"), "Género inventado extraño")

    def test_filter_games_by_shelf(self):
        games = [
            {
                "name": "Metroid Prime",
                "favorite": True,
                "platform": "GameCube",
                "genre": "Action-Adventure",
                "play_count": 5,
                "collections": ["Nintendo Exclusives"]
            },
            {
                "name": "Elden Ring",
                "favorite": True,
                "platform": "Steam",
                "genre": "RPG",
                "status": "Jugando",
                "play_count": 8,
                "collections": ["Hardcore", "GOTY"]
            },
            {
                "name": "Hollow Knight",
                "favorite": False,
                "platform": "Steam",
                "genre": "Metroidvania",
                "status": "Completado",
                "play_count": 12,
                "collections": ["Indies"]
            },
            {
                "name": "Civilization VI",
                "favorite": False,
                "platform": "Epic Games",
                "genre": "Strategy",
                "status": "Por Jugar",
                "play_count": 0
            }
        ]

        # Todos
        all_games = filter_games_by_shelf("all", games)
        self.assertEqual(len(all_games), 4)

        # Favoritos
        favs = filter_games_by_shelf("favorites", games)
        self.assertEqual(len(favs), 2)
        self.assertEqual({g["name"] for g in favs}, {"Metroid Prime", "Elden Ring"})

        # Recientes (jugados con play_count > 0 ordenados desc)
        recents = filter_games_by_shelf("recent", games)
        self.assertEqual(len(recents), 3)
        self.assertEqual(recents[0]["name"], "Hollow Knight")  # 12 veces

        # Estado Por Jugar
        backlog = filter_games_by_shelf("status_backlog", games)
        self.assertEqual(len(backlog), 1)
        self.assertEqual(backlog[0]["name"], "Civilization VI")

        # Estado Completado
        completed = filter_games_by_shelf("status_completed", games)
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0]["name"], "Hollow Knight")

        # Plataforma Steam
        steam_games = filter_games_by_shelf("platform:Steam", games)
        self.assertEqual(len(steam_games), 2)

        # Género canónico Rol (RPG)
        rpg_games = filter_games_by_shelf("genre:Rol (RPG)", games)
        self.assertEqual(len(rpg_games), 1)
        self.assertEqual(rpg_games[0]["name"], "Elden Ring")

        # Colección personalizada
        indies = filter_games_by_shelf("custom:Indies", games)
        self.assertEqual(len(indies), 1)
        self.assertEqual(indies[0]["name"], "Hollow Knight")

    def test_config_save_load_and_active_shelves(self):
        games = [
            {"name": "Game A", "favorite": True, "platform": "Steam", "genre": "RPG"},
            {"name": "Game B", "favorite": False, "platform": "GOG", "genre": "Strategy"}
        ]

        # Guardar config personalizada
        custom_cfg = {
            "version": 1,
            "shelves": [
                {"id": "favorites", "enabled": True},
                {"id": "all", "enabled": False},
                {"id": "platform:Steam", "enabled": True}
            ],
            "custom_lists": ["Favoritos de Verano"]
        }
        save_collections_config(custom_cfg, filepath=self.config_path)

        loaded = load_collections_config(filepath=self.config_path)
        self.assertEqual(loaded["custom_lists"], ["Favoritos de Verano"])

        active = get_active_shelves(games, config_path=self.config_path)
        # Activas deben ser 'favorites' y 'platform:Steam' (ambas tienen juegos)
        active_ids = [s["id"] for s in active]
        self.assertIn("favorites", active_ids)
        self.assertIn("platform:Steam", active_ids)
        self.assertNotIn("all", active_ids)

    def test_safety_guarantee_at_least_one_shelf_active(self):
        games = [{"name": "Solo Game", "favorite": False}]
        # Si todas las estanterías estuvieran deshabilitadas en config:
        empty_cfg = {
            "version": 1,
            "shelves": [
                {"id": "all", "enabled": False},
                {"id": "favorites", "enabled": False}
            ],
            "custom_lists": []
        }
        save_collections_config(empty_cfg, filepath=self.config_path)

        active = get_active_shelves(games, config_path=self.config_path)
        # Debe haber al menos 1 activa por garantía de seguridad
        self.assertGreaterEqual(len(active), 1)
        self.assertEqual(active[0]["id"], "all")

    def test_game_collections_tagging(self):
        game = {"name": "Test Game"}
        self.assertEqual(get_game_collections(game), [])

        set_game_collections(game, ["RPG", "Favoritos 2026", " "])
        self.assertEqual(get_game_collections(game), ["RPG", "Favoritos 2026"])

        # Modificar y persistir
        set_game_collections(game, ["Colección Final"])
        self.assertEqual(get_game_collections(game), ["Colección Final"])


class TestMultiShelfNavigationAppIntegration(unittest.TestCase):
    """Pruebas de comportamiento para la navegación de estanterías en App."""

    def test_single_shelf_no_cycle(self):
        """Si solo hay 1 estantería habilitada, no baja ni sube a otro carrusel."""
        app_mock = MagicMock()
        app_mock.active_shelves = [
            {"id": "all", "name": "Todos", "games": [{"name": "A"}]}
        ]
        app_mock.current_shelf_idx = 0
        app_mock._shelf_selected_indices = {}

        # Simular método cycle_shelf
        from app import App
        cycle_fn = App.cycle_shelf.__get__(app_mock, App)

        cycle_fn(1)
        self.assertEqual(app_mock.current_shelf_idx, 0)
        cycle_fn(-1)
        self.assertEqual(app_mock.current_shelf_idx, 0)

    def test_multi_shelf_cycling_and_position_memory(self):
        """Navegación vertical recuerda posición horizontal de cada fila."""
        app_mock = MagicMock()
        app_mock.active_shelves = [
            {"id": "shelf_1", "name": "Fila 1", "games": [{"name": "1A"}, {"name": "1B"}, {"name": "1C"}]},
            {"id": "shelf_2", "name": "Fila 2", "games": [{"name": "2A"}, {"name": "2B"}]}
        ]
        app_mock.current_shelf_idx = 0
        app_mock.selected_index = 2  # Usuario estaba en el 3er juego de Fila 1
        app_mock._shelf_selected_indices = {}
        app_mock.library.games = []

        from app import App
        cycle_fn = App.cycle_shelf.__get__(app_mock, App)
        refresh_fn = App.refresh_shelves.__get__(app_mock, App)
        app_mock.refresh_shelves = refresh_fn

        # Bajar a la siguiente fila
        cycle_fn(1)
        self.assertEqual(app_mock.current_shelf_idx, 1)
        self.assertEqual(app_mock._shelf_selected_indices["shelf_1"], 2)


if __name__ == "__main__":
    unittest.main()
