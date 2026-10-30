import sys
from typing import Optional, Any
import tkinter as tk
import customtkinter as ctk

from ui.theme import apply_rounded_window_region, hide_from_taskbar, bring_to_front_absolute, COLOR_BG_CARD
from ui.modal_manager import register_modal_stack, unregister_modal_stack

class BaseGlassDialog(ctk.CTkToplevel):
    """
    Clase base unificada para todos los diálogos modales estilo Glassmorphism de GameFlow.
    
    Características integradas:
    - Ventana borderless sin barra nativa de Windows (overrideredirect).
    - Esquinas redondeadas Win32 aceleradas por hardware (CreateRoundRectRgn).
    - Fondo oscuro metálico (#141722) con borde refinado.
    - Centrado automático con respecto a la ventana padre o a la pantalla.
    - Soporte integrado para arrastrar la ventana con el ratón.
    - Registro y desregistro automático en la Pila de Modales O(1) de App (eliminando sondeos de CPU).
    - Despacho y captura de entrada de mando (cruceta, A, B, Escape).
    """
    def _windows_set_titlebar_color(self, color_mode: str):
        # Desactivado intencionadamente: los diálogos Glass son overrideredirect (sin barra de título de Windows)
        pass

    def _windows_set_titlebar_icon(self):
        # Desactivado intencionadamente: sin barra nativa
        pass

    def __init__(
        self,
        parent: Optional[tk.Widget],
        title: str = "Diálogo",
        width: int = 480,
        height: int = 320,
        corner_radius: int = 22,
        is_topmost: bool = True,
        auto_grab: bool = True
    ):
        super().__init__(parent)
        self.dialog_width = width
        self.dialog_height = height
        self.corner_radius = corner_radius
        self.parent = parent
        
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        
        try:
            self.overrideredirect(True)
        except Exception:
            pass
        try:
            self.deiconify()
        except Exception:
            pass
        if is_topmost:
            try:
                self.attributes("-topmost", True)
            except Exception:
                pass
                
        self.configure(fg_color=COLOR_BG_CARD)
        if parent:
            try:
                self.transient(parent)
            except Exception:
                pass
        hide_from_taskbar(self)
        bring_to_front_absolute(self)
                
        self._drag_x = 0
        self._drag_y = 0
        self._pending_afters = []
        
        # Centrado y redondeado automático
        self.center_window()
        try:
            self._pending_afters.append(self.after(20, self.center_window))
            self._pending_afters.append(self.after(25, lambda: bring_to_front_absolute(self)))
            self._pending_afters.append(self.after(35, self.apply_rounded_corners))
            self._pending_afters.append(self.after(80, lambda: bring_to_front_absolute(self)))
        except Exception:
            pass
        
        if auto_grab:
            try:
                self.grab_set()
            except Exception:
                pass
                
        # Registro en la Pila de Modales O(1)
        self._register_in_modal_stack()
        
        # Enlaces de teclado estándar
        self.bind("<Escape>", lambda e: self.on_cancel())
        self.bind("<Destroy>", self._on_destroy_event)

    def _find_root_app(self) -> Optional[Any]:
        curr = self.parent or getattr(self, "master", None)
        while curr:
            if hasattr(curr, "push_modal") and hasattr(curr, "_modal_stack"):
                return curr
            curr = getattr(curr, "master", None) or getattr(curr, "parent", None)
        return None

    def _register_in_modal_stack(self):
        root = self._find_root_app()
        if root and hasattr(root, "push_modal"):
            root.push_modal(self)

    def _unregister_from_modal_stack(self):
        root = self._find_root_app()
        if root and hasattr(root, "pop_modal"):
            root.pop_modal(self)

    def _on_destroy_event(self, event):
        if event.widget == self:
            self._unregister_from_modal_stack()

    def destroy(self):
        self._unregister_from_modal_stack()
        for after_id in getattr(self, "_pending_afters", []):
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._pending_afters = []
        try:
            super().destroy()
        except Exception:
            pass

    def center_window(self, width: Optional[int] = None, height: Optional[int] = None):
        """Centra la ventana respecto a la ventana padre o a la pantalla."""
        try:
            if not self.winfo_exists():
                return
            self.update_idletasks()
            w = width or self.dialog_width
            h = height or self.dialog_height
            
            p = self.parent or getattr(self, "master", None)
            if p and p.winfo_exists():
                pw = p.winfo_width()
                ph = p.winfo_height()
                px = p.winfo_rootx()
                py = p.winfo_rooty()
                x = px + max(0, (pw - w) // 2)
                y = py + max(0, (ph - h) // 2)
            else:
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                x = max(0, (sw - w) // 2)
                y = max(0, (sh - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def apply_rounded_corners(self):
        """Aplica esquinas redondeadas nativas Win32 sin parpadeos ni artefactos GDI."""
        try:
            if self.winfo_exists():
                apply_rounded_window_region(self, self.dialog_width, self.dialog_height, self.corner_radius)
        except Exception:
            pass

    def make_draggable(self, widget: tk.Widget):
        """Permite que un widget (ej: cabecera o marco) arrastre la ventana con el ratón."""
        widget.bind("<ButtonPress-1>", self._start_drag)
        widget.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    def close(self):
        """Cierra y destruye limpiamente el diálogo modal."""
        self.destroy()

    def on_cancel(self):
        """Acción por defecto al presionar Escape o botón B del mando."""
        self.destroy()

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        """Manejador base de mando. Devuelve True si consumió el input."""
        # Botón B o Back para salir/cancelar
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.on_cancel()
            return True
        return False
