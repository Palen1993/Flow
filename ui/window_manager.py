import os
import sys
import customtkinter as ctk
import win32api
import win32con

from ui.theme import COLOR_BG_DARK, COLOR_BG_CANVAS, COLOR_TRANS_KEY
from gamepad_manager import force_foreground_window
from core.logger import get_logger

logger = get_logger("WindowManager")


class WindowStateService:
    """
    Servicio desacoplado responsable de gestionar los estados de visualización de la ventana:
    - Modo Widget Pequeño Flotante (sin bordes, 100% transparente con clave de color Win32).
    - Modo Pantalla Completa Cinematográfico (Big Picture 16:9).
    - Minimización / Restauración a primer plano interactivo con retención topmost.
    - Asignación de icono Liquid Glass personalizado en ventana y barra de tareas.
    """

    def __init__(self, app: ctk.CTk):
        self.app = app
        self.is_mini_mode: bool = False
        self.is_fullscreen: bool = False
        self.is_minimized: bool = False
        self._app_icon_ref = None

    def setup_app_icon(self) -> None:
        """Asigna el icono Liquid Glass a la ventana y a la barra de tareas de Windows."""
        try:
            base_dir = (
                os.path.dirname(sys.executable)
                if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            ico_path = os.path.join(base_dir, "assets", "icon.ico")
            png_path = os.path.join(base_dir, "assets", "icon.png")
            if not os.path.isfile(ico_path):
                ico_path = os.path.join(base_dir, "_internal", "assets", "icon.ico")
            if not os.path.isfile(png_path):
                png_path = os.path.join(base_dir, "_internal", "assets", "icon.png")

            if os.path.isfile(ico_path):
                try:
                    self.app.iconbitmap(ico_path)
                except Exception:
                    pass

            if os.path.isfile(png_path):
                try:
                    from PIL import Image, ImageTk
                    with Image.open(png_path) as raw_im:
                        photo = ImageTk.PhotoImage(raw_im.resize((64, 64), Image.Resampling.LANCZOS))
                        self.app.iconphoto(True, photo)
                        self._app_icon_ref = photo
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Aviso configurando icono: {e}")

    def set_mini_mode(self, cover_stage, top_bar=None, bottom_panel=None) -> None:
        """Activa el modo widget pequeño y flotante: UI 100% transparente sin marco ni reflejo."""
        self.is_mini_mode = True
        self.is_fullscreen = False
        self.is_minimized = False

        if top_bar:
            top_bar.grid_remove()
        if bottom_panel:
            bottom_panel.grid_remove()

        # Desactivar pantalla completa si estaba activa
        try:
            self.app.attributes("-fullscreen", False)
        except Exception:
            pass

        # Ventana flotante pura sin bordes ni barra de título
        try:
            self.app.overrideredirect(True)
        except Exception:
            pass

        try:
            self.app.attributes("-topmost", True)
        except Exception:
            pass

        # Clave de transparencia en Windows
        try:
            self.app.configure(fg_color=COLOR_TRANS_KEY)
            self.app.wm_attributes("-transparentcolor", COLOR_TRANS_KEY)
        except Exception:
            pass

        if cover_stage:
            cover_stage.configure(bg=COLOR_TRANS_KEY)
            cover_stage.is_transparent_mode = True

        self.app.minsize(400, 200)

        # Centrar ventana flotante en el monitor actual compensando el ScalingTracker de CustomTkinter
        from ui.display_scale import get_ctk_window_scaling
        ctk_scale = get_ctk_window_scaling(self.app)
        try:
            hmon = win32api.MonitorFromWindow(self.app.winfo_id(), win32con.MONITOR_DEFAULTTONEAREST)
            mon_info = win32api.GetMonitorInfo(hmon)
            rc = mon_info.get(
                "Work",
                mon_info.get("Monitor", (0, 0, self.app.winfo_screenwidth(), self.app.winfo_screenheight()))
            )
            screen_w = rc[2] - rc[0]
            screen_h = rc[3] - rc[1]
            phys_win_w = max(720, min(int(screen_w * 0.84), screen_w - 40))
            phys_win_h = max(320, min(int(screen_h * 0.48), screen_h - 60))
            x = rc[0] + max(0, (screen_w - phys_win_w) // 2)
            y = rc[1] + max(0, (screen_h - phys_win_h) // 2)
        except Exception:
            screen_w = self.app.winfo_screenwidth()
            screen_h = self.app.winfo_screenheight()
            phys_win_w = max(720, min(int(screen_w * 0.84), screen_w - 40))
            phys_win_h = max(320, min(int(screen_h * 0.48), screen_h - 60))
            x = max(0, (screen_w - phys_win_w) // 2)
            y = max(0, (screen_h - phys_win_h) // 2)

        win_w = max(400, int(round(phys_win_w / ctk_scale)))
        win_h = max(200, int(round(phys_win_h / ctk_scale)))
        self.app.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.app.update_idletasks()

        if cover_stage:
            cover_stage.last_w = 0
            cover_stage.last_h = 0
            cover_stage._rebuild_rendered_cache()
            cw = cover_stage.winfo_width()
            ch = cover_stage.winfo_height()
            if cw > 60 and ch > 60:
                cover_stage._on_resize(type("Event", (), {"width": cw, "height": ch})())
            else:
                cover_stage.redraw()

        logger.debug("Modo Mini Widget Transparente aplicado")

    def set_full_mode(self, cover_stage, top_bar=None, bottom_panel=None) -> None:
        """Restaura el modo pantalla completa con UI y fondo cinematográfico."""
        self.is_mini_mode = False
        self.is_fullscreen = True
        self.is_minimized = False

        try:
            self.app.wm_attributes("-transparentcolor", "")
        except Exception:
            pass

        try:
            self.app.attributes("-topmost", False)
        except Exception:
            pass

        try:
            self.app.overrideredirect(False)
        except Exception:
            pass

        self.app.configure(fg_color=COLOR_BG_DARK)

        if top_bar:
            top_bar.grid_remove()
        if bottom_panel:
            bottom_panel.grid_remove()

        if cover_stage:
            cover_stage.configure(bg=COLOR_BG_CANVAS)
            cover_stage.is_transparent_mode = False

        self.app.minsize(640, 400)
        try:
            self.app.attributes("-fullscreen", True)
        except Exception:
            pass

        self.app.update_idletasks()

        if cover_stage:
            cover_stage.last_w = 0
            cover_stage.last_h = 0
            cover_stage._rebuild_rendered_cache()
            cw = cover_stage.winfo_width()
            ch = cover_stage.winfo_height()
            if cw > 60 and ch > 60:
                cover_stage._on_resize(type("Event", (), {"width": cw, "height": ch})())
            else:
                cover_stage.redraw()

        logger.debug("Modo Pantalla Completa Big Picture aplicado")

    def toggle_size_mode(self, cover_stage, top_bar=None, bottom_panel=None) -> None:
        """Alterna entre Modo Mini Transparente y Modo Grande Pantalla Completa."""
        if self.is_mini_mode:
            self.set_full_mode(cover_stage, top_bar, bottom_panel)
        else:
            self.set_mini_mode(cover_stage, top_bar, bottom_panel)

    def minimize_window(self) -> None:
        """Minimiza/oculta el lanzador sin detener la escucha del mando."""
        self.is_minimized = True
        try:
            self.app.withdraw()
        except Exception:
            pass

    def restore_window(self) -> None:
        """Restaura el lanzador y lo devuelve al frente interactivo."""
        self.is_minimized = False
        try:
            self.app.deiconify()
            self.app.lift()
            self.app.focus_force()
            force_foreground_window(self.app.winfo_id(), keep_topmost=self.is_mini_mode)
        except Exception:
            pass

    def toggle_minimize(self) -> None:
        """Alterna entre ocultar/minimizar el lanzador y restaurarlo."""
        if self.is_minimized:
            self.restore_window()
        else:
            self.minimize_window()
