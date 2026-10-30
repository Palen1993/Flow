import os

canvas_path = "ui/coverflow_canvas.py"
with open(canvas_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Import get_cached_jewel_case
old_import = """from core.coverflow_engine import (
    create_procedural_album, create_jewel_case, prepare_flat_cover,
    render_cover_flow_from_flat, prevent_transparency_color_collision,
    compose_big_picture_wallpaper_bg
)"""

new_import = """from core.coverflow_engine import (
    create_procedural_album, create_jewel_case, prepare_flat_cover,
    render_cover_flow_from_flat, prevent_transparency_color_collision,
    compose_big_picture_wallpaper_bg, get_cached_jewel_case
)"""

assert old_import in content, "old_import not found"
content = content.replace(old_import, new_import, 1)

# 2. Add _get_or_create_jewel_case and update_game_cover before set_games
old_set_games_block = """    def update_game_wallpaper(self, g: Dict[str, Any]):
        \"\"\"Actualiza en caliente el wallpaper de un juego y refresca el escenario Big Picture.\"\"\"
        if not g:
            return
        key = self._get_key(g)
        self._load_wallpaper_for_game(g)
        # Invalidar caché de fondos para este juego
        to_remove = [k for k in self.wallpaper_bg_cache.keys() if k[0] == key]
        for k in to_remove:
            self.wallpaper_bg_cache.pop(k, None)
        self.redraw()

    def set_games(self, games: List[Dict[str, Any]], target_index: int = 0):
        self.games = games
        self.raw_jewels.clear()
        self.raw_wallpapers.clear()
        self.wallpaper_bg_cache.clear()
        self.flat_covers.clear()
        self.rendered_cache.clear()
        
        # Precargar carátulas y wallpapers liberando descriptores de archivo inmediatamente
        for g in self.games:
            cover_path = resolve_game_cover(g)
            try:
                with Image.open(cover_path) as raw_img:
                    loaded_img = raw_img.convert("RGBA")
            except Exception:
                loaded_img = create_procedural_album(g.get("name", "Juego"), size=380)
            key = self._get_key(g)
            self.raw_jewels[key] = create_jewel_case(loaded_img, name=g.get("name", ""), size=512)
            self._load_wallpaper_for_game(g)
            
        n = len(self.games)
        if n > 0:
            self.target_pos = float(max(0, min(n - 1, target_index)))
            self.current_pos = self.target_pos
        else:
            self.target_pos = 0.0
            self.current_pos = 0.0
            
        self._rebuild_rendered_cache()
        self.redraw()
        if self.on_selection_changed and n > 0:
            self.on_selection_changed(int(round(self.target_pos)))"""

new_set_games_block = """    def _get_or_create_jewel_case(self, g: Dict[str, Any]) -> Image.Image:
        \"\"\"Obtiene el jewel case desde la caché persistente en disco (.cache/jewels).\"\"\"
        cover_path = resolve_game_cover(g)
        return get_cached_jewel_case(cover_path, name=g.get("name", ""), size=512)

    def update_game_wallpaper(self, g: Dict[str, Any]):
        \"\"\"Actualiza en caliente el wallpaper de un juego y refresca el escenario Big Picture.\"\"\"
        if not g:
            return
        key = self._get_key(g)
        self._load_wallpaper_for_game(g)
        # Invalidar caché de fondos para este juego
        to_remove = [k for k in self.wallpaper_bg_cache.keys() if k[0] == key]
        for k in to_remove:
            self.wallpaper_bg_cache.pop(k, None)
        self.redraw()

    def update_game_cover(self, g: Dict[str, Any]):
        \"\"\"Actualiza la carátula de un único juego sin reconstruir toda la biblioteca (0 ms lag).\"\"\"
        if not g:
            return
        key = self._get_key(g)
        self.raw_jewels.pop(key, None)
        self.flat_covers.pop(key, None)
        self.rendered_cache.pop(key, None)

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
        self.raw_jewels.clear()
        self.raw_wallpapers.clear()
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
        # Fase 1: Carga inmediata y ultrarrápida del viewport visible (target +/- 3)
        visible_indices = set(range(max(0, target_int - 3), min(n, target_int + 4)))
        for idx in visible_indices:
            g = self.games[idx]
            key = self._get_key(g)
            self.raw_jewels[key] = self._get_or_create_jewel_case(g)
            self._load_wallpaper_for_game(g)

        self._rebuild_rendered_cache()
        self.redraw()
        if self.on_selection_changed and n > 0:
            self.on_selection_changed(target_int)

        # Fase 2: Carga perezosa (Lazy Loading) del resto de juegos en segundo plano
        remaining_indices = [i for i in range(n) if i not in visible_indices]
        if remaining_indices:
            def _bg_loader():
                for i in remaining_indices:
                    if i >= len(self.games):
                        break
                    g = self.games[i]
                    key = self._get_key(g)
                    if key not in self.raw_jewels:
                        self.raw_jewels[key] = self._get_or_create_jewel_case(g)
                    if key not in self.raw_wallpapers:
                        self._load_wallpaper_for_game(g)
                try:
                    self.after(0, self.redraw)
                except Exception:
                    pass
            threading.Thread(target=_bg_loader, daemon=True).start()"""

assert old_set_games_block in content, "old_set_games_block not found"
content = content.replace(old_set_games_block, new_set_games_block, 1)

# 3. LRU bounding in get_rendered_cover
old_get_rendered = """    def get_rendered_cover(self, game_key: str, af: float) -> Tuple[Optional[Image.Image], int]:
        \"\"\"Obtiene la carátula proyectada en 3D del caché o la calcula bajo demanda si aún no está lista.\"\"\"
        key = max(-1.0, min(1.0, round(af * 8.0) / 8.0))
        game_cache = self.rendered_cache.get(game_key)
        if game_cache is None:
            game_cache = {}
            self.rendered_cache[game_key] = game_cache
            
        cached = game_cache.get(key)
        if cached is not None:
            return cached
            
        flat_data = self.flat_covers.get(game_key)
        if not flat_data:
            return None, 0
            
        flat_cover, sz, _ = flat_data
        has_refl = not getattr(self, "is_transparent_mode", False)
        w_img, tw, _ = render_cover_flow_from_flat(flat_cover, sz, key, has_reflection=has_refl)
        w_img = prevent_transparency_color_collision(w_img)
        entry = (w_img, tw)
        game_cache[key] = entry
        return entry"""

new_get_rendered = """    def _prune_rendered_cache(self, max_games: int = 15):
        \"\"\"Política LRU: Acota la memoria eliminando los juegos más lejanos al índice visible.\"\"\"
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

    def get_rendered_cover(self, game_key: str, af: float) -> Tuple[Optional[Image.Image], int]:
        \"\"\"Obtiene la carátula proyectada en 3D del caché o la calcula bajo demanda con política LRU acotada.\"\"\"
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
        return entry"""

assert old_get_rendered in content, "old_get_rendered not found"
content = content.replace(old_get_rendered, new_get_rendered, 1)

with open(canvas_path, "w", encoding="utf-8") as f:
    f.write(content)

print("ui/coverflow_canvas.py successfully patched for Lazy Loading & LRU cache!")
