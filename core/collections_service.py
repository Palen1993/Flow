"""
GameFlow - Servicio de Colecciones, Estanterías Multi-Carrusel y Taxonomía de Géneros
======================================================================================
Módulo encargado de:
1. Gestionar las estanterías (shelves/canales) del dashboard de consola navegables verticalmente (↑ / ↓).
2. Taxonomía y canonización inteligente de géneros para evitar proliferación caótica de etiquetas.
3. Configuración persistente (collections_config.json) con orden personalizado y habilitación/deshabilitación.
4. Soporte para colecciones personalizadas por usuario asignables a juegos ("collections": [...]).
5. Filtro dinámico de juegos para cada estantería (Favoritos, Recientes, Plataformas, Géneros canónicos, etc.).
"""

import os
import re
import json
from typing import List, Dict, Any, Optional, Tuple

try:
    from core.config import get_storage_dir, save_json_atomic
    from core.logger import get_logger
    logger = get_logger("CollectionsService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.CollectionsService")

    def get_storage_dir() -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def save_json_atomic(filepath: str, data: Any):
        tmp = filepath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, filepath)


CONFIG_FILE = "collections_config.json"


# ==============================================================================
# TAXONOMÍA Y CANONIZACIÓN PROFESIONAL DE GÉNEROS
# ==============================================================================

CANONICAL_GENRES: List[Dict[str, Any]] = [
    {
        "id": "action",
        "name": "Acción y Aventura",
        "icon": "⚔️",
        "keywords": ["action", "acción", "adventure", "aventura", "hack", "slash", "beat", "stealth", "open world", "mundo abierto"]
    },
    {
        "id": "rpg",
        "name": "Rol (RPG)",
        "icon": "🛡️",
        "keywords": ["rpg", "role", "rol", "jrpg", "arpg", "souls", "roguelike", "rogue", "dungeon"]
    },
    {
        "id": "platformer",
        "name": "Plataformas y Metroidvania",
        "icon": "🍄",
        "keywords": ["platform", "plataforma", "plataformas", "metroidvania", "jump", "runner"]
    },
    {
        "id": "shooter",
        "name": "Shooter y Disparos",
        "icon": "🎯",
        "keywords": ["shooter", "fps", "tps", "disparos", "gun", "bullet", "shmup", "shoot"]
    },
    {
        "id": "strategy",
        "name": "Estrategia y Táctica",
        "icon": "♟️",
        "keywords": ["strategy", "estrategia", "tactic", "táctica", "tactics", "rts", "turn-based", "4x", "tower defense"]
    },
    {
        "id": "simulation",
        "name": "Simulación y Gestión",
        "icon": "🚜",
        "keywords": ["simulation", "simulación", "sim", "tycoon", "builder", "management", "gestión", "crafting", "survival"]
    },
    {
        "id": "racing_sports",
        "name": "Carreras y Deportes",
        "icon": "🏎️",
        "keywords": ["racing", "carreras", "driving", "conducción", "sports", "deportes", "football", "soccer", "fútbol", "basketball", "tennis"]
    },
    {
        "id": "fighting",
        "name": "Lucha y Combate",
        "icon": "🥊",
        "keywords": ["fighting", "lucha", "pelea", "versus", "combate", "brawler"]
    },
    {
        "id": "horror",
        "name": "Terror y Suspenso",
        "icon": "👻",
        "keywords": ["horror", "terror", "survival horror", "miedo", "zombie", "spooky"]
    },
    {
        "id": "puzzle_casual",
        "name": "Puzles y Casual",
        "icon": "🧩",
        "keywords": ["puzzle", "puzle", "rompecabezas", "casual", "cards", "cartas", "board", "mesa", "trivia", "logic", "visual novel"]
    }
]


def canonicalize_genre(raw_genre: Optional[str]) -> str:
    """
    Normaliza cualquier subgénero o etiqueta en una categoría canónica universal.
    Prioriza las palabras clave compuestas más específicas (ej: 'survival horror' antes de 'survival').
    """
    if not raw_genre or not str(raw_genre).strip():
        return "Otros"

    raw_lower = str(raw_genre).lower()
    best_match: Optional[str] = None
    best_kw_len = 0

    # 1. Búsqueda con delimitador de palabra completa (\b)
    for cat in CANONICAL_GENRES:
        for kw in cat["keywords"]:
            pattern = r'\b' + re.escape(kw.lower()) + r'\b'
            if re.search(pattern, raw_lower):
                if len(kw) > best_kw_len:
                    best_match = cat["name"]
                    best_kw_len = len(kw)

    if best_match:
        return best_match

    # 2. Búsqueda secundaria por subcadena
    for cat in CANONICAL_GENRES:
        for kw in cat["keywords"]:
            if kw.lower() in raw_lower:
                if len(kw) > best_kw_len:
                    best_match = cat["name"]
                    best_kw_len = len(kw)

    if best_match:
        return best_match

    cleaned = str(raw_genre).strip().capitalize()
    return cleaned if cleaned else "Otros"


# ==============================================================================
# CONFIGURACIÓN PREDETERMINADA DE ESTANTERÍAS (SHELVES)
# ==============================================================================

DEFAULT_SHELVES: List[Dict[str, Any]] = [
    {"id": "all", "type": "system", "name": "Todos los Juegos", "icon": "🎮", "enabled": True},
    {"id": "favorites", "type": "system", "name": "Favoritos", "icon": "⭐", "enabled": True},
    {"id": "recent", "type": "system", "name": "Jugados Recientemente", "icon": "⏱️", "enabled": True},
    {"id": "unplayed", "type": "system", "name": "Por Jugar", "icon": "🆕", "enabled": False},
    {"id": "status:Completado", "type": "system", "name": "Completados", "icon": "🏆", "enabled": False}
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "shelves": DEFAULT_SHELVES,
    "custom_collections": []
}


def _get_config_path() -> str:
    return os.path.join(get_storage_dir(), CONFIG_FILE)


def load_collections_config(filepath: Optional[str] = None) -> Dict[str, Any]:
    """Carga la configuración persistente de colecciones y estanterías del dashboard."""
    cfg_p = filepath or _get_config_path()
    if os.path.isfile(cfg_p):
        try:
            with open(cfg_p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    res = dict(DEFAULT_CONFIG)
                    res.update(data)
                    if "custom_lists" in data and "custom_collections" not in data:
                        res["custom_collections"] = [{"name": c} if isinstance(c, str) else c for c in data["custom_lists"]]
                    return res
        except Exception as e:
            logger.warning(f"Error cargando {cfg_p}: {e}")
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_collections_config(config: Dict[str, Any], filepath: Optional[str] = None) -> bool:
    """Guarda la configuración de estanterías y colecciones atómicamente."""
    cfg_p = filepath or _get_config_path()
    try:
        save_json_atomic(cfg_p, config)
        logger.info("Configuración de Colecciones y Estanterías guardada.")
        return True
    except Exception as e:
        logger.error(f"Error guardando {cfg_p}: {e}")
        return False


# ==============================================================================
# GESTIÓN Y FILTRADO DE ESTANTERÍAS DEL DASHBOARD
# ==============================================================================

def get_game_collections(game: Dict[str, Any]) -> List[str]:
    """Devuelve las listas personalizadas a las que pertenece un juego."""
    if not isinstance(game, dict):
        return []
    colls = game.get("collections", [])
    if isinstance(colls, list):
        return [str(c).strip() for c in colls if str(c).strip()]
    if isinstance(colls, str) and colls.strip():
        return [c.strip() for c in colls.split(",") if c.strip()]
    return []


def set_game_collections(game: Dict[str, Any], collections: List[str]) -> None:
    """Asigna las colecciones personalizadas a un juego."""
    if isinstance(game, dict):
        clean = [str(c).strip() for c in collections if str(c).strip()]
        # Eliminar duplicados preservando orden
        seen = set()
        deduped = []
        for c in clean:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        game["collections"] = deduped


def filter_games_by_shelf(shelf_id: str, all_games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filtra y ordena los juegos correspondientes a una estantería o lista.
    """
    if not all_games:
        return []

    s_id = str(shelf_id).strip()

    # 1. Todos los juegos
    if s_id == "all":
        return sorted(all_games, key=lambda g: (g.get("name") or "").lower())

    # 2. Favoritos
    if s_id == "favorites":
        return [g for g in all_games if bool(g.get("favorite", False))]

    # 3. Jugados recientemente (ordenados por fecha de última sesión o playtime / veces jugado)
    if s_id == "recent":
        with_last = [g for g in all_games if g.get("last_played")]
        with_last.sort(key=lambda g: str(g.get("last_played", "")), reverse=True)
        # Si hay pocos con fecha, añadir los que tienen tiempo jugado o play_count > 0
        if len(with_last) < 10:
            seen_paths = {g.get("path") or g.get("name") for g in with_last}
            by_time = [
                g for g in all_games
                if (g.get("path") or g.get("name")) not in seen_paths and (
                    int(g.get("playtime_minutes", 0) or 0) > 0 or
                    int(g.get("play_count", 0) or 0) > 0
                )
            ]
            by_time.sort(
                key=lambda g: (int(g.get("play_count", 0) or 0), int(g.get("playtime_minutes", 0) or 0)),
                reverse=True
            )
            with_last.extend(by_time)
        return with_last

    # 4. Por jugar (sin empezar o estado 'Por jugar')
    if s_id in ("unplayed", "status_backlog"):
        return [
            g for g in all_games
            if (g.get("status") or "Por jugar").strip().lower() == "por jugar" and
            int(g.get("playtime_minutes", 0) or 0) == 0 and
            int(g.get("play_count", 0) or 0) == 0
        ]

    # 5. Por estado
    if s_id in ("status:Completado", "status_completed") or s_id.startswith("status:"):
        st_target = "completado" if s_id == "status_completed" else s_id.split("status:", 1)[1].strip().lower()
        return [
            g for g in all_games
            if (g.get("status") or "").strip().lower() == st_target
        ]

    # 6. Por plataforma
    if s_id.startswith("platform:"):
        plat_target = s_id.split("platform:", 1)[1].strip().lower()
        return [
            g for g in all_games
            if (g.get("platform") or "PC").strip().lower() == plat_target
        ]

    # 7. Por género canónico
    if s_id.startswith("genre:"):
        gen_target = s_id.split("genre:", 1)[1].strip().lower()
        return [
            g for g in all_games
            if canonicalize_genre(g.get("genre")).lower() == gen_target or
            gen_target in canonicalize_genre(g.get("genre")).lower() or
            gen_target in (g.get("genre") or "").strip().lower()
        ]

    # 8. Colección personalizada
    # Puede ser "custom:nombre" o el ID directo
    coll_name = s_id[7:].strip() if s_id.startswith("custom:") else s_id
    res = []
    for g in all_games:
        colls = get_game_collections(g)
        if any(c.lower() == coll_name.lower() or c.lower() == s_id.lower() for c in colls):
            res.append(g)
    return res


def get_available_shelf_definitions(all_games: List[Dict[str, Any]], config_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Descubre todas las estanterías posibles basándose en la biblioteca actual y la configuración:
    - Estanterías de sistema predeterminadas.
    - Plataformas presentes en los juegos.
    - Géneros canónicos presentes en los juegos (con al menos 1 juego).
    - Colecciones personalizadas creadas por el usuario.
    """
    cfg = load_collections_config(filepath=config_path)
    existing_shelves_map = {s["id"]: s for s in cfg.get("shelves", [])}

    defs: List[Dict[str, Any]] = []

    # 1. Estanterías de Sistema
    sys_items = [
        {"id": "all", "type": "system", "name": "Todos los Juegos", "icon": "🎮"},
        {"id": "favorites", "type": "system", "name": "Favoritos", "icon": "⭐"},
        {"id": "recent", "type": "system", "name": "Jugados Recientemente", "icon": "⏱️"},
        {"id": "unplayed", "type": "system", "name": "Por Jugar", "icon": "🆕"},
        {"id": "status:Completado", "type": "system", "name": "Completados", "icon": "🏆"},
    ]
    for item in sys_items:
        s_id = item["id"]
        saved = existing_shelves_map.get(s_id, {})
        count = len(filter_games_by_shelf(s_id, all_games))
        defs.append({
            "id": s_id,
            "type": "system",
            "name": saved.get("name", item["name"]),
            "icon": saved.get("icon", item["icon"]),
            "enabled": saved.get("enabled", item["id"] in ("all", "favorites", "recent")),
            "count": count
        })

    # 2. Plataformas presentes
    plat_counts: Dict[str, int] = {}
    for g in all_games:
        p = (g.get("platform") or "PC").strip()
        if p:
            plat_counts[p] = plat_counts.get(p, 0) + 1

    for p, c in sorted(plat_counts.items(), key=lambda x: -x[1]):
        s_id = f"platform:{p}"
        saved = existing_shelves_map.get(s_id, {})
        defs.append({
            "id": s_id,
            "type": "platform",
            "name": saved.get("name", f"Plataforma: {p}"),
            "icon": saved.get("icon", "🕹️"),
            "enabled": saved.get("enabled", False),
            "count": c
        })

    # 3. Géneros canónicos presentes
    genre_counts: Dict[str, int] = {}
    for g in all_games:
        cg = canonicalize_genre(g.get("genre"))
        if cg and cg != "Otros":
            genre_counts[cg] = genre_counts.get(cg, 0) + 1

    for cg, c in sorted(genre_counts.items(), key=lambda x: -x[1]):
        s_id = f"genre:{cg}"
        saved = existing_shelves_map.get(s_id, {})
        # Buscar icono correspondiente
        icon = "🏷️"
        for cdef in CANONICAL_GENRES:
            if cdef["name"] == cg:
                icon = cdef["icon"]
                break
        defs.append({
            "id": s_id,
            "type": "genre",
            "name": saved.get("name", f"Género: {cg}"),
            "icon": saved.get("icon", icon),
            "enabled": saved.get("enabled", False),
            "count": c
        })

    # 4. Colecciones personalizadas del usuario
    custom_list = cfg.get("custom_collections", [])
    for citem in custom_list:
        c_id = citem.get("id") or f"custom:{citem.get('name', 'Lista')}"
        c_name = citem.get("name", "Lista Personalizada")
        c_icon = citem.get("icon", "📁")
        saved = existing_shelves_map.get(c_id, {})
        count = len(filter_games_by_shelf(c_id, all_games))
        defs.append({
            "id": c_id,
            "type": "custom",
            "name": saved.get("name", c_name),
            "icon": saved.get("icon", c_icon),
            "enabled": saved.get("enabled", True),
            "count": count
        })

    return defs


def get_active_shelves(all_games: List[Dict[str, Any]], config_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Devuelve la lista ordenada de estanterías habilitadas que se mostrarán en la pantalla principal.
    Garantiza que siempre haya al menos 1 estantería activa (por defecto 'all').
    """
    cfg = load_collections_config(filepath=config_path)
    saved_shelves = cfg.get("shelves", [])
    all_defs = {d["id"]: d for d in get_available_shelf_definitions(all_games, config_path=config_path)}

    active: List[Dict[str, Any]] = []

    # 1. Agregar en el orden guardado por el usuario
    seen_ids = set()
    for s in saved_shelves:
        s_id = s.get("id")
        if s_id and s.get("enabled", False) and s_id not in seen_ids:
            seen_ids.add(s_id)
            d = all_defs.get(s_id, {})
            games_for_s = filter_games_by_shelf(s_id, all_games)
            active.append({
                "id": s_id,
                "type": s.get("type", d.get("type", "system")),
                "name": s.get("name", d.get("name", s_id)),
                "icon": s.get("icon", d.get("icon", "🏷️")),
                "enabled": True,
                "count": len(games_for_s),
                "games": games_for_s
            })

    # Red de seguridad: si no hay ninguna habilitada, activar 'all'
    if not active:
        all_games_sorted = sorted(all_games, key=lambda g: (g.get("name") or "").lower())
        active.append({
            "id": "all",
            "type": "system",
            "name": "Todos los Juegos",
            "icon": "🎮",
            "enabled": True,
            "count": len(all_games_sorted),
            "games": all_games_sorted
        })

    return active


def update_shelf_order_and_enabled(updated_shelves: List[Dict[str, Any]]) -> bool:
    """
    Actualiza la lista ordenada de estanterías y su estado habilitado/deshabilitado.
    """
    cfg = load_collections_config()
    cfg["shelves"] = updated_shelves
    return save_collections_config(cfg)


def add_custom_collection(name: str, icon: str = "📁") -> Optional[str]:
    """Crea una nueva colección personalizada y la añade a la lista de estanterías habilitadas."""
    clean_name = str(name).strip()
    if not clean_name:
        return None

    cfg = load_collections_config()
    c_id = f"custom:{clean_name}"

    # Evitar duplicados
    for c in cfg.get("custom_collections", []):
        if c.get("id") == c_id or c.get("name", "").lower() == clean_name.lower():
            return c.get("id")

    if "custom_collections" not in cfg:
        cfg["custom_collections"] = []
    cfg["custom_collections"].append({
        "id": c_id,
        "name": clean_name,
        "icon": icon
    })

    # Añadir a estanterías como habilitada
    if "shelves" not in cfg:
        cfg["shelves"] = []
    cfg["shelves"].append({
        "id": c_id,
        "type": "custom",
        "name": clean_name,
        "icon": icon,
        "enabled": True
    })

    save_collections_config(cfg)
    return c_id


def delete_custom_collection(coll_id: str) -> bool:
    """Elimina una colección personalizada de la configuración."""
    cfg = load_collections_config()
    cfg["custom_collections"] = [c for c in cfg.get("custom_collections", []) if c.get("id") != coll_id]
    cfg["shelves"] = [s for s in cfg.get("shelves", []) if s.get("id") != coll_id]
    return save_collections_config(cfg)
