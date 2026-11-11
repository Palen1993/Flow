"""
GameFlow - Servicio de Logros e Integración con Steam API y RetroAchievements
=============================================================================
Módulo que proporciona:
1. Detección automática de perfil y SteamID64 en instalaciones locales de Windows.
2. Detección inteligente de Steam AppID y vinculación con RetroAchievements GameID.
3. Consulta de logros oficiales de Steam (vía Steam Web API o Steam Community XML público)
   con nombres localizados, descripciones, rareza global (%) e iconos oficiales.
4. Consulta de logros de RetroAchievements (vía API REST oficial) con puntuación,
   badges desbloqueados/bloqueados y fechas de obtención.
5. Caché persistente offline (achievements_cache.json) con TTL para visualización
   instantánea sin latencia de red.
6. Fallback elegante a metas y logros personales cuando el juego no esté vinculado a APIs.
"""

import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

try:
    from core.config import get_storage_dir, save_json_atomic, sanitize_game_filename
    from core.platform_layer import is_windows, winreg
    from core.logger import get_logger
    logger = get_logger("AchievementsService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.AchievementsService")

    def get_storage_dir() -> str:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def save_json_atomic(filepath: str, data: Any):
        tmp = filepath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, filepath)

    def sanitize_game_filename(name: str) -> str:
        return re.sub(r'[\\/*?:"<>|]', "_", name).strip()

    is_windows = (sys.platform == "win32")
    winreg = None


CONFIG_FILE = "achievements_config.json"
CACHE_FILE = "achievements_cache.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "steam_api_key": "",
    "steam_id64": "",
    "steam_persona_name": "",
    "retroachievements_username": "",
    "retroachievements_api_key": "",
    "cache_ttl_hours": 12,
    "auto_fetch_on_select": True
}


def _get_config_path() -> str:
    return os.path.join(get_storage_dir(), CONFIG_FILE)


def _get_cache_path() -> str:
    return os.path.join(get_storage_dir(), CACHE_FILE)


def load_achievements_config() -> Dict[str, Any]:
    """Carga la configuración persistente de credenciales de logros."""
    cfg_path = _get_config_path()
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = dict(DEFAULT_CONFIG)
                    merged.update(data)
                    return merged
        except Exception as e:
            logger.warning(f"Error cargando {CONFIG_FILE}: {e}")
    return dict(DEFAULT_CONFIG)


def save_achievements_config(config: Dict[str, Any]) -> bool:
    """Guarda la configuración de credenciales de logros de forma atómica."""
    cfg_path = _get_config_path()
    try:
        save_json_atomic(cfg_path, config)
        logger.info("Configuración de Achievements guardada correctamente.")
        return True
    except Exception as e:
        logger.error(f"Error guardando {CONFIG_FILE}: {e}")
        return False


def _load_cache() -> Dict[str, Any]:
    cache_path = _get_cache_path()
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            logger.debug(f"Error leyendo {CACHE_FILE}: {e}")
    return {}


def _save_cache(cache_data: Dict[str, Any]):
    cache_path = _get_cache_path()
    try:
        save_json_atomic(cache_path, cache_data)
    except Exception as e:
        logger.debug(f"Error guardando caché de logros: {e}")


# ==============================================================================
# DETECCIÓN DE PERFIL STEAM EN WINDOWS
# ==============================================================================

def detect_local_steam_profile() -> Dict[str, str]:
    """
    Escanea la instalación local de Steam para autodetectar el SteamID64 y el PersonaName
    del usuario más recientemente activo a través de loginusers.vdf o carpetas de userdata.
    """
    res = {
        "steam_path": "",
        "steam_id64": "",
        "persona_name": "",
        "account_name": ""
    }

    steam_path = None
    if is_windows and winreg:
        for root_key, subkey in [
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam")
        ]:
            try:
                with winreg.OpenKey(root_key, subkey) as k:
                    for val_name in ["SteamPath", "InstallPath"]:
                        try:
                            p, _ = winreg.QueryValueEx(k, val_name)
                            if p and os.path.isdir(p):
                                steam_path = os.path.normpath(p)
                                break
                        except Exception:
                            pass
                if steam_path:
                    break
            except Exception:
                pass

    if not steam_path:
        for cand in [
            r"C:\Program Files (x86)\Steam",
            r"C:\Program Files\Steam",
            os.path.expanduser("~/.steam/steam"),
            os.path.expanduser("~/.local/share/Steam")
        ]:
            if os.path.isdir(cand):
                steam_path = cand
                break

    if not steam_path:
        return res

    res["steam_path"] = steam_path

    # 1. Analizar loginusers.vdf (en Steam/config/loginusers.vdf)
    loginusers_path = os.path.join(steam_path, "config", "loginusers.vdf")
    if os.path.isfile(loginusers_path):
        try:
            with open(loginusers_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Buscar bloques con "7656119..." y "mostrecent" "1"
            user_blocks = re.findall(r'"(7656119\d{10})"\s*\{([^}]+)\}', content, re.DOTALL)
            best_id = ""
            best_persona = ""
            best_account = ""

            for uid, block in user_blocks:
                is_recent = bool(re.search(r'"MostRecent"\s+"1"', block, re.IGNORECASE))
                pers_m = re.search(r'"PersonaName"\s+"([^"]+)"', block, re.IGNORECASE)
                acc_m = re.search(r'"AccountName"\s+"([^"]+)"', block, re.IGNORECASE)
                pers_name = pers_m.group(1) if pers_m else ""
                acc_name = acc_m.group(1) if acc_m else ""

                if is_recent or not best_id:
                    best_id = uid
                    best_persona = pers_name
                    best_account = acc_name
                    if is_recent:
                        break

            if best_id:
                res["steam_id64"] = best_id
                res["persona_name"] = best_persona
                res["account_name"] = best_account
                return res
        except Exception as e:
            logger.debug(f"Error analizando loginusers.vdf: {e}")

    # 2. Alternativa: buscar en userdata/{account_id_32}
    userdata_dir = os.path.join(steam_path, "userdata")
    if os.path.isdir(userdata_dir):
        try:
            subdirs = [d for d in os.listdir(userdata_dir) if d.isdigit() and int(d) > 0]
            if subdirs:
                # Tomar la carpeta con mtime más reciente
                subdirs.sort(
                    key=lambda d: os.path.getmtime(os.path.join(userdata_dir, d)),
                    reverse=True
                )
                account_id_32 = int(subdirs[0])
                # Convertir AccountID32 a SteamID64: ID64 = ID32 + 76561197960265728
                steam_id64 = str(account_id_32 + 76561197960265728)
                res["steam_id64"] = steam_id64
        except Exception as e:
            logger.debug(f"Error analizando userdata: {e}")

    return res


# ==============================================================================
# DETECCIÓN DE STEAM APPID Y RETROACHIEVEMENTS GAMEID EN JUEGOS
# ==============================================================================

def detect_game_steam_appid(game: Dict[str, Any]) -> Optional[str]:
    """
    Detecta el AppID de Steam asociado a un juego a partir de sus metadatos,
    rutas o manifiestos appmanifest_*.acf de la biblioteca de Steam.
    """
    if not isinstance(game, dict):
        return None

    # 1. Si ya tiene el campo explícito
    if game.get("steam_appid"):
        val = str(game["steam_appid"]).strip()
        if val.isdigit():
            return val

    # 2. Si es de plataforma Steam y platform_id es numérico
    if str(game.get("platform", "")).lower() == "steam":
        pid = str(game.get("platform_id", "")).strip()
        if pid.isdigit():
            return pid

    # 3. Argumentos o ruta con steam://rungameid/<id>
    for field in [game.get("path", ""), game.get("launch_args", "")]:
        if field and "steam://run" in field:
            m = re.search(r'rungameid/(\d+)', field)
            if m:
                return m.group(1)

    # 4. Si la ruta está dentro de steamapps/common/<nombre_carpeta>
    path = game.get("path", "")
    if path and "steamapps" in path.lower():
        try:
            norm = os.path.normpath(path)
            parts = norm.split(os.sep)
            # Buscar el índice de steamapps
            lower_parts = [p.lower() for p in parts]
            if "steamapps" in lower_parts:
                s_idx = lower_parts.index("steamapps")
                steamapps_dir = os.sep.join(parts[:s_idx + 1])
                # Si estamos dentro de steamapps/common/<installdir>
                if s_idx + 2 < len(parts) and lower_parts[s_idx + 1] == "common":
                    installdir = parts[s_idx + 2].lower()
                    # Buscar en steamapps_dir los appmanifest_*.acf
                    if os.path.isdir(steamapps_dir):
                        for f in os.listdir(steamapps_dir):
                            if f.startswith("appmanifest_") and f.endswith(".acf"):
                                try:
                                    acf_p = os.path.join(steamapps_dir, f)
                                    with open(acf_p, "r", encoding="utf-8", errors="ignore") as acf_f:
                                        content = acf_f.read()
                                    idir_m = re.search(r'"installdir"\s+"([^"]+)"', content)
                                    appid_m = re.search(r'"appid"\s+"([^"]+)"', content)
                                    if idir_m and appid_m:
                                        if idir_m.group(1).strip().lower() == installdir:
                                            return appid_m.group(1).strip()
                                except Exception:
                                    pass
        except Exception:
            pass

    return None


def detect_game_retroachievements_id(game: Dict[str, Any]) -> Optional[str]:
    """Detecta si el juego tiene asociado un RetroAchievements GameID."""
    if not isinstance(game, dict):
        return None
    for k in ["ra_game_id", "retroachievements_id", "ra_id"]:
        val = str(game.get(k, "")).strip()
        if val.isdigit():
            return val
    return None


def set_game_retroachievements_id(game: Dict[str, Any], ra_id: str) -> None:
    """Asocia un RetroAchievements ID a los metadatos del juego."""
    if isinstance(game, dict):
        clean_id = str(ra_id).strip()
        if clean_id.isdigit():
            game["ra_game_id"] = clean_id
        elif not clean_id:
            game.pop("ra_game_id", None)


# ==============================================================================
# INTEGRACIÓN DE LOGROS: STEAM API
# ==============================================================================

def _http_get_json(url: str, timeout: int = 8) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "GameFlow-Launcher/2.5 (Windows; U; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
    except Exception as e:
        logger.debug(f"HTTP GET error ({url}): {e}")
    return None


def fetch_steam_achievements(
    appid: str,
    steam_id64: Optional[str] = None,
    api_key: Optional[str] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Obtiene los logros de un juego de Steam.
    Combina el esquema de logros (nombre, descripción, iconos) con el progreso del jugador
    y los porcentajes globales de desbloqueo.
    """
    cfg = load_achievements_config()
    api_key = (api_key or cfg.get("steam_api_key", "")).strip()
    steam_id64 = (steam_id64 or cfg.get("steam_id64", "")).strip()
    ttl_seconds = int(cfg.get("cache_ttl_hours", 12)) * 3600

    cache_key = f"steam_{appid}_{steam_id64}"
    cache = _load_cache()

    if not force_refresh and cache_key in cache:
        entry = cache[cache_key]
        cached_ts = entry.get("cached_at", 0)
        if time.time() - cached_ts < ttl_seconds:
            logger.debug(f"Retornando logros en caché para Steam AppID {appid}")
            return entry.get("data", {})

    achievements_list: List[Dict[str, Any]] = []
    game_title = f"Steam App {appid}"

    # 1. Obtener porcentajes globales (Público, sin API key)
    global_percentages: Dict[str, float] = {}
    url_pct = f"https://api.steampowered.com/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v0002/?gameid={appid}"
    data_pct = _http_get_json(url_pct)
    if data_pct and "achievementpercentages" in data_pct:
        for item in data_pct["achievementpercentages"].get("achievements", []):
            name = item.get("name")
            pct = item.get("percent")
            if name is not None and pct is not None:
                try:
                    global_percentages[str(name)] = round(float(pct), 1)
                except Exception:
                    pass

    # 2. Si tenemos API Key: consultar GetSchemaForGame
    schema_map: Dict[str, Dict[str, Any]] = {}
    if api_key:
        url_schema = f"https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/?key={api_key}&appid={appid}&l=spanish"
        data_schema = _http_get_json(url_schema)
        if data_schema and "game" in data_schema:
            game_obj = data_schema["game"]
            game_title = game_obj.get("gameName", game_title)
            stats = game_obj.get("availableGameStats", {})
            for a in stats.get("achievements", []):
                a_name = a.get("name")
                if a_name:
                    schema_map[a_name] = {
                        "title": a.get("displayName", a_name),
                        "description": a.get("description", ""),
                        "icon": a.get("icon", ""),
                        "icongray": a.get("icongray", ""),
                        "hidden": bool(a.get("hidden", 0))
                    }

    # 3. Logros del jugador: si tenemos API Key y SteamID64
    player_unlocked: Dict[str, Tuple[bool, Optional[str]]] = {}
    if api_key and steam_id64:
        url_player = f"https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/?appid={appid}&key={api_key}&steamid={steam_id64}&l=spanish"
        data_player = _http_get_json(url_player)
        if data_player and "playerstats" in data_player:
            pstats = data_player["playerstats"]
            if pstats.get("success"):
                game_title = pstats.get("gameName", game_title)
                for a in pstats.get("achievements", []):
                    apiname = a.get("apiname")
                    achieved = bool(a.get("achieved", 0))
                    utime = a.get("unlocktime")
                    time_str = None
                    if achieved and utime:
                        try:
                            dt = datetime.fromtimestamp(int(utime))
                            time_str = dt.strftime("%d/%m/%Y %H:%M")
                        except Exception:
                            pass
                    if apiname:
                        player_unlocked[apiname] = (achieved, time_str)

    # 4. Alternativa sin API Key: Steam Community XML (público si el perfil es accesible)
    if not schema_map and steam_id64:
        url_xml = f"https://steamcommunity.com/profiles/{steam_id64}/stats/{appid}/?xml=1"
        req = urllib.request.Request(url_xml, headers={"User-Agent": "GameFlow/2.5"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    tree = ET.fromstring(resp.read())
                    # Extraer gameName
                    gn = tree.find("game/gameName")
                    if gn is not None and gn.text:
                        game_title = gn.text.strip()
                    for ach_node in tree.findall("achievements/achievement"):
                        closed = ach_node.attrib.get("closed", "0") == "1"
                        apiname_node = ach_node.find("apiname")
                        name_node = ach_node.find("name")
                        desc_node = ach_node.find("description")
                        icon_node = ach_node.find("iconOpen")
                        icongray_node = ach_node.find("iconClosed")
                        unlock_node = ach_node.find("unlockTimestamp")

                        api_n = apiname_node.text.strip() if apiname_node is not None and apiname_node.text else ""
                        d_name = name_node.text.strip() if name_node is not None and name_node.text else api_n
                        desc = desc_node.text.strip() if desc_node is not None and desc_node.text else ""
                        ic = icon_node.text.strip() if icon_node is not None and icon_node.text else ""
                        icg = icongray_node.text.strip() if icongray_node is not None and icongray_node.text else ""

                        time_str = None
                        if closed and unlock_node is not None and unlock_node.text and unlock_node.text.isdigit():
                            try:
                                dt = datetime.fromtimestamp(int(unlock_node.text))
                                time_str = dt.strftime("%d/%m/%Y %H:%M")
                            except Exception:
                                pass

                        if api_n:
                            schema_map[api_n] = {
                                "title": d_name,
                                "description": desc,
                                "icon": ic,
                                "icongray": icg,
                                "hidden": False
                            }
                            player_unlocked[api_n] = (closed, time_str)
        except Exception as e:
            logger.debug(f"Error consultando Steam Community XML: {e}")

    # 5. Ensamblar lista unificada de logros
    unlocked_count = 0
    total_keys = set(schema_map.keys()) | set(global_percentages.keys())

    # Preservar orden del esquema o porcentaje
    for a_id in (list(schema_map.keys()) if schema_map else list(global_percentages.keys())):
        sch = schema_map.get(a_id, {})
        title = sch.get("title") or a_id.replace("_", " ").title()
        desc = sch.get("description", "")
        icon_url = sch.get("icon", "")
        icon_locked = sch.get("icongray", "")
        hidden = sch.get("hidden", False)

        is_unlocked, unlock_time = player_unlocked.get(a_id, (False, None))
        if is_unlocked:
            unlocked_count += 1

        rarity = global_percentages.get(a_id)

        achievements_list.append({
            "id": a_id,
            "title": title,
            "description": desc,
            "unlocked": is_unlocked,
            "unlock_time": unlock_time,
            "icon_url": icon_url,
            "icon_locked_url": icon_locked,
            "points": 0,
            "rarity_percent": rarity,
            "hidden": hidden
        })

    total_count = len(achievements_list)
    progress_pct = round((unlocked_count / total_count * 100), 1) if total_count > 0 else 0.0

    result = {
        "platform": "Steam",
        "game_title": game_title,
        "game_id": appid,
        "total_count": total_count,
        "unlocked_count": unlocked_count,
        "progress_percent": progress_pct,
        "total_points": 0,
        "unlocked_points": 0,
        "achievements": achievements_list
    }

    # Guardar en caché si se obtuvieron logros
    if achievements_list:
        cache[cache_key] = {
            "cached_at": time.time(),
            "data": result
        }
        _save_cache(cache)

    return result


# ==============================================================================
# INTEGRACIÓN DE LOGROS: RETROACHIEVEMENTS API
# ==============================================================================

def fetch_retroachievements(
    ra_game_id: str,
    username: Optional[str] = None,
    api_key: Optional[str] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Obtiene los logros de RetroAchievements para un juego retro.
    Devuelve los logros, medallas, puntos RetroAchievements y estado de desbloqueo.
    """
    cfg = load_achievements_config()
    username = (username or cfg.get("retroachievements_username", "")).strip()
    api_key = (api_key or cfg.get("retroachievements_api_key", "")).strip()
    ttl_seconds = int(cfg.get("cache_ttl_hours", 12)) * 3600

    cache_key = f"ra_{ra_game_id}_{username}"
    cache = _load_cache()

    if not force_refresh and cache_key in cache:
        entry = cache[cache_key]
        cached_ts = entry.get("cached_at", 0)
        if time.time() - cached_ts < ttl_seconds:
            logger.debug(f"Retornando logros en caché para RetroAchievements #{ra_game_id}")
            return entry.get("data", {})

    achievements_list: List[Dict[str, Any]] = []
    game_title = f"Retro Game #{ra_game_id}"
    total_points = 0
    unlocked_points = 0
    unlocked_count = 0

    if not username or not api_key:
        logger.warning("RetroAchievements: Usuario o Web API Key no configurados.")
        return {
            "platform": "RetroAchievements",
            "game_title": game_title,
            "game_id": ra_game_id,
            "total_count": 0,
            "unlocked_count": 0,
            "progress_percent": 0.0,
            "total_points": 0,
            "unlocked_points": 0,
            "achievements": [],
            "error": "Credenciales de RetroAchievements no configuradas."
        }

    # Endpoint oficial: API_GetGameInfoAndUserProgress.php
    params = urllib.parse.urlencode({
        "z": username,
        "y": api_key,
        "g": ra_game_id
    })
    url = f"https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?{params}"
    data = _http_get_json(url, timeout=10)

    if data and isinstance(data, dict):
        game_title = data.get("Title", game_title)
        raw_achievements = data.get("Achievements", {})

        if isinstance(raw_achievements, dict):
            # En RetroAchievements, Achievements es un dict de ID -> Datos
            items = list(raw_achievements.values())
        elif isinstance(raw_achievements, list):
            items = raw_achievements
        else:
            items = []

        for item in items:
            ach_id = str(item.get("ID", ""))
            title = item.get("Title", "Logro")
            desc = item.get("Description", "")
            pts = int(item.get("Points", 0))
            badge = str(item.get("BadgeName", "")).strip()

            date_earned = item.get("DateEarned") or item.get("DateEarnedHardcore")
            is_unlocked = bool(date_earned)

            time_str = None
            if is_unlocked and date_earned:
                try:
                    time_str = str(date_earned)[:16]
                except Exception:
                    pass

            # URLs oficiales de badges en media.retroachievements.org
            icon_url = f"https://media.retroachievements.org/Badge/{badge}.png" if badge else None
            icon_locked_url = f"https://media.retroachievements.org/Badge/{badge}_lock.png" if badge else None

            total_points += pts
            if is_unlocked:
                unlocked_count += 1
                unlocked_points += pts

            achievements_list.append({
                "id": ach_id,
                "title": title,
                "description": desc,
                "unlocked": is_unlocked,
                "unlock_time": time_str,
                "icon_url": icon_url,
                "icon_locked_url": icon_locked_url,
                "points": pts,
                "rarity_percent": None,
                "hidden": False
            })

    total_count = len(achievements_list)
    progress_pct = round((unlocked_count / total_count * 100), 1) if total_count > 0 else 0.0

    result = {
        "platform": "RetroAchievements",
        "game_title": game_title,
        "game_id": ra_game_id,
        "total_count": total_count,
        "unlocked_count": unlocked_count,
        "progress_percent": progress_pct,
        "total_points": total_points,
        "unlocked_points": unlocked_points,
        "achievements": achievements_list
    }

    if achievements_list:
        cache[cache_key] = {
            "cached_at": time.time(),
            "data": result
        }
        _save_cache(cache)

    return result


# ==============================================================================
# OBTENCIÓN UNIFICADA DE LOGROS POR JUEGO (STEAM / RETRO / METAS LOCALES)
# ==============================================================================

def get_game_achievements(game: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
    """
    Punto de entrada unificado para obtener logros de cualquier juego.
    1. Si es Steam -> Consulta Steam API / XML.
    2. Si es RetroAchievements -> Consulta RetroAchievements API.
    3. Si no tiene integración online -> Devuelve las metas personales como logros locales.
    """
    if not isinstance(game, dict):
        return {
            "platform": "None",
            "game_title": "Desconocido",
            "game_id": "",
            "total_count": 0,
            "unlocked_count": 0,
            "progress_percent": 0.0,
            "total_points": 0,
            "unlocked_points": 0,
            "achievements": []
        }

    # 1. Comprobar Steam
    steam_appid = detect_game_steam_appid(game)
    if steam_appid:
        try:
            return fetch_steam_achievements(steam_appid, force_refresh=force_refresh)
        except Exception as e:
            logger.error(f"Error consultando logros de Steam ({steam_appid}): {e}")

    # 2. Comprobar RetroAchievements
    ra_id = detect_game_retroachievements_id(game)
    if ra_id:
        try:
            return fetch_retroachievements(ra_id, force_refresh=force_refresh)
        except Exception as e:
            logger.error(f"Error consultando RetroAchievements ({ra_id}): {e}")

    # 3. Fallback a Metas Locales
    from core.stats_service import get_game_stats
    stats = get_game_stats(game)
    goals = stats.get("goals", [])
    achievements_list: List[Dict[str, Any]] = []
    unlocked_count = 0

    for g in goals:
        done = bool(g.get("completed", False))
        if done:
            unlocked_count += 1
        achievements_list.append({
            "id": g.get("id", ""),
            "title": g.get("text", "Meta"),
            "description": "Meta y objetivo personal definido en GameFlow.",
            "unlocked": done,
            "unlock_time": g.get("created_at"),
            "icon_url": None,
            "icon_locked_url": None,
            "points": 10,
            "rarity_percent": None,
            "hidden": False
        })

    tot = len(achievements_list)
    pct = round((unlocked_count / tot * 100), 1) if tot > 0 else 0.0

    return {
        "platform": "Local",
        "game_title": game.get("name", "Juego"),
        "game_id": "",
        "total_count": tot,
        "unlocked_count": unlocked_count,
        "progress_percent": pct,
        "total_points": tot * 10,
        "unlocked_points": unlocked_count * 10,
        "achievements": achievements_list
    }


def get_game_achievements_summary(game: Dict[str, Any]) -> Dict[str, Any]:
    """
    Devuelve un resumen rápido (desde caché o metas locales) para badges visuales
    en la carátula o ficha del juego sin bloquear con peticiones de red.
    """
    steam_appid = detect_game_steam_appid(game)
    if steam_appid:
        cfg = load_achievements_config()
        steam_id64 = cfg.get("steam_id64", "")
        cache_key = f"steam_{steam_appid}_{steam_id64}"
        cache = _load_cache()
        if cache_key in cache:
            d = cache[cache_key].get("data", {})
            return {
                "platform": "Steam",
                "total": d.get("total_count", 0),
                "unlocked": d.get("unlocked_count", 0),
                "percent": d.get("progress_percent", 0.0)
            }
        return {"platform": "Steam", "total": 0, "unlocked": 0, "percent": 0.0}

    ra_id = detect_game_retroachievements_id(game)
    if ra_id:
        cfg = load_achievements_config()
        u = cfg.get("retroachievements_username", "")
        cache_key = f"ra_{ra_id}_{u}"
        cache = _load_cache()
        if cache_key in cache:
            d = cache[cache_key].get("data", {})
            return {
                "platform": "RetroAchievements",
                "total": d.get("total_count", 0),
                "unlocked": d.get("unlocked_count", 0),
                "percent": d.get("progress_percent", 0.0)
            }
        return {"platform": "RetroAchievements", "total": 0, "unlocked": 0, "percent": 0.0}

    # Metas locales
    from core.stats_service import get_game_stats
    stats = get_game_stats(game)
    tot = stats.get("goals_total_count", 0)
    done = stats.get("goals_completed_count", 0)
    pct = round((done / tot * 100), 1) if tot > 0 else 0.0
    return {"platform": "Local", "total": tot, "unlocked": done, "percent": pct}
