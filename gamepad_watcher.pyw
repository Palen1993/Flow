"""
GameFlow SteamOS Watcher
Ejecuta en segundo plano silenciosamente. Detecta cuando el mando seleccionado
se enciende/conecta o cuando se pulsa el botón Xbox (Guía/Nexus) para invocar o restaurar lanzador.py.
"""
import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes
import psutil

DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
if DIR not in sys.path:
    sys.path.insert(0, DIR)

from gamepad_manager import (
    load_gamepad_config, poll_active_gamepad, ensure_gamebar_nexus_disabled,
    ensure_watcher_running, get_pythonw_executable, force_foreground_window
)

# -------------------------------------------------------------
# Garantizar Instancia Única mediante Mutex de Windows
# -------------------------------------------------------------
def acquire_single_instance_mutex():
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Local\\GameFlowSteamOSWatcherMutex"
    h_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    last_err = kernel32.GetLastError()
    if last_err == 183:  # ERROR_ALREADY_EXISTS
        sys.exit(0)
    return h_mutex

# -------------------------------------------------------------
# Búsqueda y Enfoque de la Ventana del Lanzador
# -------------------------------------------------------------
def find_launcher_process():
    """Busca el proceso activo de lanzador.py o app.py ignorando procesos muertos o externos."""
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (p.info.get('name') or '').lower()
            if name in ['gameflow launcher.exe', 'gameflow_launcher.exe', 'lanzador.exe']:
                if p.pid != os.getpid() and p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                    return p
            if name not in ['python.exe', 'pythonw.exe']:
                continue
            if p.pid == os.getpid():
                continue
            cmd = p.info.get('cmdline') or []
            if any(str(arg).lower().endswith("lanzador.py") or str(arg).lower().endswith("app.py") for arg in cmd):
                if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                    return p
        except Exception:
            pass
    return None

def kill_hung_games() -> bool:
    """Termina forzosamente cualquier juego colgado o en pantalla negra registrado en games.json."""
    try:
        from core.config import load_games_data
        games = load_games_data()
        known_exes = set()
        for g in games:
            p = g.get("path")
            if p:
                known_exes.add(os.path.basename(p).lower())
        
        killed_any = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                p_name = (proc.info.get('name') or '').lower()
                if p_name in known_exes or ('shipping' in p_name and any('shipping' in ke for ke in known_exes)):
                    log_watcher(f"Panic Kill Switch: cerrando juego colgado '{p_name}' (PID={proc.pid})...")
                    proc.kill()
                    killed_any = True
            except Exception:
                pass
        return killed_any
    except Exception as e:
        log_watcher(f"Error en kill_hung_games: {e}")
        return False

def focus_launcher_window(pid: int) -> bool:
    """Enfoca y restaura la ventana del lanzador correspondiente al PID dado."""
    if not pid:
        return False
    hwnds = []
    def enum_cb(hwnd, _):
        if ctypes.windll.user32.IsWindow(hwnd):
            lp_pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
            if lp_pid.value == pid:
                hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

    for hwnd in hwnds:
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        if force_foreground_window(hwnd):
            return True
    return False

def log_watcher(msg: str):
    try:
        log_path = os.path.join(DIR, "watcher.log")
        if os.path.isfile(log_path) and os.path.getsize(log_path) > 200 * 1024:
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                with open(log_path, "w", encoding="utf-8") as f:
                    f.writelines(lines[-300:])
            except Exception:
                pass
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

_last_launch_time = 0.0
_LAUNCH_STAMP_FILE = os.path.join(DIR, ".launch_timestamp")

def _is_interprocess_cooldown_active(cooldown_sec: float = 2.2) -> bool:
    """Verifica y actualiza un timestamp compartido entre procesos para evitar doble arranque (daemon vs ms-gamebar)."""
    global _last_launch_time
    now = time.time()
    if now - _last_launch_time < cooldown_sec:
        return True
    try:
        if os.path.isfile(_LAUNCH_STAMP_FILE):
            mtime = os.path.getmtime(_LAUNCH_STAMP_FILE)
            if 0 <= (now - mtime) < cooldown_sec:
                return True
        with open(_LAUNCH_STAMP_FILE, "w", encoding="utf-8") as f:
            f.write(str(now))
    except Exception:
        pass
    _last_launch_time = now
    return False

def launch_or_focus():
    """Si el lanzador está cerrado, lo arranca. Si ya está abierto, lo restaura y enfoca al frente absoluto."""
    if _is_interprocess_cooldown_active(2.2):
        log_watcher("launch_or_focus: cooldown activo (ignorado)")
        return
    log_watcher("launch_or_focus: comprobando instancias de lanzador.py...")

    # 1. Comprobar si existe un proceso activo de lanzador.py
    proc = find_launcher_process()
    if proc is not None:
        log_watcher(f"launch_or_focus: proceso encontrado PID={proc.pid}, trayendo al frente...")
        if focus_launcher_window(proc.pid):
            log_watcher(f"launch_or_focus: ventana enfocada con éxito (PID={proc.pid})")
            return

        # Si el proceso acaba de iniciar (< 6.5s), esperar a que termine de crear su ventana en vez de matarlo
        try:
            proc_age = time.time() - proc.create_time()
        except Exception:
            proc_age = 999.0

        if proc_age < 6.5:
            log_watcher(f"launch_or_focus: PID={proc.pid} está arrancando (edad={proc_age:.2f}s). Esperando ventana...")
            for _ in range(25):
                time.sleep(0.15)
                if not proc.is_running():
                    break
                if focus_launcher_window(proc.pid):
                    log_watcher(f"launch_or_focus: ventana recién creada enfocada con éxito (PID={proc.pid})")
                    return
            return

        log_watcher(f"launch_or_focus: PID={proc.pid} sin ventana interactiva (edad={proc_age:.1f}s), cerrando para arranque limpio...")
        try:
            proc.kill()
            time.sleep(0.2)
        except Exception:
            pass

    # 2. Si no hay proceso o no tenía ventana válida, arrancar nueva instancia limpia
    launcher_exe = os.path.join(DIR, "GameFlow Launcher.exe")
    if getattr(sys, 'frozen', False) and os.path.isfile(launcher_exe):
        log_watcher(f"launch_or_focus: iniciando {launcher_exe}...")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", launcher_exe, "", DIR, 1)
            log_watcher(f"launch_or_focus: ShellExecuteW retornó {ret}")
            if ret <= 32:
                flags = (0x08000000 | 0x00000200)
                p = subprocess.Popen([launcher_exe], cwd=DIR, creationflags=flags)
                log_watcher(f"launch_or_focus: Popen fallback PID={p.pid}")
        except Exception as e:
            log_watcher(f"launch_or_focus: error: {e}")
            flags = (0x08000000 | 0x00000200)
            p = subprocess.Popen([launcher_exe], cwd=DIR, creationflags=flags)
            log_watcher(f"launch_or_focus: exception fallback PID={p.pid}")
        return

    pythonw = get_pythonw_executable()
    launcher_path = os.path.join(DIR, "lanzador.py")
    if not os.path.isfile(launcher_path):
        log_watcher(f"launch_or_focus: no existe {launcher_path}")
        return

    log_watcher(f"launch_or_focus: iniciando {pythonw} {launcher_path}...")
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "open", pythonw, f'"{launcher_path}"', DIR, 1
        )
        log_watcher(f"launch_or_focus: ShellExecuteW retornó {ret}")
        if ret <= 32:
            flags = (0x08000000 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            p = subprocess.Popen([pythonw, launcher_path], cwd=DIR, creationflags=flags)
            log_watcher(f"launch_or_focus: Popen fallback PID={p.pid}")
    except Exception as e:
        log_watcher(f"launch_or_focus: error: {e}")
        flags = (0x08000000 | 0x00000200)
        p = subprocess.Popen([pythonw, launcher_path], cwd=DIR, creationflags=flags)
        log_watcher(f"launch_or_focus: exception fallback PID={p.pid}")


def launch_or_focus_overlay():
    """Lanza el In-Game Overlay flotante cuando se pulsa el botón Guía durante una partida."""
    overlay_exe = os.path.join(DIR, "GameFlow Overlay.exe")
    if getattr(sys, 'frozen', False) and os.path.isfile(overlay_exe):
        try:
            flags = (0x08000000 | 0x00000200)
            subprocess.Popen([overlay_exe], cwd=DIR, creationflags=flags)
            return
        except Exception:
            pass

    pythonw = get_pythonw_executable()
    overlay_script = os.path.join(DIR, "overlay.py")
    if os.path.isfile(overlay_script):
        try:
            flags = (0x08000000 | 0x00000200)
            subprocess.Popen([pythonw, overlay_script], cwd=DIR, creationflags=flags)
            return
        except Exception:
            pass

    # Fallback si no está el script de overlay
    launch_or_focus()


def main():
    _mutex = acquire_single_instance_mutex()
    ensure_gamebar_nexus_disabled()
    log_watcher("Watcher main() iniciado correctamente")

    prev_guide = False
    panic_start_time = 0.0
    last_config_check = 0.0
    cfg = load_gamepad_config()

    target_id = cfg.get("selected_controller_id", "any")
    was_connected, dev_name, _ = poll_active_gamepad(target_id)
    log_watcher(f"Estado inicial del mando: conectado={was_connected}, dev={dev_name}")

    while True:
        now = time.time()
        # Recargar configuración periódicamente (con caché mtime) y mantener GameBar sincronizada
        if now - last_config_check > 5.0:
            cfg = load_gamepad_config()
            ensure_gamebar_nexus_disabled()
            last_config_check = now

        target_id = cfg.get("selected_controller_id", "any")
        is_conn, dev_name, inputs = poll_active_gamepad(target_id)
        
        # 1. Detección de pulsación del botón Xbox / Guía (Overlay en juego o lanzador en escritorio)
        curr_guide = inputs.get("guide", False)
        if curr_guide and not prev_guide:
            log_watcher("¡BOTÓN XBOX / GUÍA PULSADO!")
            if cfg.get("launch_on_xbox_button", True):
                try:
                    from core.active_game_tracker import is_game_running
                    in_game = is_game_running()
                except Exception:
                    in_game = False

                if in_game:
                    log_watcher("Partida en curso detectada: abriendo In-Game Overlay...")
                    launch_or_focus_overlay()
                else:
                    launch_or_focus()
                time.sleep(1.0)  # Evitar múltiples aperturas por mantener pulsado
        prev_guide = curr_guide

        # 2. Detección precisa de conexión/desconexión (independiente de la bandera de auto_launch)
        if is_conn and not was_connected:
            was_connected = True
            log_watcher(f"Mando encendido/conectado: {dev_name}.")
            if cfg.get("auto_launch_on_connect", True):
                log_watcher("auto_launch_on_connect activo. Iniciando lanzador...")
                launch_or_focus()
                time.sleep(2.0)
        elif not is_conn:
            if was_connected:
                log_watcher("Mando desconectado.")
            was_connected = False

        # 3. Combinación de Emergencia / Pánico desde el sofá (Back + Start sostenidos 2.5s)
        # Fuerza el cierre de cualquier juego congelado en pantalla negra y restaura el menú principal
        curr_back = inputs.get("back", False)
        curr_start = inputs.get("start", False)
        if curr_back and curr_start:
            if panic_start_time == 0.0:
                panic_start_time = now
            elif now - panic_start_time >= 2.5:
                log_watcher("¡COMBINACIÓN DE PÁNICO DETECTADA (Back + Start)! Cerrando juegos colgados...")
                try:
                    from core.feedback import trigger_haptic, play_feedback_sound
                    play_feedback_sound("launch")
                    trigger_haptic(left=55000, right=65000, duration_ms=320)
                except Exception:
                    pass
                kill_hung_games()
                launch_or_focus()
                panic_start_time = 0.0
                time.sleep(1.5)
        else:
            panic_start_time = 0.0

        time.sleep(0.04)  # Sondeo rápido de 40ms (~25 FPS) para respuesta instantánea con 0% de CPU

if __name__ == "__main__":
    # Si Windows invoca el protocolo ms-gamebar al pulsar el botón Xbox:
    if len(sys.argv) > 1 and ("ms-gamebar" in sys.argv[1].lower() or "--launch" in sys.argv[1].lower()):
        log_watcher(f"Invocado por protocolo ms-gamebar con argv: {sys.argv}")
        ensure_watcher_running()
        launch_or_focus()
        time.sleep(0.5)
        sys.exit(0)

    try:
        main()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
    except Exception as e:
        import traceback
        with open(os.path.join(DIR, "watcher_crash.log"), "w", encoding="utf-8") as f:
            f.write(f"Exited with: {type(e).__name__}: {e}\n")
            f.write(traceback.format_exc())
