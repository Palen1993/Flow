import unittest
import os
import sys
import math
import time
from unittest.mock import MagicMock, patch
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import tempfile
import shutil
import core.cover_resolver as cover_res_mod
import core.coverflow_engine as cover_eng_mod
import tkinter as tk
from ui.coverflow_canvas import CoverFlowCanvas

class TestCarouselTransitionAnimation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_assets = tempfile.mkdtemp()
        cls._orig_covers = cover_res_mod.COVERS_DIR
        cls._orig_jewels = cover_eng_mod.JEWELS_CACHE_DIR
        cover_res_mod.COVERS_DIR = os.path.join(cls._tmp_assets, "covers")
        cover_eng_mod.JEWELS_CACHE_DIR = os.path.join(cls._tmp_assets, "jewels")
        os.makedirs(cover_res_mod.COVERS_DIR, exist_ok=True)
        os.makedirs(cover_eng_mod.JEWELS_CACHE_DIR, exist_ok=True)
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
            cls.has_tk = True
        except Exception:
            cls.has_tk = False

    @classmethod
    def tearDownClass(cls):
        cover_res_mod.COVERS_DIR = cls._orig_covers
        cover_eng_mod.JEWELS_CACHE_DIR = cls._orig_jewels
        shutil.rmtree(cls._tmp_assets, ignore_errors=True)
        if getattr(cls, "has_tk", False) and cls.root:
            try:
                cls.root.destroy()
            except Exception:
                pass

    def setUp(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available in this environment")
        self.canvas = CoverFlowCanvas(self.root, width=800, height=600)
        self.dummy_games = [
            {"name": f"Game {i}", "path": f"/games/game_{i}.exe"}
            for i in range(10)
        ]
        self.dummy_shelf_2 = [
            {"name": f"RPG {i}", "path": f"/games/rpg_{i}.exe"}
            for i in range(8)
        ]

    def tearDown(self):
        if hasattr(self, "canvas") and self.canvas:
            if getattr(self.canvas, "anim_timer", None):
                try:
                    self.canvas.after_cancel(self.canvas.anim_timer)
                except Exception:
                    pass
            self.canvas.destroy()

    def test_initial_shelf_state(self):
        """Verifica que el estado inicial no tiene offsets ni animaciones pendientes."""
        self.assertEqual(self.canvas.shelf_offset_y, 0.0)
        self.assertEqual(self.canvas.shelf_transition_dir, 0)
        self.assertFalse(self.canvas.is_shelf_animating)
        self.assertIsNone(self.canvas._outgoing_covers_layer)

    def test_initial_set_games_without_transition(self):
        """Carga inicial sin dirección de transición debe ser estática."""
        self.canvas.set_games(self.dummy_games, target_index=0, transition_direction=0)
        self.assertEqual(self.canvas.shelf_offset_y, 0.0)
        self.assertFalse(self.canvas.is_shelf_animating)
        self.assertIsNone(self.canvas._outgoing_covers_layer)
        self.assertEqual(len(self.canvas.games), 10)

    def test_downward_transition_trigger(self):
        """Navegación hacia abajo (direction=1) debe iniciar animación con offset positivo (desde abajo)."""
        # Primero cargar estantería 1
        self.canvas.set_games(self.dummy_games, target_index=2, transition_direction=0)
        self.canvas.redraw(force_w=800, force_h=600)
        
        # Transición hacia abajo
        self.canvas.set_games(self.dummy_shelf_2, target_index=0, transition_direction=1)
        self.assertTrue(self.canvas.is_shelf_animating)
        self.assertEqual(self.canvas.shelf_transition_dir, 1)
        self.assertGreater(self.canvas.shelf_offset_y, 100.0)
        self.assertIsNotNone(self.canvas._outgoing_covers_layer)
        self.assertEqual(self.canvas._outgoing_covers_layer.width, self.canvas.last_w)

    def test_upward_transition_trigger(self):
        """Navegación hacia arriba (direction=-1) debe iniciar animación con offset negativo (desde arriba)."""
        self.canvas.set_games(self.dummy_games, target_index=0, transition_direction=0)
        self.canvas.redraw(force_w=800, force_h=600)

        # Transición hacia arriba
        self.canvas.set_games(self.dummy_shelf_2, target_index=3, transition_direction=-1)
        self.assertTrue(self.canvas.is_shelf_animating)
        self.assertEqual(self.canvas.shelf_transition_dir, -1)
        self.assertLess(self.canvas.shelf_offset_y, -100.0)
        self.assertIsNotNone(self.canvas._outgoing_covers_layer)

    def test_anim_tick_exponential_decay_and_termination(self):
        """Verifica que _anim_tick reduce suavemente el offset_y y finaliza al converger a 0."""
        self.canvas.set_games(self.dummy_games, target_index=0, transition_direction=0)
        self.canvas.redraw(force_w=800, force_h=600)
        self.canvas.set_games(self.dummy_shelf_2, target_index=0, transition_direction=1)

        # Cancelar cualquier timer programado para control paso a paso
        if self.canvas.anim_timer:
            self.canvas.after_cancel(self.canvas.anim_timer)
            self.canvas.anim_timer = None

        initial_offset = self.canvas.shelf_offset_y
        self.assertGreater(initial_offset, 0.0)

        # Simular 3 ticks temporales
        self.canvas._last_anim_time = time.perf_counter() - 0.016
        self.canvas._anim_tick()
        if self.canvas.anim_timer:
            self.canvas.after_cancel(self.canvas.anim_timer)
            self.canvas.anim_timer = None

        tick1_offset = self.canvas.shelf_offset_y
        self.assertLess(tick1_offset, initial_offset)
        self.assertGreater(tick1_offset, 0.0)

        # Forzar un offset pequeño cercano a 0 (ej: 0.4px) para comprobar terminación limpia
        self.canvas.shelf_offset_y = 0.4
        self.canvas._last_anim_time = time.perf_counter() - 0.016
        self.canvas._anim_tick()

        self.assertEqual(self.canvas.shelf_offset_y, 0.0)
        self.assertFalse(self.canvas.is_shelf_animating)
        self.assertIsNone(self.canvas._outgoing_covers_layer)
        self.assertIsNone(self.canvas._outgoing_alpha_mask)

    def test_redraw_during_transition_composites_cleanly(self):
        """Verifica que redraw() no lanza excepciones y genera el frame correctamente durante la transición."""
        self.canvas.set_games(self.dummy_games, target_index=0, transition_direction=0)
        self.canvas.redraw(force_w=800, force_h=600)
        self.canvas.set_games(self.dummy_shelf_2, target_index=0, transition_direction=1)

        # redraw en estado intermedio
        self.canvas.shelf_offset_y = 150.0
        self.canvas.redraw(force_w=800, force_h=600)
        self.assertIsNotNone(self.canvas.photo_ref)

    def test_rapid_shelf_switching_safety(self):
        """Cambios rápidos sucesivos de estantería no deben fallar ni provocar fugas de estado."""
        self.canvas.set_games(self.dummy_games, target_index=0, transition_direction=0)
        for i in range(5):
            dir_val = 1 if i % 2 == 0 else -1
            self.canvas.set_games(self.dummy_shelf_2 if i % 2 == 0 else self.dummy_games, target_index=0, transition_direction=dir_val)
            self.assertTrue(self.canvas.is_shelf_animating)
            self.canvas.redraw(force_w=800, force_h=600)

        # Terminar animación
        self.canvas.shelf_offset_y = 0.2
        self.canvas._last_anim_time = time.perf_counter() - 0.016
        self.canvas._anim_tick()
        self.assertEqual(self.canvas.shelf_offset_y, 0.0)
        self.assertFalse(self.canvas.is_shelf_animating)

    def test_mouse_drag_interrupts_shelf_transition(self):
        """Si el usuario interactúa arrastrando con el ratón, la transición vertical se asienta de inmediato."""
        self.canvas.set_games(self.dummy_games, target_index=0, transition_direction=0)
        self.canvas.set_games(self.dummy_shelf_2, target_index=0, transition_direction=1)
        self.assertTrue(self.canvas.is_shelf_animating)

        mock_event = MagicMock()
        mock_event.x = 400
        mock_event.y = 300
        self.canvas._on_mouse_down(mock_event)

        self.assertEqual(self.canvas.shelf_offset_y, 0.0)
        self.assertFalse(self.canvas.is_shelf_animating)
        self.assertIsNone(self.canvas._outgoing_covers_layer)

class TestAppShelfNavigationIntegration(unittest.TestCase):
    def test_app_cycle_shelf_passes_transition_direction(self):
        from app import App
        app = MagicMock()
        app.active_shelves = [
            {"id": "shelf_1", "name": "Favoritos", "games": [{"name": "G1"}]},
            {"id": "shelf_2", "name": "RPG", "games": [{"name": "G2"}]},
            {"id": "shelf_3", "name": "Estrategia", "games": [{"name": "G3"}]},
        ]
        app.current_shelf_idx = 0
        app.selected_index = 0
        app._shelf_selected_indices = {}
        app.cover_stage = MagicMock()
        app.update_ui_details = MagicMock()
        app.set_status = MagicMock()

        # Llamar cycle_shelf(1) de App
        App.cycle_shelf(app, 1)

        self.assertEqual(app.current_shelf_idx, 1)
        app.cover_stage.set_games.assert_called_with(
            app.active_shelves[1]["games"],
            target_index=0,
            transition_direction=1
        )

        # Llamar cycle_shelf(-1)
        App.cycle_shelf(app, -1)
        self.assertEqual(app.current_shelf_idx, 0)
        app.cover_stage.set_games.assert_called_with(
            app.active_shelves[0]["games"],
            target_index=0,
            transition_direction=-1
        )

if __name__ == "__main__":
    unittest.main()

