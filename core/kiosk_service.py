"""
GameFlow - Servicio de Modo Kiosco y Shell de Consola en Windows
================================================================
Permite transformar un PC, consola portátil (ROG Ally, Steam Deck, Legion Go) o bartop arcade
en una consola de videojuegos dedicada, sustituyendo el shell de Windows (explorer.exe) por GameFlow.

Funcionalidades:
1. Verificación del estado actual del shell de Windows (Default vs GameFlow).
2. Activación segura del Modo Kiosco (HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon\\Shell).
3. Desactivación y restauración limpia a explorer.exe en cualquier momento.
4. Activación/Desactivación de inicio automático con Windows (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).
5. Lanzamiento bajo demanda de Windows Explorer (explorer.exe) para acceder al escritorio sin desinstalar el modo kiosco.
6. Aislamiento total multiplataforma mediante core.platform_layer (funciona en CI y Linux sin errores).
"""

import os
import sys
import subprocess
from typing import Dict, Any, Tuple, Optional

try:
    from core.platform_layer import winreg, is_windows
    from core.logger import get_logger
    logger = get_logger("KioskService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.KioskService")
    is_windows = lambda: sys.platform == "win32"
    winreg = None


WINLOGON_SUBKEY = r"Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SHELL_VALUE_NAME = "Shell"
RUN_VALUE_NAME = "GameFlowLauncher"


def get_launcher_executable_path() -> str:
    """Devuelve la ruta absoluta al ejecutable de GameFlow o al comando pythonw de arranque."""
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
        return f'"{exe_path}"'
    else:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lanzador_py = os.path.join(base_dir, "lanzador.py")
        # Preferir pythonw si existe para evitar ventana de consola negra
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.isfile(pythonw):
            pythonw = sys.executable
        return f'"{pythonw}" "{lanzador_py}"'


def is_kiosk_shell_active() -> bool:
    """Indica si GameFlow está registrado como el Shell principal del usuario actual."""
    if not is_windows() or winreg is None:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINLOGON_SUBKEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, SHELL_VALUE_NAME)
            val_clean = str(val).strip().lower()
            return bool(val_clean and "explorer.exe" not in val_clean and ("gameflow" in val_clean or "lanzador" in val_clean))
    except (FileNotFoundError, OSError):
        return False
    except Exception as e:
        logger.debug(f"Error consultando Shell en Winlogon: {e}")
        return False


def get_current_shell_command() -> str:
    """Devuelve el comando Shell configurado en el registro para el usuario actual (o 'explorer.exe' si es por defecto)."""
    if not is_windows() or winreg is None:
        return "explorer.exe"

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINLOGON_SUBKEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, SHELL_VALUE_NAME)
            return str(val).strip() if val else "explorer.exe"
    except Exception:
        return "explorer.exe"


def enable_kiosk_shell() -> Tuple[bool, str]:
    """
    Configura GameFlow como el Shell de Windows en HKCU\\...\\Winlogon.
    Al iniciar sesión en Windows, arrancará GameFlow directamente en lugar de la barra de tareas y escritorio.
    """
    if not is_windows() or winreg is None:
        return False, "El Modo Kiosco solo está disponible en sistemas Windows."

    cmd = get_launcher_executable_path()
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WINLOGON_SUBKEY) as key:
            winreg.SetValueEx(key, SHELL_VALUE_NAME, 0, winreg.REG_SZ, cmd)
        logger.info(f"Modo Kiosco activado con éxito. Shell = {cmd}")
        return True, "Modo Kiosco activado con éxito. GameFlow se iniciará como shell principal de Windows al encender el equipo o iniciar sesión."
    except Exception as e:
        logger.error(f"Error activando Modo Kiosco en registro: {e}", exc_info=True)
        return False, f"No se pudo escribir en el registro de Windows: {e}"


def disable_kiosk_shell() -> Tuple[bool, str]:
    """
    Restaura el Shell estándar de Windows (elimina la entrada en HKCU para que Windows use explorer.exe).
    """
    if not is_windows() or winreg is None:
        return True, "Modo Kiosco desactivado."

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINLOGON_SUBKEY, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, SHELL_VALUE_NAME)
            except FileNotFoundError:
                pass
        logger.info("Modo Kiosco desactivado con éxito. Shell restaurado al escritorio tradicional (explorer.exe).")
        return True, "Modo Kiosco desactivado. El escritorio tradicional de Windows (explorer.exe) ha sido restaurado."
    except Exception as e:
        logger.error(f"Error desactivando Modo Kiosco en registro: {e}", exc_info=True)
        return False, f"Error al restaurar el shell de Windows: {e}"


def is_autostart_active() -> bool:
    """Comprueba si GameFlow está configurado para iniciar automáticamente con Windows (Run key)."""
    if not is_windows() or winreg is None:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_SUBKEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return bool(val and ("gameflow" in str(val).lower() or "lanzador" in str(val).lower()))
    except Exception:
        return False


def set_autostart(enable: bool) -> Tuple[bool, str]:
    """Habilita o deshabilita el inicio automático de GameFlow junto a Windows (HKCU\\...\\Run)."""
    if not is_windows() or winreg is None:
        return False, "La opción de inicio automático solo está disponible en Windows."

    try:
        if enable:
            cmd = get_launcher_executable_path()
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_SUBKEY) as key:
                winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, cmd)
            logger.info(f"Inicio automático con Windows habilitado: {cmd}")
            return True, "Inicio automático con Windows habilitado."
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_SUBKEY, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass
            logger.info("Inicio automático con Windows deshabilitado.")
            return True, "Inicio automático con Windows deshabilitado."
    except Exception as e:
        logger.error(f"Error modificando inicio automático en registro: {e}", exc_info=True)
        return False, f"Error modificando el registro de inicio: {e}"


def launch_windows_explorer() -> Tuple[bool, str]:
    """
    Inicia el proceso explorer.exe para mostrar la barra de tareas y el escritorio tradicional de Windows
    cuando se está en Modo Kiosco.
    """
    if not is_windows():
        return False, "Función solo disponible en sistemas Windows."

    try:
        # Verificar si explorer.exe ya está en ejecución
        import psutil
        for p in psutil.process_iter(['name']):
            if (p.info.get('name') or '').lower() == 'explorer.exe':
                return True, "El Explorador de Windows ya está en ejecución."
    except Exception:
        pass

    try:
        subprocess.Popen(["explorer.exe"])
        logger.info("Explorador de Windows (explorer.exe) lanzado con éxito.")
        return True, "Escritorio de Windows iniciado."
    except Exception as e:
        logger.error(f"Error lanzando explorer.exe: {e}", exc_info=True)
        return False, f"No se pudo iniciar explorer.exe: {e}"


def get_kiosk_status() -> Dict[str, Any]:
    """Devuelve un resumen del estado del sistema Kiosco y arranque."""
    return {
        "is_windows": is_windows(),
        "kiosk_active": is_kiosk_shell_active(),
        "autostart_active": is_autostart_active(),
        "current_shell": get_current_shell_command(),
        "launcher_cmd": get_launcher_executable_path()
    }
