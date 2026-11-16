"""
Design system and style tokens for GameFlow Launcher.
iOS Liquid Glass / Neumorphic Glass Dark aesthetic (VisionOS / iOS 18 style).
Inspired by dark frosted glass, specular highlights, and vibrant iOS pill actions.
"""
import customtkinter as ctk

# -------------------------------------------------------------
# Clave de transparencia en Windows (#000001 -> RGB: 0, 0, 1)
# -------------------------------------------------------------
COLOR_TRANS_KEY = "#000001"

# -------------------------------------------------------------
# Paleta de Fondos Apple Glassmorphism Oscuro (rgba(20, 20, 30, 0.65) -> grafito translúcido)
# -------------------------------------------------------------
COLOR_BG_DARK = "#12121a"           # Fondo principal profundo estilo Apple Dark Glass
COLOR_BG_CANVAS = "#12121a"         # Fondo continuo del canvas Cover Flow
COLOR_BG_CARD = "#161620"           # Panel / modal de vidrio oscuro semitransparente
COLOR_BG_CARD_SECONDARY = "#1c1c28" # Superficie interna secundaria (cabeceras/listas)
COLOR_BG_CARD_TERTIARY = "#232332"  # Superficie interna elevada
COLOR_BG_DROPDOWN = "#181822"       # Fondo de menús desplegables y contextuales
COLOR_BG_PILL = "#1e1e2a"           # Cápsula de control redondeada (píldora)
COLOR_BG_INPUT = "#1a1a26"          # Fondo de campos de entrada y cajas de texto
COLOR_BG_INPUT_ACTIVE = "#262636"   # Fondo de campo con foco o cursor activo
COLOR_BG_ITEM_HOVER = "#343444"     # Estado hover/activo translúcido aclarado en desplegables

# -------------------------------------------------------------
# Bordes Sutiles 1px (rgba(255, 255, 255, 0.10 - 0.18)) y Biseles Especulares
# -------------------------------------------------------------
COLOR_GLASS_BORDER = "#363646"       # Borde muy sutil de 1px con baja opacidad
COLOR_GLASS_BORDER_LIGHT = "#5e5e74" # Borde especular aclarado en estado hover/activo
COLOR_GLASS_FILL = "#1a1a26"         # Relleno de vidrio translúcido
COLOR_GLASS_HOVER = "#2c2c3c"        # Hover luminoso suave sobre vidrio
COLOR_BORDER_DEFAULT = "#2c2c3a"
COLOR_BORDER_CARD = "#343444"
COLOR_BORDER_INPUT = "#363646"
COLOR_BORDER_INPUT_FOCUS = "#0a84ff"
COLOR_BORDER_FOCUS = "#6e6e84"       # Borde de botón/elemento con foco

# -------------------------------------------------------------
# Acentos Vibrantes Apple (Iconic Pills)
# -------------------------------------------------------------
# Azul Eléctrico Vibrante (Botón Principal "▶ INICIAR JUEGO", "Aceptar")
COLOR_IOS_BLUE = "#007aff"
COLOR_IOS_BLUE_HOVER = "#2997ff"     # Azul eléctrico aclarado/iluminado en hover
COLOR_IOS_BLUE_BORDER = "#4da3ff"
COLOR_IOS_BLUE_GLOW = "#60a5fa"

# Rojo Carmesí iOS (Acción destructiva, Cancelar crítico, Batería Baja)
COLOR_IOS_RED = "#ff2d55"
COLOR_IOS_RED_HOVER = "#ff476b"
COLOR_IOS_RED_BORDER = "#ff6384"

# Verde Interruptor Apple (Toggle activo / Botón A / Batería Llena)
COLOR_IOS_GREEN = "#34c759"
COLOR_IOS_GREEN_HOVER = "#30d158"

# Ámbar / Naranja iOS (Avisos, Batería Media)
COLOR_IOS_ORANGE = "#ff9500"
COLOR_IOS_ORANGE_HOVER = "#ffa929"

# Cian & Resplandor Suave
COLOR_CYAN_ACCENT = "#38bdf8"
COLOR_CYAN_BORDER = "#007aff"
COLOR_CYAN_GLOW = "#60a5fa"
COLOR_CYAN_BRIGHT = "#00e5ff"

# Estados de la Aplicación
COLOR_STATUS_SUCCESS = COLOR_IOS_GREEN
COLOR_STATUS_SUCCESS_HOVER = COLOR_IOS_GREEN_HOVER
COLOR_STATUS_WARNING = COLOR_IOS_ORANGE
COLOR_STATUS_WARNING_HOVER = COLOR_IOS_ORANGE_HOVER
COLOR_STATUS_DANGER = COLOR_IOS_RED
COLOR_STATUS_DANGER_HOVER = COLOR_IOS_RED_HOVER
COLOR_STATUS_DANGER_BORDER = COLOR_IOS_RED_BORDER

# -------------------------------------------------------------
# Botones Principales, Secundarios y de Peligro (Forma de Píldora)
# -------------------------------------------------------------
COLOR_BTN_PRIMARY_BG = COLOR_IOS_BLUE
COLOR_BTN_PRIMARY_HOVER = COLOR_IOS_BLUE_HOVER
COLOR_BTN_PRIMARY_BORDER = COLOR_IOS_BLUE_BORDER

COLOR_BTN_SECONDARY_BG = "#1c212d"
COLOR_BTN_SECONDARY_HOVER = "#32394a"  # Aclara ligeramente el fondo translúcido en hover
COLOR_BTN_SECONDARY_BORDER = "#3d4456" # Borde sutil de 1px con baja opacidad

COLOR_BTN_DANGER_BG = COLOR_IOS_RED
COLOR_BTN_DANGER_HOVER = COLOR_IOS_RED_HOVER
COLOR_BTN_DANGER_BORDER = COLOR_IOS_RED_BORDER

# -------------------------------------------------------------
# Tipografía de Alto Contraste (Blanco Puro y Gris Claro Muting)
# -------------------------------------------------------------
COLOR_TEXT_WHITE = "#ffffff"        # Blanco puro para textos principales y botones
COLOR_TEXT_MAIN = "#ffffff"         # Blanco puro de alto contraste para títulos y etiquetas
COLOR_TEXT_BRIGHT = "#f4f4f8"       # Texto destacado
COLOR_TEXT_LIGHT = "#e4e4ee"        # Texto secundario claro
COLOR_TEXT_MUTED_LIGHT = "#c8c8d6"  # Gris claro para descripciones y textos secundarios (muting)
COLOR_TEXT_MUTED = "#9e9eb0"        # Texto atenuado secundario
COLOR_TEXT_DIM = "#6e6e82"          # Texto terciario/apagado
COLOR_TEXT_EXTRA_DIM = "#4c4c5e"    # Placeholder o deshabilitado
COLOR_TEXT_CYAN = "#38bdf8"
COLOR_TEXT_BLUE = "#007aff"
COLOR_TEXT_GREEN = "#34c759"
COLOR_TEXT_RED = "#ff2d55"
COLOR_TEXT_ORANGE = "#ff9500"

THEME_TOKENS = {
    "bg_dark": COLOR_BG_DARK,
    "bg_canvas": COLOR_BG_CANVAS,
    "bg_card": COLOR_BG_CARD,
    "bg_card_secondary": COLOR_BG_CARD_SECONDARY,
    "bg_dropdown": COLOR_BG_DROPDOWN,
    "bg_input": COLOR_BG_INPUT,
    "bg_input_active": COLOR_BG_INPUT_ACTIVE,
    "glass_border": COLOR_GLASS_BORDER,
    "glass_border_light": COLOR_GLASS_BORDER_LIGHT,
    "border_focus": COLOR_BORDER_FOCUS,
    "primary": COLOR_IOS_BLUE,
    "primary_hover": COLOR_IOS_BLUE_HOVER,
    "cyan_accent": COLOR_CYAN_ACCENT,
    "status_success": COLOR_STATUS_SUCCESS,
    "status_warning": COLOR_STATUS_WARNING,
    "status_danger": COLOR_STATUS_DANGER,
    "text_white": COLOR_TEXT_WHITE,
    "text_main": COLOR_TEXT_MAIN,
    "text_muted": COLOR_TEXT_MUTED,
    "text_dim": COLOR_TEXT_DIM
}

from ui.display_scale import get_active_display_scale, get_ctk_window_scaling

FONT_FAMILY = "Segoe UI"
FONT_HEADING = "Segoe UI Semibold"

def font_title(size: int = 24, weight: str = "bold", scale: float = None) -> ctk.CTkFont:
    sc = scale if scale is not None else get_active_display_scale()
    return ctk.CTkFont(family=FONT_HEADING, size=max(12, int(round(size * sc))), weight=weight)

def font_body(size: int = 12, weight: str = "normal", scale: float = None) -> ctk.CTkFont:
    sc = scale if scale is not None else get_active_display_scale()
    return ctk.CTkFont(family=FONT_FAMILY, size=max(10, int(round(size * sc))), weight=weight)

def font_button(size: int = 13, weight: str = "bold", scale: float = None) -> ctk.CTkFont:
    sc = scale if scale is not None else get_active_display_scale()
    return ctk.CTkFont(family=FONT_HEADING, size=max(10, int(round(size * sc))), weight=weight)


def apply_rounded_window_region(window, width: int, height: int, radius: int = 28):
    """Aplica esquinas redondeadas nativas Win32 en píxeles físicos sin usar -transparentcolor."""
    import sys
    import ctypes
    if sys.platform != "win32":
        return
    try:
        if not window or not window.winfo_exists():
            return
        window.update_idletasks()
        ctk_scale = get_ctk_window_scaling(window)
        actual_w = window.winfo_width()
        actual_h = window.winfo_height()
        phys_w = actual_w if actual_w > 100 else int(round(width * ctk_scale))
        phys_h = actual_h if actual_h > 100 else int(round(height * ctk_scale))
        phys_r = int(round(radius * ctk_scale))
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, phys_w + 1, phys_h + 1, phys_r, phys_r)
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


def bring_to_front_absolute(window):
    """
    Garantiza que la ventana modal o menú flotante se sitúe en el primer plano
    absoluto del escritorio por encima de cualquier ventana fullscreen o topmost.
    """
    import sys
    import ctypes
    if not window:
        return
    try:
        if not window.winfo_exists():
            return
        window.lift()
        window.focus_force()
        if sys.platform.startswith("win"):
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040
            ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def hide_from_taskbar(window):
    """
    Oculta completamente una ventana emergente o menú flotante de la barra de tareas
    y del selector Alt+Tab de Windows vinculándola como ventana poseída (GWLP_HWNDPARENT)
    y aplicando el estilo WS_EX_TOOLWINDOW y HWND_TOPMOST.
    """
    import sys
    import ctypes
    if not sys.platform.startswith("win"):
        return
    try:
        if not window or not window.winfo_exists():
            return
        try:
            window.update_idletasks()
        except Exception:
            pass
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()

        # Enlazar HWND propietario a la ventana principal para que Windows no lo liste en Alt+Tab
        master = getattr(window, "master", None) or getattr(window, "parent", None)
        if master and hasattr(master, "winfo_id"):
            try:
                parent_hwnd = ctypes.windll.user32.GetParent(master.winfo_id()) or master.winfo_id()
                if parent_hwnd:
                    from ctypes import wintypes
                    GWLP_HWNDPARENT = -8
                    if hasattr(ctypes.windll.user32, "SetWindowLongPtrW"):
                        ctypes.windll.user32.SetWindowLongPtrW.restype = wintypes.HWND
                        ctypes.windll.user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HWND]
                        ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, parent_hwnd)
                    else:
                        ctypes.windll.user32.SetWindowLongW(hwnd, GWLP_HWNDPARENT, parent_hwnd)
            except Exception:
                pass

        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOPMOST = 0x00000008
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_TOOLWINDOW | WS_EX_TOPMOST) & ~WS_EX_APPWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        SWP_FRAMECHANGED = 0x0020
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_FRAMECHANGED)
    except Exception:
        pass


def scroll_to_widget(scroll_frame, target_widget=None, force_edge: str = None):
    """
    Desplaza automáticamente un CTkScrollableFrame para asegurar que target_widget sea visible,
    haciendo que la barra lateral acompañe el movimiento al bajar/subir con el mando o teclado.
    """
    try:
        if not scroll_frame or not scroll_frame.winfo_exists():
            return
        canvas = getattr(scroll_frame, "_parent_canvas", None)
        if not canvas or not canvas.winfo_exists():
            return

        if force_edge == "top":
            canvas.yview_moveto(0.0)
            return
        elif force_edge == "bottom":
            canvas.yview_moveto(1.0)
            return

        if not target_widget or not target_widget.winfo_exists():
            return

        content_h = scroll_frame.winfo_height()
        if content_h <= 1:
            scroll_frame.update_idletasks()
            content_h = scroll_frame.winfo_height()
        content_h = max(1, content_h)
        viewport_h = max(1, canvas.winfo_height())
        if content_h <= viewport_h:
            canvas.yview_moveto(0.0)
            return

        widget_top = target_widget.winfo_rooty() - scroll_frame.winfo_rooty()
        widget_bottom = widget_top + target_widget.winfo_height()
        widget_center = (widget_top + widget_bottom) * 0.5

        # Hacer que el scroll acompañe progresivamente al elemento enfocado manteniéndolo centrado
        target_px = widget_center - (viewport_h * 0.42)
        clamped_px = max(0.0, min(float(content_h - viewport_h), target_px))
        canvas.yview_moveto(clamped_px / float(content_h))
    except Exception:
        pass


def apply_gamepad_focus(widget, is_focused: bool, role: str = "secondary"):
    """
    Aplica un resaltado de alto contraste estilo consola (10-foot UI / Big Picture)
    a cualquier botón, entrada, desplegable, checkbox o tarjeta cuando recibe el foco del mando.
      - role in ('primary', 'secondary', 'danger', 'dropdown', 'entry', 'check', 'switch', 'card')
    """
    if not widget:
        return
    try:
        if not widget.winfo_exists():
            return
    except Exception:
        return

    if role == "danger":
        if is_focused:
            widget.configure(
                fg_color=COLOR_IOS_RED_HOVER,
                hover_color="#ff5c7c",
                border_color="#ffffff",
                border_width=2,
                text_color="#ffffff"
            )
        else:
            widget.configure(
                fg_color=COLOR_BTN_DANGER_BG,
                hover_color=COLOR_BTN_DANGER_HOVER,
                border_color=COLOR_BTN_DANGER_BORDER,
                border_width=1,
                text_color="#ffd6de"
            )
    elif role == "primary":
        if is_focused:
            widget.configure(
                fg_color=COLOR_IOS_BLUE_HOVER,
                hover_color=COLOR_IOS_BLUE_HOVER,
                border_color="#ffffff",
                border_width=2,
                text_color="#ffffff"
            )
        else:
            widget.configure(
                fg_color=COLOR_IOS_BLUE,
                hover_color=COLOR_IOS_BLUE_HOVER,
                border_color=COLOR_IOS_BLUE_BORDER,
                border_width=0,
                text_color="#ffffff"
            )
    elif role == "secondary":
        if is_focused:
            widget.configure(
                fg_color=COLOR_BTN_SECONDARY_HOVER,
                hover_color="#424258",
                border_color="#ffffff",
                border_width=2,
                text_color="#ffffff"
            )
        else:
            widget.configure(
                fg_color=COLOR_BTN_SECONDARY_BG,
                hover_color=COLOR_BTN_SECONDARY_HOVER,
                border_color=COLOR_BTN_SECONDARY_BORDER,
                border_width=1,
                text_color=COLOR_TEXT_WHITE
            )
    elif role == "dropdown":
        if is_focused:
            widget.configure(
                fg_color=COLOR_BG_ITEM_HOVER,
                hover_color=COLOR_BG_ITEM_HOVER,
                border_color="#ffffff",
                border_width=2,
                text_color="#ffffff"
            )
        else:
            widget.configure(
                fg_color=COLOR_BG_PILL,
                hover_color=COLOR_GLASS_HOVER,
                border_color=COLOR_GLASS_BORDER,
                border_width=1,
                text_color=COLOR_TEXT_WHITE
            )
    elif role == "entry":
        if is_focused:
            widget.configure(
                fg_color=COLOR_BG_INPUT_ACTIVE,
                border_color="#ffffff",
                border_width=2
            )
            try:
                widget.focus_set()
            except Exception:
                pass
        else:
            widget.configure(
                fg_color=COLOR_BG_INPUT,
                border_color=COLOR_GLASS_BORDER,
                border_width=1
            )
            try:
                cur_focus = widget.focus_get()
                if cur_focus is not None and (cur_focus is widget or str(cur_focus).startswith(str(widget))):
                    widget.winfo_toplevel().focus_set()
            except Exception:
                pass
    elif role == "check":
        if is_focused:
            widget.configure(
                text_color=COLOR_TEXT_WHITE,
                border_color="#ffffff"
            )
        else:
            widget.configure(
                text_color=COLOR_TEXT_MAIN,
                border_color=COLOR_GLASS_BORDER_LIGHT
            )
    elif role == "switch":
        if is_focused:
            widget.configure(
                text_color=COLOR_TEXT_WHITE,
                progress_color=COLOR_IOS_GREEN,
                button_color="#ffffff"
            )
        else:
            widget.configure(
                text_color=COLOR_TEXT_MAIN,
                progress_color=COLOR_IOS_GREEN,
                button_color="#e4e4ee"
            )
    elif role == "card":
        if is_focused:
            widget.configure(
                fg_color="#2c2c3c",
                border_color="#ffffff",
                border_width=2
            )
        else:
            widget.configure(
                fg_color=COLOR_BG_CARD_SECONDARY,
                border_color=COLOR_GLASS_BORDER,
                border_width=1
            )

