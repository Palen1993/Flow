"""
GameFlow Launcher • iPod Cover Flow 3D
Punto de entrada principal del lanzador.
Mantiene compatibilidad total con run.bat y gamepad_watcher.pyw.
"""
import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import ctypes
import customtkinter as ctk

from app import App
from core.system import ensure_admin

# Re-exportaciones para compatibilidad
from core.system import get_monitors, is_admin, move_window_to_monitor
from core.launcher import launch_game_thread
from ui.coverflow_canvas import CoverFlowCanvas
from ui.dropdowns import FloatingGlassDropdown, GlassDropdownButton, FloatingGlassMenu
from ui.dialogs import (
    AddEditGameDialog, ScanResultsDialog, SelectGameToEditDialog,
    GamepadConfigDialog, ConfirmExitDialog, CoverPickerDialog
)

_GLOBAL_LAUNCHER_MUTEX = None

def acquire_single_instance_mutex():
    """Garantiza que solo pueda existir una única instancia del lanzador ejecutándose a la vez."""
    global _GLOBAL_LAUNCHER_MUTEX
    kernel32 = ctypes.windll.kernel32
    mutex_name = "Local\\GameFlowLauncherAppMutex"
    h_mutex = kernel32.CreateMutexW(None, False, mutex_name)
    last_err = kernel32.GetLastError()
    if last_err == 183:  # ERROR_ALREADY_EXISTS
        return None
    _GLOBAL_LAUNCHER_MUTEX = h_mutex
    return h_mutex

def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("gameflow.launcher.liquidglass.v1")
    except Exception:
        pass

    _mutex = acquire_single_instance_mutex()
    if not _mutex:
        print("[Lanzador] Ya existe una instancia activa. Trayendo al frente y cerrando duplicado.")
        try:
            from gamepad_watcher import find_launcher_process, focus_launcher_window
            proc = find_launcher_process()
            if proc:
                focus_launcher_window(proc.pid)
        except Exception:
            pass
        sys.exit(0)

    ensure_admin()
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass
        
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    app = App()
    try:
        app.mainloop()
    finally:
        try:
            ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass

if __name__ == "__main__":
    main()
