import os
import sys
import time
import subprocess
import json
import ctypes
from typing import List, Dict, Any, Tuple
import psutil
import win32gui
import win32api
import win32process
try:
    from core.logger import get_logger
    logger = get_logger("System")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.System")
import win32con

# Asegurar codificación segura UTF-8 para evitar errores con títulos Unicode (como el carácter Δ de Metal Gear)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Configurar conciencia DPI por monitor (Per-Monitor DPI Aware)
# Esto garantiza que las coordenadas del escritorio coincidan 1:1 con los píxeles reales de Windows
try:
    # 2 = PROCESS_PER_MONITOR_DPI_AWARE
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def is_admin() -> bool:
    """Comprueba si el proceso actual tiene permisos de Administrador."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False

def ensure_admin():
    """No fuerza UAC para permitir arranque fluido e instantáneo desde el mando y el watcher."""
    pass

def _read_edid_friendly_names_from_registry() -> Dict[str, str]:
    """Lee el nombre comercial del monitor directamente desde los descriptores EDID en el Registro de Windows (<0.5ms)."""
    names = {}
    try:
        import winreg
        key_path = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root_key:
            count = winreg.QueryInfoKey(root_key)[0]
            for i in range(count):
                dev_id = winreg.EnumKey(root_key, i)
                try:
                    with winreg.OpenKey(root_key, dev_id) as dev_key:
                        inst_count = winreg.QueryInfoKey(dev_key)[0]
                        for j in range(inst_count):
                            inst_name = winreg.EnumKey(dev_key, j)
                            try:
                                with winreg.OpenKey(dev_key, f"{inst_name}\\Device Parameters") as dp_key:
                                    edid_val, _ = winreg.QueryValueEx(dp_key, "EDID")
                                    if isinstance(edid_val, (bytes, bytearray)) and len(edid_val) >= 128:
                                        for offset in (54, 72, 90, 108):
                                            if edid_val[offset:offset+3] == b"\x00\x00\x00" and edid_val[offset+3] == 0xFC:
                                                raw_text = edid_val[offset+5:offset+18]
                                                name = raw_text.decode("latin1", errors="ignore").split("\n")[0].strip()
                                                if name:
                                                    names[dev_id.upper()] = name
                                                    names[f"{dev_id}\\{inst_name}".upper()] = name
                                                    break
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass
    return names

def _read_wmi_friendly_names_com() -> Dict[str, str]:
    """Consulta WmiMonitorID en proceso mediante WMI COM (~10ms) sin lanzar subprocesos."""
    names = {}
    try:
        import win32com.client
        wmi = win32com.client.GetObject(r"winmgmts:\\.\root\wmi")
        items = wmi.ExecQuery("SELECT InstanceName, UserFriendlyName FROM WmiMonitorID")
        for item in items:
            raw_name = getattr(item, "UserFriendlyName", None)
            inst = getattr(item, "InstanceName", "")
            if raw_name:
                fname = "".join(chr(c) for c in raw_name if c > 0).strip()
                if fname:
                    names[inst.upper()] = fname
                    parts = inst.split("\\")
                    if len(parts) > 1:
                        names[parts[1].upper()] = fname
    except Exception:
        pass
    return names

def _read_wmi_friendly_names_powershell() -> Dict[str, str]:
    """Respaldo de último recurso mediante subproceso de PowerShell si COM y Registro están restringidos."""
    names = {}
    try:
        ps_script = (
            'Get-WmiObject -Namespace root\\wmi -Class WmiMonitorID | '
            'Select-Object InstanceName, @{Name="FriendlyName";Expression={[System.Text.Encoding]::ASCII.GetString($_.UserFriendlyName)}} | '
            'ConvertTo-Json'
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                fname = item.get("FriendlyName", "").replace("\u0000", "").strip()
                inst = item.get("InstanceName", "").upper()
                if fname:
                    names[inst] = fname
                    parts = inst.split("\\")
                    if len(parts) > 1:
                        names[parts[1].upper()] = fname
    except Exception:
        pass
    return names

def _get_wmi_monitor_map() -> Dict[str, str]:
    """Obtiene el mapa de modelos amigables mediante 3 niveles de defensa progresivos: Registro EDID -> WMI COM -> PowerShell."""
    # Nivel 1: Registro directo EDID (<0.5ms)
    names = _read_edid_friendly_names_from_registry()
    if names:
        return names
    # Nivel 2: WMI COM en proceso (~10ms)
    names = _read_wmi_friendly_names_com()
    if names:
        return names
    # Nivel 3: Subproceso PowerShell (Respaldo de emergencia)
    return _read_wmi_friendly_names_powershell()

# Caché de nombres de monitor para evitar reconsultas redundantes
_WMI_MONITOR_MAP: Dict[str, str] = {}
_WMI_MAP_TIMESTAMP: float = 0.0

def get_monitors(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Detecta todos los monitores activos obteniendo su resolución, posición y
    nombre de modelo amigable mediante emparejamiento exacto de ID de Hardware (EDID/WMI).
    Utiliza lectura ultrarrápida nativa (<2ms) eliminando la sobrecarga de subprocesos externos.
    """
    global _WMI_MONITOR_MAP, _WMI_MAP_TIMESTAMP
    monitors = []
    wmi_map = _WMI_MONITOR_MAP

    now = time.time()
    if force_refresh or not _WMI_MONITOR_MAP or (now - _WMI_MAP_TIMESTAMP > 60.0):
        new_map = _get_wmi_monitor_map()
        if new_map:
            _WMI_MONITOR_MAP = new_map
            _WMI_MAP_TIMESTAMP = now
            wmi_map = new_map

    for i, monitor in enumerate(win32api.EnumDisplayMonitors()):
        monitor_info = win32api.GetMonitorInfo(monitor[0])
        device_name = monitor_info['Device']
        rect = monitor_info['Monitor']
        is_primary = bool(monitor_info.get('Flags', 0) & 1)
        
        friendly_name = f"Monitor {i}"
        try:
            device = win32api.EnumDisplayDevices(device_name, 0, 0)
            dev_id = getattr(device, "DeviceID", "").upper()
            dev_string = getattr(device, "DeviceString", "")
            
            # Extraer token de hardware (ej: ACR053C, SAM0F14, LEN61BC)
            parts = dev_id.split('\\')
            hw_id = parts[1] if len(parts) > 1 else ''
            
            if hw_id in wmi_map:
                friendly_name = wmi_map[hw_id]
            else:
                matched = False
                for inst, name in wmi_map.items():
                    if hw_id and hw_id in inst:
                        friendly_name = name
                        matched = True
                        break
                if not matched and dev_string and dev_string.lower() != "generic pnp monitor":
                    friendly_name = dev_string
        except Exception:
            pass
            
        display_name = f"{friendly_name} (Principal)" if is_primary else friendly_name
            
        monitors.append({
            "id": i,
            "device": device_name,
            "name": display_name,
            "raw_name": friendly_name,
            "is_primary": is_primary,
            "rect": rect  # (left, top, right, bottom)
        })
    return monitors

def set_high_priority(pid: int):
    """Establece prioridad de ejecución 'Alta' para el proceso dado."""
    try:
        p = psutil.Process(pid)
        p.nice(psutil.HIGH_PRIORITY_CLASS)
        logger.info(f"Prioridad alta establecida para PID {pid}")
    except Exception as e:
        logger.error(f"Error al establecer prioridad: {e}")

def get_game_windows(pids: List[int]) -> List[Dict[str, Any]]:
    """
    Busca todas las ventanas visibles asociadas a los PIDs dados,
    clasificándolas según su tamaño y características (filtrando invisibles, herramientas, IME).
    Prioriza ventanas de juego reales (3D viewport) sobre splash screens.
    """
    pids_set = set(pids)
    results = []

    def callback(hwnd, _):
        if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid not in pids_set:
                return True

            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            if w <= 10 or h <= 10:
                return True

            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)

            # Excluir ventanas de herramientas flotantes o no interactivas
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return True

            class_name = win32gui.GetClassName(hwnd)
            if class_name in ("tooltips_class32", "MSCTFIME UI", "IME", "Default IME"):
                return True

            title = win32gui.GetWindowText(hwnd) or ""
            safe_title = title.encode('ascii', 'replace').decode('ascii')
            area = w * h
            is_main_candidate = (w >= 640 and h >= 480) or bool(title.strip())

            results.append({
                "hwnd": hwnd,
                "pid": found_pid,
                "rect": rect,
                "width": w,
                "height": h,
                "area": area,
                "title": title,
                "safe_title": safe_title,
                "class": class_name,
                "style": style,
                "ex_style": ex_style,
                "is_main_candidate": is_main_candidate
            })
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        pass

    # Ordenar priorizando ventanas de juego reales (mayor área y dimensiones de juego)
    results.sort(key=lambda x: (x["is_main_candidate"], x["area"]), reverse=True)
    return results

def get_hwnds_for_pid(pid: int) -> List[int]:
    """Obtiene la lista de identificadores de ventana (HWND) visibles pertenecientes a un PID."""
    windows = get_game_windows([pid])
    return [w["hwnd"] for w in windows]

def warp_cursor_to_monitor(monitor_rect: Tuple[int, int, int, int]):
    """
    Sitúa el puntero del ratón en el centro geométrico del monitor objetivo.
    La mayoría de motores gráficos modernos (Unreal, CryEngine, Frostbite) consultan
    la posición del ratón para decidir en qué monitor instanciar su ventana principal.
    """
    try:
        left, top, right, bottom = monitor_rect
        cx = left + (right - left) // 2
        cy = top + (bottom - top) // 2
        ctypes.windll.user32.SetCursorPos(int(cx), int(cy))
        logger.info(f"Cursor situado preventivamente en el centro del monitor: ({cx}, {cy})")
    except Exception as e:
        logger.warning(f"No se pudo situar el cursor: {e}")

def send_win_shift_arrow(direction: str = 'left'):
    """
    Simula a nivel de hardware la combinación nativa del kernel de Windows:
    (Win + Shift + Flecha Izquierda / Derecha).
    Fuerza al Desktop Window Manager (DWM) a trasladar físicamente la superficie
    de pantalla al monitor contiguo sin depender de las llamadas de la API de la ventana.
    """
    VK_LWIN = 0x5B
    VK_SHIFT = 0x10
    VK_LEFT = 0x25
    VK_RIGHT = 0x27
    KEYEVENTF_KEYUP = 0x0002

    vk_arrow = VK_LEFT if direction.lower() == 'left' else VK_RIGHT
    try:
        # Pulsar: Win + Shift + Flecha
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_arrow, 0, 0, 0)
        import time
        time.sleep(0.06)
        # Soltar: Flecha + Shift + Win
        ctypes.windll.user32.keybd_event(vk_arrow, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
        ctypes.windll.user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)
        logger.info(f"Inyección DWM ejecutada: Win + Shift + {direction.upper()}")
    except Exception as e:
        logger.error(f"Error inyectando combinación Win+Shift+Flecha: {e}")

def force_dwm_window_shift_to_monitor(hwnd: int, target_monitor_rect: Tuple[int, int, int, int], max_tries: int = 3) -> bool:
    """
    Aplica el bypass DWM por hardware (Win + Shift + Flecha) si una ventana
    permanece fuera del monitor objetivo tras los intentos de SetWindowPos.
    """
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False

    t_left, t_top, t_right, t_bottom = target_monitor_rect
    import time
    for attempt in range(max_tries):
        try:
            cur_rect = win32gui.GetWindowRect(hwnd)
            # Comprobar si ya está dentro del monitor objetivo
            if (cur_rect[0] >= t_left - 30 and cur_rect[1] >= t_top - 30 and 
                cur_rect[2] <= t_right + 30 and cur_rect[3] <= t_bottom + 30):
                return True

            cur_cx = cur_rect[0] + (cur_rect[2] - cur_rect[0]) // 2
            t_cx = t_left + (t_right - t_left) // 2
            direction = 'left' if t_cx < cur_cx else 'right'

            # Traer al frente para que reciba la orden del Compositor DWM
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.08)
            send_win_shift_arrow(direction)
            time.sleep(0.35)
        except Exception:
            break

    try:
        cur_rect = win32gui.GetWindowRect(hwnd)
        return (cur_rect[0] >= t_left - 30 and cur_rect[1] >= t_top - 30 and 
                cur_rect[2] <= t_right + 30 and cur_rect[3] <= t_bottom + 30)
    except Exception:
        return False

def move_window_to_monitor(hwnd: int, monitor_rect: Tuple[int, int, int, int], force_borderless: bool = True) -> bool:
    """
    Mueve la ventana al monitor objetivo sin provocar desbordamientos ni snapping al monitor principal.
    Aplica posicionamiento exacto para Borderless Fullscreen y ventanas estándar sin romper el viewport.
    Si force_borderless es True, retira marcos rígidos para lograr pantalla completa sin bordes perfecta.
    """
    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    try:
        left, top, right, bottom = monitor_rect
        target_width = right - left
        target_height = bottom - top

        cur_rect = win32gui.GetWindowRect(hwnd)
        cur_left, cur_top, cur_right, cur_bottom = cur_rect
        cur_w = cur_right - cur_left
        cur_h = cur_bottom - cur_top

        # Si ya está exactamente posicionada en el monitor objetivo, no forzar nada
        if abs(cur_left - left) <= 2 and abs(cur_top - top) <= 2 and abs(cur_w - target_width) <= 4 and abs(cur_h - target_height) <= 4:
            return True

        # Si la ventana estaba minimizada, restaurarla primero
        placement = win32gui.GetWindowPlacement(hwnd)
        if placement[1] == win32con.SW_SHOWMINIMIZED:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        is_popup_or_borderless = bool(style & win32con.WS_POPUP)

        # Si force_borderless está activo y tiene marcos de ventana convencionales, limpiarlos
        if force_borderless and not is_popup_or_borderless and cur_w >= target_width * 0.7:
            new_style = style & ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME | win32con.WS_MINIMIZEBOX | win32con.WS_MAXIMIZEBOX | win32con.WS_SYSMENU)
            new_style |= win32con.WS_POPUP
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
            is_popup_or_borderless = True

        flags = win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW | win32con.SWP_FRAMECHANGED

        if is_popup_or_borderless or cur_w >= target_width * 0.75:
            # Juego en pantalla completa o borderless: ajustar exactamente al área del monitor objetivo
            # No se usa SW_MAXIMIZE porque desborda 8px en el monitor contiguo y reinicia el swapchain en DirectX/UE
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, left, top, target_width, target_height, flags)
        else:
            # Ventana de tamaño menor/fijo: centrar en el monitor objetivo
            pos_x = left + max(0, (target_width - cur_w) // 2)
            pos_y = top + max(0, (target_height - cur_h) // 2)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, pos_x, pos_y, cur_w, cur_h, flags)

        # Forzar foco y primer plano de la ventana del juego
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

        logger.info(f"Ventana {hwnd} posicionada con éxito en ({left}, {top}) [{target_width}x{target_height}]")
        return True
    except Exception as e:
        if getattr(e, 'winerror', None) == 5 or "acceso denegado" in str(e).lower() or "access denied" in str(e).lower():
            logger.warning(f"Aviso UIPI: No se puede mover la ventana {hwnd} (el juego requiere permisos de Administrador)")
        else:
            logger.error(f"Error al mover ventana {hwnd}: {e}")
        return False


