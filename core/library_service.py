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

    @property
    def file_mtime(self) -> float:
        return self._file_mtime

    def load(self) -> List[Dict[str, Any]]:
        """Carga la colección completa de juegos resolviendo carátulas y registrando mtime."""
        loaded = load_games_data()
        for g in loaded:
            resolve_game_cover(g)
        self.games = loaded
        self._file_mtime = get_games_file_mtime()
        logger.info(f"Biblioteca cargada con {len(self.games)} juego(s) (mtime={self._file_mtime:.2f})")
        return self.games

    def save(self) -> None:
        """Serializa atómicamente la colección a games.json y actualiza el timestamp de control."""
        save_games_data(self.games)
        self._file_mtime = get_games_file_mtime()
        logger.debug(f"Biblioteca guardada atómicamente ({len(self.games)} juegos)")

    def refresh_if_modified(self) -> bool:
        """
        Comprueba si games.json ha sido modificado externamente (por el centinela o sincronización).
        Si es así, recarga y actualiza metadatos (playtime, last_played) sin perder la referencia en memoria.
        """
        try:
            current_mtime = get_games_file_mtime()
            if current_mtime <= self._file_mtime:
                return False

            fresh_games = load_games_data()
            if not fresh_games:
                return False

            self._file_mtime = current_mtime
            fresh_by_path: Dict[str, Dict[str, Any]] = {}
            fresh_by_name: Dict[str, Dict[str, Any]] = {}
            for fg in fresh_games:
                resolve_game_cover(fg)
                p = fg.get("path")
                if p:
                    fresh_by_path[os.path.normcase(os.path.normpath(p))] = fg
                n = fg.get("name", "").strip().lower()
                if n:
                    fresh_by_name[n] = fg

            for g in self.games:
                gp = g.get("path")
                norm_p = os.path.normcase(os.path.normpath(gp)) if gp else ""
                fg = fresh_by_path.get(norm_p) or fresh_by_name.get(g.get("name", "").strip().lower())
                if fg:
                    g["playtime_minutes"] = fg.get("playtime_minutes", g.get("playtime_minutes", 0))
                    g["last_played"] = fg.get("last_played", g.get("last_played"))

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
        launch_args: str = ""
    ) -> int:
        """Añade un nuevo juego a la colección y persiste en disco. Devuelve el índice del nuevo juego."""
        new_game = {
            "name": name,
            "path": path,
            "monitor": monitor,
            "high_priority": high_priority,
            "cover": cover
        }
        if launch_args:
            new_game["launch_args"] = launch_args
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
        launch_args: str = ""
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
            self.games[index] = existing
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

    def format_subtitle(self, game: Dict[str, Any], monitors: Optional[List[Dict[str, Any]]] = None) -> str:
        """Genera el texto de subtítulo con monitor asignado, horas jugadas y última sesión."""
        mon_idx = int(game.get("monitor", 0) or 0)
        parts = [format_monitor_label(mon_idx, monitors)]
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
        char: str = ""
    ) -> Optional[int]:
        """Calcula el siguiente índice de salto alfabético (por letra o por gatillo LT/RT)."""
        n = len(self.games)
        if n == 0:
            return None

        if direction != 0:
            cur_name = (self.games[current_index].get("name") or "").strip().lower()
            cur_initial = cur_name[0] if cur_name else ""
            step = 1 if direction > 0 else -1
            for offset in range(1, n):
                idx = (current_index + offset * step) % n
                cand_name = (self.games[idx].get("name") or "").strip().lower()
                cand_initial = cand_name[0] if cand_name else ""
                if cand_initial != cur_initial:
                    return idx
            return None

        if char and len(char) == 1 and char.isalnum():
            ch = char.lower()
            start = (current_index + 1) % n
            for offset in range(n):
                idx = (start + offset) % n
                g_name = (self.games[idx].get("name") or "").strip().lower()
                if g_name.startswith(ch):
                    return idx
        return None
