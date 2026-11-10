import os
from typing import List, Dict, Any, Optional

from core.config import load_games_data, save_games_data, get_games_file_mtime
from core.cover_resolver import resolve_game_cover
from core.system import get_monitors
from core.logger import get_logger

logger = get_logger("LibraryService")


def format_monitor_label(mon_idx: int, monitors: Optional[List[Dict[str, Any]]] = None) -> str:
    """Devuelve el texto formateado del monitor (ej: 'Monitor 2 - SAMSUNG (1920x1080)')."""
    if not monitors:
        try:
            monitors = get_monitors()
        except Exception:
            monitors = []
    matched = None
    for m in (monitors or []):
        if m.get("id") == mon_idx:
            matched = m
            break
    if matched is None and monitors and 0 <= mon_idx < len(monitors):
        matched = monitors[mon_idx]
    if matched:
        rect = matched.get("rect", (0, 0, 1920, 1080))
        mw = rect[2] - rect[0]
        mh = rect[3] - rect[1]
        return f"🖥 Monitor {matched['id']} - {matched['name']} ({mw}x{mh})"
    return f"🖥 Monitor {mon_idx} - Predeterminado"


class GameLibraryService:
    """
    Servicio desacoplado responsable exclusivamente de la gestión, ordenamiento,
    filtrado, persistencia y sincronización reactiva de la biblioteca de juegos (games.json).
    """

    def __init__(self):
        self.games: List[Dict[str, Any]] = []
        self._file_mtime: float = 0.0
        self._filter_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._alpha_jump_cache: Dict[str, Dict[str, int]] = {}

    @property
    def file_mtime(self) -> float:
        return self._file_mtime

    def invalidate_caches(self) -> None:
        """Invalida las cachés en memoria de filtros calculados e índices alfabéticos."""
        self._filter_cache.clear()
        self._alpha_jump_cache.clear()

    def load(self, eager_covers: bool = False) -> List[Dict[str, Any]]:
        """
        Carga la colección completa de juegos con verificación diferida (lazy) de carátulas para arranque instantáneo (<5ms).
        En modo diferido (por defecto), solo valida carátulas ya existentes en disco sin rastrear carpetas profundamente.
        """
        self.invalidate_caches()
        loaded = load_games_data()
        from core.config import COVERS_DIR
        for g in loaded:
            if eager_covers:
                resolve_game_cover(g)
            else:
                cov = g.get("cover")
                if not cov or not os.path.isfile(cov):
                    # Comprobar rápido si la carátula estándar ya existe en covers/ sin escaneo recursivo
                    safe_name = "".join(c for c in g.get("name", "game") if c.isalnum() or c in (' ', '_', '-')).strip() or "game"
                    cand = os.path.join(COVERS_DIR, f"{safe_name}.png")
                    if os.path.isfile(cand):
                        g["cover"] = cand

        self.games = loaded
        self._file_mtime = get_games_file_mtime()
        logger.info(f"Biblioteca cargada con {len(self.games)} juego(s) (mtime={self._file_mtime:.2f})")
        return self.games

    def save(self) -> None:
        """Serializa atómicamente la colección a games.json y actualiza el timestamp de control."""
        self.invalidate_caches()
        save_games_data(self.games)
        self._file_mtime = get_games_file_mtime()
        logger.debug(f"Biblioteca guardada atómicamente ({len(self.games)} juegos)")

    def refresh_if_modified(self) -> bool:
        """
        Comprueba si games.json ha sido modificado externamente (por el centinela o sincronización).
        Si es así, recarga y actualiza metadatos (playtime, last_played, arte y colección) preservando referencias existentes.
        """
        try:
            current_mtime = get_games_file_mtime()
            if current_mtime <= self._file_mtime:
                return False

            self._file_mtime = current_mtime
            self.invalidate_caches()
            fresh_games = load_games_data()
            if not fresh_games:
                if self.games:
                    self.games.clear()
                    return True
                return False

            from core.config import COVERS_DIR
            fresh_by_path: Dict[str, Dict[str, Any]] = {}
            fresh_by_name: Dict[str, Dict[str, Any]] = {}
            for fg in fresh_games:
                cov = fg.get("cover")
                if not cov or not os.path.isfile(cov):
                    safe_name = "".join(c for c in fg.get("name", "game") if c.isalnum() or c in (' ', '_', '-')).strip() or "game"
                    cand = os.path.join(COVERS_DIR, f"{safe_name}.png")
                    if os.path.isfile(cand):
                        fg["cover"] = cand
                p = fg.get("path")
                if p:
                    fresh_by_path[os.path.normcase(os.path.normpath(p))] = fg
                n = fg.get("name", "").strip().lower()
                if n:
                    fresh_by_name[n] = fg

            # Actualizar en el lugar los juegos que ya están en memoria
            existing_keys = set()
            for g in self.games:
                gp = g.get("path")
                norm_p = os.path.normcase(os.path.normpath(gp)) if gp else ""
                fg = fresh_by_path.get(norm_p) or fresh_by_name.get(g.get("name", "").strip().lower())
                if fg:
                    existing_keys.add(norm_p or g.get("name", "").strip().lower())
                    g["playtime_minutes"] = fg.get("playtime_minutes", g.get("playtime_minutes", 0))
                    g["last_played"] = fg.get("last_played", g.get("last_played"))
                    for field in (
                        "cover", "wallpaper", "wallpaper_opacity", "wallpaper_blur",
                        "monitor", "high_priority", "launch_args",
                        "favorite", "status", "genre", "platform"
                    ):
                        if field in fg:
                            g[field] = fg[field]

            # Si se añadieron o eliminaron juegos externamente, sincronizar la lista
            if len(fresh_games) != len(self.games) or len(existing_keys) != len(self.games):
                self.games[:] = fresh_games

            logger.info("Metadatos de biblioteca sincronizados con éxito desde el disco")
            return True
        except Exception as e:
            logger.error(f"Error sincronizando biblioteca desde disco: {e}", exc_info=True)
            return False

    def add_game(
        self,
        name: str,
        path: str,
        monitor: int,
        high_priority: bool,
        cover: str,
        launch_args: str = "",
        wallpaper: Optional[str] = None,
        wallpaper_opacity: Optional[float] = None,
        wallpaper_blur: Optional[float] = None,
        favorite: bool = False,
        status: str = "Por jugar",
        genre: str = "",
        platform: str = "PC"
    ) -> int:
        """Añade un nuevo juego a la colección y persiste en disco. Devuelve el índice del nuevo juego."""
        new_game = {
            "name": name,
            "path": path,
            "monitor": monitor,
            "high_priority": high_priority,
            "cover": cover,
            "favorite": bool(favorite),
            "status": status or "Por jugar",
            "genre": genre or "",
            "platform": platform or "PC"
        }
        if launch_args:
            new_game["launch_args"] = launch_args
        if wallpaper:
            new_game["wallpaper"] = wallpaper
        if wallpaper_opacity is not None:
            new_game["wallpaper_opacity"] = round(float(wallpaper_opacity), 2)
        if wallpaper_blur is not None:
            new_game["wallpaper_blur"] = round(float(wallpaper_blur), 1)
        self.games.append(new_game)
        self.save()
        return len(self.games) - 1

    def update_game(
        self,
        index: int,
        name: str,
        path: str,
        monitor: int,
        high_priority: bool,
        cover: str,
        launch_args: str = "",
        wallpaper: Optional[str] = None,
        wallpaper_opacity: Optional[float] = None,
        wallpaper_blur: Optional[float] = None,
        favorite: Optional[bool] = None,
        status: Optional[str] = None,
        genre: Optional[str] = None,
        platform: Optional[str] = None
    ) -> bool:
        """Actualiza los metadatos de un juego existente y guarda en disco."""
        if 0 <= index < len(self.games):
            existing = dict(self.games[index])
            existing.update({
                "name": name,
                "path": path,
                "monitor": monitor,
                "high_priority": high_priority,
                "cover": cover,
                "launch_args": launch_args
            })
            if wallpaper is not None:
                if wallpaper:
                    existing["wallpaper"] = wallpaper
                else:
                    existing.pop("wallpaper", None)
            if wallpaper_opacity is not None:
                existing["wallpaper_opacity"] = round(float(wallpaper_opacity), 2)
            if wallpaper_blur is not None:
                existing["wallpaper_blur"] = round(float(wallpaper_blur), 1)
            if favorite is not None:
                existing["favorite"] = bool(favorite)
            if status is not None:
                existing["status"] = status
            if genre is not None:
                existing["genre"] = genre
            if platform is not None:
                existing["platform"] = platform
            self.games[index] = existing
            self.save()
            return True
        return False

    def toggle_favorite(self, index: int) -> bool:
        """Alterna el estado favorito de un juego y persiste en disco. Devuelve el nuevo estado."""
        if 0 <= index < len(self.games):
            cur = bool(self.games[index].get("favorite", False))
            self.games[index]["favorite"] = not cur
            self.save()
            return not cur
        return False

    def set_game_status(self, index: int, status: str) -> bool:
        """Establece el estado de un juego ('Por jugar', 'Jugando', 'Completado', 'Abandonado') y persiste."""
        if 0 <= index < len(self.games):
            self.games[index]["status"] = status
            self.save()
            return True
        return False

    def delete_game(self, index: int) -> int:
        """Elimina el juego en la posición indicada y guarda en disco. Devuelve el nuevo índice recomendado."""
        if 0 <= index < len(self.games):
            self.games.pop(index)
            self.save()
            return max(0, min(len(self.games) - 1, index))
        return 0

    def get_available_filters(self) -> List[Dict[str, Any]]:
        """
        Calcula dinámicamente la lista de colecciones y filtros disponibles con conteo de juegos:
        - Todos
        - Favoritos
        - Por Jugar, Jugando, Completados
        - Plataformas presentes en la biblioteca (Steam, Epic, GOG, PC...)
        - Géneros presentes en la biblioteca (Acción, RPG, etc.)
        """
        filters: List[Dict[str, Any]] = []
        total = len(self.games)
        fav_count = sum(1 for g in self.games if g.get("favorite", False))
        pj_count = sum(1 for g in self.games if (g.get("status") or "Por jugar").strip().lower() == "por jugar")
        jg_count = sum(1 for g in self.games if (g.get("status") or "").strip().lower() == "jugando")
        comp_count = sum(1 for g in self.games if (g.get("status") or "").strip().lower() in ("completado", "completados"))
        aband_count = sum(1 for g in self.games if (g.get("status") or "").strip().lower() in ("abandonado", "abandonados"))

        filters.append({"id": "all", "label": "Todos", "icon": "🎮", "category": "general", "count": total})
        filters.append({"id": "favorite", "label": "Favoritos", "icon": "⭐", "category": "favorite", "count": fav_count})
        filters.append({"id": "status:Por jugar", "label": "Por Jugar", "icon": "⏳", "category": "status", "count": pj_count})
        if jg_count > 0:
            filters.append({"id": "status:Jugando", "label": "Jugando", "icon": "🔥", "category": "status", "count": jg_count})
        filters.append({"id": "status:Completado", "label": "Completados", "icon": "🏆", "category": "status", "count": comp_count})
        if aband_count > 0:
            filters.append({"id": "status:Abandonado", "label": "Abandonados", "icon": "💤", "category": "status", "count": aband_count})

        # Plataformas presentes (Steam, Epic Games, GOG, PC, Emuladores...)
        platforms: Dict[str, int] = {}
        for g in self.games:
            p = (g.get("platform") or "PC").strip()
            if p:
                platforms[p] = platforms.get(p, 0) + 1
        for p, count in sorted(platforms.items(), key=lambda x: -x[1]):
            if count > 0:
                filters.append({"id": f"platform:{p}", "label": p, "icon": "🕹️", "category": "platform", "count": count})

        # Géneros presentes (separados por comas si hay varios)
        genres: Dict[str, int] = {}
        for g in self.games:
            raw_gen = g.get("genre") or ""
            for piece in raw_gen.replace("/", ",").split(","):
                piece_clean = piece.strip()
                if piece_clean:
                    genres[piece_clean] = genres.get(piece_clean, 0) + 1
        for gen, count in sorted(genres.items(), key=lambda x: -x[1]):
            if count > 0:
                filters.append({"id": f"genre:{gen}", "label": gen, "icon": "🏷️", "category": "genre", "count": count})

        return filters

    def filter_games(
        self,
        filter_id: str,
        games_source: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filtra la lista de juegos según el identificador de filtro indicado con memoización en memoria:
        - 'all': todos los juegos
        - 'favorite': únicamente los marcados como favoritos
        - 'status:<val>': coincide con el estado
        - 'platform:<val>': coincide con la plataforma
        - 'genre:<val>': coincide con el género
        """
        is_default_source = (games_source is None)
        if is_default_source and filter_id in self._filter_cache:
            return list(self._filter_cache[filter_id])

        source = self.games if is_default_source else games_source
        if not filter_id or filter_id == "all":
            res = list(source)
        elif filter_id == "favorite":
            res = [g for g in source if bool(g.get("favorite", False))]
        elif filter_id.startswith("status:"):
            target_st = filter_id.split("status:", 1)[1].strip().lower()
            res = [
                g for g in source
                if (g.get("status") or "Por jugar").strip().lower() == target_st
            ]
        elif filter_id.startswith("platform:"):
            target_plat = filter_id.split("platform:", 1)[1].strip().lower()
            res = [
                g for g in source
                if (g.get("platform") or "PC").strip().lower() == target_plat
            ]
        elif filter_id.startswith("genre:"):
            target_gen = filter_id.split("genre:", 1)[1].strip().lower()
            res = [
                g for g in source
                if target_gen in (g.get("genre") or "").strip().lower()
            ]
        else:
            res = list(source)

        if is_default_source:
            self._filter_cache[filter_id] = res
        return list(res)

    def format_subtitle(self, game: Dict[str, Any], monitors: Optional[List[Dict[str, Any]]] = None) -> str:
        """Genera el texto de subtítulo con monitor, estado/favorito, plataforma/género y tiempo jugado."""
        mon_idx = int(game.get("monitor", 0) or 0)
        parts = [format_monitor_label(mon_idx, monitors)]

        # Estado y Favorito
        if bool(game.get("favorite", False)):
            parts.append("★ Favorito")
        st = (game.get("status") or "").strip()
        if st and st.lower() != "por jugar":
            parts.append(st)
        plat = (game.get("platform") or "").strip()
        if plat and plat != "PC":
            parts.append(plat)
        gen = (game.get("genre") or "").strip()
        if gen:
            parts.append(gen)

        mins = int(game.get("playtime_minutes", 0) or 0)
        if mins >= 60:
            hours = mins / 60.0
            parts.append(f"⏱ {hours:.1f} h jugadas")
        elif mins > 0:
            parts.append(f"⏱ {mins} min jugados")
        last_p = game.get("last_played")
        if last_p:
            parts.append(f"Última sesión: {last_p.split(' ')[0]}")
        return "   •   ".join(parts)

    def find_alphabetical_jump(
        self,
        current_index: int,
        direction: int = 0,
        char: str = "",
        games_list: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[int]:
        """Calcula el siguiente índice de salto alfabético sobre la lista activa optimizado con tabla memoizada."""
        games = self.games if games_list is None else games_list
        n = len(games)
        if n == 0:
            return None

        if direction != 0:
            cur_name = (games[current_index].get("name") or "").strip().lower() if 0 <= current_index < n else ""
            cur_initial = cur_name[0] if cur_name else ""
            step = 1 if direction > 0 else -1
            for offset in range(1, n):
                idx = (current_index + offset * step) % n
                cand_name = (games[idx].get("name") or "").strip().lower()
                cand_initial = cand_name[0] if cand_name else ""
                if cand_initial != cur_initial:
                    return idx
            return None

        if char and len(char) == 1 and char.isalnum():
            ch = char.lower()
            cache_key = f"{id(games)}:{n}"
            if cache_key not in self._alpha_jump_cache:
                first_letter_map = {}
                for i, g in enumerate(games):
                    nm = (g.get("name") or "").strip().lower()
                    if nm and nm[0] not in first_letter_map:
                        first_letter_map[nm[0]] = i
                self._alpha_jump_cache[cache_key] = first_letter_map

            letter_map = self._alpha_jump_cache.get(cache_key, {})
            if ch in letter_map:
                target = letter_map[ch]
                if target != current_index:
                    return target

            start = (current_index + 1) % n if 0 <= current_index < n else 0
            for offset in range(n):
                idx = (start + offset) % n
                g_name = (games[idx].get("name") or "").strip().lower()
                if g_name.startswith(ch):
                    return idx
        return None

    def resolve_missing_covers_async(self, on_cover_resolved=None) -> None:
        """Resuelve en segundo plano carátulas para juegos que carecen de arte sin bloquear la interfaz."""
        import threading
        def _worker():
            for g in list(self.games):
                cov = g.get("cover")
                if not cov or not os.path.isfile(cov):
                    new_cov = resolve_game_cover(g)
                    if new_cov and os.path.isfile(new_cov):
                        g["cover"] = new_cov
                        if on_cover_resolved:
                            try:
                                on_cover_resolved(g)
                            except Exception:
                                pass
        threading.Thread(target=_worker, daemon=True).start()
