import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes
from typing import Optional
import re
import psutil
import threading
import win32gui
import win32con
try:
    from core.logger import get_logger
    logger = get_logger("Launcher")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.Launcher")

# Estructura nativa para ShellExecuteExW con retención de handle de proceso (PID exacto)
class SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]

def launch_with_elevation(game_path: str, params: str, game_dir: str) -> Optional[int]:
    """
    Ejecuta el juego con permisos de Administrador usando ShellExecuteExW.
    Obtiene el PID exacto inmediatamente desde el kernel sin necesidad de esperas o sondeos a ciegas.
    """
    game_path = os.path.normpath(os.path.abspath(game_path))
    game_dir = os.path.normpath(os.path.abspath(game_dir)) if game_dir else os.path.dirname(game_path)
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    sei = SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = SEE_MASK_NOCLOSEPROCESS
    sei.hwnd = None
    sei.lpVerb = "runas"
    sei.lpFile = game_path
    sei.lpParameters = params or None
    sei.lpDirectory = game_dir
    sei.nShow = win32con.SW_SHOWNORMAL

    success = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
    if not success:
        err = ctypes.windll.kernel32.GetLastError()
        if err == 1223:  # ERROR_CANCELLED (El usuario pulsó 'No' en el prompt de UAC)
            raise PermissionError("Permisos de Administrador cancelados por el usuario.")
        elif err == 5:     # ERROR_ACCESS_DENIED
            raise PermissionError("Acceso denegado al solicitar permisos de Administrador.")
        else:
            raise OSError(f"Error al elevar proceso de Windows (código {err})")

    pid = None
    if sei.hProcess:
        try:
            pid = ctypes.windll.kernel32.GetProcessId(sei.hProcess)
        finally:
            ctypes.windll.kernel32.CloseHandle(sei.hProcess)
    return pid

# Asegurar codificación segura UTF-8 para evitar errores con caracteres como el símbolo Δ de Metal Gear
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.system import (
    set_high_priority, get_monitors, get_game_windows, get_hwnds_for_pid, move_window_to_monitor,
    warp_cursor_to_monitor, force_dwm_window_shift_to_monitor
)

def detect_game_engine(game_path: str) -> str:
    """
    Detecta automáticamente el motor gráfico del juego analizando su estructura de archivos.
    Soporta: Unreal Engine, Unity Engine, Godot, Source Engine, o Generic.
    """
    norm = game_path.replace("/", "\\").lower()
    game_dir = os.path.dirname(game_path)

    # 1. Unreal Engine (Binaries/Win64, Shipping.exe)
    if "binaries\\win64" in norm or "shipping.exe" in norm:
        return "unreal"

    # 2. Unity Engine (*_Data, UnityPlayer.dll, UnityCrashHandler)
    if os.path.isdir(game_dir):
        try:
            files = os.listdir(game_dir)
            for f in files:
                fl = f.lower()
                if fl.endswith("_data") or fl == "unityplayer.dll" or "unitycrashhandler" in fl:
                    return "unity"
        except Exception:
            pass

    # 3. Godot Engine (.pck en el directorio)
    if os.path.isdir(game_dir):
        try:
            files = os.listdir(game_dir)
            for f in files:
                if f.lower().endswith(".pck"):
                    return "godot"
        except Exception:
            pass

    # 4. Source Engine (Valve: hl2.exe, vpk, etc.)
    if "hl2.exe" in norm or "source" in norm:
        return "source"

    return "generic"

def is_unreal_engine_game(game_path: str) -> bool:
    """Detecta si un ejecutable pertenece a un juego de Unreal Engine."""
    return detect_game_engine(game_path) == "unreal"

def sync_unreal_engine_config(game_path: str, target_monitor_rect: tuple):
    """
    Sincroniza GameUserSettings.ini de juegos Unreal Engine (ej: MGS Delta, Wukong, Split Fiction).
    Asegura FullscreenMode=1 (Pantalla completa sin bordes / Borderless) y WindowPosX/WindowPosY exactos,
    evitando que DirectX 12 en modo exclusivo (FullscreenMode=0) secuestre la salida GPU hacia el monitor incorrecto.
    """
    try:
        parts = os.path.normpath(game_path).split(os.sep)
        game_name = None
        for i, p in enumerate(parts):
            if p.lower() == 'binaries' and i > 0:
                game_name = parts[i - 1]
                break

        if not game_name:
            return

        local_app = os.environ.get('LOCALAPPDATA', '')
        if not local_app:
            return

        t_left, t_top, t_right, t_bottom = target_monitor_rect
        w = t_right - t_left
        h = t_bottom - t_top

        for sub in ['Windows', 'WindowsNoEditor']:
            ini_path = os.path.join(local_app, game_name, 'Saved', 'Config', sub, 'GameUserSettings.ini')
            if os.path.isfile(ini_path):
                with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                content = re.sub(r'WindowPosX=[-\d]+', f'WindowPosX={t_left}', content)
                content = re.sub(r'WindowPosY=[-\d]+', f'WindowPosY={t_top}', content)
                content = re.sub(r'FullscreenMode=\d+', 'FullscreenMode=1', content)
                content = re.sub(r'PreferredFullscreenMode=\d+', 'PreferredFullscreenMode=1', content)
                content = re.sub(r'LastConfirmedFullscreenMode=\d+', 'LastConfirmedFullscreenMode=1', content)
                content = re.sub(r'ResolutionSizeX=\d+', f'ResolutionSizeX={w}', content)
                content = re.sub(r'ResolutionSizeY=\d+', f'ResolutionSizeY={h}', content)
                content = re.sub(r'LastUserConfirmedResolutionSizeX=\d+', f'LastUserConfirmedResolutionSizeX={w}', content)
                content = re.sub(r'LastUserConfirmedResolutionSizeY=\d+', f'LastUserConfirmedResolutionSizeY={h}', content)

                with open(ini_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Configuración de Unreal Engine ({game_name}) sincronizada: Pos=({t_left}, {t_top}), Res={w}x{h}, Mode=Borderless")
                break
    except Exception as e:
        logger.error(f"Error al sincronizar config de Unreal Engine: {e}")

def sync_game_display_config(game_path: str, target_monitor_index: int, target_monitor_rect=None):
    """
    Sincroniza archivos .ini de configuración gráfica de juegos que usan DirectX exclusivo
    o índices de pantalla propios (como Assassin's Creed Black Flag Resynced o juegos de Unreal Engine).
    Garantiza que el motor gráfico inicie directamente en la pantalla seleccionada.
    """
    try:
        exe_base = os.path.basename(game_path).lower()
        if "acblackflag" in exe_base:
            ini_path = os.path.expanduser(r"~\Documents\Assassin's Creed Black Flag Resynced\ACBlackFlag.ini")
            if os.path.isfile(ini_path):
                with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                content = re.sub(r"DisplayIndex=\d+", f"DisplayIndex={target_monitor_index}", content)
                if target_monitor_rect:
                    content = re.sub(r"WindowPosX=[-\d]+", f"WindowPosX={target_monitor_rect[0]}", content)
                    content = re.sub(r"WindowPosY=[-\d]+", f"WindowPosY={target_monitor_rect[1]}", content)
                with open(ini_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Configuración de AC Black Flag sincronizada con Monitor {target_monitor_index}")

        # Sincronización automática de GameUserSettings.ini para juegos Unreal Engine
        if target_monitor_rect and is_unreal_engine_game(game_path):
            sync_unreal_engine_config(game_path, target_monitor_rect)

    except Exception as e:
        logger.error(f"Error al sincronizar config gráfica: {e}")

def run_game_sentinel(initial_pids: list, exe_base: str, target_monitor_rect: tuple, target_monitor_name: str):
    """
    Capa 6 - Centinela Activo en segundo plano (Daemon Guard).
    Supervisa la ventana del juego durante el arranque y a lo largo de su ejecución.
    Si el motor gráfico intenta secuestrar la pantalla o cambiar de monitor en caliente
    (por ejemplo, tras cargar logos, intros cinemáticas o partidas guardadas a los 15-20 segundos),
    el centinela lo detecta inmediatamente y lo devuelve al monitor seleccionado sin intervención del usuario.
    """
    t_left, t_top, t_right, t_bottom = target_monitor_rect
    start_time = time.time()
    tracked_pids = set(initial_pids or [])
    last_correction_time = 0
    logger.info(f"Guardia activa iniciada para {target_monitor_name} {target_monitor_rect}")

    while True:
        try:
            # 1. Comprobar si los procesos siguen con vida
            alive_pids = {p for p in tracked_pids if psutil.pid_exists(p)}

            # Buscar por nombre si no tenemos PIDs vivos
            if not alive_pids and exe_base:
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        p_name = (p.info.get('name') or '').lower()
                        if p_name == exe_base or ('shipping' in exe_base and 'shipping' in p_name):
                            alive_pids.add(p.pid)
                    except Exception:
                        pass

            if not alive_pids:
                logger.info(f"El proceso del juego ({exe_base}) ha concluido. Centinela apagado.")
                break

            # Incorporar procesos hijos
            for p in list(alive_pids):
                tracked_pids.add(p)
                try:
                    proc = psutil.Process(p)
                    for child in proc.children(recursive=True):
                        tracked_pids.add(child.pid)
                        alive_pids.add(child.pid)
                except Exception:
                    pass

            # 2. Supervisar ventanas visibles del juego
            windows = get_game_windows(list(alive_pids))
            if windows:
                for w in windows:
                    # Si hay varias, priorizar ventanas de juego reales
                    if not w.get("is_main_candidate", False) and len(windows) > 1:
                        continue

                    hwnd = w["hwnd"]
                    rect = w["rect"]

                    # Comprobar si está dentro de los límites del monitor objetivo (tolerancia 25px)
                    is_inside = (
                        rect[0] >= t_left - 25 and rect[1] >= t_top - 25 and
                        rect[2] <= t_right + 25 and rect[3] <= t_bottom + 25
                    )

                    if not is_inside and (time.time() - last_correction_time > 0.8):
                        last_correction_time = time.time()
                        w_title = w.get('title') or w.get('safe_title', 'Juego')
                        logger.warning(f"¡Re-anclaje detectado en caliente! '{w_title}' se desvió a Rect={rect}. Devolviendo a {target_monitor_name}...")
                        move_window_to_monitor(hwnd, target_monitor_rect, force_borderless=True)
                        time.sleep(0.15)
                        try:
                            check_r = win32gui.GetWindowRect(hwnd)
                            still_out = not (
                                check_r[0] >= t_left - 30 and check_r[1] >= t_top - 30 and
                                check_r[2] <= t_right + 30 and check_r[3] <= t_bottom + 30
                            )
                            if still_out:
                                force_dwm_window_shift_to_monitor(hwnd, target_monitor_rect)
                        except Exception:
                            pass

        except Exception as e:
            pass

        # Frecuencia de chequeo adaptativa:
        # Primeros 45s (fase crítica de intro/carga de saves): 0.5s
        # Resto de la partida: 1.5s (coste de CPU < 0.001%)
        elapsed = time.time() - start_time
        time.sleep(0.5 if elapsed < 45.0 else 1.5)

def spawn_detached_sentinel(pids: list, exe_base: str, target_monitor_rect: tuple, target_monitor_name: str, game_path: str = ""):
    """
    Capa 6 - Guardián Desacoplado Independiente (Standalone Daemon).
    Lanza core/sentinel_process.py como un proceso de Windows totalmente independiente (DETACHED_PROCESS).
    Garantiza que el centinela permanezca vivo supervisando el juego incluso si el proceso principal del lanzador
    se cierra por completo (ej: cuando close_on_game_launch está activado).
    """
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sentinel_exe = os.path.join(base_dir, "sentinel_process.exe")

        pids_str = ",".join(str(p) for p in pids if p)
        rect_str = f"{target_monitor_rect[0]},{target_monitor_rect[1]},{target_monitor_rect[2]},{target_monitor_rect[3]}"

        if getattr(sys, 'frozen', False) and os.path.isfile(sentinel_exe):
            cmd = [
                sentinel_exe,
                "--pids", pids_str,
                "--exe", exe_base,
                "--rect", rect_str,
                "--name", target_monitor_name
            ]
        else:
            from gamepad_manager import get_pythonw_executable
            pythonw = get_pythonw_executable()
            sentinel_script = os.path.join(base_dir, "core", "sentinel_process.py")
            cmd = [
                pythonw,
                sentinel_script,
                "--pids", pids_str,
                "--exe", exe_base,
                "--rect", rect_str,
                "--name", target_monitor_name
            ]

        if game_path:
            cmd.extend(["--game-path", game_path])

        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(cmd, cwd=base_dir, creationflags=flags, close_fds=True)
        logger.info(f"Guardián desacoplado iniciado (PID {proc.pid}) para {target_monitor_name} {target_monitor_rect}")
        return proc.pid
    except Exception as e:
        logger.error(f"Error iniciando guardián desacoplado: {e}")
        return None

def launch_game_thread(game_path: str, target_monitor_index: int, high_priority: bool, 
                       status_cb=None, on_success_cb=None, on_error_cb=None, custom_args: str = ""):
    """
    Hilo de ejecución para lanzar el juego, asignar prioridad alta,
    detectar activamente su ventana y blindar su posicionamiento en el monitor seleccionado.
    Aplica la Defensa en 6 Capas:
      1. Warping del cursor al monitor destino antes de la creación de ventana.
      2. Inyección universal de variables de entorno SDL2/SDL3, parámetros de motor y argumentos personalizados.
      3. Sincronización proactiva de archivos de configuración (.ini).
      4. Intercepción activa multi-PID y formateo a Borderless Fullscreen sin desbordamientos.
      5. Bypass DWM de hardware (Win + Shift + Flecha) como respaldo definitivo.
      6. Centinela Desacoplado Independiente post-arranque (sin colisión de hilos) con registro de tiempo de juego.
    """
    try:
        import shlex
        game_path = os.path.normpath(os.path.abspath(game_path))
        if not os.path.isfile(game_path):
            raise FileNotFoundError(f"El ejecutable del juego no existe o la ruta no es accesible:\n{game_path}")

        monitors = get_monitors()
        target_monitor = None
        if target_monitor_index < len(monitors):
            target_monitor = monitors[target_monitor_index]
        elif monitors:
            # Fallback inteligente: si la pantalla preferida está apagada/desconectada, usar el monitor principal
            primary = next((m for m in monitors if m.get("is_primary")), monitors[0])
            target_monitor = primary
            orig_idx = target_monitor_index
            target_monitor_index = primary.get("id", 0)
            fallback_msg = f"Monitor {orig_idx} desconectado. Redirigiendo a {primary['name']}..."
            logger.info(fallback_msg)
            if status_cb:
                status_cb(fallback_msg)

        # Capa 3: Sincronizar configuración interna (.ini) antes del arranque
        if target_monitor:
            sync_game_display_config(game_path, target_monitor_index, target_monitor.get('rect'))

        if status_cb:
            status_cb("Iniciando ejecutable...")
        logger.info(f"Iniciando {game_path}...")
        game_dir = os.path.dirname(game_path)
        pid = None

        # Capa 2a: Variables de Entorno Universales (SDL2, SDL3, Bypass UAC en mando)
        game_env = os.environ.copy()
        game_env["SDL_VIDEO_FULLSCREEN_DISPLAY"] = str(target_monitor_index)
        game_env["SDL_VIDEO_DISPLAY"] = str(target_monitor_index)
        game_env["SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"] = "0"
        # Suprime peticiones innecesarias de administrador para arrancar directo con el mando sin diálogo UAC
        game_env["__COMPAT_LAYER"] = "RunAsInvoker"

        # Capa 2b: Detección de motor e inyección de parámetros universales + argumentos personalizados
        engine = detect_game_engine(game_path)
        cmd = [game_path]
        extra_args_list = []

        if target_monitor:
            t_left, t_top, t_right, t_bottom = target_monitor['rect']
            w = t_right - t_left
            h = t_bottom - t_top

            if engine == "unreal":
                ue_params = ["-borderless", f"-WinX={t_left}", f"-WinY={t_top}", f"-ResX={w}", f"-ResY={h}"]
                cmd.extend(ue_params)
                extra_args_list.extend(ue_params)
                logger.info(f"Blindaje Unreal Engine inyectado: {' '.join(ue_params)}")
            elif engine == "unity":
                # Unity indexa pantallas desde 1 (1 = DISPLAY1, 2 = DISPLAY2, 3 = DISPLAY3)
                unity_params = ["-monitor", str(target_monitor_index + 1), "-screen-fullscreen", "1"]
                cmd.extend(unity_params)
                extra_args_list.extend(unity_params)
                logger.info(f"Blindaje Unity Engine inyectado: {' '.join(unity_params)}")
            elif engine == "godot":
                godot_params = ["--screen", str(target_monitor_index)]
                cmd.extend(godot_params)
                extra_args_list.extend(godot_params)
                logger.info(f"Blindaje Godot Engine inyectado: {' '.join(godot_params)}")
            elif engine == "source":
                source_params = ["-noborder", "-x", str(t_left), "-y", str(t_top)]
                cmd.extend(source_params)
                extra_args_list.extend(source_params)
                logger.info(f"Blindaje Source Engine inyectado: {' '.join(source_params)}")

        if custom_args and custom_args.strip():
            try:
                user_tokens = shlex.split(custom_args.strip(), posix=False)
            except Exception:
                user_tokens = custom_args.strip().split()
            cmd.extend(user_tokens)
            extra_args_list.extend(user_tokens)

        extra_args = " ".join(extra_args_list)

        # Capa 1: Warping preventivo del cursor al centro del monitor antes de crear la ventana
        if target_monitor:
            warp_cursor_to_monitor(target_monitor['rect'])

        try:
            process = subprocess.Popen(cmd, env=game_env, cwd=game_dir)
            pid = process.pid
        except (OSError, PermissionError) as e:
            # Error 740: Requiere elevación como Administrador
            if getattr(e, 'winerror', None) == 740 or "requiere elevaci" in str(e).lower() or "elevation" in str(e).lower():
                logger.info(f"{game_path} requiere elevación. Solicitando permisos de Administrador...")
                if status_cb:
                    status_cb("Solicitando permisos de Administrador...")
                pid = launch_with_elevation(game_path, extra_args, game_dir)
            else:
                raise e

        # Si se inició mediante ShellExecuteW o proceso bootstrap, buscar PID por nombre de ejecutable
        exe_base = os.path.basename(game_path).lower()
        if pid is None or not psutil.pid_exists(pid):
            time.sleep(1.0)
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    if (p.info.get('name') or '').lower() == exe_base:
                        pid = p.pid
                        break
                except Exception:
                    pass

        if pid and high_priority:
            set_high_priority(pid)
            if status_cb:
                status_cb("Prioridad alta asignada")

        if target_monitor:
            t_name = target_monitor.get('name', f'Monitor {target_monitor_index}')
            t_rect = target_monitor['rect']
            t_left, t_top, t_right, t_bottom = t_rect

            if status_cb:
                status_cb(f"Sincronizando con {t_name}...")
            logger.info(f"Monitorizando ventanas del juego para {t_name} {t_rect}...")

            timeout = 25.0
            start_time = time.time()
            stable_consecutive_checks = 0
            moved_any = False
            last_moved_hwnd = None
            failed_moves_count = 0
            target_pids = [pid] if pid else []

            while time.time() - start_time < timeout:
                # Recopilar todos los PIDs relevantes (proceso padre, procesos hijos y ejecutables asociados)
                target_pids = []
                if pid and psutil.pid_exists(pid):
                    target_pids.append(pid)
                    try:
                        proc = psutil.Process(pid)
                        for child in proc.children(recursive=True):
                            if child.pid not in target_pids:
                                target_pids.append(child.pid)
                    except Exception:
                        pass
                else:
                    for p in psutil.process_iter(['pid', 'name']):
                        try:
                            if (p.info.get('name') or '').lower() == exe_base:
                                target_pids.append(p.pid)
                        except Exception:
                            pass

                if target_pids:
                    windows = get_game_windows(target_pids)
                    if windows:
                        # get_game_windows clasifica la ventana de juego 3D principal primero
                        best_window = windows[0]
                        hwnd = best_window["hwnd"]
                        cur_rect = best_window["rect"]

                        # Comprobar si ya está dentro de los límites del monitor objetivo (tolerancia 15px)
                        is_inside = (
                            cur_rect[0] >= t_left - 15 and cur_rect[1] >= t_top - 15 and 
                            cur_rect[2] <= t_right + 15 and cur_rect[3] <= t_bottom + 15
                        )

                        # Capa 4: Posicionamiento activo y conversión a Borderless
                        if not is_inside or hwnd != last_moved_hwnd:
                            w_title = best_window.get('title') or best_window.get('safe_title', 'Juego')
                            logger.info(f"Ventana detectada '{w_title}' ({best_window['width']}x{best_window['height']}). Posicionando en {t_name}...")
                            if status_cb:
                                status_cb("Posicionando juego en la pantalla seleccionada...")
                            move_window_to_monitor(hwnd, t_rect, force_borderless=True)
                            moved_any = True
                            last_moved_hwnd = hwnd
                            stable_consecutive_checks = 0

                            # Capa 5: Ataque de Respaldo por Hardware DWM si la ventana se resiste
                            time.sleep(0.15)
                            try:
                                check_rect = win32gui.GetWindowRect(hwnd)
                                still_outside = not (
                                    check_rect[0] >= t_left - 30 and check_rect[1] >= t_top - 30 and 
                                    check_rect[2] <= t_right + 30 and check_rect[3] <= t_bottom + 30
                                )
                                if still_outside:
                                    failed_moves_count += 1
                                    if failed_moves_count >= 2:
                                        logger.warning("La ventana no responde a SetWindowPos. Disparando bypass DWM por hardware (Win + Shift + Flecha)...")
                                        force_dwm_window_shift_to_monitor(hwnd, t_rect)
                            except Exception:
                                pass
                        else:
                            # Ventana principal candidata ya dentro de los límites correctos
                            if best_window["is_main_candidate"]:
                                stable_consecutive_checks += 1
                                # Estabilizada durante al menos 4 chequeos consecutivos (~2 segundos seguidos)
                                if stable_consecutive_checks >= 4:
                                    logger.info(f"Ventana principal estabilizada correctamente en {t_name}.")
                                    break

                time.sleep(0.4)

            # Capa 6: Una vez concluida la estabilización inicial, lanzar el único Centinela Desacoplado Independiente
            # para evitar competencia simultánea de hilos sobre DWM / SetWindowPos.
            sentinel_pids = target_pids if target_pids else ([pid] if pid else [])
            spawn_detached_sentinel(sentinel_pids, exe_base, t_rect, t_name, game_path=game_path)

            if moved_any:
                if status_cb:
                    status_cb(f"¡Juego ejecutándose en {t_name}!")
            else:
                logger.info("Tiempo de espera finalizado (juego ejecutándose).")
                if status_cb:
                    status_cb("¡Juego iniciado!")
        else:
            sentinel_pids = [pid] if pid else []
            spawn_detached_sentinel(sentinel_pids, exe_base, (0, 0, 0, 0), "Predeterminado", game_path=game_path)
            time.sleep(0.5)
            if status_cb:
                status_cb("¡Juego iniciado!")

        if on_success_cb:
            on_success_cb()

    except Exception as e:
        logger.error(f"Error ejecutando el juego: {e}", exc_info=True)
        if status_cb:
            status_cb(f"Error: {e}")
        with open("error.log", "a", encoding="utf-8") as f:
            f.write(f"Error ejecutando {game_path}: {e}\n")
        if on_error_cb:
            on_error_cb(str(e))



