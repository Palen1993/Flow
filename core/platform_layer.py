"""
Capa de Abstracción Multiplataforma y Mocks para GameFlow.

Aísla completamente las dependencias nativas del sistema operativo (Win32, pywin32, winreg, winsound, XInput)
permitiendo que el núcleo de la aplicación, el motor de carátulas, la biblioteca y las suites de pruebas unitarias
se ejecuten de manera 100% determinista tanto en Windows como en entornos Linux, macOS y flujos de CI.
"""

import os
import sys
import ctypes
from typing import List, Dict, Any, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Detección de Plataforma
# ---------------------------------------------------------------------------

def is_windows() -> bool:
    """Indica si el entorno actual es Windows nativo."""
    return sys.platform == "win32" or sys.platform.startswith("win")

def is_linux() -> bool:
    """Indica si el entorno actual es Linux."""
    return sys.platform.startswith("linux")

def is_macos() -> bool:
    """Indica si el entorno actual es macOS (Darwin)."""
    return sys.platform == "darwin"


# ---------------------------------------------------------------------------
# Mocks / Shims de Módulos Win32 para Entornos no Windows o Sin pywin32
# ---------------------------------------------------------------------------

class _Win32ConShim:
    """Constantes comunes de la API de Windows."""
    SW_SHOWMINIMIZED = 2
    SW_RESTORE = 9
    GWL_STYLE = -16
    GWL_EXSTYLE = -20
    WS_POPUP = 0x80000000
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_SYSMENU = 0x00080000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOPMOST = 0x00000008

    SWP_NOZORDER = 0x0004
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001

    HWND_TOP = 0
    HWND_TOPMOST = -1

    MONITOR_DEFAULTTONEAREST = 2
    MONITOR_DEFAULTTOPRIMARY = 1
    MONITORINFOF_PRIMARY = 1

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010


class _Win32GuiShim:
    """Shim seguro para funciones de win32gui."""
    @staticmethod
    def GetWindowPlacement(hwnd):
        return (0, 1, (-1, -1), (-1, -1), (0, 0, 1920, 1080))

    @staticmethod
    def ShowWindow(hwnd, cmd):
        return True

    @staticmethod
    def GetWindowLong(hwnd, index):
        return 0

    @staticmethod
    def SetWindowLong(hwnd, index, val):
        return 0

    @staticmethod
    def SetWindowPos(hwnd, insert_after, x, y, cx, cy, flags):
        return True

    @staticmethod
    def BringWindowToTop(hwnd):
        return True

    @staticmethod
    def SetForegroundWindow(hwnd):
        return True

    @staticmethod
    def GetDC(hwnd):
        return 0

    @staticmethod
    def ReleaseDC(hwnd, hdc):
        return 1

    @staticmethod
    def DrawIconEx(*args, **kwargs):
        return True

    @staticmethod
    def DeleteObject(handle):
        return True

    @staticmethod
    def EnumWindows(callback, extra):
        return True

    @staticmethod
    def GetWindowText(hwnd):
        return ""

    @staticmethod
    def IsWindowVisible(hwnd):
        return False


class _Win32ApiShim:
    """Shim seguro para funciones de win32api."""
    @staticmethod
    def GetCursorPos():
        return (0, 0)

    @staticmethod
    def MonitorFromWindow(hwnd, flags):
        return 1

    @staticmethod
    def MonitorFromPoint(pt, flags):
        return 1

    @staticmethod
    def GetMonitorInfo(hmon):
        return {
            "Monitor": (0, 0, 1920, 1080),
            "Work": (0, 0, 1920, 1040),
            "Flags": 1,
            "Device": "\\\\.\\DISPLAY1"
        }

    @staticmethod
    def EnumDisplayMonitors(hdc=None, clip=None):
        return [(1, 0, (0, 0, 1920, 1080))]

    @staticmethod
    def EnumDisplayDevices(device_name=None, dev_num=0, flags=0):
        class _Dev:
            DeviceName = "\\\\.\\DISPLAY1"
            DeviceString = "Generic Display"
            StateFlags = 1
            DeviceID = "MONITOR\\DEF0001"
            DeviceKey = ""
        if dev_num == 0:
            return _Dev()
        raise Exception("No more display devices")

    @staticmethod
    def GetLogicalDriveStrings():
        if is_windows():
            return "C:\\\x00"
        return "/\x00"


class _Win32UiShim:
    """Shim seguro para win32ui."""
    @staticmethod
    def CreateDCFromHandle(hdc):
        class _DC:
            def CreateCompatibleDC(self):
                return _DC()
            def SelectObject(self, obj):
                return None
            def GetHandleOutput(self):
                return 0
            def DeleteDC(self):
                return True
        return _DC()

    @staticmethod
    def CreateBitmap():
        class _Bmp:
            def CreateCompatibleBitmap(self, hdc, w, h):
                pass
            def GetInfo(self):
                return {"bmWidth": 32, "bmHeight": 32}
            def GetBitmapBits(self, flag):
                return b"\x00" * (32 * 32 * 4)
            def GetHandle(self):
                return 1
        return _Bmp()


class _Win32ProcessShim:
    """Shim seguro para win32process."""
    @staticmethod
    def GetWindowThreadProcessId(hwnd):
        return (0, os.getpid())


class _WinRegShim:
    """Shim seguro para el módulo winreg."""
    HKEY_CURRENT_USER = 0x80000001
    HKEY_LOCAL_MACHINE = 0x80000002
    KEY_READ = 0x20019
    KEY_SET_VALUE = 0x0002
    REG_SZ = 1
    REG_DWORD = 4

    class _KeyContext:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def Close(self):
            pass

    @classmethod
    def OpenKey(cls, key, subkey, reserved=0, access=0):
        return cls._KeyContext()

    @classmethod
    def CreateKey(cls, key, subkey):
        return cls._KeyContext()

    @classmethod
    def DeleteKey(cls, key, subkey):
        pass

    @classmethod
    def DeleteValue(cls, key, value):
        pass

    @classmethod
    def SetValueEx(cls, key, value_name, reserved, type_, value):
        pass

    @classmethod
    def QueryValueEx(cls, key, value_name):
        return ("", cls.REG_SZ)

    @classmethod
    def QueryInfoKey(cls, key):
        return (0, 0, 0)

    @classmethod
    def EnumKey(cls, key, index):
        raise OSError("No more keys")


class _WinSoundShim:
    """Shim seguro para el módulo winsound."""
    SND_FILENAME = 0x00020000
    SND_ASYNC = 0x00000001
    SND_NODEFAULT = 0x00000002
    SND_MEMORY = 0x00000004

    @staticmethod
    def PlaySound(sound, flags):
        return True


# ---------------------------------------------------------------------------
# Exportación Segura de Módulos (Nativo vs Shim)
# ---------------------------------------------------------------------------

try:
    if is_windows():
        import win32con
    else:
        win32con = _Win32ConShim()
except ImportError:
    win32con = _Win32ConShim()

try:
    if is_windows():
        import win32gui
    else:
        win32gui = _Win32GuiShim()
except ImportError:
    win32gui = _Win32GuiShim()

try:
    if is_windows():
        import win32api
    else:
        win32api = _Win32ApiShim()
except ImportError:
    win32api = _Win32ApiShim()

try:
    if is_windows():
        import win32ui
    else:
        win32ui = _Win32UiShim()
except ImportError:
    win32ui = _Win32UiShim()

try:
    if is_windows():
        import win32process
    else:
        win32process = _Win32ProcessShim()
except ImportError:
    win32process = _Win32ProcessShim()

try:
    if is_windows():
        import winreg
    else:
        winreg = _WinRegShim
except ImportError:
    winreg = _WinRegShim

try:
    if is_windows():
        import winsound
    else:
        winsound = _WinSoundShim()
except ImportError:
    winsound = _WinSoundShim()


# ---------------------------------------------------------------------------
# Utilidades de Sistema Multiplataforma
# ---------------------------------------------------------------------------

def get_system_drives() -> List[str]:
    """
    Retorna la lista de unidades de almacenamiento o puntos de montaje accesibles
    en el sistema de forma unificada (ej: ['C:\\', 'D:\\'] en Windows o ['/'] en Linux/macOS).
    """
    drives: List[str] = []
    if is_windows():
        try:
            raw = win32api.GetLogicalDriveStrings()
            drives = [d for d in raw.split("\x00") if d]
        except Exception:
            pass
        if not drives:
            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                candidate = f"{letter}:\\"
                if os.path.exists(candidate):
                    drives.append(candidate)
        if not drives:
            drives = ["C:\\"]
    else:
        drives = ["/"]
        for mount in ["/media", "/mnt", "/Volumes"]:
            if os.path.isdir(mount):
                try:
                    for entry in os.listdir(mount):
                        full_p = os.path.join(mount, entry)
                        if os.path.isdir(full_p):
                            drives.append(full_p)
                except Exception:
                    pass
    return drives


def safe_set_dpi_awareness() -> bool:
    """Configura Per-Monitor DPI Awareness de forma segura sin lanzar excepciones."""
    if not is_windows():
        return False
    try:
        windll = getattr(ctypes, "windll", None)
        if not windll:
            return False
        shcore = getattr(windll, "shcore", None)
        if shcore and hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness(2)
            return True
        user32 = getattr(windll, "user32", None)
        if user32 and hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
            return True
    except Exception:
        pass
    return False


def safe_set_app_user_model_id(app_id: str) -> bool:
    """Registra el AppUserModelID para agrupar la ventana en la barra de tareas de Windows."""
    if not is_windows():
        return False
    try:
        windll = getattr(ctypes, "windll", None)
        if windll and hasattr(windll, "shell32") and hasattr(windll.shell32, "SetCurrentProcessExplicitAppUserModelID"):
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
            return True
    except Exception:
        pass
    return False


def safe_play_sound(sound_path_or_data: Union[str, bytes], flags: int = 0) -> bool:
    """Reproduce un efecto de sonido sin bloquear y de forma tolerante a fallos multiplataforma."""
    if not winsound:
        return False
    try:
        default_flags = winsound.SND_ASYNC | winsound.SND_NODEFAULT
        if isinstance(sound_path_or_data, bytes):
            default_flags |= getattr(winsound, "SND_MEMORY", 0x0004)
        else:
            default_flags |= getattr(winsound, "SND_FILENAME", 0x00020000)
        winsound.PlaySound(sound_path_or_data, flags or default_flags)
        return True
    except Exception:
        return False
