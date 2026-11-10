"""
Dynamic Display Scale & Resolution Management for GameFlow Launcher.
Handles per-monitor DPI, CustomTkinter ScalingTracker compensation,
and responsive UI geometry from 720p handhelds to 4K TVs.
"""
import sys
import ctypes
from typing import Tuple, Optional
import tkinter as tk
try:
    import win32api
    import win32con
except ImportError:
    win32api = None
    win32con = None

# Línea base de diseño de referencia: Full HD (1920x1080 @ 96 DPI)
BASE_RES_W = 1920
BASE_RES_H = 1080
BASE_DPI = 96

_CURRENT_ACTIVE_SCALE: float = 1.0


def get_monitor_work_area_for_window(window: Optional[tk.Widget] = None) -> Tuple[int, int, Tuple[int, int, int, int]]:
    """
    Retorna en píxeles físicos (work_width, work_height, work_rect) del monitor donde reside la ventana (o cursor).
    work_rect = (left, top, right, bottom)
    """
    if sys.platform != "win32":
        try:
            w = window.winfo_screenwidth() if window else 1920
            h = window.winfo_screenheight() if window else 1080
        except Exception:
            w, h = 1920, 1080
        return w, h, (0, 0, w, h)

    hwnd = 0
    if window:
        try:
            if hasattr(window, "winfo_id"):
                hwnd = window.winfo_id()
        except Exception:
            hwnd = 0

    try:
        if hwnd:
            hmon = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        else:
            pt = win32api.GetCursorPos()
            hmon = win32api.MonitorFromPoint(pt, win32con.MONITOR_DEFAULTTOPRIMARY)

        info = win32api.GetMonitorInfo(hmon)
        rc = info.get("Work", info.get("Monitor", (0, 0, 1920, 1080)))
        w = max(640, rc[2] - rc[0])
        h = max(480, rc[3] - rc[1])
        return w, h, rc
    except Exception:
        try:
            sw = window.winfo_screenwidth() if window else 1920
            sh = window.winfo_screenheight() if window else 1080
        except Exception:
            sw, sh = 1920, 1080
        return sw, sh, (0, 0, sw, sh)


def get_window_dpi(window: Optional[tk.Widget] = None) -> int:
    """Obtiene el DPI físico por monitor de la ventana en Windows 10/11 (96 = 100%, 192 = 200%)."""
    if sys.platform != "win32" or not window:
        return BASE_DPI
    try:
        if hasattr(window, "winfo_id"):
            hwnd = window.winfo_id()
            if hwnd and hasattr(ctypes.windll.user32, "GetDpiForWindow"):
                dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
                if dpi > 0:
                    return dpi
    except Exception:
        pass
    return BASE_DPI


def get_ctk_window_scaling(window: Optional[tk.Widget] = None) -> float:
    """
    Retorna el factor de escala interno que CustomTkinter (ScalingTracker) aplica automáticamente
    a todas las llamadas de geometry(WxH), widgets y CTkFont.
    """
    if window is not None:
        try:
            from customtkinter.windows.widgets.scaling import ScalingTracker
            sc = float(ScalingTracker.get_window_scaling(window))
            if sc > 0.1:
                return sc
        except Exception:
            pass
    dpi = get_window_dpi(window)
    return max(1.0, dpi / float(BASE_DPI))


def get_display_scale_factor(window: Optional[tk.Widget] = None) -> float:
    """
    Calcula el factor de escala LÓGICO para unidades de CustomTkinter (0.68x .. 2.50x).
    Como CustomTkinter ya multiplica internamente por `ctk_scale` (DPI / 96), el factor lógico es:
        logical_scale = (phys_work_h / 1080.0) / ctk_scale = logical_work_h / 1080.0
    Así, el tamaño físico resultante en pantalla (`logical_scale * ctk_scale`) es siempre
    exactamente proporcional a la resolución física del monitor:
      - En 4K (2160p) @ 200% DPI (ctk_scale=2.0) -> logical_scale=1.0 -> físico final = 2.0x (1840x1280).
      - En 4K (2160p) @ 100% DPI (ctk_scale=1.0) -> logical_scale=2.0 -> físico final = 2.0x (1840x1280).
      - En 4K (2160p) @ 300% DPI (ctk_scale=3.0) -> logical_scale=0.68 -> físico final = 2.0x (sin desbordar).
      - En 1080p @ 100% DPI (ctk_scale=1.0) -> logical_scale=1.0 -> físico final = 1.0x (920x640).
      - En 720p @ 100% DPI (ctk_scale=1.0) -> logical_scale=0.80 -> cabe holgadamente en pantalla.
    """
    phys_w, phys_h, _ = get_monitor_work_area_for_window(window)
    ctk_scale = get_ctk_window_scaling(window)

    logical_h = phys_h / ctk_scale
    if logical_h < 950:
        # Pantallas con área lógica compacta (720p/800p o laptops 1080p al 150% / 4K al 300%)
        scale = max(0.72, logical_h / float(BASE_RES_H))
    else:
        scale = logical_h / float(BASE_RES_H)

    return round(max(0.68, min(2.5, scale)), 2)


def set_active_display_scale(scale: float):
    """Actualiza la escala lógica activa para la creación de widgets y fuentes."""
    global _CURRENT_ACTIVE_SCALE
    _CURRENT_ACTIVE_SCALE = max(0.68, min(2.5, scale))


def get_active_display_scale() -> float:
    """Retorna la escala lógica actualmente activa."""
    return _CURRENT_ACTIVE_SCALE


def scale_value(val: int, scale: Optional[float] = None, min_val: int = 1) -> int:
    """Escala un valor entero lógico proporcionalmente."""
    sc = scale if scale is not None else _CURRENT_ACTIVE_SCALE
    return max(min_val, int(round(val * sc)))


def calculate_dialog_bounds(
    base_w: int,
    base_h: int,
    window: Optional[tk.Widget] = None,
    max_w_ratio: float = 0.92,
    max_h_ratio: float = 0.90
) -> Tuple[int, int, float]:
    """
    Calcula las dimensiones LÓGICAS (dialog_width, dialog_height, scale_factor) para un CTkToplevel,
    garantizando que una vez multiplicadas por el ScalingTracker de CustomTkinter nunca superen
    el 92% del ancho ni el 90% del alto físico del monitor activo.
    """
    scale = get_display_scale_factor(window)
    phys_w, phys_h, _ = get_monitor_work_area_for_window(window)
    ctk_scale = get_ctk_window_scaling(window)

    logical_work_w = phys_w / ctk_scale
    logical_work_h = phys_h / ctk_scale

    scaled_w = int(round(base_w * scale))
    scaled_h = int(round(base_h * scale))

    max_w = int(logical_work_w * max_w_ratio)
    max_h = int(logical_work_h * max_h_ratio)

    final_w = max(320, min(scaled_w, max_w))
    final_h = max(180, min(scaled_h, max_h))
    return final_w, final_h, scale
