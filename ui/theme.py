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
# Paleta de Fondos iOS Liquid Glass (Carbón mate y vidrio ahumado)
# -------------------------------------------------------------
COLOR_BG_DARK = "#0f1218"           # Fondo principal profundo y sedoso
COLOR_BG_CANVAS = "#0f1218"         # Fondo continuo del canvas Cover Flow
COLOR_BG_CARD = "#141722"           # Tarjeta de vidrio ahumado principal / diálogos
COLOR_BG_CARD_SECONDARY = "#181d28" # Superficie interna secundaria (cabeceras/listas)
COLOR_BG_CARD_TERTIARY = "#1d2331"  # Superficie interna elevada
COLOR_BG_DROPDOWN = "#131620"       # Fondo de menús flotantes estilo isla
COLOR_BG_PILL = "#1a1f2b"           # Cápsula de control redondeada
COLOR_BG_INPUT = "#181d28"          # Fondo de campos de entrada y cajas de texto
COLOR_BG_INPUT_ACTIVE = "#242c3d"   # Fondo de campo con foco o cursor activo
COLOR_BG_ITEM_HOVER = "#242a3a"     # Fondo de elemento resaltado o hover

# -------------------------------------------------------------
# Bordes y Biseles Especulares (Liquid Glass Highlights)
# -------------------------------------------------------------
COLOR_GLASS_BORDER = "#2b3345"       # Borde sutil translúcido
COLOR_GLASS_BORDER_LIGHT = "#3d4860" # Bisel superior iluminado
COLOR_GLASS_FILL = "#171b26"         # Relleno de vidrio translúcido
COLOR_GLASS_HOVER = "#242a3a"        # Hover luminoso suave sobre vidrio
COLOR_BORDER_DEFAULT = "#222836"
COLOR_BORDER_CARD = "#2a3142"
COLOR_BORDER_INPUT = "#2b3345"
COLOR_BORDER_INPUT_FOCUS = "#38bdf8"
COLOR_BORDER_FOCUS = "#343f55"       # Borde de botón/elemento con foco de mando

# -------------------------------------------------------------
# Acentos Vibrantes iOS (Iconic Pills)
# -------------------------------------------------------------
# Azul iOS Eléctrico (Pill Button "▶ Play", "Continue", "Allow")
COLOR_IOS_BLUE = "#007aff"
COLOR_IOS_BLUE_HOVER = "#0062cc"
COLOR_IOS_BLUE_BORDER = "#3894ff"
COLOR_IOS_BLUE_GLOW = "#60a5fa"

# Rojo Carmesí iOS (Pill Button "Delete", Cancelar, Batería Baja)
COLOR_IOS_RED = "#ff2d55"
COLOR_IOS_RED_HOVER = "#e02245"
COLOR_IOS_RED_BORDER = "#ff6384"

# Verde Interruptor iOS (Toggle / Online / Verified / Batería Llena)
COLOR_IOS_GREEN = "#34c759"
COLOR_IOS_GREEN_HOVER = "#2db14f"

# Ámbar / Naranja iOS (Avisos, Batería Media)
COLOR_IOS_ORANGE = "#ff9500"
COLOR_IOS_ORANGE_HOVER = "#e08500"

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
# Botones Primarios, Secundarios y de Peligro
# -------------------------------------------------------------
COLOR_BTN_PRIMARY_BG = COLOR_IOS_BLUE
COLOR_BTN_PRIMARY_HOVER = COLOR_IOS_BLUE_HOVER
COLOR_BTN_PRIMARY_BORDER = COLOR_IOS_BLUE_BORDER

COLOR_BTN_SECONDARY_BG = "#1c212d"
COLOR_BTN_SECONDARY_HOVER = "#283040"
COLOR_BTN_SECONDARY_BORDER = "#333c50"

COLOR_BTN_DANGER_BG = COLOR_IOS_RED
COLOR_BTN_DANGER_HOVER = COLOR_IOS_RED_HOVER
COLOR_BTN_DANGER_BORDER = COLOR_IOS_RED_BORDER

# -------------------------------------------------------------
# Tipografía y Textos iOS
# -------------------------------------------------------------
COLOR_TEXT_WHITE = "#ffffff"        # Blanco puro
COLOR_TEXT_MAIN = "#f8fafc"         # Texto principal 95% blanco
COLOR_TEXT_BRIGHT = "#f1f5f9"       # Texto destacado
COLOR_TEXT_LIGHT = "#e2e8f0"        # Texto secundario claro
COLOR_TEXT_MUTED_LIGHT = "#cbd5e1"  # Texto secundario medio
COLOR_TEXT_MUTED = "#94a3b8"        # Texto atenuado/descripciones
COLOR_TEXT_DIM = "#64748b"          # Texto terciario/apagado
COLOR_TEXT_EXTRA_DIM = "#475569"    # Placeholder o deshabilitado
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

FONT_FAMILY = "Segoe UI"
FONT_HEADING = "Segoe UI Semibold"

def font_title(size: int = 24, weight: str = "bold") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_HEADING, size=size, weight=weight)

def font_body(size: int = 12, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)

def font_button(size: int = 13, weight: str = "bold") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_HEADING, size=size, weight=weight)


def apply_rounded_window_region(window, width: int, height: int, radius: int = 28):
    """Aplica esquinas redondeadas nativas Win32 sin usar -transparentcolor (evita artefactos GDI al hacer scroll)."""
    import sys
    import ctypes
    if sys.platform != "win32":
        return
    try:
        if not window or not window.winfo_exists():
            return
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, int(width) + 1, int(height) + 1, int(radius), int(radius))
        ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
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

        scroll_frame.update_idletasks()
        if force_edge == "top":
            canvas.yview_moveto(0.0)
            return
        elif force_edge == "bottom":
            canvas.yview_moveto(1.0)
            return

        if not target_widget or not target_widget.winfo_exists():
            return

        content_h = max(1, scroll_frame.winfo_height())
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
