import os
import json
import time
import contextlib
import ctypes
from ctypes import wintypes
import threading
from typing import List, Dict, Any
import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _determine_storage_dir() -> str:
    """
    Determina la ruta óptima de almacenamiento persistente:
    1. Si existe un archivo '.portable' en BASE_DIR, se fuerza el modo portable local.
    2. Si BASE_DIR tiene permisos de escritura válidos, opera en modo portable local.
    3. Si BASE_DIR está protegido (ej: C:\\Program Files\\), redirige limpiamente a %APPDATA%\\GameFlow.
    """
    portable_marker = os.path.join(BASE_DIR, ".portable")
    if os.path.isfile(portable_marker):
        return BASE_DIR

    test_path = os.path.join(BASE_DIR, f".perm_test_{os.getpid()}.tmp")
    try:
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_path)
        return BASE_DIR
    except (PermissionError, OSError):
        appdata_base = os.environ.get("APPDATA") or os.path.expanduser("~")
        gameflow_data = os.path.join(appdata_base, "GameFlow")
        os.makedirs(gameflow_data, exist_ok=True)
        return gameflow_data

STORAGE_DIR = _determine_storage_dir()

def get_storage_dir() -> str:
    """Devuelve la ruta del directorio activo de persistencia (Local o %APPDATA%)."""
    return STORAGE_DIR

def is_portable_mode() -> bool:
    """Indica si la aplicación está operando en almacenamiento local portable."""
    return os.path.abspath(STORAGE_DIR) == os.path.abspath(BASE_DIR)

CONFIG_FILE = os.path.join(STORAGE_DIR, "games.json")
COVERS_DIR = os.path.join(STORAGE_DIR, "covers")
WALLPAPERS_DIR = os.path.join(STORAGE_DIR, "wallpapers")
GAMEPAD_CONFIG_FILE = os.path.join(STORAGE_DIR, "gamepad_config.json")
CACHE_DIR = os.path.join(STORAGE_DIR, ".cache")
JEWELS_CACHE_DIR = os.path.join(CACHE_DIR, "jewels")

# Asegurar carpetas persistentes
try:
    os.makedirs(COVERS_DIR, exist_ok=True)
    os.makedirs(WALLPAPERS_DIR, exist_ok=True)
    os.makedirs(JEWELS_CACHE_DIR, exist_ok=True)
except Exception:
    pass

# Si estamos en modo AppData y el archivo games.json aún no existe allí, importar el de BASE_DIR
if STORAGE_DIR != BASE_DIR and not os.path.exists(CONFIG_FILE):
    base_config = os.path.join(BASE_DIR, "games.json")
    if os.path.exists(base_config):
        try:
            import shutil
            shutil.copy2(base_config, CONFIG_FILE)
        except Exception:
            pass

def _get_logger():
    try:
        from core.logger import get_logger
        return get_logger("Config")
    except Exception:
        import logging
        return logging.getLogger("GameFlow.Config")

_local_thread_lock = threading.RLock()

@contextlib.contextmanager
def config_lock(timeout_ms: int = 5000):
    """
    Mutex inter-proceso de Windows para serializar lecturas y escrituras concurrentes en games.json.
    Previene condiciones de carrera entre la interfaz gráfica principal y el proceso centinela (sentinel_process).
    """
    with _local_thread_lock:
        mutex_handle = None
        acquired = False
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
            kernel32.ReleaseMutex.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL

            mutex_handle = kernel32.CreateMutexW(None, False, r"Local\GameFlowConfigMutex")
            if mutex_handle:
                res = kernel32.WaitForSingleObject(mutex_handle, int(timeout_ms))
                if res in (0x0, 0x80):
                    acquired = True
        except Exception:
            acquired = False

        try:
            yield acquired
        finally:
            if mutex_handle:
                if acquired:
                    try:
                        kernel32.ReleaseMutex(mutex_handle)
                    except Exception:
                        pass
                try:
                    kernel32.CloseHandle(mutex_handle)
                except Exception:
                    pass

def get_games_file_mtime() -> float:
    """Devuelve la fecha de última modificación (mtime) de games.json para sincronización reactiva."""
    try:
        if os.path.exists(CONFIG_FILE):
            return os.path.getmtime(CONFIG_FILE)
    except Exception:
        pass
    return 0.0

def load_games_data() -> List[Dict[str, Any]]:
    """Carga la lista de juegos desde games.json con soporte de restauración automática de respaldo y sincronización segura."""
    with config_lock():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for g in data:
                            if isinstance(g, dict):
                                if g.get("path"):
                                    g["path"] = os.path.normpath(g["path"])
                                if g.get("cover") and not os.path.exists(g["cover"]):
                                    cand = os.path.join(COVERS_DIR, os.path.basename(g["cover"]))
                                    if not os.path.exists(cand) and STORAGE_DIR != BASE_DIR:
                                        cand_base = os.path.join(BASE_DIR, "covers", os.path.basename(g["cover"]))
                                        if os.path.exists(cand_base):
                                            cand = cand_base
                                    if os.path.exists(cand):
                                        g["cover"] = cand
                                if g.get("wallpaper") and not os.path.exists(g["wallpaper"]):
                                    cand = os.path.join(WALLPAPERS_DIR, os.path.basename(g["wallpaper"]))
                                    if not os.path.exists(cand) and STORAGE_DIR != BASE_DIR:
                                        cand_base = os.path.join(BASE_DIR, "wallpapers", os.path.basename(g["wallpaper"]))
                                        if os.path.exists(cand_base):
                                            cand = cand_base
                                    if os.path.exists(cand):
                                        g["wallpaper"] = cand
                        return data
            except Exception as e:
                _get_logger().error(f"Error cargando {CONFIG_FILE}: {e}", exc_info=True)
                bak_file = f"{CONFIG_FILE}.bak"
                if os.path.exists(bak_file):
                    try:
                        with open(bak_file, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                _get_logger().info(f"Biblioteca restaurada con éxito desde {bak_file}")
                                return data
                    except Exception as e2:
                        _get_logger().error(f"Error leyendo archivo de respaldo {bak_file}: {e2}")
        return []

def save_games_data(games: List[Dict[str, Any]], merge_existing_playtime: bool = True) -> bool:
    """
    Guarda la lista de juegos en games.json de manera atómica con rotación de copia de seguridad (.bak).
    Si merge_existing_playtime=True, preserva de forma segura los tiempos de juego y última sesión
    guardados en disco por el centinela en segundo plano.
    """
    tmp_file = f"{CONFIG_FILE}.tmp"
    bak_file = f"{CONFIG_FILE}.bak"

    with config_lock():
        # Fusión inteligente de horas jugadas si el archivo ya existe en disco
        if merge_existing_playtime and os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    disk_data = json.load(f)
                if isinstance(disk_data, list):
                    disk_by_path = {}
                    disk_by_name = {}
                    for dg in disk_data:
                        if isinstance(dg, dict):
                            p = dg.get("path")
                            if p:
                                disk_by_path[os.path.normcase(os.path.normpath(p))] = dg
                            n = dg.get("name", "").strip().lower()
                            if n:
                                disk_by_name[n] = dg

                    for g in games:
                        if not isinstance(g, dict):
                            continue
                        gp = g.get("path")
                        norm_p = os.path.normcase(os.path.normpath(gp)) if gp else ""
                        match = disk_by_path.get(norm_p) or disk_by_name.get(g.get("name", "").strip().lower())
                        if match:
                            disk_mins = int(match.get("playtime_minutes", 0) or 0)
                            mem_mins = int(g.get("playtime_minutes", 0) or 0)
                            if disk_mins > mem_mins:
                                g["playtime_minutes"] = disk_mins
                            disk_last = match.get("last_played")
                            mem_last = g.get("last_played")
                            if disk_last and (not mem_last or disk_last > mem_last):
                                g["last_played"] = disk_last
            except Exception as e:
                _get_logger().warning(f"Aviso en merge de playtime: {e}")

        try:
            # Si el archivo actual existe y es válido, mantenerlo como respaldo .bak antes de sobrescribir
            if os.path.exists(CONFIG_FILE) and os.path.getsize(CONFIG_FILE) > 5:
                try:
                    import shutil
                    shutil.copy2(CONFIG_FILE, bak_file)
                except Exception:
                    pass

            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(games, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, CONFIG_FILE)
            return True
        except Exception as e:
            _get_logger().error(f"Error guardando {CONFIG_FILE}: {e}", exc_info=True)
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except Exception:
                    pass
            return False

def record_game_session(game_path_or_exe: str, elapsed_seconds: float, exe_base: str = "") -> bool:
    """
    Registra atómicamente el tiempo de juego transcurrido y la fecha de última sesión en games.json.
    Diseñado para ser invocado por el centinela independiente o hilos de monitorización.
    """
    if not game_path_or_exe and not exe_base:
        return False
    if elapsed_seconds < 10.0:
        return False

    with config_lock():
        games = load_games_data()
        added_mins = max(1, int(round(elapsed_seconds / 60.0)))
        today_str = time.strftime("%Y-%m-%d %H:%M")
        updated = False

        target_norm = os.path.normcase(os.path.normpath(game_path_or_exe)) if game_path_or_exe else ""
        target_base = (exe_base or os.path.basename(game_path_or_exe) or "").lower()

        # 1. Emparejamiento por ruta canónica absoluta normalizada
        if target_norm:
            for g in games:
                gp = g.get("path")
                if gp and os.path.normcase(os.path.normpath(gp)) == target_norm:
                    prev_mins = int(g.get("playtime_minutes", 0) or 0)
                    g["playtime_minutes"] = prev_mins + added_mins
                    g["last_played"] = today_str
                    updated = True
                    break

        # 2. Respaldo por nombre base de ejecutable
        if not updated and target_base:
            for g in games:
                gp = g.get("path")
                if gp and os.path.basename(gp).lower() == target_base:
                    prev_mins = int(g.get("playtime_minutes", 0) or 0)
                    g["playtime_minutes"] = prev_mins + added_mins
                    g["last_played"] = today_str
                    updated = True
                    break

        if updated:
            return save_games_data(games, merge_existing_playtime=False)
        return False
