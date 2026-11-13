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
    compose_big_picture_wallpaper_bg, get_cached_jewel_case, invalidate_jewel_case_cache,
    render_vertical_shelf_tilt, scale_alpha_mask
)
from core.cover_resolver import resolve_game_cover
from ui.theme import COLOR_BG_CANVAS, COLOR_TRANS_KEY
from ui.controller_hud import (
    render_controller_hud_strip,
    render_big_picture_top_hud,
    render_launch_button_pill,
    render_filter_capsule
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
        self._cache_lock = threading.RLock()

        # Estado del HUD superpuesto sin barras grises en modo Big Picture
        self.ui_title = ""
        self.ui_status = ""
        self.ui_status_color = (148, 163, 184)
        self.ui_battery_text = "🎮 Mando"
        self.ui_battery_color = (100, 116, 139)
        self.ui_launch_disabled = False
        self.ui_filter_label = "Todos"
        self.ui_filter_count = 0
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

        # Animación vertical de cambio de estantería (carousel transition + stack 3D persistente)
        self.shelf_offset_y = 0.0
        self.shelf_transition_dir = 0
        self.shelf_distance = 300
        self.is_shelf_animating = False
        self._outgoing_covers_layer: Optional[Image.Image] = None
        self._outgoing_alpha_mask: Optional[Image.Image] = None
        self._outgoing_body_crop: Optional[Image.Image] = None
        self._outgoing_body_x: int = 0
        self._outgoing_refl_crop: Optional[Image.Image] = None
        self._outgoing_refl_mask: Optional[Image.Image] = None
        self._outgoing_size: int = 0
        self._outgoing_bg: Optional[Image.Image] = None
        self._incoming_shelf_cache: Optional[Tuple[Tuple[Any, ...], Image.Image, int, Optional[Image.Image], Optional[Image.Image]]] = None
        self._shelf_stack: List[Dict[str, Any]] = []
        self._shelf_stack_idx: int = 0
        self._shelf_selected_indices: Dict[str, int] = {}
        self._last_shelf_dir: int = 1
        self._shelf_strip_cache: Dict[Tuple[Any, ...], Tuple[Image.Image, float, float]] = {}
        self._bg_slot_warp_cache: Dict[Tuple[Any, ...], Tuple[Image.Image, Image.Image, int, int]] = {}
        self._stack_prewarm_gen: int = 0
        
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
        cov_path = g.get("cover")
        if cov_path:
            invalidate_jewel_case_cache(cov_path)
        with self._cache_lock:
            self.raw_jewels.pop(key, None)
            self.flat_covers.pop(key, None)
            self.rendered_cache.pop(key, None)
            self._cover_sigs[key] = self._get_cover_sig(g)

            jewel = self._get_or_create_jewel_case(g)
            self.raw_jewels[key] = jewel

            has_refl = self._use_reflection()
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
            self._incoming_shelf_cache = None
            self._shelf_strip_cache.clear()
            self._bg_slot_warp_cache.clear()
        self.redraw()

    def _clear_outgoing_shelf(self):
        """Libera las capas temporales de transición vertical entre estanterías."""
        self._outgoing_covers_layer = None
        self._outgoing_alpha_mask = None
        self._outgoing_body_crop = None
        self._outgoing_body_x = 0
        self._outgoing_refl_crop = None
        self._outgoing_refl_mask = None
        self._outgoing_size = 0
        self._outgoing_bg = None
        self._incoming_shelf_cache = None

    def _is_vertical_stack_active(self) -> bool:
        """Indica si hay múltiples carruseles visibles en pila 3D vertical (modo Big Picture/ventana)."""
        return (
            not getattr(self, "is_transparent_mode", False)
            and len(getattr(self, "_shelf_stack", [])) >= 2
        )

    def _use_reflection(self) -> bool:
        """Usa reflejo en suelo solo en modo single-shelf (en pila 3D los carruseles inferiores van debajo)."""
        return (
            not getattr(self, "is_transparent_mode", False)
            and not self._is_vertical_stack_active()
        )

    def set_shelves_context(
        self,
        shelves: List[Dict[str, Any]],
        current_idx: int,
        selected_indices: Optional[Dict[str, int]] = None,
    ):
        """Registra la lista completa de estanterías activas y sus índices recordados para el carrusel 3D vertical."""
        prev_active = self._is_vertical_stack_active()
        self._shelf_stack = list(shelves or [])
        n_shelves = len(self._shelf_stack)
        if n_shelves > 0:
            self._shelf_stack_idx = max(0, min(n_shelves - 1, int(current_idx)))
        else:
            self._shelf_stack_idx = 0
        self._shelf_selected_indices = dict(selected_indices or {})
        self._bg_slot_warp_cache.clear()

        now_active = self._is_vertical_stack_active()
        if prev_active != now_active:
            self._shelf_strip_cache.clear()
            w = self.winfo_width()
            h = self.winfo_height()
            if w >= 60 and h >= 60 and not getattr(self, "is_transparent_mode", False):
                max_by_w = int(w * 0.36)
                h_ratio = 0.42 if now_active else 0.44
                self.base_size = max(180, min(int(h * h_ratio), max_by_w))

        self._prewarm_neighbor_shelves_async()

    def _get_visible_neighbor_offsets(self) -> List[int]:
        """Devuelve los desplazamientos relativos visibles (sin duplicar la misma estantería arriba y abajo)."""
        n_shelves = len(getattr(self, "_shelf_stack", []))
        if n_shelves <= 1:
            return []
        if n_shelves == 2:
            return [-1] if self._shelf_stack_idx == 1 else [1]
        if n_shelves in (3, 4):
            return [-1, 1]
        return [-2, -1, 1, 2]

    def _get_shelf_center_idx(self, shelf: Dict[str, Any]) -> int:
        games = shelf.get("games") or []
        if not games:
            return 0
        sid = shelf.get("id", "")
        idx = int(self._shelf_selected_indices.get(sid, 0) or 0)
        return max(0, min(len(games) - 1, idx))

    def _get_shelf_strip_sig(
        self,
        shelf_id: str,
        shelf_games: List[Dict[str, Any]],
        target_idx: int,
        w: int,
        full_size: int,
    ) -> Tuple[Any, ...]:
        n = len(shelf_games)
        center_idx = max(0, min(n - 1, target_idx)) if n > 0 else 0
        start_i = max(0, center_idx - 3)
        end_i = min(n, center_idx + 4)
        cov_keys = tuple(
            (self._get_key(shelf_games[i]), shelf_games[i].get("cover", ""))
            for i in range(start_i, end_i)
        )
        return (shelf_id, center_idx, w, full_size, cov_keys)

    def _get_bg_shelf_strip(
        self,
        shelf: Dict[str, Any],
        target_idx: int,
        w: int,
        full_size: int,
        allow_disk: bool = False,
    ) -> Optional[Tuple[Image.Image, float, float]]:
        """
        Compone y cachea una tira horizontal compacta (~58% resolución) para una estantería en segundo plano.
        Si allow_disk=False (hilo UI), jamás bloquea leyendo disco; devuelve None hasta que el hilo de precarga termine.
        """
        shelf_games = shelf.get("games") or []
        n = len(shelf_games)
        if n == 0 or w < 50 or full_size < 40:
            return None

        shelf_id = str(shelf.get("id", ""))
        center_idx = max(0, min(n - 1, int(target_idx)))
        strip_sig = self._get_shelf_strip_sig(shelf_id, shelf_games, center_idx, w, full_size)
        cached = self._shelf_strip_cache.get(strip_sig)
        if cached is not None:
            return cached

        STRIP_SCALE = 0.58
        strip_sz = max(64, int(round(full_size * STRIP_SCALE)))
        strip_w = max(80, int(round(w * STRIP_SCALE)))
        cx = strip_w // 2
        center_spacing = int(strip_sz * 0.82)
        stack_spacing = int(strip_sz * 0.22)

        start_left = max(0, center_idx - 3)
        end_right = min(n - 1, center_idx + 3)

        ordered_indices: List[int] = []
        for i in range(start_left, center_idx):
            ordered_indices.append(i)
        for i in range(end_right, center_idx, -1):
            ordered_indices.append(i)
        ordered_indices.append(center_idx)

        jewels_by_idx: Dict[int, Image.Image] = {}
        for i in ordered_indices:
            g = shelf_games[i]
            key = self._get_key(g)
            jewel = self.raw_jewels.get(key)
            if jewel is None:
                if not allow_disk:
                    return None
                jewel = self._get_or_create_jewel_case(g)
                if jewel is not None:
                    with self._cache_lock:
                        self.raw_jewels[key] = jewel
                        self._cover_sigs[key] = self._get_cover_sig(g)
            if jewel is not None:
                jewels_by_idx[i] = jewel

        if center_idx not in jewels_by_idx:
            return None

        layer = Image.new("RGBA", (strip_w, strip_sz), (0, 0, 0, 0))
        for i in ordered_indices:
            jewel = jewels_by_idx.get(i)
            if jewel is None:
                continue
            d = float(i - center_idx)
            flat_small = prevent_transparency_color_collision(
                jewel.resize((strip_sz, strip_sz), Image.Resampling.BILINEAR)
            )
            if abs(d) < 0.02:
                w_img = flat_small
                w_w = strip_sz
                pos_x = int(cx - w_w // 2)
            else:
                af = max(-1.0, min(1.0, d))
                w_img, w_w, _ = render_cover_flow_from_flat(flat_small, strip_sz, af, has_reflection=False)
                if d <= -1.0:
                    pos_x = int(cx - center_spacing + (d + 1.0) * stack_spacing - w_w // 2)
                else:
                    pos_x = int(cx + center_spacing + (d - 1.0) * stack_spacing - w_w // 2)
            if pos_x + w_w < -16 or pos_x > strip_w + 16:
                continue
            layer.paste(w_img, (pos_x, 0), w_img)

        bbox = layer.getbbox()
        if not bbox:
            return None
        bx1, _, bx2, _ = bbox
        body_crop = layer.crop((bx1, 0, bx2, strip_sz))
        cx_in_strip = (strip_w / 2.0) - float(bx1)
        entry = (body_crop, cx_in_strip, STRIP_SCALE)

        if len(self._shelf_strip_cache) >= 28:
            # Evict oldest entries smoothly
            for old_k in list(self._shelf_strip_cache.keys())[:8]:
                self._shelf_strip_cache.pop(old_k, None)
        self._shelf_strip_cache[strip_sig] = entry
        return entry

    def _prewarm_neighbor_shelves_async(self):
        """Precarga en segundo plano las estanterías adyacentes (-3..+3) sin bloquear el hilo UI."""
        if not self._is_vertical_stack_active():
            return
        self._stack_prewarm_gen = getattr(self, "_stack_prewarm_gen", 0) + 1
        gen = self._stack_prewarm_gen
        shelves = list(self._shelf_stack)
        cur_idx = self._shelf_stack_idx
        n_shelves = len(shelves)
        if n_shelves <= 1:
            return

        w = self.winfo_width()
        if w < 60:
            w = getattr(self, "last_w", 0) or 1280
        full_size = max(120, self.base_size)

        seen_idxs = {cur_idx}
        targets: List[Tuple[Dict[str, Any], int]] = []
        for rel in (-1, 1, -2, 2, -3, 3):
            s_idx = (cur_idx + rel) % n_shelves
            if s_idx in seen_idxs:
                continue
            seen_idxs.add(s_idx)
            sh = shelves[s_idx]
            if sh.get("games"):
                targets.append((sh, self._get_shelf_center_idx(sh)))

        if not targets:
            return

        def _worker():
            # Si hay una animación vertical activa, ceder un breve instante para no competir con sus primeros frames
            if getattr(self, "is_shelf_animating", False):
                time.sleep(0.06)
            built_any = False
            for sh, t_idx in targets:
                if self._stack_prewarm_gen != gen:
                    return
                sh_games = sh.get("games") or []
                sig = self._get_shelf_strip_sig(str(sh.get("id", "")), sh_games, t_idx, w, full_size)
                if sig in self._shelf_strip_cache:
                    continue
                res = self._get_bg_shelf_strip(sh, t_idx, w, full_size, allow_disk=True)
                if res is not None:
                    built_any = True
            if built_any and self._stack_prewarm_gen == gen and not getattr(self, "is_animating", False):
                q = getattr(self.master, "_action_queue", None)
                if q is not None:
                    q.put(("callable", self.redraw))

        threading.Thread(target=_worker, daemon=True).start()

    def _eval_stack_slot_params(self, s: float, full_size: int) -> Tuple[float, float, int, float, float, float]:
        """
        Calcula parámetros 3D continuos para una estantería en la posición relativa s:
          s = 0.0 -> primer plano nítido y plano
          s < 0   -> carruseles superiores retrocediendo por detrás
          s > 0   -> carruseles inferiores retrocediendo por detrás
        Retorna: (scale_d, tilt, tilt_dir, alpha, bright, peek_px).
        """
        abs_s = abs(float(s))
        tilt_dir = -1 if s < 0.0 else 1

        if abs_s <= 0.012:
            return 1.0, 0.0, tilt_dir, 1.0, 1.0, 0.0

        scale_d = max(0.48, 1.0 - 0.17 * abs_s + 0.01 * (abs_s * abs_s))
        tilt = min(0.94, 0.56 * (abs_s ** 0.55))
        bright = max(0.32, 1.0 - 0.26 * abs_s + 0.02 * (abs_s * abs_s))
        fade_tail = max(0.0, abs_s - 2.0) ** 1.15
        alpha = 1.0 if abs_s <= 0.40 else max(0.0, min(1.0, 1.0 - 0.12 * (abs_s - 0.40) - 0.85 * fade_tail))

        abs_pos = min(2.8, abs_s)
        peek_px = float(full_size) * (0.28 * abs_pos - 0.048 * (abs_pos * abs_pos))
        return scale_d, tilt, tilt_dir, alpha, bright, peek_px

    def _draw_stack_shelf_slot(
        self,
        bg: Image.Image,
        shelf: Dict[str, Any],
        target_idx: int,
        s: float,
        w: int,
        h: int,
        floor_y: int,
        full_size: int,
        full_body_override: Optional[Tuple[Image.Image, int]] = None,
        is_resting: bool = False,
        extra_alpha: float = 1.0,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Renderiza una estantería en el slot continuo s de la pila 3D vertical usando caché si está en reposo."""
        scale_d, tilt, tilt_dir, alpha, bright, peek_px = self._eval_stack_slot_params(s, full_size)
        alpha *= max(0.0, min(1.0, float(extra_alpha)))
        if alpha <= 0.02:
            return None

        shelf_id = str(shelf.get("id", ""))
        abs_s = abs(s)
        warp_key = None
        if is_resting and abs_s >= 0.02 and full_body_override is None:
            shelf_games = shelf.get("games") or []
            strip_sig = self._get_shelf_strip_sig(shelf_id, shelf_games, target_idx, w, full_size)
            warp_key = (strip_sig, round(s, 3), w, h, full_size)
            cached_warp = self._bg_slot_warp_cache.get(warp_key)
            if cached_warp is not None:
                warped, mask, x_draw, y_draw = cached_warp
                bg.paste(warped, (x_draw, y_draw), mask)
                return (x_draw, y_draw, warped.width, warped.height)

        if full_body_override is not None:
            src_strip, bx1_full = full_body_override
            if src_strip is None:
                return None
            cx_in_strip = (w / 2.0) - float(bx1_full)
            strip_scale = 1.0
        else:
            strip_res = self._get_bg_shelf_strip(shelf, target_idx, w, full_size, allow_disk=False)
            if strip_res is None:
                return None
            src_strip, cx_in_strip, strip_scale = strip_res

        rel_scale = scale_d / max(0.1, strip_scale)
        res_mode = Image.Resampling.BILINEAR if is_resting else Image.Resampling.NEAREST

        warped, mask, th = render_vertical_shelf_tilt(
            src_strip,
            tilt=tilt,
            tilt_dir=tilt_dir,
            center_x_in_crop=cx_in_strip,
            alpha_scale=alpha,
            brightness_scale=bright,
            max_angle_rad=1.15,
            resample=res_mode,
            transparent_key_safe=False,
            out_scale=rel_scale,
        )

        cx_out = cx_in_strip * (float(warped.width) / float(max(1, src_strip.width)))
        x_draw = int(round((w / 2.0) - cx_out))
        if tilt_dir < 0:
            y_draw = (floor_y - full_size) - int(round(peek_px))
        else:
            y_bot = floor_y + int(round(peek_px))
            y_draw = y_bot - th

        if warp_key is not None:
            if len(self._bg_slot_warp_cache) >= 24:
                self._bg_slot_warp_cache.clear()
            self._bg_slot_warp_cache[warp_key] = (warped, mask, x_draw, y_draw)

        bg.paste(warped, (x_draw, y_draw), mask)
        return (x_draw, y_draw, warped.width, th)

    def _iter_visible_cover_slots(self, w: int, size: int):
        """Genera (idx, pos_x, w_img, w_w) de las carátulas visibles en orden de pintado (izq, der, centro)."""
        n = len(self.games)
        if n == 0:
            return
        p = self.current_pos
        cx = w // 2
        center_int = int(round(p))
        center_spacing = int(size * 0.82)
        stack_spacing = int(size * 0.22)

        # 1. Pila Izquierda (culling a las 4 más cercanas visibles)
        start_left = max(0, center_int - 4)
        for i in range(start_left, center_int):
            if i >= n:
                continue
            d = i - p
            w_img, w_w = self.get_rendered_cover(self._get_key(self.games[i]), max(-1.0, d))
            if not w_img:
                continue
            if d <= -1.0:
                pos_x = int(cx - center_spacing + (d + 1.0) * stack_spacing - w_w // 2)
            else:
                pos_x = int(cx + d * center_spacing - w_w // 2)
            if pos_x + w_w < -20 or pos_x > w + 20:
                continue
            yield (i, pos_x, w_img, w_w)

        # 2. Pila Derecha (culling a las 4 más cercanas visibles)
        end_right = min(n - 1, center_int + 4)
        for i in range(end_right, center_int, -1):
            if i < 0:
                continue
            d = i - p
            w_img, w_w = self.get_rendered_cover(self._get_key(self.games[i]), min(1.0, d))
            if not w_img:
                continue
            if d >= 1.0:
                pos_x = int(cx + center_spacing + (d - 1.0) * stack_spacing - w_w // 2)
            else:
                pos_x = int(cx + d * center_spacing - w_w // 2)
            if pos_x + w_w < -20 or pos_x > w + 20:
                continue
            yield (i, pos_x, w_img, w_w)

        # 3. Carátula Central
        if 0 <= center_int < n:
            d = center_int - p
            c_img, cw = self.get_rendered_cover(self._get_key(self.games[center_int]), d)
            if c_img:
                pos_x = int(cx + d * center_spacing - cw // 2)
                yield (center_int, pos_x, c_img, cw)

    def _compose_shelf_layer(self, w: int, tot_h: int) -> Image.Image:
        """Compone las carátulas visibles del carrusel actual en una capa RGBA única."""
        layer = Image.new("RGBA", (w, tot_h), (0, 0, 0, 0))
        size = self.base_size
        for _, pos_x, w_img, _ in self._iter_visible_cover_slots(w, size):
            layer.paste(w_img, (pos_x, 0), w_img)
        return layer

    def _extract_shelf_crops(self, layer: Image.Image, w: int, size: int) -> Tuple[Optional[Image.Image], int, Optional[Image.Image], Optional[Image.Image]]:
        """Separa y recorta al bounding box el cuerpo de carátulas (0..size) y su reflejo inferior."""
        if not layer or layer.width <= 0 or layer.height <= 0:
            return None, 0, None, None
        body_h = min(size, layer.height)
        body_strip = layer.crop((0, 0, w, body_h))
        bbox = body_strip.getbbox()
        if not bbox:
            return None, 0, None, None
        bx1, _, bx2, _ = bbox
        body_crop = body_strip.crop((bx1, 0, bx2, body_h))

        refl_crop = None
        refl_mask = None
        if layer.height > body_h and not getattr(self, "is_transparent_mode", False):
            refl_strip = layer.crop((bx1, body_h, bx2, layer.height))
            rbbox = refl_strip.getbbox()
            if rbbox and rbbox[3] > 0:
                refl_crop = refl_strip.crop((0, 0, bx2 - bx1, rbbox[3]))
                refl_mask = refl_crop.getchannel("A")
        return body_crop, bx1, refl_crop, refl_mask

    def _capture_outgoing_shelf(self):
        """Captura las carátulas de la estantería saliente en una capa RGBA para transición 3D fluida."""
        if not self.games:
            self._clear_outgoing_shelf()
            return

        w = self.winfo_width()
        if w < 50:
            w = getattr(self, "last_w", 0)
        if w < 50:
            w = 1280

        h = self.winfo_height()
        if h < 50:
            h = getattr(self, "last_h", 0)
        if h < 50:
            h = 720

        size = self.base_size
        tot_h = (int(size * 1.6) + 20) if self._use_reflection() else (size + 4)
        layer = self._compose_shelf_layer(w, tot_h)

        self._outgoing_covers_layer = layer
        try:
            self._outgoing_alpha_mask = layer.split()[3]
        except Exception:
            self._outgoing_alpha_mask = None

        body_crop, bx1, refl_crop, refl_mask = self._extract_shelf_crops(layer, w, size)
        self._outgoing_body_crop = body_crop
        self._outgoing_body_x = bx1
        self._outgoing_refl_crop = refl_crop
        self._outgoing_refl_mask = refl_mask
        self._outgoing_size = size

        if not getattr(self, "is_transparent_mode", False):
            try:
                p = self.current_pos
                n = len(self.games)
                center_int = max(0, min(n - 1, int(round(p))))
                center_game = self.games[center_int]
                floor_y = self._compute_floor_y(h, size)
                prev_bg = self.get_background_for_game(center_game, w, h, floor_y) or self.bg_cache
                self._outgoing_bg = prev_bg.copy() if prev_bg is not None else None
            except Exception:
                self._outgoing_bg = None
        else:
            self._outgoing_bg = None

    def set_games(self, games: List[Dict[str, Any]], target_index: int = 0, transition_direction: int = 0):
        # Si se solicita animación vertical de cambio de estantería y hay juegos previos (o pila 3D activa):
        if transition_direction != 0 and (self.games or self._is_vertical_stack_active()):
            self._capture_outgoing_shelf()
            size = self.base_size
            h = self.winfo_height()
            if h < 50:
                h = getattr(self, "last_h", 0)
            if h < 50:
                h = 720
            self.shelf_distance = int(round(max(size * 1.15, h * 0.35)))
            self.shelf_transition_dir = transition_direction
            self._last_shelf_dir = 1 if transition_direction >= 0 else -1
            self.shelf_offset_y = float(transition_direction * self.shelf_distance)
            self.is_shelf_animating = True
            self._incoming_shelf_cache = None
        else:
            self.shelf_offset_y = 0.0
            self.shelf_transition_dir = 0
            self.is_shelf_animating = False
            self._clear_outgoing_shelf()

        self.games = games
        self._library_load_id = getattr(self, "_library_load_id", 0) + 1
        current_load_id = self._library_load_id

        # Conservar en memoria las imágenes raw de la estantería activa y las estanterías vecinas visibles
        valid_games_by_key: Dict[str, Dict[str, Any]] = {self._get_key(g): g for g in self.games}
        if self._shelf_stack:
            n_sh = len(self._shelf_stack)
            for rel in (-3, -2, -1, 1, 2, 3):
                sh = self._shelf_stack[(self._shelf_stack_idx + rel) % n_sh]
                sh_games = sh.get("games") or []
                if not sh_games:
                    continue
                c_idx = self._get_shelf_center_idx(sh)
                for j in range(max(0, c_idx - 3), min(len(sh_games), c_idx + 4)):
                    ng = sh_games[j]
                    nk = self._get_key(ng)
                    if nk not in valid_games_by_key:
                        valid_games_by_key[nk] = ng

        valid_keys = set(valid_games_by_key.keys())
        for k in list(self.raw_jewels.keys()):
            if k not in valid_keys:
                self.raw_jewels.pop(k, None)
                self._cover_sigs.pop(k, None)
        active_wp_keys = {self._get_key(g) for g in self.games}
        for k in list(self.raw_wallpapers.keys()):
            if k not in active_wp_keys:
                self.raw_wallpapers.pop(k, None)
                self._wp_sigs.pop(k, None)

        # Optimización masiva (+500 juegos): solo comprobar cambios en disco para los juegos que ya residen en memoria
        for key in list(self.raw_jewels.keys()):
            g = valid_games_by_key.get(key)
            if not g:
                self.raw_jewels.pop(key, None)
                self.flat_covers.pop(key, None)
                self.rendered_cache.pop(key, None)
                self._cover_sigs.pop(key, None)
                continue
            new_cov_sig = self._get_cover_sig(g)
            if self._cover_sigs.get(key) != new_cov_sig:
                self.raw_jewels.pop(key, None)
                self.flat_covers.pop(key, None)
                self.rendered_cache.pop(key, None)
                self._cover_sigs[key] = new_cov_sig
                self._shelf_strip_cache.clear()
                self._bg_slot_warp_cache.clear()

        games_by_key = {self._get_key(g): g for g in self.games}
        for key in list(self.raw_wallpapers.keys()):
            g = games_by_key.get(key)
            if not g:
                self.raw_wallpapers.pop(key, None)
                self._wp_sigs.pop(key, None)
                continue
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
        if self.is_shelf_animating:
            self._start_animation()
        else:
            self.redraw()
        if self.on_selection_changed and n > 0:
            self.on_selection_changed(target_int)

        # Fase 2: Carga diferida en segundo plano para el búfer deslizante (evita cargar 500+ carátulas en RAM)
        buffer_indices = [
            i for i in range(max(0, target_int - 10), min(n, target_int + 11))
            if i not in visible_indices
        ]
        if buffer_indices:
            init_w = max(60, self.winfo_width())
            init_h = max(60, self.winfo_height())

            def _bg_loader():
                for i in buffer_indices:
                    if self._library_load_id != current_load_id or i >= len(self.games):
                        return
                    g = self.games[i]
                    key = self._get_key(g)
                    if key not in self.raw_jewels:
                        self.raw_jewels[key] = self._get_or_create_jewel_case(g)
                        self._cover_sigs[key] = self._get_cover_sig(g)

                    jewel = self.raw_jewels.get(key)
                    if jewel and key not in self.flat_covers:
                        has_refl = self._use_reflection()
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
                self._prune_memory_caches(target_int)
                cur_w, cur_h = getattr(self, "_last_canvas_dims", (init_w, init_h))
                self._precache_wallpapers_async(cur_w, cur_h, getattr(self, "floor_y", 0))
                q = getattr(self.master, "_action_queue", None)
                if q is not None:
                    q.put(("callable", self.redraw))
            threading.Thread(target=_bg_loader, daemon=True).start()

    def _rebuild_rendered_cache(self):
        """Genera instantáneamente los ángulos estáticos de la ventana activa y precomputa en segundo plano los ángulos de transición."""
        self._cache_generation += 1
        current_gen = self._cache_generation
        has_refl = self._use_reflection()
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

            # En bibliotecas masivas (+500 juegos), precalcular ángulos intermedios únicamente para el búfer cercano (+/- 12)
            buffer_indices = [
                i for i in range(max(0, center_idx - 12), min(n, center_idx + 13))
                if i not in active_indices
            ]
            for idx in buffer_indices:
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
                self._prune_memory_caches(center_idx)
                q = getattr(self.master, "_action_queue", None)
                if q is not None:
                    q.put(("callable", self.redraw))
                        
        threading.Thread(target=_bg_precompute, daemon=True).start()

    def _prune_memory_caches(self, center_idx: Optional[int] = None):
        """
        Garantiza consumo de memoria RAM estrictamente acotado (<150 MB) incluso con más de 1000 juegos.
        Aplica política LRU y distancia al viewport para evacuar imágenes 3D, estuches y fondos lejanos.
        """
        if not self.games:
            return
        if center_idx is None:
            center_idx = int(round(getattr(self, "current_pos", 0.0)))
        key_to_idx = {self._get_key(g): i for i, g in enumerate(self.games)}

        shelf_stack = getattr(self, "_shelf_stack", None) or []
        neighbor_keys = set()
        if shelf_stack:
            n_sh = len(shelf_stack)
            cur_s_idx = getattr(self, "_shelf_stack_idx", 0)
            for rel in (-2, -1, 1, 2):
                sh = shelf_stack[(cur_s_idx + rel) % n_sh]
                sh_games = sh.get("games") or []
                if not sh_games:
                    continue
                c_i = self._get_shelf_center_idx(sh)
                for j in range(max(0, c_i - 3), min(len(sh_games), c_i + 4)):
                    neighbor_keys.add(self._get_key(sh_games[j]))

        # 1. Acotar rendered_cache y flat_covers (máx 36 juegos)
        MAX_RENDERED = 36
        with self._cache_lock:
            if len(self.rendered_cache) > MAX_RENDERED:
                sorted_rendered = sorted(
                    self.rendered_cache.keys(),
                    key=lambda k: abs(key_to_idx.get(k, 9999) - center_idx),
                    reverse=True
                )
                to_remove = sorted_rendered[:len(self.rendered_cache) - MAX_RENDERED]
                for k in to_remove:
                    self.rendered_cache.pop(k, None)
                    self.flat_covers.pop(k, None)

        # 2. Acotar raw_jewels (máx 64 en modo fila única, 80 con pila 3D multi-estantería; prioriza vecinos)
        MAX_JEWELS = 80 if len(shelf_stack) >= 2 else 64
        if len(self.raw_jewels) > MAX_JEWELS:
            sorted_jewels = sorted(
                self.raw_jewels.keys(),
                key=lambda k: 0 if k in neighbor_keys else abs(key_to_idx.get(k, 9999) - center_idx),
                reverse=True
            )
            for k in sorted_jewels[:len(self.raw_jewels) - MAX_JEWELS]:
                self.raw_jewels.pop(k, None)

        # 3. Acotar raw_wallpapers y wallpaper_bg_cache (máx 12 fondos crudos, 6 compuestos)
        MAX_WP = 12
        if len(self.raw_wallpapers) > MAX_WP:
            sorted_wp = sorted(
                self.raw_wallpapers.keys(),
                key=lambda k: abs(key_to_idx.get(k, 9999) - center_idx),
                reverse=True
            )
            for k in sorted_wp[:len(self.raw_wallpapers) - MAX_WP]:
                self.raw_wallpapers.pop(k, None)

        MAX_BG_COMPOSED = 6
        if len(self.wallpaper_bg_cache) > MAX_BG_COMPOSED:
            sorted_bg = sorted(
                self.wallpaper_bg_cache.keys(),
                key=lambda item: abs(key_to_idx.get(item[0], 9999) - center_idx),
                reverse=True
            )
            for bg_k in sorted_bg[:len(self.wallpaper_bg_cache) - MAX_BG_COMPOSED]:
                self.wallpaper_bg_cache.pop(bg_k, None)

    def get_rendered_cover(self, game_key: str, af: float) -> Tuple[Optional[Image.Image], int]:
        """Obtiene la carátula proyectada en 3D del caché o la calcula bajo demanda con política LRU acotada."""
        key = max(-1.0, min(1.0, round(af * 8.0) / 8.0))
        with self._cache_lock:
            game_cache = self.rendered_cache.get(game_key)
            if game_cache is None:
                self._prune_memory_caches()
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
                if not jewel:
                    if not hasattr(self, "_fallback_jewel") or self._fallback_jewel is None:
                        self._fallback_jewel = create_procedural_album("GameFlow", size=380)
                    jewel = self._fallback_jewel

                has_refl = self._use_reflection()
                size = self.base_size
                flat_data = prepare_flat_cover(jewel, size, has_reflection=has_refl)
                self.flat_covers[game_key] = flat_data

            flat_cover, sz, _ = flat_data
            has_refl = self._use_reflection()
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
        """Pre-compone en segundo plano únicamente los wallpapers adyacentes (+/- 2) al juego seleccionado."""
        if getattr(self, "is_transparent_mode", False) or not self.games:
            return
        center_int = int(round(getattr(self, "target_pos", 0.0)))
        n = len(self.games)
        near_indices = [i for i in range(max(0, center_int - 2), min(n, center_int + 3))]
        near_games = [self.games[i] for i in near_indices]

        def _worker():
            for g in near_games:
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
            self._prune_memory_caches(center_int)

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
                # Si el usuario sigue posicionado en este juego, actualizar suavemente vía cola segura
                if not self.is_animating and not self.is_dragging:
                    center_int = int(round(self.current_pos))
                    if 0 <= center_int < len(self.games) and self._get_key(self.games[center_int]) == key:
                        q = getattr(self.master, "_action_queue", None)
                        if q is not None:
                            q.put(("callable", self.redraw))

        threading.Thread(target=_bg_generate, daemon=True).start()
        return self.bg_cache

    def _on_resize(self, event):
        w = event.width
        h = event.height
        if w < 60 or h < 60:
            return
        self._last_canvas_dims = (w, h)
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

        has_refl = self._use_reflection()
        # Sizing óptimo: adaptable dinámicamente según la resolución y modo de visualización
        if getattr(self, "is_transparent_mode", False):
            new_base_size = max(180, min(int(h * 0.72), int(w * 0.42)))
        else:
            max_by_w = int(w * 0.36)
            h_ratio = 0.42 if self._is_vertical_stack_active() else 0.44
            # En Big Picture la carátula escala con la altura sin límite rígido de 420px (en 4K llega a ~900px)
            new_base_size = max(180, min(int(h * h_ratio), max_by_w))
        
        size_changed = (new_base_size != self.base_size)
        refl_changed = (getattr(self, "rendered_has_refl", None) != has_refl)
        self.base_size = new_base_size
        
        self._shelf_strip_cache.clear()
        self._bg_slot_warp_cache.clear()
        self._rebuild_background(w, h)
        self._precache_wallpapers_async(w, h, getattr(self, "floor_y", 0))
        if size_changed or refl_changed or not self.rendered_cache:
            self._rebuild_rendered_cache()
        if self._is_vertical_stack_active():
            self._prewarm_neighbor_shelves_async()
            
        self.redraw()

    def select_index(self, index: int):
        n = len(self.games)
        if n == 0:
            return
        idx = max(0, min(n - 1, index))
        if self._shelf_stack and 0 <= self._shelf_stack_idx < len(self._shelf_stack):
            cur_sid = self._shelf_stack[self._shelf_stack_idx].get("id")
            if cur_sid is not None:
                self._shelf_selected_indices[cur_sid] = idx
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

        diff_h = self.target_pos - self.current_pos
        diff_v = 0.0 - getattr(self, "shelf_offset_y", 0.0)

        need_anim_h = abs(diff_h) > 0.002
        was_shelf_anim = getattr(self, "is_shelf_animating", False)
        need_anim_v = abs(diff_v) > 1.2 and was_shelf_anim

        if need_anim_h or need_anim_v:
            # Física adaptativa independiente de FPS:
            # horizontal ágil (k=22) para carátulas, vertical pausado y sedoso (k=6.8) para apreciar la rotación 3D
            if need_anim_h:
                factor_h = 1.0 - math.exp(-22.0 * dt)
                self.current_pos += diff_h * factor_h
            else:
                self.current_pos = self.target_pos

            if need_anim_v:
                factor_v = 1.0 - math.exp(-6.8 * dt)
                self.shelf_offset_y += diff_v * factor_v
            else:
                self.shelf_offset_y = 0.0
                self.is_shelf_animating = False
                self._clear_outgoing_shelf()
                if was_shelf_anim and self._is_vertical_stack_active():
                    self._prewarm_neighbor_shelves_async()

            t0 = time.perf_counter()
            self.redraw()
            draw_ms = (time.perf_counter() - t0) * 1000.0
            delay = max(1, int(round(16.0 - draw_ms)))
            self.anim_timer = self.after(delay, self._anim_tick)
        else:
            self.current_pos = self.target_pos
            self.shelf_offset_y = 0.0
            self.is_shelf_animating = False
            self._clear_outgoing_shelf()
            self.is_animating = False
            self.anim_timer = None
            self._prune_memory_caches(int(round(self.target_pos)))
            self._precache_wallpapers_async(self.winfo_width(), self.winfo_height(), getattr(self, "floor_y", 0))
            if was_shelf_anim and self._is_vertical_stack_active():
                self._prewarm_neighbor_shelves_async()
            self.redraw()

    def _on_mouse_down(self, event):
        self.drag_start_x = event.x
        self.drag_start_pos = self.current_pos
        self.is_dragging = True
        self.has_dragged = False
        self._last_drag_int = int(round(self.current_pos))
        if getattr(self, "is_shelf_animating", False):
            self.shelf_offset_y = 0.0
            self.is_shelf_animating = False
            self._clear_outgoing_shelf()

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

        # 0. Modo Big Picture: Píldora de Colección y Filtro arriba a la izquierda [ (LB/L1) ‹ FAVORITOS (4) › (RB/R1) ]
        try:
            filt_lbl = getattr(self, "ui_filter_label", "Todos")
            filt_cnt = getattr(self, "ui_filter_count", len(self.games))
            top_h = max(28, int(round(36 * scale)))
            s_idx = getattr(self, "ui_shelf_index", 0)
            s_tot = getattr(self, "ui_total_shelves", 1)
            filt_img, filt_boxes = render_filter_capsule(
                filter_label=filt_lbl,
                count=filt_cnt,
                family=fam,
                height=top_h,
                shelf_index=s_idx,
                total_shelves=s_tot
            )
            filt_x = int(18 * scale)
            filt_y = int(14 * scale)
            bg.paste(filt_img, (filt_x, filt_y), filt_img)
            for (bx1, by1, bx2, by2, act) in filt_boxes:
                self.hud_hitboxes.append((filt_x + bx1, filt_y + by1, filt_x + bx2, filt_y + by2, act))
        except Exception:
            pass

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

    def _compute_floor_y(self, h: int, size: int) -> int:
        """Calcula la coordenada vertical del suelo de carátulas según modo y escala."""
        scale = getattr(self, "display_scale", 1.0)
        if self._is_vertical_stack_active():
            target_floor = int(round(h * 0.62))
            min_floor = size + int(round(56 * scale))
            max_floor = h - int(round(138 * scale))
            if min_floor > max_floor:
                return max(size + 10, (h + size) // 2)
            return max(min_floor, min(max_floor, target_floor))
        if self._use_reflection():
            refl_h = int(size * 0.38)
            target_floor = int(round(h * 0.63))
            min_floor = size + int(round(36 * scale))
            max_floor = h - refl_h - int(round(96 * scale))
            return max(min_floor, min(max_floor, target_floor))
        return (h + size) // 2

    def _draw_outgoing_shelf_3d(self, bg: Image.Image, w: int, floor_y: int, size: int, progress: float):
        """Dibuja el carrusel saliente rotando en 3D hacia arriba (al bajar) o hacia abajo (al subir)."""
        if progress <= 0.02 or not getattr(self, "_outgoing_covers_layer", None):
            return
        if self._outgoing_covers_layer.width != w:
            return

        trans_dir = getattr(self, "shelf_transition_dir", 0)
        body_crop = getattr(self, "_outgoing_body_crop", None)
        if trans_dir != 0 and body_crop is not None and getattr(self, "_outgoing_size", 0) == size:
            tilt_out = min(1.0, (1.0 - progress) ** 0.88)
            tilt_dir_out = -trans_dir
            alpha_out = max(0.0, min(1.0, progress ** 1.75))
            center_x_in_crop = (w / 2.0) - self._outgoing_body_x

            warped_out, mask_out, th_out = render_vertical_shelf_tilt(
                body_crop,
                tilt=tilt_out,
                tilt_dir=tilt_dir_out,
                center_x_in_crop=center_x_in_crop,
                alpha_scale=alpha_out,
                transparent_key_safe=getattr(self, "is_transparent_mode", False),
            )

            travel = (1.0 - progress) * self.shelf_distance * 0.90
            if tilt_dir_out < 0:
                y_bot_out = floor_y - int(round(travel))
                y_draw_out = y_bot_out - th_out
            else:
                y_draw_out = (floor_y - size) + int(round(travel))
                y_bot_out = y_draw_out + th_out

            refl_crop = getattr(self, "_outgoing_refl_crop", None)
            refl_mask = getattr(self, "_outgoing_refl_mask", None)
            if refl_crop is not None and refl_mask is not None and tilt_out < 0.34 and not getattr(self, "is_transparent_mode", False):
                refl_alpha = max(0.0, 1.0 - tilt_out * 3.0) * alpha_out
                if refl_alpha > 0.02:
                    bg.paste(refl_crop, (self._outgoing_body_x, y_bot_out), scale_alpha_mask(refl_mask, refl_alpha))

            bg.paste(warped_out, (self._outgoing_body_x, y_draw_out), mask_out)
            return

        # Fallback si cambió el tamaño de ventana durante la animación
        out_y = floor_y - size + int(round(self.shelf_offset_y - trans_dir * self.shelf_distance))
        if progress >= 0.98 or not self._outgoing_alpha_mask:
            bg.paste(self._outgoing_covers_layer, (0, out_y), self._outgoing_covers_layer)
        else:
            try:
                frame_mask = scale_alpha_mask(self._outgoing_alpha_mask, progress)
                bg.paste(self._outgoing_covers_layer, (0, out_y), frame_mask)
            except Exception:
                bg.paste(self._outgoing_covers_layer, (0, out_y), self._outgoing_covers_layer)

    def _get_incoming_shelf_crops(self, w: int, size: int) -> Tuple[Optional[Image.Image], int, Optional[Image.Image], Optional[Image.Image]]:
        """Construye y cachea la capa recortada de la estantería entrante durante la transición vertical."""
        has_refl = self._use_reflection()
        sig = (
            getattr(self, "_library_load_id", 0),
            getattr(self, "_cache_generation", 0),
            round(self.current_pos, 3),
            w,
            size,
            has_refl,
        )
        cached = getattr(self, "_incoming_shelf_cache", None)
        if cached is not None and cached[0] == sig:
            return cached[1], cached[2], cached[3], cached[4]

        tot_h = (int(size * 1.6) + 20) if has_refl else (size + 4)
        layer = self._compose_shelf_layer(w, tot_h)
        body_crop, bx1, refl_crop, refl_mask = self._extract_shelf_crops(layer, w, size)
        self._incoming_shelf_cache = (sig, body_crop, bx1, refl_crop, refl_mask)
        return body_crop, bx1, refl_crop, refl_mask

    def _blend_transition_bg(self, base_bg: Image.Image, w: int, h: int, progress: float) -> Image.Image:
        """Mezcla suavemente el fondo/wallpaper saliente con el entrante durante la transición."""
        prev_bg = getattr(self, "_outgoing_bg", None)
        if (
            not getattr(self, "is_transparent_mode", False)
            and prev_bg is not None
            and base_bg is not None
            and prev_bg.size == (w, h)
            and base_bg.size == (w, h)
            and progress > 0.008
        ):
            blend_t = max(0.0, min(1.0, (1.0 - progress) ** 0.9))
            return Image.blend(prev_bg, base_bg, blend_t)
        return base_bg.copy()

    def _present_frame(self, bg: Image.Image, w: int, h: int):
        """Actualiza el Tkinter Canvas reutilizando el DIB bitmap cuando las dimensiones no cambian."""
        if self.photo_ref is None or getattr(self, "_photo_w", 0) != w or getattr(self, "_photo_h", 0) != h:
            self._photo_w = w
            self._photo_h = h
            self.photo_ref = ImageTk.PhotoImage(bg)
            self.delete("all")
            self.canvas_img_id = self.create_image(0, 0, image=self.photo_ref, anchor="nw")
        else:
            self.photo_ref.paste(bg)

    def _draw_vertical_stack_frame(
        self,
        bg: Image.Image,
        w: int,
        h: int,
        floor_y: int,
        size: int,
        is_vertical_anim: bool,
        progress: float,
    ):
        """
        Renderiza la pila 3D vertical completa en Orden de Pintor (Z-order: fondo -> primer plano):
          - En reposo: dibuja -2, +2, -1, +1 en segundo plano cacheados (0 ms tilt), y al frente (s=0) nítido.
          - En transición vertical: desliza todas las estanterías de forma continua por el túnel 3D (s = rel + dir*progress).
        """
        n_shelves = len(self._shelf_stack)
        cur_idx = self._shelf_stack_idx
        if n_shelves <= 0:
            return

        if is_vertical_anim and progress > 0.008:
            trans_dir = getattr(self, "shelf_transition_dir", 0)
            dir_sign = 1 if trans_dir >= 0 else -1
            if n_shelves == 2:
                rels = [-dir_sign, 0]
            elif n_shelves in (3, 4):
                rels = [-2, -1, 0, 1] if dir_sign > 0 else [-1, 0, 1, 2]
            else:
                rels = [-3, -2, -1, 0, 1, 2] if dir_sign > 0 else [-2, -1, 0, 1, 2, 3]

            slots = [(rel, float(rel) + float(dir_sign) * progress) for rel in rels]
            slots.sort(key=lambda item: abs(item[1]), reverse=True)

            out_body = getattr(self, "_outgoing_body_crop", None)
            out_bx1 = getattr(self, "_outgoing_body_x", 0)
            out_override = (out_body, out_bx1) if (out_body is not None and getattr(self, "_outgoing_size", 0) == size) else None

            for rel, s in slots:
                sh = self._shelf_stack[(cur_idx + rel) % n_shelves]
                if rel == 0:
                    if not self.games:
                        continue
                    if abs(s) <= 0.012:
                        pos_y = floor_y - size
                        for i, pos_x, w_img, w_w in self._iter_visible_cover_slots(w, size):
                            bg.paste(w_img, (pos_x, pos_y), w_img)
                            self.hitboxes.append((pos_x, pos_y, pos_x + w_w, pos_y + size, i))
                    else:
                        in_body, in_bx1, _, _ = self._get_incoming_shelf_crops(w, size)
                        if in_body is None:
                            continue
                        slot_box = self._draw_stack_shelf_slot(
                            bg,
                            sh,
                            int(round(self.current_pos)),
                            s,
                            w,
                            h,
                            floor_y,
                            size,
                            full_body_override=(in_body, in_bx1),
                            is_resting=False,
                        )
                        if slot_box is not None:
                            _, y_draw_in, _, th_in = slot_box
                            for i, pos_x, _, w_w in self._iter_visible_cover_slots(w, size):
                                self.hitboxes.append((pos_x, y_draw_in, pos_x + w_w, y_draw_in + th_in, i))
                elif rel == -dir_sign:
                    t_idx = self._get_shelf_center_idx(sh)
                    self._draw_stack_shelf_slot(
                        bg,
                        sh,
                        t_idx,
                        s,
                        w,
                        h,
                        floor_y,
                        size,
                        full_body_override=out_override,
                        is_resting=False,
                    )
                else:
                    extra_a = max(0.0, min(1.0, 2.0 - abs(s))) if n_shelves in (3, 4) else 1.0
                    t_idx = self._get_shelf_center_idx(sh)
                    self._draw_stack_shelf_slot(
                        bg,
                        sh,
                        t_idx,
                        s,
                        w,
                        h,
                        floor_y,
                        size,
                        is_resting=False,
                        extra_alpha=extra_a,
                    )
            return

        # En reposo: primero pintar carruseles de fondo más lejanos (-2, +2, -1, +1) desde caché de warp
        for rel in sorted(self._get_visible_neighbor_offsets(), key=lambda r: abs(r), reverse=True):
            sh = self._shelf_stack[(cur_idx + rel) % n_shelves]
            t_idx = self._get_shelf_center_idx(sh)
            self._draw_stack_shelf_slot(
                bg,
                sh,
                t_idx,
                float(rel),
                w,
                h,
                floor_y,
                size,
                is_resting=True,
            )

        # Finalmente pintar el carrusel activo (s=0) al frente nítido y plano
        if self.games:
            pos_y = floor_y - size
            for i, pos_x, w_img, w_w in self._iter_visible_cover_slots(w, size):
                bg.paste(w_img, (pos_x, pos_y), w_img)
                self.hitboxes.append((pos_x, pos_y, pos_x + w_w, pos_y + size, i))

    def redraw(self, force_w: Optional[int] = None, force_h: Optional[int] = None):
        w = force_w or self.winfo_width()
        h = force_h or self.winfo_height()
        if (w < 50 or h < 50) and getattr(self, "last_w", 0) > 50:
            w = self.last_w
            h = self.last_h
        if w < 50 or h < 50:
            return
        self.last_w = w
        self.last_h = h

        size = self.base_size
        has_refl = self._use_reflection()
        is_stack = self._is_vertical_stack_active()
        is_vertical_anim = getattr(self, "is_shelf_animating", False) and getattr(self, "shelf_transition_dir", 0) != 0
        progress = max(0.0, min(1.0, abs(getattr(self, "shelf_offset_y", 0.0)) / max(1.0, float(getattr(self, "shelf_distance", 300)))))
        offset_y = int(round(getattr(self, "shelf_offset_y", 0.0)))

        n = len(self.games)
        if n == 0:
            self.hitboxes = []
            if is_stack and not getattr(self, "is_transparent_mode", False):
                if not self.bg_cache or self.bg_cache.size != (w, h):
                    self._rebuild_background(w, h)
                base_empty = self.bg_cache
            else:
                bg_col = (0, 0, 1) if getattr(self, "is_transparent_mode", False) else (12, 14, 19)
                base_empty = Image.new('RGB', (w, h), bg_col)
            bg = self._blend_transition_bg(base_empty, w, h, progress) if is_vertical_anim else base_empty.copy()
            floor_y = self._compute_floor_y(h, size)
            self.floor_y = floor_y
            if is_stack:
                self._draw_vertical_stack_frame(bg, w, h, floor_y, size, is_vertical_anim, progress)
            elif is_vertical_anim:
                self._draw_outgoing_shelf_3d(bg, w, floor_y, size, progress)
            draw = ImageDraw.Draw(bg)
            filt_lbl = getattr(self, "ui_filter_label", "Todos")
            if filt_lbl and filt_lbl.strip().lower() != "todos":
                msg = f"No hay juegos en la colección '{filt_lbl}'\nUsa ↑ / ↓ o LB / RB para cambiar de canal o añade juegos con (X)"
            else:
                msg = "No hay juegos en la biblioteca\nHaz clic en 'Opciones' arriba a la derecha para agregar o escanear juegos"
            msg_y = (floor_y - size // 2) if is_stack else ((h // 2) + (int(round(offset_y * 0.35)) if is_vertical_anim else 0))
            draw.text((w // 2, msg_y), msg, fill=(150, 160, 180), anchor='mm')
            self._draw_overlays(bg, w, h)
            self._present_frame(bg, w, h)
            return

        if not self.bg_cache or self.bg_cache.size != (w, h):
            self._rebuild_background(w, h)

        p = self.current_pos
        floor_y = self._compute_floor_y(h, size)
        self.hitboxes = []

        center_int = int(round(p))
        center_game = self.games[max(0, min(n - 1, center_int))] if n > 0 else None

        # Clonar fondo RGB ultra rápido (0.8 ms en 1080p; con crossfade suave entre estanterías)
        base_bg = self.get_background_for_game(center_game, w, h, floor_y) or self.bg_cache
        bg = self._blend_transition_bg(base_bg, w, h, progress) if is_vertical_anim else base_bg.copy()
        self.floor_y = floor_y

        if is_stack:
            self._draw_vertical_stack_frame(bg, w, h, floor_y, size, is_vertical_anim, progress)
        else:
            # 1. Capa de carátulas de la estantería saliente rotando 3D (modo fila única o mini transparente)
            if is_vertical_anim:
                self._draw_outgoing_shelf_3d(bg, w, floor_y, size, progress)

            # 2. Carrusel actual: en transición vertical rota en 3D hacia su posición; en reposo pinta directo
            drawn_vertical_3d = False
            if is_vertical_anim and progress > 0.008:
                in_body, in_bx1, in_refl, in_refl_mask = self._get_incoming_shelf_crops(w, size)
                if in_body is not None:
                    tilt_in = progress
                    tilt_dir_in = self.shelf_transition_dir
                    alpha_in = 0.05 + 0.95 * ((1.0 - progress) ** 0.90)
                    center_x_in_crop = (w / 2.0) - in_bx1

                    warped_in, mask_in, th_in = render_vertical_shelf_tilt(
                        in_body,
                        tilt=tilt_in,
                        tilt_dir=tilt_dir_in,
                        center_x_in_crop=center_x_in_crop,
                        alpha_scale=alpha_in,
                        transparent_key_safe=getattr(self, "is_transparent_mode", False),
                    )

                    if tilt_dir_in > 0:
                        y_draw_in = (floor_y - size) + offset_y
                        y_bot_in = y_draw_in + th_in
                    else:
                        y_bot_in = floor_y + offset_y
                        y_draw_in = y_bot_in - th_in

                    if has_refl and in_refl is not None and in_refl_mask is not None and tilt_in < 0.34:
                        refl_alpha_in = max(0.0, 1.0 - tilt_in * 3.0) * alpha_in
                        if refl_alpha_in > 0.02:
                            bg.paste(in_refl, (in_bx1, y_bot_in), scale_alpha_mask(in_refl_mask, refl_alpha_in))

                    bg.paste(warped_in, (in_bx1, y_draw_in), mask_in)
                    for i, pos_x, _, w_w in self._iter_visible_cover_slots(w, size):
                        self.hitboxes.append((pos_x, y_draw_in, pos_x + w_w, y_draw_in + th_in, i))
                    drawn_vertical_3d = True

            if not drawn_vertical_3d:
                pos_y = floor_y - size + offset_y
                for i, pos_x, w_img, w_w in self._iter_visible_cover_slots(w, size):
                    bg.paste(w_img, (pos_x, pos_y), w_img)
                    self.hitboxes.append((pos_x, pos_y, pos_x + w_w, pos_y + size, i))

        # 3.5. Superposición de HUD superior e inferior sin barras grises (RGBA transparente)
        self._draw_overlays(bg, w, h)

        # 4. Actualización eficiente de Tkinter Canvas (sin recrear DIB bitmaps de GDI)
        self._present_frame(bg, w, h)
