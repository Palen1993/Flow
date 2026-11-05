import os
import time
import math
import threading
from typing import List, Dict, Tuple, Optional, Any
import tkinter as tk
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

from core.coverflow_engine import (
    create_procedural_album, create_jewel_case, prepare_flat_cover,
    render_cover_flow_from_flat, prevent_transparency_color_collision,
    compose_big_picture_wallpaper_bg, get_cached_jewel_case
)
from core.cover_resolver import resolve_game_cover
from ui.theme import COLOR_BG_CANVAS, COLOR_TRANS_KEY
from ui.controller_hud import (
    render_controller_hud_strip,
    render_big_picture_top_hud,
    render_launch_button_pill
)

class CoverFlowCanvas(tk.Canvas):
    """Componente Canvas interactivo para visualización 3D Cover Flow estilo iPod."""
    def __init__(self, parent, on_selection_changed=None, on_launch_requested=None, on_hud_action=None, **kwargs):
        super().__init__(parent, highlightthickness=0, bg=COLOR_BG_CANVAS, **kwargs)
        self.on_selection_changed = on_selection_changed
        self.on_launch_requested = on_launch_requested
        self.on_hud_action = on_hud_action
        self.controller_family = "xbox"
        self.hud_hitboxes: List[Tuple[int, int, int, int, str]] = []
        
        self.games: List[Dict[str, Any]] = []
        self.raw_jewels: Dict[str, Image.Image] = {}
        self.raw_wallpapers: Dict[str, Image.Image] = {}
        self.wallpaper_bg_cache: Dict[Tuple[str, int, int, float, float], Image.Image] = {}
        self.flat_covers: Dict[str, Tuple[Image.Image, int, int]] = {}
        self.rendered_cache: Dict[str, Dict[float, Tuple[Image.Image, int]]] = {}
        self._cover_sigs: Dict[str, Tuple[Any, ...]] = {}
        self._wp_sigs: Dict[str, Tuple[Any, ...]] = {}
        self._cache_generation = 0
        self._library_load_id = 0

        # Estado del HUD superpuesto sin barras grises en modo Big Picture
        self.ui_title = ""
        self.ui_status = ""
        self.ui_status_color = (148, 163, 184)
        self.ui_battery_text = "🎮 Mando"
        self.ui_battery_color = (100, 116, 139)
        self.ui_launch_disabled = False
        self._launch_hovered = False
        self._bottom_overlay_cache: Dict[Tuple[Any, ...], Image.Image] = {}
        self.display_scale = 1.0
        self._current_font_scale = 1.0

        try:
            self._font_title_bp = ImageFont.truetype("segoeuib.ttf", 26)
            self._font_sub_bp = ImageFont.truetype("segoeuib.ttf", 13)
        except Exception:
            self._font_title_bp = ImageFont.load_default()
            self._font_sub_bp = ImageFont.load_default()
        
        self.base_size = 240
        self.last_w = 0
        self.last_h = 0
        self.bg_cache: Optional[Image.Image] = None
        
        # Animación física suave e independiente de FPS
        self.current_pos = 0.0
        self.target_pos = 0.0
        self.is_animating = False
        self.anim_timer = None
        self._last_anim_time = 0.0
        
        # Interacción arrastre (swipe)
        self.drag_start_x = 0
        self.drag_start_pos = 0.0
        self.is_dragging = False
        self.has_dragged = False
        
        # Zonas de clic para detección
        self.hitboxes: List[Tuple[int, int, int, int, int]] = []  # (x1, y1, x2, y2, index)
        self.photo_ref = None
        self._photo_w = 0
        self._photo_h = 0
        self.is_transparent_mode = False
        
        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._on_mouse_down)
        self.bind("<B1-Motion>", self._on_mouse_drag)
        self.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.bind("<Button-3>", self._on_right_mouse_down)
        self.bind("<B3-Motion>", self._on_right_mouse_drag)
        self.bind("<MouseWheel>", self._on_mouse_wheel)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Motion>", self._on_mouse_hover)
        
    def _on_right_mouse_down(self, event):
        top = self.winfo_toplevel()
        self._rdrag_x = event.x_root - top.winfo_x()
        self._rdrag_y = event.y_root - top.winfo_y()

    def _on_right_mouse_drag(self, event):
        top = self.winfo_toplevel()
        if getattr(top, "is_mini_mode", False):
            nx = event.x_root - getattr(self, "_rdrag_x", 0)
            ny = event.y_root - getattr(self, "_rdrag_y", 0)
            top.geometry(f"+{nx}+{ny}")
        
    def _get_key(self, g: Dict[str, Any]) -> str:
        """Genera un identificador único para el juego evitando colisiones de nombres iguales."""
        return g.get("path") or g.get("name", "game")

    def _get_cover_sig(self, g: Dict[str, Any]) -> Tuple[Any, ...]:
        """Calcula una firma única del archivo y metadatos de carátula para detectar cambios en caliente."""
        cover_path = resolve_game_cover(g)
        mtime = 0.0
        fsize = 0
        if cover_path and os.path.isfile(cover_path):
            try:
                st = os.stat(cover_path)
                mtime = st.st_mtime
                fsize = st.st_size
            except Exception:
                pass
        return (cover_path, mtime, fsize, g.get("name", ""))

    def _get_wallpaper_sig(self, g: Dict[str, Any]) -> Tuple[Any, ...]:
        """Calcula una firma única del archivo y parámetros del wallpaper para detectar cambios en caliente."""
        wp_path = g.get("wallpaper") or ""
        mtime = 0.0
        fsize = 0
        if wp_path and os.path.isfile(wp_path):
            try:
                st = os.stat(wp_path)
                mtime = st.st_mtime
                fsize = st.st_size
            except Exception:
                pass
        opacity = g.get("wallpaper_opacity", 0.25)
        blur = g.get("wallpaper_blur", 1.5)
        return (wp_path, mtime, fsize, opacity, blur)

    def _load_wallpaper_for_game(self, g: Dict[str, Any]):
        """Carga en memoria el wallpaper apaisado de un juego (si está configurado y existe)."""
        key = self._get_key(g)
        wp_path = g.get("wallpaper")
        if wp_path and os.path.isfile(wp_path):
            try:
                with Image.open(wp_path) as raw_wp:
                    wp_rgb = raw_wp.convert("RGB")
                    # Mantener resolución nativa Full HD / 2K para máxima nitidez (limitar solo si excede 2560px)
                    if wp_rgb.width > 2560:
                        ratio = 2560.0 / float(wp_rgb.width)
                        wp_rgb = wp_rgb.resize((2560, max(1, int(wp_rgb.height * ratio))), Image.Resampling.BILINEAR)
                    self.raw_wallpapers[key] = wp_rgb
            except Exception:
                self.raw_wallpapers.pop(key, None)
        else:
            self.raw_wallpapers.pop(key, None)

    def _get_or_create_jewel_case(self, g: Dict[str, Any]) -> Image.Image:
        """Obtiene el jewel case desde la caché persistente en disco (.cache/jewels)."""
        cover_path = resolve_game_cover(g)
        return get_cached_jewel_case(cover_path, name=g.get("name", ""), size=512)

    def update_game_wallpaper(self, g: Dict[str, Any]):
        """Actualiza en caliente el wallpaper de un juego y refresca el escenario Big Picture."""
        if not g:
            return
        key = self._get_key(g)
        self.raw_wallpapers.pop(key, None)
        self._load_wallpaper_for_game(g)
        self._wp_sigs[key] = self._get_wallpaper_sig(g)
        # Invalidar caché de fondos para este juego
        to_remove = [k for k in self.wallpaper_bg_cache.keys() if k[0] == key]
        for k in to_remove:
            self.wallpaper_bg_cache.pop(k, None)
        self.redraw()

    def update_game_cover(self, g: Dict[str, Any]):
        """Actualiza la carátula de un único juego sin reconstruir toda la biblioteca (0 ms lag)."""
        if not g:
            return
        key = self._get_key(g)
        self.raw_jewels.pop(key, None)
        self.flat_covers.pop(key, None)
        self.rendered_cache.pop(key, None)
        self._cover_sigs[key] = self._get_cover_sig(g)

        jewel = self._get_or_create_jewel_case(g)
        self.raw_jewels[key] = jewel

        has_refl = not getattr(self, "is_transparent_mode", False)
        size = self.base_size
        flat_cover, sz, tot_h = prepare_flat_cover(jewel, size, has_reflection=has_refl)
        self.flat_covers[key] = (flat_cover, sz, tot_h)

        w_left, w_lw, _ = render_cover_flow_from_flat(flat_cover, size, -1.0, has_reflection=has_refl)
        w_right, w_rw, _ = render_cover_flow_from_flat(flat_cover, size, 1.0, has_reflection=has_refl)
        self.rendered_cache[key] = {
            -1.0: (w_left, w_lw),
            0.0: (flat_cover, sz),
            1.0: (w_right, w_rw)
        }
        self.redraw()

    def set_games(self, games: List[Dict[str, Any]], target_index: int = 0):
        self.games = games
        self._library_load_id = getattr(self, "_library_load_id", 0) + 1
        current_load_id = self._library_load_id

        # Conservar en memoria las imágenes raw de los juegos que siguen existiendo (evita re-lectura innecesaria de disco)
        valid_keys = {self._get_key(g) for g in self.games}
        for k in list(self.raw_jewels.keys()):
            if k not in valid_keys:
                self.raw_jewels.pop(k, None)
                self._cover_sigs.pop(k, None)
        for k in list(self.raw_wallpapers.keys()):
            if k not in valid_keys:
                self.raw_wallpapers.pop(k, None)
                self._wp_sigs.pop(k, None)

        # Detectar cambios en carátulas o wallpapers y purgar selectivamente la caché en caliente
        for g in self.games:
            key = self._get_key(g)
            new_cov_sig = self._get_cover_sig(g)
            if self._cover_sigs.get(key) != new_cov_sig:
                self.raw_jewels.pop(key, None)
                self.flat_covers.pop(key, None)
                self.rendered_cache.pop(key, None)
                self._cover_sigs[key] = new_cov_sig

            new_wp_sig = self._get_wallpaper_sig(g)
            if self._wp_sigs.get(key) != new_wp_sig:
                self.raw_wallpapers.pop(key, None)
                to_remove = [k for k in self.wallpaper_bg_cache.keys() if k[0] == key]
                for k in to_remove:
                    self.wallpaper_bg_cache.pop(k, None)
                self._wp_sigs[key] = new_wp_sig

        self.wallpaper_bg_cache.clear()
        self.flat_covers.clear()
        self.rendered_cache.clear()

        n = len(self.games)
        if n > 0:
            self.target_pos = float(max(0, min(n - 1, target_index)))
            self.current_pos = self.target_pos
        else:
            self.target_pos = 0.0
            self.current_pos = 0.0

        target_int = int(round(self.target_pos))
        # Fase 1: Carga inmediata del viewport visible prioritario (target +/- 3)
        visible_indices = set(range(max(0, target_int - 3), min(n, target_int + 4)))
        for idx in visible_indices:
            g = self.games[idx]
            key = self._get_key(g)
            if key not in self.raw_jewels:
                self.raw_jewels[key] = self._get_or_create_jewel_case(g)
                self._cover_sigs[key] = self._get_cover_sig(g)
            if key not in self.raw_wallpapers:
                self._load_wallpaper_for_game(g)
                self._wp_sigs[key] = self._get_wallpaper_sig(g)

        self._rebuild_rendered_cache()
        cw = max(60, self.winfo_width())
        ch = max(60, self.winfo_height())
        self._precache_wallpapers_async(cw, ch, getattr(self, "floor_y", 0))
        self.redraw()
        if self.on_selection_changed and n > 0:
            self.on_selection_changed(target_int)

        # Fase 2: Carga en segundo plano para el resto de juegos (inmune a redimensionamiento de ventana)
        remaining_indices = [i for i in range(n) if i not in visible_indices]
        if remaining_indices:
            def _bg_loader():
                for i in remaining_indices:
                    if self._library_load_id != current_load_id or i >= len(self.games):
                        return
                    g = self.games[i]
                    key = self._get_key(g)
                    if key not in self.raw_jewels:
                        self.raw_jewels[key] = self._get_or_create_jewel_case(g)
                        self._cover_sigs[key] = self._get_cover_sig(g)
                    if key not in self.raw_wallpapers:
                        self._load_wallpaper_for_game(g)
                        self._wp_sigs[key] = self._get_wallpaper_sig(g)

                    # Si este juego ya tiene jewel pero aún no tiene flat cover, generarlo
                    jewel = self.raw_jewels.get(key)
                    if jewel and key not in self.flat_covers:
                        has_refl = not getattr(self, "is_transparent_mode", False)
                        flat_cover, sz, tot_h = prepare_flat_cover(jewel, self.base_size, has_reflection=has_refl)
                        self.flat_covers[key] = (flat_cover, sz, tot_h)
                        if key not in self.rendered_cache:
                            w_left, w_lw, _ = render_cover_flow_from_flat(flat_cover, sz, -1.0, has_reflection=has_refl)
                            w_right, w_rw, _ = render_cover_flow_from_flat(flat_cover, sz, 1.0, has_reflection=has_refl)
                            self.rendered_cache[key] = {
                                -1.0: (w_left, w_lw),
                                0.0: (flat_cover, sz),
                                1.0: (w_right, w_rw)
                            }
                if self._library_load_id != current_load_id:
                    return
                # Pre-componer fondos para todos los juegos recién cargados
                cur_w = max(60, self.winfo_width())
                cur_h = max(60, self.winfo_height())
                self._precache_wallpapers_async(cur_w, cur_h, getattr(self, "floor_y", 0))
                q = getattr(self.master, "_action_queue", None)
                if q is not None:
                    q.put(("callable", self.redraw))
                else:
                    try:
                        self.after(10, self.redraw)
                    except Exception:
                        pass
            threading.Thread(target=_bg_loader, daemon=True).start()

    def _rebuild_rendered_cache(self):
        """Genera instantáneamente los ángulos estáticos de la ventana activa y precomputa en segundo plano los ángulos de transición."""
        self._cache_generation += 1
        current_gen = self._cache_generation
        has_refl = not getattr(self, "is_transparent_mode", False)
        self.rendered_has_refl = has_refl
        
        self.flat_covers.clear()
        self.rendered_cache.clear()
        size = self.base_size
        center_idx = int(round(getattr(self, "target_pos", 0.0)))
        n = len(self.games)
        active_indices = [
            i for i in range(max(0, center_idx - 7), min(n, center_idx + 8))
        ]
        active_Indices_sorted = sorted(active_indices, key=lambda idx: abs(idx - center_idx))
        
        # 1. Fase síncrona ultra rápida (<60ms total): crea carátulas planas y los 3 ángulos de reposo (-1.0, 0.0, +1.0)
        for idx in active_Indices_sorted:
            g = self.games[idx]
            key = self._get_key(g)
            jewel = self.raw_jewels.get(key)
            if not jewel:
                jewel = self._get_or_create_jewel_case(g)
                self.raw_jewels[key] = jewel
            if not jewel:
                continue
            flat_cover, sz, tot_h = prepare_flat_cover(jewel, size, has_reflection=has_refl)
            self.flat_covers[key] = (flat_cover, sz, tot_h)
            
            # Ángulo 0.0 es la carátula plana sin transformación (0 ms)
            w_left, w_lw, _ = render_cover_flow_from_flat(flat_cover, size, -1.0, has_reflection=has_refl)
            w_right, w_rw, _ = render_cover_flow_from_flat(flat_cover, size, 1.0, has_reflection=has_refl)
            
            self.rendered_cache[key] = {
                -1.0: (w_left, w_lw),
                0.0: (flat_cover, sz),
                1.0: (w_right, w_rw)
            }
            
        # 2. Fase asíncrona: precalcula en hilo secundario los 14 ángulos intermedios (paso 0.125 para 60 FPS sedoso)
        def _bg_precompute():
            intermediate_angles = [
                -0.875, -0.75, -0.625, -0.5, -0.375, -0.25, -0.125,
                0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875
            ]
            # Primero procesar el vecindario activo
            for idx in active_Indices_sorted:
                if self._cache_generation != current_gen or idx >= len(self.games):
                    return
                g = self.games[idx]
                key = self._get_key(g)
                flat_data = self.flat_covers.get(key)
                if not flat_data:
                    continue
                flat_cover, sz, _ = flat_data
                for af in intermediate_angles:
                    if self._cache_generation != current_gen:
                        return
                    w_img, tw, _ = render_cover_flow_from_flat(flat_cover, sz, af, has_reflection=has_refl)
                    g_cache = self.rendered_cache.get(key)
                    if g_cache is not None:
                        g_cache[af] = (w_img, tw)

            # A continuación procesar el resto de la biblioteca en segundo plano para scroll infinito sin tirones
            other_indices = [i for i in range(n) if i not in active_indices]
            for idx in other_indices:
                if self._cache_generation != current_gen or idx >= len(self.games):
                    return
                g = self.games[idx]
                key = self._get_key(g)
                jewel = self.raw_jewels.get(key)
                if not jewel:
                    jewel = self._get_or_create_jewel_case(g)
                    self.raw_jewels[key] = jewel
                if not jewel:
                    continue
                if key not in self.flat_covers:
                    flat_cover, sz, tot_h = prepare_flat_cover(jewel, size, has_reflection=has_refl)
                    self.flat_covers[key] = (flat_cover, sz, tot_h)
                else:
                    flat_cover, sz, _ = self.flat_covers[key]

                if key not in self.rendered_cache:
                    w_left, w_lw, _ = render_cover_flow_from_flat(flat_cover, sz, -1.0, has_reflection=has_refl)
                    w_right, w_rw, _ = render_cover_flow_from_flat(flat_cover, sz, 1.0, has_reflection=has_refl)
                    self.rendered_cache[key] = {
                        -1.0: (w_left, w_lw),
                        0.0: (flat_cover, sz),
                        1.0: (w_right, w_rw)
                    }
                g_cache = self.rendered_cache[key]
                for af in intermediate_angles:
                    if self._cache_generation != current_gen:
                        return
                    if af not in g_cache:
                        w_img, tw, _ = render_cover_flow_from_flat(flat_cover, sz, af, has_reflection=has_refl)
                        g_cache[af] = (w_img, tw)

            if self._cache_generation == current_gen:
                q = getattr(self.master, "_action_queue", None)
                if q is not None:
                    q.put(("callable", self.redraw))
                        
        threading.Thread(target=_bg_precompute, daemon=True).start()

    def _prune_rendered_cache(self, max_games: int = 40):
        """Política LRU: Acota la memoria eliminando las carátulas 3D de los juegos más lejanos al índice visible."""
        if len(self.rendered_cache) <= max_games:
            return
        center_idx = int(round(getattr(self, "target_pos", 0.0)))
        key_to_dist = {}
        for key in list(self.rendered_cache.keys()):
            idx = next((i for i, g in enumerate(self.games) if self._get_key(g) == key), 9999)
            key_to_dist[key] = abs(idx - center_idx)

        sorted_keys = sorted(key_to_dist.keys(), key=lambda k: key_to_dist[k], reverse=True)
        for k in sorted_keys[:len(self.rendered_cache) - max_games]:
            self.rendered_cache.pop(k, None)
            self.flat_covers.pop(k, None)

    def get_rendered_cover(self, game_key: str, af: float) -> Tuple[Optional[Image.Image], int]:
        """Obtiene la carátula proyectada en 3D del caché o la calcula bajo demanda con política LRU acotada."""
        key = max(-1.0, min(1.0, round(af * 8.0) / 8.0))
        game_cache = self.rendered_cache.get(game_key)
        if game_cache is None:
            self._prune_rendered_cache(max_games=15)
            game_cache = {}
            self.rendered_cache[game_key] = game_cache
            
        cached = game_cache.get(key)
        if cached is not None:
            return cached
            
        flat_data = self.flat_covers.get(game_key)
        if not flat_data:
            jewel = self.raw_jewels.get(game_key)
            if not jewel:
                g = next((gm for gm in self.games if self._get_key(gm) == game_key), None)
                if g:
                    jewel = self._get_or_create_jewel_case(g)
                    self.raw_jewels[game_key] = jewel
            if jewel:
                has_refl = not getattr(self, "is_transparent_mode", False)
                size = self.base_size
                flat_data = prepare_flat_cover(jewel, size, has_reflection=has_refl)
                self.flat_covers[game_key] = flat_data
            else:
                return None, 0
            
        flat_cover, sz, _ = flat_data
        has_refl = not getattr(self, "is_transparent_mode", False)
        w_img, tw, _ = render_cover_flow_from_flat(flat_cover, sz, key, has_reflection=has_refl)
        w_img = prevent_transparency_color_collision(w_img)
        entry = (w_img, tw)
        game_cache[key] = entry
        return entry

    def _rebuild_background(self, w: int, h: int):
        """Pre-renderiza el escenario estático y foco de luz como RGB ultra optimizado (sin líneas grises)."""
        if getattr(self, "is_transparent_mode", False):
            # Fondo 100% transparente en modo pequeño (color clave RGB: 0, 0, 1)
            self.bg_cache = Image.new('RGB', (w, h), (0, 0, 1))
            return

        bg = Image.new('RGB', (w, h), (15, 18, 24))
        
        # Spotlight ambiental ultra suave estilo Liquid Glass proporcional al lienzo
        spot_w = max(400, min(w, int(w * 0.60)))
        spot_h = max(240, min(h, int(h * 0.46)))
        spot_small = Image.new('RGBA', (200, 100), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(spot_small)
        s_draw.ellipse([10, 10, 190, 90], fill=(0, 122, 255, 30))
        spot_small = spot_small.filter(ImageFilter.GaussianBlur(16))
        spot_big = spot_small.resize((spot_w, spot_h), Image.Resampling.BILINEAR)
        
        cx = w // 2
        cy = int(h * 0.40)
        bg.paste(spot_big, (cx - spot_w // 2, cy - spot_h // 2), spot_big)
            
        self.bg_cache = bg
        self.wallpaper_bg_cache.clear()
        self._bottom_overlay_cache.clear()

    def _precache_wallpapers_async(self, w: int, h: int, floor_y: int):
        """Pre-compone en segundo plano todos los wallpapers de la biblioteca para pase a 60 FPS con 0 ms de latencia."""
        if getattr(self, "is_transparent_mode", False) or not self.games:
            return
        games_list = list(self.games)
        
        def _worker():
            for g in games_list:
                key = self._get_key(g)
                wp_img = self.raw_wallpapers.get(key)
                if not wp_img:
                    self._load_wallpaper_for_game(g)
                    wp_img = self.raw_wallpapers.get(key)
                if not wp_img:
                    continue
                opacity = round(float(g.get("wallpaper_opacity", 0.30)), 2)
                blur_rad = round(float(g.get("wallpaper_blur", 1.8)), 2)
                cache_key = (key, w, h, opacity, blur_rad)
                if cache_key not in self.wallpaper_bg_cache:
                    composed = compose_big_picture_wallpaper_bg(
                        wp_img, w=w, h=h, floor_y=floor_y, opacity=opacity, blur_radius=blur_rad
                    )
                    self.wallpaper_bg_cache[cache_key] = composed
        
        threading.Thread(target=_worker, daemon=True).start()

    def get_background_for_game(self, g: Optional[Dict[str, Any]], w: int, h: int, floor_y: int) -> Image.Image:
        """
        Retorna el fondo RGB para el juego seleccionado en modo Big Picture.
        Utiliza la caché en RAM instantánea (0 ms); si aún no se ha generado, devuelve de inmediato
        el fondo ambiental oscuro para no provocar caídas de frames en la animación y lanza la carga en segundo plano.
        """
        if getattr(self, "is_transparent_mode", False) or not g:
            return self.bg_cache

        key = self._get_key(g)
        wp_img = self.raw_wallpapers.get(key)
        if not wp_img:
            self._load_wallpaper_for_game(g)
            wp_img = self.raw_wallpapers.get(key)
        if not wp_img:
            return self.bg_cache

        opacity = round(float(g.get("wallpaper_opacity", 0.30)), 2)
        blur_rad = round(float(g.get("wallpaper_blur", 1.8)), 2)
        cache_key = (key, w, h, opacity, blur_rad)
        cached = self.wallpaper_bg_cache.get(cache_key)
        if cached is not None:
            return cached

        # Si estamos en plena animación física o arrastre, devolver el fondo base para mantener 60 FPS fijos
        # y generar el wallpaper en segundo plano para que esté listo al detenerse
        def _bg_generate():
            if cache_key not in self.wallpaper_bg_cache:
                composed = compose_big_picture_wallpaper_bg(
                    wp_img, w=w, h=h, floor_y=floor_y, opacity=opacity, blur_radius=blur_rad
                )
                self.wallpaper_bg_cache[cache_key] = composed
                # Si el usuario sigue posicionado en este juego, actualizar suavemente
                if not self.is_animating and not self.is_dragging:
                    center_int = int(round(self.current_pos))
                    if 0 <= center_int < len(self.games) and self._get_key(self.games[center_int]) == key:
                        self.after(10, self.redraw)

        threading.Thread(target=_bg_generate, daemon=True).start()
        return self.bg_cache

    def _on_resize(self, event):
        w = event.width
        h = event.height
        if w < 60 or h < 60:
            return
        is_trans = getattr(self, "is_transparent_mode", False)
        mode_changed = (getattr(self, "_last_mode_was_trans", None) != is_trans)
        if not mode_changed and abs(w - self.last_w) < 4 and abs(h - self.last_h) < 4:
            return
            
        self._last_mode_was_trans = is_trans
        self.last_w = w
        self.last_h = h
        
        # Factor de escala relativo a 1080p (720p=~0.8, 1080p=1.0, 1440p=~1.33, 4K=~2.0)
        self.display_scale = max(0.75, min(2.5, h / 1080.0))
        
        # Actualizar fuentes vectoriales del HUD si la resolución cambió significativamente
        if abs(self.display_scale - getattr(self, "_current_font_scale", 1.0)) > 0.05:
            self._current_font_scale = self.display_scale
            title_pt = max(16, int(round(26 * self.display_scale)))
            sub_pt = max(10, int(round(13 * self.display_scale)))
            try:
                self._font_title_bp = ImageFont.truetype("segoeuib.ttf", title_pt)
                self._font_sub_bp = ImageFont.truetype("segoeuib.ttf", sub_pt)
            except Exception:
                self._font_title_bp = ImageFont.load_default()
                self._font_sub_bp = ImageFont.load_default()
            self._bottom_overlay_cache.clear()

        has_refl = not getattr(self, "is_transparent_mode", False)
        # Sizing óptimo: adaptable dinámicamente según la resolución y modo de visualización
        if getattr(self, "is_transparent_mode", False):
            new_base_size = max(180, min(int(h * 0.72), int(w * 0.42)))
        else:
            max_by_w = int(w * 0.36)
            # En Big Picture la carátula escala con la altura sin límite rígido de 420px (en 4K llega a ~900px)
            new_base_size = max(180, min(int(h * 0.44), max_by_w))
        
        size_changed = (new_base_size != self.base_size)
        refl_changed = (getattr(self, "rendered_has_refl", None) != has_refl)
        self.base_size = new_base_size
        
        self._rebuild_background(w, h)
        self._precache_wallpapers_async(w, h, getattr(self, "floor_y", 0))
        if size_changed or refl_changed or not self.rendered_cache:
            self._rebuild_rendered_cache()
            
        self.redraw()

    def select_index(self, index: int):
        n = len(self.games)
        if n == 0:
            return
        idx = max(0, min(n - 1, index))
        if idx != self.target_pos or not self.is_animating:
            old_idx = int(round(self.target_pos))
            self.target_pos = float(idx)
            self._start_animation()
            if self.on_selection_changed:
                self.on_selection_changed(idx)
            if idx != old_idx:
                try:
                    from core.feedback import feedback_click
                    feedback_click()
                except Exception:
                    pass

    def next_cover(self):
        n = len(self.games)
        if n == 0:
            return
        new_target = min(n - 1, int(round(self.target_pos)) + 1)
        self.select_index(new_target)

    def prev_cover(self):
        n = len(self.games)
        if n == 0:
            return
        new_target = max(0, int(round(self.target_pos)) - 1)
        self.select_index(new_target)

    def _start_animation(self):
        self._last_anim_time = time.perf_counter()
        if not self.is_animating:
            self.is_animating = True
            self._anim_tick()

    def _anim_tick(self):
        now = time.perf_counter()
        dt = min(0.05, max(0.001, now - getattr(self, "_last_anim_time", now)))
        self._last_anim_time = now

        diff = self.target_pos - self.current_pos
        if abs(diff) > 0.002:
            # Física adaptativa independiente de FPS: transición sedosa a 60 FPS
            factor = 1.0 - math.exp(-22.0 * dt)
            self.current_pos += diff * factor
            t0 = time.perf_counter()
            self.redraw()
            draw_ms = (time.perf_counter() - t0) * 1000.0
            delay = max(1, int(round(16.0 - draw_ms)))
            self.anim_timer = self.after(delay, self._anim_tick)
        else:
            self.current_pos = self.target_pos
            self.is_animating = False
            self.anim_timer = None
            self.redraw()

    def _on_mouse_down(self, event):
        self.drag_start_x = event.x
        self.drag_start_pos = self.current_pos
        self.is_dragging = True
        self.has_dragged = False
        self._last_drag_int = int(round(self.current_pos))

    def _on_mouse_drag(self, event):
        if not self.is_dragging or len(self.games) == 0:
            return
        dx = event.x - self.drag_start_x
        if abs(dx) > 6:
            self.has_dragged = True
            
        delta_index = -(dx / max(140.0, self.base_size * 0.75))
        n = len(self.games)
        new_pos = self.drag_start_pos + delta_index
        self.current_pos = max(-0.3, min(n - 0.7, new_pos))
        
        if self.has_dragged:
            cur_int = int(round(max(0, min(n - 1, self.current_pos))))
            if cur_int != getattr(self, "_last_drag_int", -1):
                self._last_drag_int = cur_int
                try:
                    from core.feedback import feedback_click
                    feedback_click()
                except Exception:
                    pass
                    
        self.redraw()

    def _on_mouse_up(self, event):
        if not self.is_dragging:
            return
        self.is_dragging = False
        if not self.has_dragged:
            hud_act = self._get_hud_action_at(event.x, event.y)
            if hud_act and self.on_hud_action:
                self.on_hud_action(hud_act)
                return

        n = len(self.games)
        if n == 0:
            return
            
        if self.has_dragged:
            best_idx = int(round(max(0, min(n - 1, self.current_pos))))
            self.select_index(best_idx)
        else:
            clicked_idx = self._get_index_at(event.x, event.y)
            if clicked_idx is not None:
                self.select_index(clicked_idx)

    def _on_double_click(self, event):
        if self._get_hud_action_at(event.x, event.y):
            return
        clicked_idx = self._get_index_at(event.x, event.y)
        if clicked_idx is not None and clicked_idx == int(round(self.target_pos)):
            if self.on_launch_requested:
                self.on_launch_requested()

    def _on_mouse_wheel(self, event):
        if len(self.games) == 0:
            return
        if event.delta > 0:
            self.prev_cover()
        elif event.delta < 0:
            self.next_cover()

    def _on_mouse_hover(self, event):
        hud_act = self._get_hud_action_at(event.x, event.y)
        is_launch_hov = (hud_act == "launch")
        if is_launch_hov != getattr(self, "_launch_hovered", False):
            self._launch_hovered = is_launch_hov
            self.redraw()

        if hud_act is not None or self._get_index_at(event.x, event.y) is not None:
            self.config(cursor="hand2")
        else:
            self.config(cursor="")

    def _get_hud_action_at(self, x: int, y: int) -> Optional[str]:
        for (x1, y1, x2, y2, act) in self.hud_hitboxes:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return act
        return None

    def _get_index_at(self, x: int, y: int) -> Optional[int]:
        for (x1, y1, x2, y2, idx) in reversed(self.hitboxes):
            if x1 <= x <= x2 and y1 <= y <= y2:
                return idx
        return None

    def _draw_overlays(self, bg: Image.Image, w: int, h: int):
        """
        Superpone con transparencia RGBA real:
          - En modo Transparente: la cápsula superior derecha [Vista | Ocultar | Salir].
          - En modo Big Picture:
              1. Arriba a la derecha: [ ⚙ (X) ]  [ 🔋 -- ]  [ Vista | Ocultar | Salir ] (sin barra gris superior).
              2. Abajo centrado: Título del juego, Monitor/Tiempo jugado y botón '▶ INICIAR JUEGO (A)' (sin barra gris inferior).
        """
        self.hud_hitboxes = []
        fam = getattr(self, "controller_family", "xbox")
        scale = getattr(self, "display_scale", 1.0)

        if getattr(self, "is_transparent_mode", False):
            # En modo normal / transparente flotante: ocultar todo el modo Big Picture y mostrar únicamente las carátulas 3D
            self.hud_hitboxes = []
            return

        # 1. Modo Big Picture: Botones flotantes arriba a la derecha (wallpaper visible hasta y=0 detrás)
        try:
            top_h = max(28, int(round(36 * scale)))
            top_img, top_boxes = render_big_picture_top_hud(
                family=fam,
                battery_txt=getattr(self, "ui_battery_text", "🎮 Mando"),
                battery_col=getattr(self, "ui_battery_color", (100, 116, 139)),
                height=top_h
            )
            hud_x = max(10, w - top_img.width - int(18 * scale))
            hud_y = int(14 * scale)
            bg.paste(top_img, (hud_x, hud_y), top_img)
            for (bx1, by1, bx2, by2, act) in top_boxes:
                self.hud_hitboxes.append((hud_x + bx1, hud_y + by1, hud_x + bx2, hud_y + by2, act))
        except Exception:
            pass

        # 2. Modo Big Picture: Título, Monitor y botón '▶ INICIAR JUEGO' abajo (wallpaper visible hasta y=h detrás)
        try:
            bot_h = max(120, int(round(158 * scale)))
            title_y = int(round(23 * scale))
            sub_y = int(round(57 * scale))
            pill_y = int(round(76 * scale))
            pill_w = max(180, int(round(248 * scale)))
            pill_h = max(36, int(round(48 * scale)))

            b_key = (
                w,
                bot_h,
                self.ui_title,
                self.ui_status,
                self.ui_status_color,
                fam,
                bool(self._launch_hovered),
                bool(self.ui_launch_disabled)
            )
            bot_strip = self._bottom_overlay_cache.get(b_key)
            if bot_strip is None:
                bot_strip = Image.new("RGBA", (w, bot_h), (0, 0, 0, 0))
                bdraw = ImageDraw.Draw(bot_strip)
                cx = w // 2

                # Título del juego con sombra suave para legibilidad total sobre cualquier wallpaper
                if self.ui_title:
                    bdraw.text((cx + 1, title_y + 1), self.ui_title, font=self._font_title_bp, fill=(0, 0, 0, 215), anchor="mm")
                    bdraw.text((cx, title_y), self.ui_title, font=self._font_title_bp, fill=(248, 250, 252, 255), anchor="mm")

                # Subtítulo (Monitor 2 - SAMSUNG (1920x1080) • Tiempo jugado)
                # Limpiamos emojis fuera de Latin/Geometric que segoeuib.ttf en Pillow renderizaría como '□'
                if self.ui_status:
                    clean_status = (
                        self.ui_status
                        .replace("🖥", "")
                        .replace("⏱", "Tiempo:")
                        .replace("🎮", "")
                        .replace("⚙", "Opciones")
                        .replace("\ufe0f", "")
                        .strip()
                    )
                    while "  •" in clean_status:
                        clean_status = clean_status.replace("  •", " •")
                    clean_status = clean_status.replace(" • ", "   •   ")
                    bdraw.text((cx + 1, sub_y + 1), clean_status, font=self._font_sub_bp, fill=(0, 0, 0, 215), anchor="mm")
                    bdraw.text((cx, sub_y), clean_status, font=self._font_sub_bp, fill=(*self.ui_status_color, 255), anchor="mm")

                # Píldora '▶ INICIAR JUEGO (A/✕)'
                if self.games:
                    pill_img = render_launch_button_pill(
                        family=fam,
                        hovered=self._launch_hovered,
                        disabled=self.ui_launch_disabled,
                        width=pill_w,
                        height=pill_h
                    )
                    bot_strip.paste(pill_img, (cx - pill_w // 2, pill_y), pill_img)

                if len(self._bottom_overlay_cache) > 16:
                    self._bottom_overlay_cache.clear()
                self._bottom_overlay_cache[b_key] = bot_strip

            bot_y = max(0, h - bot_h - int(round(14 * scale)))
            bg.paste(bot_strip, (0, bot_y), bot_strip)
            if self.games and not self.ui_launch_disabled:
                cx = w // 2
                self.hud_hitboxes.append((cx - pill_w // 2, bot_y + pill_y, cx + pill_w // 2, bot_y + pill_y + pill_h, "launch"))
        except Exception:
            pass

    def redraw(self, force_w: Optional[int] = None, force_h: Optional[int] = None):
        w = force_w or self.winfo_width()
        h = force_h or self.winfo_height()
        if (w < 50 or h < 50) and getattr(self, "last_w", 0) > 50:
            w = self.last_w
            h = self.last_h
        if w < 50 or h < 50:
            return

        n = len(self.games)
        if n == 0:
            bg_col = (0, 0, 1) if getattr(self, "is_transparent_mode", False) else (12, 14, 19)
            bg = Image.new('RGB', (w, h), bg_col)
            draw = ImageDraw.Draw(bg)
            draw.text((w // 2, h // 2), "No hay juegos en la biblioteca\nHaz clic en 'Opciones' arriba a la derecha para agregar o escanear juegos", fill=(150, 160, 180), anchor='mm')
            self._draw_overlays(bg, w, h)
            self._photo_w = w
            self._photo_h = h
            self.photo_ref = ImageTk.PhotoImage(bg)
            self.delete("all")
            self.canvas_img_id = self.create_image(0, 0, image=self.photo_ref, anchor="nw")
            return

        if not self.bg_cache or self.bg_cache.size != (w, h):
            self._rebuild_background(w, h)

        p = self.current_pos
        cx = w // 2
        size = self.base_size
        scale = getattr(self, "display_scale", 1.0)
        has_refl = not getattr(self, "is_transparent_mode", False)
        if has_refl:
            refl_h = int(size * 0.38)
            # Centrado vertical estético: colocar el suelo de las carátulas al ~63% de la altura
            # para que la caja 3D quede perfectamente centrada en la pantalla con su reflejo y no pegada arriba
            target_floor = int(round(h * 0.63))
            min_floor = size + int(round(36 * scale))
            max_floor = h - refl_h - int(round(96 * scale))
            floor_y = max(min_floor, min(max_floor, target_floor))
        else:
            refl_h = 0
            floor_y = (h + size) // 2

        center_spacing = int(size * 0.82)
        stack_spacing = int(size * 0.22)
        self.hitboxes = []

        center_int = int(round(p))
        center_game = self.games[max(0, min(n - 1, center_int))] if n > 0 else None

        # Clonar fondo RGB ultra rápido (0.8 ms en 1080p; con wallpaper apaisado en modo Big Picture)
        base_bg = self.get_background_for_game(center_game, w, h, floor_y) or self.bg_cache
        bg = base_bg.copy()

        # 1. Pila Izquierda (menores que p, culling a las 4 más cercanas visibles)
        start_left = max(0, center_int - 4)
        for i in range(start_left, center_int):
            if i >= n:
                continue
            d = i - p
            game = self.games[i]
            w_img, w_w = self.get_rendered_cover(self._get_key(game), max(-1.0, d))
            if not w_img:
                continue

            if d <= -1.0:
                pos_x = int(cx - center_spacing + (d + 1.0) * stack_spacing - w_w // 2)
            else:
                pos_x = int(cx + d * center_spacing - w_w // 2)

            # Frustum culling: descartar si cae fuera del ancho visible del canvas
            if pos_x + w_w < -20 or pos_x > w + 20:
                continue

            pos_y = floor_y - size
            bg.paste(w_img, (pos_x, pos_y), w_img)
            self.hitboxes.append((pos_x, pos_y, pos_x + w_w, pos_y + size, i))

        # 2. Pila Derecha (mayores que p, culling a las 4 más cercanas visibles)
        end_right = min(n - 1, center_int + 4)
        for i in range(end_right, center_int, -1):
            if i < 0:
                continue
            d = i - p
            game = self.games[i]
            w_img, w_w = self.get_rendered_cover(self._get_key(game), min(1.0, d))
            if not w_img:
                continue

            if d >= 1.0:
                pos_x = int(cx + center_spacing + (d - 1.0) * stack_spacing - w_w // 2)
            else:
                pos_x = int(cx + d * center_spacing - w_w // 2)

            # Frustum culling
            if pos_x + w_w < -20 or pos_x > w + 20:
                continue

            pos_y = floor_y - size
            bg.paste(w_img, (pos_x, pos_y), w_img)
            self.hitboxes.append((pos_x, pos_y, pos_x + w_w, pos_y + size, i))

        # 3. Carátula Central (más cercana a p, dibujada encima de todo)
        if 0 <= center_int < n:
            d = center_int - p
            game = self.games[center_int]
            c_img, cw = self.get_rendered_cover(self._get_key(game), d)
            if c_img:
                pos_x = int(cx + d * center_spacing - cw // 2)
                pos_y = floor_y - size
                bg.paste(c_img, (pos_x, pos_y), c_img)
                self.hitboxes.append((pos_x, pos_y, pos_x + cw, pos_y + size, center_int))

        # 3.5. Superposición de HUD superior e inferior sin barras grises (RGBA transparente)
        self._draw_overlays(bg, w, h)

        # 4. Actualización eficiente de Tkinter Canvas (sin recrear DIB bitmaps de GDI)
        if self.photo_ref is None or getattr(self, "_photo_w", 0) != w or getattr(self, "_photo_h", 0) != h:
            self._photo_w = w
            self._photo_h = h
            self.photo_ref = ImageTk.PhotoImage(bg)
            self.delete("all")
            self.canvas_img_id = self.create_image(0, 0, image=self.photo_ref, anchor="nw")
        else:
            self.photo_ref.paste(bg)
