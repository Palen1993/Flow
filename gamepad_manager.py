import os
import sys
import time
import json
import subprocess
import ctypes
from ctypes import wintypes
from core.platform_layer import winreg, is_windows
from typing import Tuple, Dict, Any, List, Optional

# -------------------------------------------------------------
# Constantes y Configuración de Mando
# -------------------------------------------------------------
try:
    from core.config import GAMEPAD_CONFIG_FILE
except Exception:
    GAMEPAD_CONFIG_FILE = os.path.join(
        os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__)),
        "gamepad_config.json"
    )
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VAL_NAME = "GameFlowGamepadWatcher"

DEFAULT_GAMEPAD_CONFIG = {
    "selected_controller_id": "any",
    "selected_controller_name": "Cualquier Mando Conectado (Universal)",
    "auto_launch_on_connect": True,
    "launch_on_xbox_button": True,
    "auto_fullscreen": False,
    "start_in_mini_mode": True,
    "enable_controller_nav": True,
    "enable_haptics": True,
    "enable_sound_fx": True,
    "start_with_windows": False,
    "close_on_game_launch": True
}

# Caché en memoria de configuración de mando para evitar lecturas de disco repetitivas
_CONFIG_CACHE: Optional[Dict[str, Any]] = None
_CONFIG_MTIME: float = -1.0
_LAST_GAMEBAR_STATE: Optional[bool] = None

# Seguimiento en tiempo real del último dispositivo/ranura activo detectado
_LAST_ACTIVE_XINPUT_SLOT: Optional[int] = None
_LAST_ACTIVE_DEVICE_TYPE: Optional[str] = None
_LAST_ACTIVE_DEVICE_NAME: str = "Ninguno"

def get_pythonw_executable() -> str:
    """Obtiene la ruta absoluta a pythonw.exe, priorizando el entorno virtual del proyecto."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_pythonw = os.path.join(base_dir, "venv", "Scripts", "pythonw.exe")
    if os.path.isfile(venv_pythonw):
        return venv_pythonw
    cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.isfile(cand):
        return cand
    return sys.executable

def ensure_gamebar_nexus_disabled(force: bool = False):
    """
    Configura el registro de Windows para que el botón Xbox abra directamente el lanzador,
    deshabilite la Game Bar y suprima el diálogo 'Obtener una aplicación para abrir este vínculo de ms-gamebar'.
    Respeta la opción 'launch_on_xbox_button' y evita escrituras redundantes en el registro.
    """
    global _LAST_GAMEBAR_STATE
    cfg = load_gamepad_config()
    want_xbox_hook = bool(cfg.get("launch_on_xbox_button", True))
    if not force and _LAST_GAMEBAR_STATE == want_xbox_hook:
        return
    _LAST_GAMEBAR_STATE = want_xbox_hook

    if not want_xbox_hook:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\ms-gamebar\shell\open\command")
        except Exception:
            pass
        return

    try:
        # Permitir que el botón Nexus/Xbox invoque el protocolo registrado ms-gamebar
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar") as k:
            winreg.SetValueEx(k, "UseNexusForGameBarEnabled", 0, winreg.REG_DWORD, 1)
    except Exception:
        pass
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\GameDVR") as k:
            winreg.SetValueEx(k, "AppCaptureEnabled", 0, winreg.REG_DWORD, 0)
    except Exception:
        pass
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"System\GameConfigStore") as k:
            winreg.SetValueEx(k, "GameDVR_Enabled", 0, winreg.REG_DWORD, 0)
    except Exception:
        pass
    try:
        # Registrar el protocolo ms-gamebar para que al pulsar el botón Xbox se ejecute el watcher/lanzador
        # en lugar de mostrar el aviso de Microsoft Store
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        watcher_exe = os.path.join(base_dir, "gamepad_watcher.exe")
        if getattr(sys, 'frozen', False) and os.path.isfile(watcher_exe):
            cmd = f'"{watcher_exe}" "%1"'
        else:
            pythonw = get_pythonw_executable()
            watcher_path = os.path.join(base_dir, "gamepad_watcher.pyw")
            cmd = f'"{pythonw}" "{watcher_path}" "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\ms-gamebar") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:ms-gamebar Protocol")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\ms-gamebar\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    except Exception:
        pass

def ensure_watcher_running():
    """Asegura que el proceso en segundo plano gamepad_watcher esté activo sin duplicarse."""
    if os.environ.get("GAMEFLOW_DISABLE_WATCHER") == "1":
        return

    try:
        import psutil
        for p in psutil.process_iter(['name', 'cmdline']):
            try:
                name = (p.info.get('name') or '').lower()
                if name in ['gamepad_watcher.exe', 'gamepad_watcher']:
                    return
                if name not in ['python.exe', 'pythonw.exe']:
                    continue
                cmd = p.info.get('cmdline') or []
                if any(str(arg).lower().endswith("gamepad_watcher.pyw") for arg in cmd):
                    return
            except Exception:
                pass
    except Exception:
        pass
        
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        watcher_exe = os.path.join(base_dir, "gamepad_watcher.exe")
        flags = (0x08000000 | 0x00000200) if os.name == 'nt' else 0
        popen_kwargs = {
            "cwd": base_dir,
            "creationflags": flags,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "close_fds": True,
        }

        if getattr(sys, 'frozen', False) and os.path.isfile(watcher_exe):
            subprocess.Popen([watcher_exe], **popen_kwargs)
            return

        watcher_path = os.path.join(base_dir, "gamepad_watcher.pyw")
        if not os.path.isfile(watcher_path):
            return
            
        pythonw = get_pythonw_executable()
        subprocess.Popen([pythonw, watcher_path], **popen_kwargs)
    except Exception:
        pass

def force_foreground_window(hwnd: int, keep_topmost: Optional[bool] = None) -> bool:
    """
    Fuerza que la ventana 'hwnd' pase al frente absoluto e interactivo,
    superando el bloqueo de primer plano de Windows (AttachThreadInput + HWND_TOPMOST).
    Restaura el estado no-topmost original cuando corresponde para no bloquear otras ventanas en modo completo.
    """
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return False
    user32 = windll.user32
    kernel32 = windll.kernel32

    root = user32.GetAncestor(hwnd, 2)  # GA_ROOT
    if root:
        hwnd = root

    if not user32.IsWindow(hwnd):
        return False

    GWL_EXSTYLE = -20
    WS_EX_TOPMOST = 0x00000008
    was_topmost = bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)
    should_stay_topmost = was_topmost if keep_topmost is None else keep_topmost

    # Restaurar si está minimizada o icónica
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    else:
        user32.ShowWindow(hwnd, 5)  # SW_SHOW

    fore_hwnd = user32.GetForegroundWindow()
    fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
    curr_thread = kernel32.GetCurrentThreadId()

    # 1. Simular pulsación de Alt (desbloquea permiso de primer plano en Windows)
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)

    # 2. AttachThreadInput para heredar permisos de foco del proceso en primer plano
    attached = False
    if fore_thread != curr_thread and fore_thread != 0:
        try:
            attached = bool(user32.AttachThreadInput(curr_thread, fore_thread, True))
        except Exception:
            attached = False

    try:
        # 3. Forzar HWND_TOPMOST (-1) para colocarla por encima de cualquier juego / app
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if not should_stay_topmost:
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    finally:
        if attached:
            try:
                user32.AttachThreadInput(curr_thread, fore_thread, False)
            except Exception:
                pass

    return True

def load_gamepad_config() -> dict:
    """Carga la configuración del mando con caché en memoria validada por mtime para 0 I/O redundante."""
    global _CONFIG_CACHE, _CONFIG_MTIME
    if os.path.isfile(GAMEPAD_CONFIG_FILE):
        try:
            mtime = os.path.getmtime(GAMEPAD_CONFIG_FILE)
            if _CONFIG_CACHE is not None and mtime == _CONFIG_MTIME:
                return _CONFIG_CACHE.copy()
            with open(GAMEPAD_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg = DEFAULT_GAMEPAD_CONFIG.copy()
                cfg.update(data)
                _CONFIG_CACHE = cfg
                _CONFIG_MTIME = mtime
                return cfg.copy()
        except Exception as e:
            print(f"Error cargando {GAMEPAD_CONFIG_FILE}: {e}")
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE.copy()
    return DEFAULT_GAMEPAD_CONFIG.copy()

def save_gamepad_config(cfg: dict) -> bool:
    global _CONFIG_CACHE, _CONFIG_MTIME
    tmp_file = f"{GAMEPAD_CONFIG_FILE}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, GAMEPAD_CONFIG_FILE)
        merged = DEFAULT_GAMEPAD_CONFIG.copy()
        merged.update(cfg)
        _CONFIG_CACHE = merged
        try:
            _CONFIG_MTIME = os.path.getmtime(GAMEPAD_CONFIG_FILE)
        except Exception:
            pass
        ensure_gamebar_nexus_disabled(force=True)
        return True
    except Exception as e:
        print(f"Error guardando {GAMEPAD_CONFIG_FILE}: {e}")
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
        return False

def is_windows_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_READ) as k:
            try:
                winreg.QueryValueEx(k, STARTUP_VAL_NAME)
                return True
            except Exception:
                winreg.QueryValueEx(k, "GameFlowSteamOSWatcher")
                return True
    except Exception:
        return False

def set_windows_startup(enable: bool) -> bool:
    base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    watcher_exe = os.path.join(base_dir, "gamepad_watcher.exe")
    if getattr(sys, 'frozen', False) and os.path.isfile(watcher_exe):
        cmd = f'"{watcher_exe}"'
    else:
        watcher_script = os.path.join(base_dir, "gamepad_watcher.pyw")
        pythonw = get_pythonw_executable()
        cmd = f'"{pythonw}" "{watcher_script}"'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY, 0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, "GameFlowSteamOSWatcher")
            except Exception:
                pass
            if enable:
                winreg.SetValueEx(k, STARTUP_VAL_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, STARTUP_VAL_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"Error configurando inicio de Windows: {e}")
        return False

# -------------------------------------------------------------
# Detección de Mandos Sincronizados en Windows (Bluetooth / HID)
# -------------------------------------------------------------
def get_paired_gamepads() -> list:
    """Devuelve la lista de mandos sincronizados o conocidos en Windows."""
    controllers = [
        {
            "id": "any",
            "name": "✨ Cualquier Mando Conectado (Universal)",
            "type": "any",
            "desc": "Detecta automáticamente DualSense, Xbox o cualquier mando al encenderlo"
        }
    ]
    
    # 1. Buscar en registros de Bluetooth de Windows
    seen_ids = set()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices") as k:
            num = winreg.QueryInfoKey(k)[0]
            for i in range(num):
                addr = winreg.EnumKey(k, i)
                try:
                    with winreg.OpenKey(k, addr) as sk:
                        raw_name, _ = winreg.QueryValueEx(sk, "Name")
                        name = raw_name.decode("utf-8", errors="ignore").rstrip("\x00")
                        keywords = ["controller", "dualsense", "dualshock", "xbox", "gamepad", "wireless", "joystick", "8bitdo"]
                        if any(kw in name.lower() for kw in keywords):
                            seen_ids.add(addr.lower())
                            controllers.append({
                                "id": addr,
                                "name": f"🎮 {name}",
                                "type": "bluetooth",
                                "desc": f"Dispositivo Bluetooth emparejado (MAC: {addr})"
                            })
                except Exception:
                    pass
    except Exception:
        pass

    # 2. Opciones universales por tecnología
    controllers.append({
        "id": "xinput_all",
        "name": "🎮 Mandos Xbox / XInput (Inalámbrico o USB)",
        "type": "xinput",
        "desc": "Xbox Series X|S, Xbox One, Xbox 360 o compatibles"
    })
    controllers.append({
        "id": "directinput_all",
        "name": "🎮 Mandos PlayStation / DirectInput (DualSense, DualShock)",
        "type": "directinput",
        "desc": "DualSense, DualShock 4 o mandos genéricos Bluetooth/USB"
    })
    return controllers

# -------------------------------------------------------------
# XInput (Xbox & Mandos compatibles)
# -------------------------------------------------------------
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", wintypes.SHORT),
        ("sThumbLY", wintypes.SHORT),
        ("sThumbRX", wintypes.SHORT),
        ("sThumbRY", wintypes.SHORT),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XINPUT_GAMEPAD)
    ]

_xinput_dll = None
_xinput_get_state_ex = None
if hasattr(ctypes, "windll"):
    for _dll in ["xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"]:
        try:
            _xinput_dll = ctypes.windll.LoadLibrary(_dll)
            try:
                # Ordinal 100 es la función no documentada XInputGetStateEx que incluye el botón Xbox / Guide (0x0400)
                _xinput_get_state_ex = _xinput_dll[100]
            except Exception:
                _xinput_get_state_ex = None
            break
        except Exception:
            pass

# -------------------------------------------------------------
# WinMM (DirectInput, DualSense, DualShock y Bluetooth)
# -------------------------------------------------------------
class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwFlags", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwXpos", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwYpos", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwZpos", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwRpos", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwUpos", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwVpos", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwButtons", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwButtonNumber", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwPOV", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwReserved1", wintypes.DWORD if wintypes else ctypes.c_uint32),
        ("dwReserved2", wintypes.DWORD if wintypes else ctypes.c_uint32)
    ]

class JOYCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", ctypes.c_ushort),
        ("wPid", ctypes.c_ushort),
        ("szPname", ctypes.c_wchar * 32),
        ("wXmin", ctypes.c_uint), ("wXmax", ctypes.c_uint),
        ("wYmin", ctypes.c_uint), ("wYmax", ctypes.c_uint),
        ("wZmin", ctypes.c_uint), ("wZmax", ctypes.c_uint),
        ("wNumButtons", ctypes.c_uint),
        ("wPeriodMin", ctypes.c_uint), ("wPeriodMax", ctypes.c_uint),
        ("wRmin", ctypes.c_uint), ("wRmax", ctypes.c_uint),
        ("wUmin", ctypes.c_uint), ("wUmax", ctypes.c_uint),
        ("wVmin", ctypes.c_uint), ("wVmax", ctypes.c_uint),
        ("wCaps", ctypes.c_uint),
        ("wMaxAxes", ctypes.c_uint), ("wNumAxes", ctypes.c_uint),
        ("wMaxButtons", ctypes.c_uint),
        ("szRegKey", ctypes.c_wchar * 32),
        ("szOEMVxD", ctypes.c_wchar * 260),
    ]

class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [("hDevice", wintypes.HANDLE if wintypes else ctypes.c_void_p), ("dwType", wintypes.DWORD if wintypes else ctypes.c_uint32)]

_windll = getattr(ctypes, "windll", None)
_winmm = getattr(_windll, "winmm", None)
_user32 = getattr(_windll, "user32", None)
JOY_RETURNALL = 0x000000FF

def get_connected_controller_family(cfg: Optional[Dict[str, Any]] = None) -> str:
    """
    Determina en tiempo real la familia del mando conectado ('xbox' o 'playstation').
    1. Inspecciona los dispositivos HID activos en RawInput (0x054C = Sony PlayStation, 0x045E = Microsoft Xbox),
       detectando DualSense/DualShock incluso si usan envoltorio XInput o DS4Windows.
    2. Comprueba WinMM joyGetDevCapsW y el estado activo del mando.
    3. Usa la preferencia de configuración como respaldo si no hay mando conectado.
    Si hay un mando PRINCIPAL fijado, la familia se decide únicamente por él (el secundario no cambia los iconos).
    """
    primary = globals().get("_PRIMARY_DEVICE")
    if primary is not None and primary[0] == "winmm":
        return "playstation"
    primary_is_xinput = primary is not None and primary[0] == "xinput"
    has_winmm_secondary = any(d[0] == "winmm" for d in globals().get("_CONNECT_ORDER", []))

    # 1. Detección directa por hardware HID conectado en tiempo real (RawInput < 0.05 ms)
    try:
        n_devs = wintypes.UINT(0)
        _user32.GetRawInputDeviceList(None, ctypes.byref(n_devs), ctypes.sizeof(RAWINPUTDEVICELIST))
        if n_devs.value > 0:
            arr = (RAWINPUTDEVICELIST * n_devs.value)()
            _user32.GetRawInputDeviceList(arr, ctypes.byref(n_devs), ctypes.sizeof(RAWINPUTDEVICELIST))
            raw_has_sony = False
            raw_has_xbox = False
            for item in arr:
                if item.dwType == 2:  # RIM_TYPEHID
                    sz = wintypes.UINT(0)
                    _user32.GetRawInputDeviceInfoW(item.hDevice, 0x20000007, None, ctypes.byref(sz))
                    if sz.value > 0:
                        buf = ctypes.create_unicode_buffer(sz.value)
                        _user32.GetRawInputDeviceInfoW(item.hDevice, 0x20000007, buf, ctypes.byref(sz))
                        path_up = buf.value.upper()
                        if "054C" in path_up:
                            raw_has_sony = True
                        elif "045E" in path_up and ("IG_" in path_up or "PID_02" in path_up or "PID_0B" in path_up):
                            raw_has_xbox = True
            # Principal XInput: solo es PlayStation si es un DualSense/DualShock envuelto (DS4Windows),
            # es decir, hay hardware Sony pero no aparece como mando WinMM independiente.
            if primary_is_xinput:
                return "playstation" if (raw_has_sony and not has_winmm_secondary) else "xbox"
            # Si hay un mando físico Sony (054C) conectado, priorizar PlayStation incluso si emula XInput (045E)
            if raw_has_sony:
                return "playstation"
            if raw_has_xbox:
                return "xbox"
    except Exception:
        pass

    if primary_is_xinput:
        return "xbox"

    # 2. Comprobar WinMM joyGetDevCapsW en dispositivos activos
    try:
        num_devs = min(8, _winmm.joyGetNumDevs())
        has_sony = False
        has_xbox = False
        for dev_id in range(num_devs):
            info = JOYINFOEX()
            info.dwSize = ctypes.sizeof(info)
            info.dwFlags = JOY_RETURNALL
            if _winmm.joyGetPosEx(dev_id, ctypes.byref(info)) == 0:
                caps = JOYCAPSW()
                if _winmm.joyGetDevCapsW(dev_id, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
                    if caps.wMid == 0x054C:
                        has_sony = True
                    elif caps.wMid == 0x045E:
                        has_xbox = True
        if has_sony:
            return "playstation"
        if has_xbox:
            return "xbox"
    except Exception:
        pass

    if _LAST_ACTIVE_DEVICE_TYPE == "directinput":
        return "playstation"

    # 3. Respaldo según perfil seleccionado en configuración
    if cfg is None:
        cfg = load_gamepad_config()
    sel_id = str(cfg.get("selected_controller_id", "any") or "any").lower()
    sel_name = str(cfg.get("selected_controller_name", "") or "").lower()
    ps_keywords = ("playstation", "dualsense", "dualshock", "ps4", "ps5", "sony")
    if sel_id == "directinput_all" or any(k in sel_name for k in ps_keywords):
        return "playstation"
    return "xbox"

# -------------------------------------------------------------
# Sondeo Unificado de Mandos
# -------------------------------------------------------------
def get_active_xinput_slot() -> Optional[int]:
    """Devuelve el índice de ranura XInput (0-3) del mando PRINCIPAL, o None si el principal no es XInput."""
    return _LAST_ACTIVE_XINPUT_SLOT


# -------------------------------------------------------------
# Gestión de Mando Principal / Secundario
# -------------------------------------------------------------
# El primer mando que se conecta es el PRINCIPAL: es el único que maneja la aplicación.
# Cualquier otro mando conectado después es SECUNDARIO: solo se lee su estado y batería.
# Si el principal se desconecta (más de PRIMARY_GRACE_S segundos), el siguiente en orden
# de conexión pasa a ser el principal.
PRIMARY_GRACE_S = 1.5
ENUM_INTERVAL_S = 1.0

# Lista ordenada por orden de conexión de dispositivos: ("xinput", slot) | ("winmm", dev_id)
_CONNECT_ORDER: List[Tuple[str, int]] = []
_PRIMARY_DEVICE: Optional[Tuple[str, int]] = None
_PRIMARY_LOST_AT: float = 0.0
_LAST_ENUM_TIME: float = 0.0
_LAST_ENUM_TARGET: str = ""
_WINMM_CAPS_CACHE: Dict[int, Tuple[int, int, str]] = {}

_EMPTY_STATE = {
    "left": False, "right": False, "up": False, "down": False,
    "a": False, "b": False, "x": False, "y": False,
    "lb": False, "rb": False, "lt": False, "rt": False,
    "start": False, "back": False,
    "guide": False,
    "raw_buttons": 0
}


def _read_xinput_slot(slot: int) -> Optional[Dict[str, Any]]:
    """Lee el estado de una ranura XInput. Devuelve None si no hay mando en esa ranura."""
    if not _xinput_dll:
        return None
    st = XINPUT_STATE()
    res = -1
    if _xinput_get_state_ex:
        try:
            res = _xinput_get_state_ex(slot, ctypes.byref(st))
        except Exception:
            res = -1
    if res != 0:
        try:
            res = _xinput_dll.XInputGetState(slot, ctypes.byref(st))
        except Exception:
            res = -1
    if res != 0:
        return None

    gp = st.Gamepad
    btns = gp.wButtons
    lx = gp.sThumbLX / 32767.0
    ly = gp.sThumbLY / 32767.0
    deadzone = 0.35
    return {
        "left": bool((btns & 0x0004) or (lx < -deadzone)),
        "right": bool((btns & 0x0008) or (lx > deadzone)),
        "up": bool((btns & 0x0001) or (ly > deadzone)),
        "down": bool((btns & 0x0002) or (ly < -deadzone)),
        "a": bool(btns & 0x1000),      # A / Cruz
        "b": bool(btns & 0x2000),      # B / Círculo
        "x": bool(btns & 0x4000),      # X / Cuadrado
        "y": bool(btns & 0x8000),      # Y / Triángulo
        "lb": bool(btns & 0x0100),     # LB / L1
        "rb": bool(btns & 0x0200),     # RB / R1
        "lt": bool(gp.bLeftTrigger > 120),
        "rt": bool(gp.bRightTrigger > 120),
        "start": bool(btns & 0x0010),  # Start / Options
        "back": bool(btns & 0x0020),   # Back / Share / Select
        "guide": bool(btns & 0x0400),  # Botón Xbox / Guide / Nexus
        "raw_buttons": btns
    }


def _read_winmm_dev(dev_id: int) -> Optional[Dict[str, Any]]:
    """Lee el estado de un dispositivo WinMM (DirectInput / PlayStation / Bluetooth)."""
    info = JOYINFOEX()
    info.dwSize = ctypes.sizeof(info)
    info.dwFlags = JOY_RETURNALL
    try:
        if _winmm.joyGetPosEx(dev_id, ctypes.byref(info)) != 0:
            return None
    except Exception:
        return None

    norm_x = (info.dwXpos - 32767) / 32767.0
    norm_y = (info.dwYpos - 32767) / 32767.0
    deadzone = 0.35

    pov = info.dwPOV
    pov_left = (pov == 27000 or (22500 <= pov <= 31500))
    pov_right = (pov == 9000 or (4500 <= pov <= 13500))
    pov_up = (pov == 0 or pov == 36000 or (0 <= pov <= 4500) or (31500 <= pov <= 36000))
    pov_down = (pov == 18000 or (13500 <= pov <= 22500))

    b = info.dwButtons
    # Mapeo DirectInput / DualSense estándar (bits únicos sin superposición):
    # Botón 1 (0x0001): Cuadrado / X     Botón 2 (0x0002): Cruz / A
    # Botón 3 (0x0004): Círculo / B      Botón 4 (0x0008): Triángulo / Y
    # Botón 5 (0x0010): L1 / LB          Botón 6 (0x0020): R1 / RB
    # Botón 7 (0x0040): L2 / LT          Botón 8 (0x0080): R2 / RT
    # Botón 9 (0x0100): Share / Back     Botón 10 (0x0200): Options / Start
    # Botón 13 (0x1000): PS / Guide
    return {
        "left": bool(norm_x < -deadzone or pov_left),
        "right": bool(norm_x > deadzone or pov_right),
        "up": bool(norm_y < -deadzone or pov_up),
        "down": bool(norm_y > deadzone or pov_down),
        "a": bool(b & 0x0002),       # Cruz (A)
        "b": bool(b & 0x0004),       # Círculo (B)
        "x": bool(b & 0x0001),       # Cuadrado (X)
        "y": bool(b & 0x0008),       # Triángulo (Y)
        "lb": bool(b & 0x0010),      # L1 (LB)
        "rb": bool(b & 0x0020),      # R1 (RB)
        "lt": bool(b & 0x0040),      # L2 (LT)
        "rt": bool(b & 0x0080),      # R2 (RT)
        "start": bool(b & 0x0200),   # Options (Start)
        "back": bool(b & 0x0100),    # Share (Back)
        "guide": bool(b & 0x1000),   # Botón PS / Guía
        "raw_buttons": b
    }


def _winmm_caps(dev_id: int) -> Tuple[int, int, str]:
    """Devuelve (fabricante, producto, nombre) de un dispositivo WinMM (cacheado)."""
    cached = _WINMM_CAPS_CACHE.get(dev_id)
    if cached is not None:
        return cached
    caps = JOYCAPSW()
    result = (0, 0, "")
    try:
        if _winmm.joyGetDevCapsW(dev_id, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            result = (int(caps.wMid), int(caps.wPid), str(caps.szPname or "").strip())
    except Exception:
        pass
    _WINMM_CAPS_CACHE[dev_id] = result
    return result


def _is_xinput_duplicate(dev_id: int) -> bool:
    """Los mandos Xbox/XInput también aparecen en WinMM: los descartamos para no contarlos dos veces."""
    mid, _pid, name = _winmm_caps(dev_id)
    low = name.lower()
    return mid == 0x045E or "xbox" in low or "xinput" in low


def _device_label(dev: Tuple[str, int]) -> str:
    kind, idx = dev
    if kind == "xinput":
        return f"Mando Xbox / XInput (Ranura {idx + 1})"
    mid, _pid, name = _winmm_caps(idx)
    if mid == 0x054C or any(k in name.lower() for k in ("dualsense", "dualshock", "wireless controller", "playstation")):
        return f"Mando PlayStation (Dispositivo {idx + 1})"
    if name:
        return f"{name} (Dispositivo {idx + 1})"
    return f"Mando DirectInput / Bluetooth (Dispositivo {idx + 1})"


def _device_family(dev: Optional[Tuple[str, int]]) -> Optional[str]:
    if dev is None:
        return None
    if dev[0] == "xinput":
        return "xbox"
    return "playstation"


def _enumerate_connected(target_id: str = "any") -> List[Tuple[str, int]]:
    """Lista todos los mandos conectados (sin duplicados XInput/WinMM) respetando el filtro de configuración."""
    found: List[Tuple[str, int]] = []
    use_x = target_id != "directinput_all"
    use_w = target_id != "xinput_all"
    if use_x and _xinput_dll:
        for slot in range(4):
            if _read_xinput_slot(slot) is not None:
                found.append(("xinput", slot))
    if use_w:
        try:
            num_devs = min(16, _winmm.joyGetNumDevs())
        except Exception:
            num_devs = 0
        has_xinput = any(k == "xinput" for k, _ in found)
        for dev_id in range(num_devs):
            if _read_winmm_dev(dev_id) is None:
                _WINMM_CAPS_CACHE.pop(dev_id, None)
                continue
            # Solo descartar duplicados si XInput está activo (si se filtra a DirectInput, un Xbox cuenta como WinMM)
            if use_x and has_xinput and _is_xinput_duplicate(dev_id):
                continue
            found.append(("winmm", dev_id))
    return found


def _update_connect_order(found: List[Tuple[str, int]]):
    """Mantiene la lista en orden de conexión: quita los desconectados y añade los nuevos al final."""
    global _CONNECT_ORDER
    found_set = set(found)
    _CONNECT_ORDER = [d for d in _CONNECT_ORDER if d in found_set]
    for d in found:
        if d not in _CONNECT_ORDER:
            _CONNECT_ORDER.append(d)


def _read_device(dev: Tuple[str, int]) -> Optional[Dict[str, Any]]:
    return _read_xinput_slot(dev[1]) if dev[0] == "xinput" else _read_winmm_dev(dev[1])


def _set_primary(dev: Optional[Tuple[str, int]]):
    global _PRIMARY_DEVICE, _LAST_ACTIVE_XINPUT_SLOT, _LAST_ACTIVE_DEVICE_TYPE, _LAST_ACTIVE_DEVICE_NAME
    _PRIMARY_DEVICE = dev
    if dev is None:
        _LAST_ACTIVE_XINPUT_SLOT = None
        _LAST_ACTIVE_DEVICE_TYPE = None
        _LAST_ACTIVE_DEVICE_NAME = "Ninguno"
    elif dev[0] == "xinput":
        _LAST_ACTIVE_XINPUT_SLOT = dev[1]
        _LAST_ACTIVE_DEVICE_TYPE = "xinput"
        _LAST_ACTIVE_DEVICE_NAME = _device_label(dev)
    else:
        _LAST_ACTIVE_XINPUT_SLOT = None
        _LAST_ACTIVE_DEVICE_TYPE = "directinput"
        _LAST_ACTIVE_DEVICE_NAME = _device_label(dev)


def get_primary_controller() -> Optional[Tuple[str, int]]:
    """Devuelve el identificador del mando principal actual (('xinput', slot) | ('winmm', dev_id)) o None."""
    return _PRIMARY_DEVICE


def poll_active_gamepad(target_id: str = "any") -> Tuple[bool, str, Dict[str, Any]]:
    """
    Sondea el mando PRINCIPAL (el primero que se conectó) y devuelve (conectado, nombre, botones).
    Los mandos secundarios NO controlan la aplicación: sus pulsaciones se ignoran.
    La enumeración completa de mandos se hace como máximo 1 vez por segundo para no penalizar el sondeo a 40 Hz.
    """
    global _PRIMARY_LOST_AT, _LAST_ENUM_TIME, _LAST_ENUM_TARGET
    now = time.monotonic()
    target_id = str(target_id or "any")

    # 1. Camino rápido: leer solo el mando principal
    if _PRIMARY_DEVICE is not None and _LAST_ENUM_TARGET == target_id:
        st = _read_device(_PRIMARY_DEVICE)
        if st is not None:
            _PRIMARY_LOST_AT = 0.0
            # Refrescar el orden de conexión periódicamente (detecta mandos secundarios nuevos)
            if now - _LAST_ENUM_TIME >= ENUM_INTERVAL_S:
                _LAST_ENUM_TIME = now
                found = _enumerate_connected(target_id)
                if _PRIMARY_DEVICE not in found:
                    found.insert(0, _PRIMARY_DEVICE)
                _update_connect_order(found)
                # Garantizar que el principal siga el primero de la lista
                if _PRIMARY_DEVICE in _CONNECT_ORDER:
                    _CONNECT_ORDER.remove(_PRIMARY_DEVICE)
                _CONNECT_ORDER.insert(0, _PRIMARY_DEVICE)
            return True, _LAST_ACTIVE_DEVICE_NAME, st

        # Principal sin respuesta: periodo de gracia para microcortes inalámbricos
        if _PRIMARY_LOST_AT == 0.0:
            _PRIMARY_LOST_AT = now
        if now - _PRIMARY_LOST_AT < PRIMARY_GRACE_S:
            return True, _LAST_ACTIVE_DEVICE_NAME, dict(_EMPTY_STATE)
        # Se agotó la gracia: el principal se considera desconectado
        if _PRIMARY_DEVICE in _CONNECT_ORDER:
            _CONNECT_ORDER.remove(_PRIMARY_DEVICE)
        _set_primary(None)
        _PRIMARY_LOST_AT = 0.0
        _LAST_ENUM_TIME = 0.0

    # 2. Sin principal: enumerar (limitado a 1 vez/s si no hay nada conectado) y elegir el más antiguo
    if _LAST_ENUM_TARGET != target_id:
        _CONNECT_ORDER.clear()
        _set_primary(None)
        _LAST_ENUM_TARGET = target_id
        _LAST_ENUM_TIME = 0.0
    if now - _LAST_ENUM_TIME < ENUM_INTERVAL_S and not _CONNECT_ORDER:
        return False, "Ninguno", dict(_EMPTY_STATE)

    _LAST_ENUM_TIME = now
    _update_connect_order(_enumerate_connected(target_id))
    for dev in list(_CONNECT_ORDER):
        st = _read_device(dev)
        if st is not None:
            _set_primary(dev)
            _PRIMARY_LOST_AT = 0.0
            return True, _LAST_ACTIVE_DEVICE_NAME, st

    _set_primary(None)
    return False, "Ninguno", dict(_EMPTY_STATE)


# -------------------------------------------------------------
# Información de Batería del Mando (XInput + PlayStation HID + DirectInput Fallback)
# -------------------------------------------------------------
from core.gamepad_hid import (
    DIGCF_PRESENT,
    DIGCF_DEVICEINTERFACE,
    _GUID,
    _SP_DEVICE_INTERFACE_DATA,
    _HIDD_ATTRIBUTES,
    SONY_VID,
    SONY_PIDS,
    _PS_BATTERY_CACHE,
    _PS_CACHE_TTL_S,
    decode_playstation_hid_report,
    _query_sony_hid_battery,
    _get_playstation_hid_battery,
)

class XINPUT_BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BatteryType", wintypes.BYTE),
        ("BatteryLevel", wintypes.BYTE),
    ]


def _battery_for_device(dev: Tuple[str, int]) -> Dict[str, Any]:
    """Estado de conexión y batería de un mando concreto (XInput: real; PlayStation/HID: real; DirectInput genérico: activo)."""
    kind, idx = dev
    base = {
        "connected": False,
        "is_wired": False,
        "is_charging": False,
        "level": "unknown",
        "percent": 0,
        "icon": "🎮",
        "text": "--",
        "device_name": _device_label(dev),
        "family": _device_family(dev),
        "device": dev,
    }
    if kind == "xinput":
        base["slot"] = idx + 1
        if _read_xinput_slot(idx) is None:
            return base
        base["connected"] = True
        if _xinput_dll and hasattr(_xinput_dll, "XInputGetBatteryInformation"):
            try:
                bat = XINPUT_BATTERY_INFORMATION()
                if _xinput_dll.XInputGetBatteryInformation(idx, 0, ctypes.byref(bat)) == 0:
                    b_type = bat.BatteryType & 0xFF
                    b_level = bat.BatteryLevel & 0xFF
                    if b_type == 0x01:  # BATTERY_TYPE_WIRED
                        base.update(is_wired=True, level="wired", percent=100, icon="⚡", text="Cable USB")
                        return base
                    if b_type != 0x00:
                        level_map = {
                            0: ("empty", 10, "🪫", "10%"),
                            1: ("low", 35, "🪫", "35%"),
                            2: ("medium", 70, "🔋", "70%"),
                            3: ("full", 100, "🔋", "100%"),
                        }
                        lvl, pct, icon, txt = level_map.get(b_level, ("unknown", 50, "🔋", "50%"))
                        base.update(level=lvl, percent=pct, icon=icon, text=txt)
                        return base
            except Exception:
                pass
        base.update(level="unknown", percent=0, text="Conectado")
        return base

    # DirectInput / PlayStation
    if _read_winmm_dev(idx) is not None:
        base.update(connected=True)
        mid, _pid, name = _winmm_caps(idx)
        is_sony = (mid == 0x054C or any(k in name.lower() for k in ("dualsense", "dualshock", "wireless controller", "playstation")))
        if is_sony:
            sony_idx = 0
            for k, d_id in _CONNECT_ORDER:
                if k == "winmm" and d_id == idx:
                    break
                if k == "winmm":
                    m, _, n = _winmm_caps(d_id)
                    if m == 0x054C or any(x in n.lower() for x in ("dualsense", "dualshock", "wireless controller", "playstation")):
                        sony_idx += 1
            ps_bat = _get_playstation_hid_battery(sony_idx)
            if ps_bat:
                base.update(
                    is_wired=ps_bat.get("is_wired", False),
                    is_charging=ps_bat.get("is_charging", False),
                    level=ps_bat.get("level", "medium"),
                    percent=ps_bat.get("percent", 100),
                    icon=ps_bat.get("icon", "🔋"),
                    text=ps_bat.get("text", "100%")
                )
                return base
        base.update(level="directinput", percent=100, text="Activo")
    return base


def get_all_gamepads_info() -> List[Dict[str, Any]]:
    """
    Devuelve la lista de mandos conectados en orden de conexión con su rol y batería:
    el primero es el 'principal' (maneja la app) y el resto 'secundario' (solo lectura).
    """
    if not _CONNECT_ORDER:
        try:
            _update_connect_order(_enumerate_connected(_LAST_ENUM_TARGET or "any"))
        except Exception:
            pass
    order = list(_CONNECT_ORDER)
    if _PRIMARY_DEVICE is not None:
        if _PRIMARY_DEVICE in order:
            order.remove(_PRIMARY_DEVICE)
        order.insert(0, _PRIMARY_DEVICE)

    result: List[Dict[str, Any]] = []
    for dev in order:
        info = _battery_for_device(dev)
        if not info.get("connected") and dev != _PRIMARY_DEVICE:
            continue
        info["role"] = "principal" if not result else "secundario"
        result.append(info)
    return result


def get_gamepad_battery_info(slot: Optional[int] = None) -> Dict[str, Any]:
    """
    Consulta en tiempo real el estado y batería del mando PRINCIPAL (o de la ranura XInput indicada).
    Incluye 'secondary' con la información del mando secundario si hay uno conectado.
    """
    empty = {
        "connected": False,
        "is_wired": False,
        "level": "unknown",
        "percent": 0,
        "icon": "🎮",
        "text": "--",
        "device_name": _LAST_ACTIVE_DEVICE_NAME,
        "secondary": None,
    }
    if slot is not None:
        return _battery_for_device(("xinput", int(slot)))

    all_info = get_all_gamepads_info()
    if not all_info:
        return empty
    primary = dict(all_info[0])
    primary["secondary"] = all_info[1] if len(all_info) > 1 else None
    return primary
