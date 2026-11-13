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


class TestVertical3DRotation(unittest.TestCase):
    def test_render_vertical_shelf_tilt_flat_passthrough(self):
        """Con tilt cercano a 0 no debe deformar dimensiones."""
        from core.coverflow_engine import render_vertical_shelf_tilt
        body = Image.new("RGBA", (300, 200), (90, 140, 210, 255))
        warped, mask, th = render_vertical_shelf_tilt(body, tilt=0.0, tilt_dir=-1, center_x_in_crop=150.0)
        self.assertEqual(th, 200)
        self.assertEqual(warped.size, (300, 200))
        self.assertEqual(mask.size, (300, 200))

    def test_render_vertical_shelf_tilt_upward_narrows_top_and_foreshortens(self):
        """Rotación hacia arriba (tilt_dir=-1) estrecha el borde superior y acorta la altura."""
        from core.coverflow_engine import render_vertical_shelf_tilt
        body = Image.new("RGBA", (400, 200), (180, 200, 220, 255))
        warped, mask, th = render_vertical_shelf_tilt(body, tilt=0.75, tilt_dir=-1, center_x_in_crop=200.0)
        self.assertLess(th, 200)
        self.assertGreaterEqual(th, 8)
        # En la fila superior (y=2), las esquinas extremas deben quedar transparentes (borde estrechado)
        self.assertEqual(mask.getpixel((4, 2)), 0)
        self.assertEqual(mask.getpixel((395, 2)), 0)
        # El centro superior sigue opaco/visible, aunque ligeramente atenuado frente al borde inferior
        self.assertGreater(mask.getpixel((200, 2)), 0)
        self.assertGreater(mask.getpixel((200, th - 2)), mask.getpixel((200, 2)))
        # En la fila inferior (y=th-2), los extremos conservan el ancho completo
        self.assertGreater(mask.getpixel((10, th - 2)), 0)
        self.assertGreater(mask.getpixel((389, th - 2)), 0)

    def test_render_vertical_shelf_tilt_downward_narrows_bottom_and_foreshortens(self):
        """Rotación hacia abajo (tilt_dir=1) estrecha el borde inferior y acorta la altura."""
        from core.coverflow_engine import render_vertical_shelf_tilt
        body = Image.new("RGBA", (400, 200), (180, 200, 220, 255))
        warped, mask, th = render_vertical_shelf_tilt(body, tilt=0.75, tilt_dir=1, center_x_in_crop=200.0)
        self.assertLess(th, 200)
        # Fila superior conserva el ancho completo
        self.assertGreater(mask.getpixel((10, 2)), 0)
        self.assertGreater(mask.getpixel((389, 2)), 0)
        # Fila inferior queda estrechada (esquinas transparentes) y atenuada frente a la superior
        self.assertEqual(mask.getpixel((4, th - 2)), 0)
        self.assertEqual(mask.getpixel((395, th - 2)), 0)
        self.assertGreater(mask.getpixel((200, th - 2)), 0)
        self.assertGreater(mask.getpixel((200, 2)), mask.getpixel((200, th - 2)))

    def test_asymmetric_crop_converges_toward_screen_center(self):
        """Cuando center_x_in_crop está desplazado (p.ej. primer juego sin pila izq), fuga hacia ese eje."""
        from core.coverflow_engine import render_vertical_shelf_tilt
        body = Image.new("RGBA", (400, 200), (180, 200, 220, 255))
        # Eje visual en x=80 (mucho más contenido a la derecha que a la izquierda)
        _, mask, th = render_vertical_shelf_tilt(body, tilt=0.8, tilt_dir=-1, center_x_in_crop=80.0)
        # El borde derecho (320px lejos del eje) se estrecha mucho más que el izquierdo (80px del eje)
        # Medimos el primer/último píxel visible en la fila superior
        left_x = next(x for x in range(400) if mask.getpixel((x, 2)) > 0)
        right_x = next(x for x in range(399, -1, -1) if mask.getpixel((x, 2)) > 0)
        self.assertGreater(399 - right_x, left_x)

    def test_empty_shelf_transition_renders_outgoing_3d(self):
        """Al cambiar a una colección vacía (n=0), el carrusel saliente sigue animando en 3D sin fallar."""
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")
        try:
            canvas = CoverFlowCanvas(root, width=800, height=600)
            with patch("ui.coverflow_canvas.resolve_game_cover", return_value=""):
                canvas.set_games([{"name": "SoloUno", "path": "/a.exe"}], target_index=0, transition_direction=0)
                canvas.redraw(force_w=800, force_h=600)
                canvas.set_games([], target_index=0, transition_direction=1)
                self.assertTrue(canvas.is_shelf_animating)
                canvas.shelf_offset_y = float(canvas.shelf_distance * 0.5)
                canvas.redraw(force_w=800, force_h=600)
                self.assertIsNotNone(canvas.photo_ref)
            canvas.destroy()
        finally:
            root.destroy()

    def test_transparent_mode_vertical_3d_transition(self):
        """En modo mini transparente no hay errores ni pérdida de canal alfa durante la rotación 3D."""
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")
        try:
            canvas = CoverFlowCanvas(root, width=900, height=320)
            canvas.is_transparent_mode = True
            with patch("ui.coverflow_canvas.resolve_game_cover", return_value=""):
                canvas.set_games([{"name": "Alpha", "path": "/a.exe"}], target_index=0, transition_direction=0)
                canvas.redraw(force_w=900, force_h=320)
                canvas.set_games([{"name": "Beta", "path": "/b.exe"}], target_index=0, transition_direction=-1)
                canvas.shelf_offset_y = float(-canvas.shelf_distance * 0.6)
                canvas.redraw(force_w=900, force_h=320)
                self.assertIsNotNone(canvas.photo_ref)
            canvas.destroy()
        finally:
            root.destroy()

    def test_vertical_transition_pacing_and_bg_crossfade(self):
        """La transición vertical es pausada (>85% restante tras 16ms) y mezcla suavemente los fondos."""
        try:
            root = tk.Tk()
            root.withdraw()
        except Exception:
            self.skipTest("Tkinter display not available")
        try:
            canvas = CoverFlowCanvas(root, width=800, height=600)
            with patch("ui.coverflow_canvas.resolve_game_cover", return_value=""):
                canvas.set_games([{"name": "A", "path": "/a.exe"}], target_index=0, transition_direction=0)
                canvas.redraw(force_w=800, force_h=600)
                canvas.set_games([{"name": "B", "path": "/b.exe"}], target_index=0, transition_direction=1)
                if canvas.anim_timer:
                    canvas.after_cancel(canvas.anim_timer)
                    canvas.anim_timer = None
                start_y = canvas.shelf_offset_y
                canvas._last_anim_time = time.perf_counter() - 0.016
                canvas._anim_tick()
                if canvas.anim_timer:
                    canvas.after_cancel(canvas.anim_timer)
                    canvas.anim_timer = None
                # Tras 16ms debe conservar >85% del recorrido para apreciarse con fluidez
                self.assertGreater(canvas.shelf_offset_y / start_y, 0.85)

                # Verificar mezcla de fondos saliente/entrante
                canvas._outgoing_bg = Image.new("RGB", (800, 600), (20, 40, 80))
                new_bg = Image.new("RGB", (800, 600), (120, 40, 40))
                blended = canvas._blend_transition_bg(new_bg, 800, 600, progress=0.5)
                px = blended.getpixel((400, 300))
                self.assertGreater(px[0], 30)
                self.assertLess(px[0], 110)
            canvas.destroy()
        finally:
            root.destroy()


class TestPersistentVerticalStack(unittest.TestCase):
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

    def _make_shelves(self, count: int):
        return [
            {
                "id": f"shelf_{s}",
                "name": f"Colección {s}",
                "games": [{"name": f"S{s}G{i}", "path": f"/roms/s{s}/g{i}.exe"} for i in range(5)],
            }
            for s in range(count)
        ]

    def test_visible_neighbor_offsets_no_duplicates(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available")
        canvas = CoverFlowCanvas(self.root, width=800, height=600)
        try:
            canvas.set_shelves_context(self._make_shelves(1), 0, {})
            self.assertFalse(canvas._is_vertical_stack_active())
            self.assertTrue(canvas._use_reflection())
            self.assertEqual(canvas._get_visible_neighbor_offsets(), [])

            s2 = self._make_shelves(2)
            canvas.set_shelves_context(s2, 0, {})
            self.assertTrue(canvas._is_vertical_stack_active())
            self.assertFalse(canvas._use_reflection())
            self.assertEqual(canvas._get_visible_neighbor_offsets(), [1])
            canvas.set_shelves_context(s2, 1, {})
            self.assertEqual(canvas._get_visible_neighbor_offsets(), [-1])

            canvas.set_shelves_context(self._make_shelves(3), 1, {})
            self.assertEqual(canvas._get_visible_neighbor_offsets(), [-1, 1])

            canvas.set_shelves_context(self._make_shelves(5), 2, {})
            self.assertEqual(canvas._get_visible_neighbor_offsets(), [-2, -1, 1, 2])
        finally:
            canvas.destroy()

    def test_persistent_stack_draws_above_and_below_and_reuses_warp_cache(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available")
        canvas = CoverFlowCanvas(self.root, width=960, height=640)
        try:
            canvas.last_w = 960
            canvas.last_h = 640
            canvas.base_size = int(640 * 0.42)
            shelves = self._make_shelves(5)
            sel = {f"shelf_{i}": 2 for i in range(5)}
            colors = [(220, 60, 60), (60, 200, 80), (70, 130, 240), (230, 170, 40), (190, 70, 220)]

            def fake_jewel(g):
                s_idx = int(g["name"].split("G")[0][1:])
                return Image.new("RGBA", (320, 320), (*colors[s_idx % len(colors)], 255))

            with patch.object(canvas, "_get_or_create_jewel_case", side_effect=fake_jewel):
                canvas.set_shelves_context(shelves, 2, sel)
                canvas.set_games(shelves[2]["games"], target_index=2, transition_direction=0)
                for rel in (-2, -1, 1, 2):
                    sh = shelves[(2 + rel) % 5]
                    canvas._get_bg_shelf_strip(sh, 2, 960, canvas.base_size, allow_disk=True)

            floor_y = canvas._compute_floor_y(640, canvas.base_size)
            bg = Image.new("RGB", (960, 640), (0, 0, 0))
            canvas._draw_vertical_stack_frame(bg, 960, 640, floor_y, canvas.base_size, False, 0.0)

            top_fg = floor_y - canvas.base_size
            # Debe haber píxeles visibles arriba (carrusel -1/-2), centro (s=0) y abajo (+1/+2)
            above_px = bg.getpixel((480, max(10, top_fg - 35)))
            center_px = bg.getpixel((480, top_fg + canvas.base_size // 2))
            below_px = bg.getpixel((480, min(630, floor_y + 35)))
            self.assertGreater(sum(above_px), 30)
            self.assertGreater(sum(below_px), 30)
            # Primer plano (shelf_2: azul) más luminoso que los carruseles traseros
            self.assertGreater(center_px[2], 200)
            self.assertGreater(sum(center_px), sum(above_px))
            self.assertGreater(sum(center_px), sum(below_px))

            # Segundo render en reposo debe reutilizar 100% _bg_slot_warp_cache sin invocar render_vertical_shelf_tilt
            with patch("ui.coverflow_canvas.render_vertical_shelf_tilt") as mock_tilt:
                bg2 = Image.new("RGB", (960, 640), (0, 0, 0))
                canvas._draw_vertical_stack_frame(bg2, 960, 640, floor_y, canvas.base_size, False, 0.0)
                mock_tilt.assert_not_called()
        finally:
            canvas.destroy()

    def test_ui_redraw_never_blocks_on_neighbor_disk_io(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available")
        canvas = CoverFlowCanvas(self.root, width=800, height=600)
        try:
            canvas.last_w = 800
            canvas.last_h = 600
            canvas.base_size = int(600 * 0.42)
            shelves = self._make_shelves(3)
            with patch("ui.coverflow_canvas.resolve_game_cover", return_value=""):
                with patch.object(canvas, "_prewarm_neighbor_shelves_async"):
                    canvas.set_shelves_context(shelves, 1, {})
                    canvas.set_games(shelves[1]["games"], target_index=0, transition_direction=0)
                    # Limpiar jewels de vecinos si quedara alguno y verificar que _get_bg_shelf_strip(..., allow_disk=False) no lee disco
                    for sh_idx in (0, 2):
                        for g in shelves[sh_idx]["games"]:
                            canvas.raw_jewels.pop(canvas._get_key(g), None)
                    with patch.object(canvas, "_get_or_create_jewel_case") as mock_disk:
                        canvas.redraw(force_w=800, force_h=600)
                        mock_disk.assert_not_called()
        finally:
            canvas.destroy()

    def test_continuous_stack_animation_painter_order_and_sizes(self):
        if not self.has_tk:
            self.skipTest("Tkinter display not available")
        for n_count in (2, 3, 5):
            canvas = CoverFlowCanvas(self.root, width=960, height=600)
            try:
                canvas.last_w = 960
                canvas.last_h = 600
                canvas.base_size = int(600 * 0.42)
                shelves = self._make_shelves(n_count)
                sel = {f"shelf_{i}": 2 for i in range(n_count)}
                with patch.object(canvas, "_get_or_create_jewel_case", return_value=Image.new("RGBA", (320, 320), (120, 160, 210, 255))):
                    canvas.set_shelves_context(shelves, 0, sel)
                    canvas.set_games(shelves[0]["games"], target_index=2, transition_direction=0)
                    canvas.set_shelves_context(shelves, 1, sel)
                    canvas.set_games(shelves[1]["games"], target_index=2, transition_direction=1)
                    for sh in shelves:
                        canvas._get_bg_shelf_strip(sh, 2, 960, canvas.base_size, allow_disk=True)

                    drawn_s_values = []
                    orig_slot = canvas._draw_stack_shelf_slot

                    def spy_slot(*args, **kwargs):
                        drawn_s_values.append(args[3])
                        return orig_slot(*args, **kwargs)

                    canvas._draw_stack_shelf_slot = spy_slot
                    canvas.shelf_offset_y = float(canvas.shelf_distance * 0.4)
                    canvas.redraw(force_w=960, force_h=600)
                    self.assertGreaterEqual(len(drawn_s_values), 2)
                    # Verificar orden de pintor estricto: abs(s) decreciente (fondo antes que primer plano)
                    abs_vals = [abs(v) for v in drawn_s_values]
                    self.assertEqual(abs_vals, sorted(abs_vals, reverse=True))
            finally:
                canvas.destroy()


if __name__ == "__main__":
    unittest.main()

