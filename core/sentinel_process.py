"""
GameFlow Sentinel Process (Capa 6 - Guardián Desacoplado en Segundo Plano)
Ejecuta como un proceso independiente en segundo plano (pythonw.exe).
Sobrevive al cierre del lanzador principal y garantiza que ningún juego pueda
secuestrar la pantalla ni saltar a otro monitor al cargar cinemáticas, menús o partidas.
"""
import os
import sys
import time
import argparse
import logging
import psutil
import win32gui

# Añadir raíz del proyecto a sys.path
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from core.logger import get_logger
    logger = get_logger("Sentinel")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.Sentinel")

try:
    from core.system import (
        move_window_to_monitor, force_dwm_window_shift_to_monitor, get_game_windows
    )
    from core.config import record_game_session
except Exception as e:
    logger.error(f"Error importando módulos core: {e}")
    sys.exit(1)

def _record_session_playtime(exe_base: str, elapsed_seconds: float, game_path: str = ""):
    """Registra automáticamente el tiempo jugado y la fecha de última sesión en games.json."""
    if elapsed_seconds < 10.0:
        return
    try:
        ok = record_game_session(game_path or "", elapsed_seconds, exe_base=exe_base)
        mins = max(1, int(round(elapsed_seconds / 60.0)))
        if ok:
            logger.info(f"Tiempo de juego actualizado para '{game_path or exe_base}': +{mins} min.")
        else:
            logger.warning(f"No se pudo emparejar el juego para actualizar tiempo: path='{game_path}', exe='{exe_base}'")
    except Exception as e:
        logger.error(f"Error registrando tiempo de juego: {e}")

def main():
    parser = argparse.ArgumentParser(description="GameFlow Screen Sentinel")
    parser.add_argument("--pids", type=str, default="", help="PIDs separados por coma")
    parser.add_argument("--exe", type=str, default="", help="Nombre base del ejecutable")
    parser.add_argument("--rect", type=str, required=True, help="left,top,right,bottom del monitor objetivo")
    parser.add_argument("--name", type=str, default="Monitor", help="Nombre descriptivo del monitor")
    parser.add_argument("--game-path", type=str, default="", help="Ruta canónica completa al ejecutable del juego")
    args = parser.parse_args()

    try:
        coords = [int(x.strip()) for x in args.rect.split(",")]
        if len(coords) != 4:
            raise ValueError("Rect debe tener 4 enteros")
        t_rect = tuple(coords)
    except Exception as e:
        logger.error(f"Error parseando --rect '{args.rect}': {e}")
        sys.exit(1)

    t_left, t_top, t_right, t_bottom = t_rect
    t_name = args.name
    exe_base = (args.exe or "").lower()
    game_path = (args.game_path or "").strip()

    tracked_pids = set()
    if args.pids:
        for p_str in args.pids.split(","):
            p_str = p_str.strip()
            if p_str.isdigit():
                tracked_pids.add(int(p_str))

    logger.info(f"=== CENTINELA INDEPENDIENTE INICIADO ===")
    # Evitar centinelas duplicados para el mismo ejecutable
    curr_pid = os.getpid()
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if p.pid != curr_pid:
                cmd = p.info.get('cmdline') or []
                if any('sentinel_process.py' in str(c) for c in cmd) and any(exe_base in str(c).lower() for c in cmd):
                    logger.info(f"Cerrando centinela anterior duplicado (PID {p.pid}) para {exe_base}...")
                    p.kill()
        except Exception:
            pass

    start_time = time.time()
    last_correction_time = 0
    consecutive_not_found = 0

    while True:
        try:
            # 1. Comprobar procesos vivos
            alive_pids = {p for p in tracked_pids if psutil.pid_exists(p)}

            # Si no tenemos PIDs vivos, buscar por nombre de ejecutable
            if not alive_pids and exe_base:
                for p in psutil.process_iter(['pid', 'name']):
                    try:
                        p_name = (p.info.get('name') or '').lower()
                        if p_name == exe_base or ('shipping' in exe_base and 'shipping' in p_name):
                            alive_pids.add(p.pid)
                    except Exception:
                        pass

            if not alive_pids:
                consecutive_not_found += 1
                # En los primeros 60s (fase de arranque, anti-cheat y launchers intermediarios),
                # dar hasta 20 comprobaciones (~10s) de margen antes de considerar el juego muerto.
                # Una vez estabilizado el juego, 5 comprobaciones (~7.5s) son suficientes.
                max_missing = 20 if (time.time() - start_time < 60.0) else 5
                if consecutive_not_found >= max_missing:
                    logger.info("El proceso del juego ha finalizado. Centinela apagado.")
                    break
            else:
                consecutive_not_found = 0

            # Descubrir y añadir procesos hijos
            for p in list(alive_pids):
                tracked_pids.add(p)
                try:
                    proc = psutil.Process(p)
                    for child in proc.children(recursive=True):
                        tracked_pids.add(child.pid)
                        alive_pids.add(child.pid)
                except Exception:
                    pass

            # 2. Supervisar y corregir ventanas (solo cuando se especificó un monitor concreto)
            if alive_pids and t_rect != (0, 0, 0, 0):
                windows = get_game_windows(list(alive_pids))
                if windows:
                    for w in windows:
                        if not w.get("is_main_candidate", False) and len(windows) > 1:
                            continue

                        hwnd = w["hwnd"]
                        rect = w["rect"]

                        # Comprobar si está dentro de los límites del monitor objetivo (tolerancia 25px)
                        is_inside = (
                            rect[0] >= t_left - 25 and rect[1] >= t_top - 25 and
                            rect[2] <= t_right + 25 and rect[3] <= t_bottom + 25
                        )

                        if not is_inside and (time.time() - last_correction_time > 0.6):
                            last_correction_time = time.time()
                            w_title = w.get('title') or w.get('safe_title', 'Juego')
                            logger.warning(
                                f"¡Re-anclaje detectado! '{w_title}' (HWND={hwnd}) se desvió a Rect={rect}. "
                                f"Devolviendo forzosamente a {t_name} {t_rect}..."
                            )
                            move_window_to_monitor(hwnd, t_rect, force_borderless=True)
                            time.sleep(0.15)
                            try:
                                check_r = win32gui.GetWindowRect(hwnd)
                                still_out = not (
                                    check_r[0] >= t_left - 30 and check_r[1] >= t_top - 30 and
                                    check_r[2] <= t_right + 30 and check_r[3] <= t_bottom + 30
                                )
                                if still_out:
                                    logger.warning("Ventana aún fuera. Disparando bypass DWM por hardware...")
                                    force_dwm_window_shift_to_monitor(hwnd, t_rect)
                            except Exception:
                                pass

        except Exception as e:
            logger.error(f"Excepción en ciclo del centinela: {e}")

        # Frecuencia adaptativa
        elapsed = time.time() - start_time
        sleep_sec = 0.5 if elapsed < 60.0 else 1.5
        time.sleep(sleep_sec)

    _record_session_playtime(exe_base, time.time() - start_time, game_path=game_path)
    logger.info("=== CENTINELA FINALIZADO LIMPIAMENTE ===")

if __name__ == "__main__":
    main()
