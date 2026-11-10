"""
Detector y Monitor de Videojuegos en Ejecución para GameFlow.

Rastrea de forma proactiva procesos de videojuegos activos (lanzados por GameFlow o vigilados por el centinela)
permitiendo al In-Game Overlay mostrar el título actual, enfocar la ventana de juego o cerrarla limpiamente.
"""

import os
import sys
from typing import Optional, Dict, Any, List
import psutil

from core.platform_layer import win32gui, is_windows
from core.config import load_games_data


def get_running_game() -> Optional[Dict[str, Any]]:
    """
    Detecta si hay un juego lanzado o vigilado en ejecución.
    Prioriza procesos supervisados por sentinel_process.py o que coincidan con la biblioteca games.json.
    """
    # 1. Comprobar si hay un centinela activo con argumentos de juego
    sentinel_exe = ""
    sentinel_pids = []
    sentinel_game_path = ""

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info.get('cmdline') or []
            if any('sentinel_process.py' in str(c) for c in cmd):
                for i, arg in enumerate(cmd):
                    if arg == '--exe' and i + 1 < len(cmd):
                        sentinel_exe = cmd[i + 1].lower()
                    elif arg == '--game-path' and i + 1 < len(cmd):
                        sentinel_game_path = cmd[i + 1]
                    elif arg == '--pids' and i + 1 < len(cmd):
                        sentinel_pids = [int(p) for p in cmd[i + 1].split(',') if p.isdigit()]
                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Si encontramos el centinela, buscar el proceso del juego
    if sentinel_exe or sentinel_pids:
        for p in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                pname = (p.info.get('name') or '').lower()
                if (sentinel_pids and p.pid in sentinel_pids) or (sentinel_exe and pname == sentinel_exe):
                    return {
                        "name": _resolve_game_name(sentinel_game_path or pname),
                        "exe": pname,
                        "pid": p.pid,
                        "path": sentinel_game_path or (p.info.get('exe') or ''),
                        "hwnd": _find_main_hwnd_for_pid(p.pid)
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    # 2. Comprobar ejecutables de la biblioteca games.json
    games = load_games_data()
    running_names = {}
    for p in psutil.process_iter(['pid', 'name', 'exe']):
        try:
            pname = (p.info.get('name') or '').lower()
            if pname:
                running_names[pname] = (p.pid, p.info.get('exe') or '')
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for g in games:
        gpath = g.get('path', '')
        if not gpath:
            continue
        gbase = os.path.basename(gpath.replace('\\', '/')).lower()
        if gbase in running_names:
            pid, real_exe = running_names[gbase]
            return {
                "name": g.get('name', gbase),
                "exe": gbase,
                "pid": pid,
                "path": gpath,
                "hwnd": _find_main_hwnd_for_pid(pid)
            }

    return None


def is_game_running() -> bool:
    """Devuelve True si hay una partida de videojuego activa en el sistema."""
    return get_running_game() is not None


def _resolve_game_name(path_or_exe: str) -> str:
    """Obtiene el nombre comercial del juego a partir de su ruta o ejecutable."""
    games = load_games_data()
    norm_target = os.path.normcase(os.path.abspath(path_or_exe)) if os.path.isabs(path_or_exe) else path_or_exe.lower()
    for g in games:
        gp = g.get('path', '')
        if gp:
            if os.path.normcase(os.path.abspath(gp)) == norm_target or os.path.basename(gp).lower() == norm_target:
                return g.get('name', os.path.basename(path_or_exe))
    base = os.path.splitext(os.path.basename(path_or_exe))[0]
    return base.replace('_', ' ').replace('-', ' ').title()


def _find_main_hwnd_for_pid(target_pid: int) -> Optional[int]:
    """Encuentra el HWND de la ventana principal interactiva asociada a un PID."""
    if not is_windows():
        return None

    hwnds = []
    from core.platform_layer import win32process, win32gui

    def _enum_cb(hwnd, extra):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == target_pid:
                title = win32gui.GetWindowText(hwnd)
                if title:
                    hwnds.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_enum_cb, None)
        return hwnds[0] if hwnds else None
    except Exception:
        return None


def terminate_running_game(game_info: Optional[Dict[str, Any]] = None) -> bool:
    """Cierra limpiamente el juego en ejecución o fuerza su terminación si no responde."""
    info = game_info or get_running_game()
    if not info:
        return False

    pid = info.get("pid")
    if not pid:
        return False

    try:
        proc = psutil.Process(pid)
        # Terminar hijos recursivamente
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except Exception:
                pass
        proc.terminate()

        # Esperar hasta 2 segundos a que el proceso libere recursos
        _, alive = psutil.wait_procs([proc] + children, timeout=2.0)
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
        return True
    except Exception:
        return False


def focus_running_game(game_info: Optional[Dict[str, Any]] = None) -> bool:
    """Restaura el foco a la ventana del juego activo al reanudar partida."""
    info = game_info or get_running_game()
    if not info:
        return False

    hwnd = info.get("hwnd")
    if not hwnd or not is_windows():
        return False

    try:
        from core.platform_layer import win32gui, win32con
        if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False
