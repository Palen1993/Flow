import tkinter as tk
import customtkinter as ctk
from typing import Optional

from ui.theme import (
    font_button, font_body, apply_gamepad_focus,
    COLOR_BG_CARD, COLOR_GLASS_BORDER, COLOR_TEXT_MAIN, COLOR_TEXT_WHITE,
    COLOR_TEXT_MUTED_LIGHT, COLOR_CYAN_ACCENT,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_IOS_RED, COLOR_IOS_RED_HOVER, COLOR_IOS_RED_BORDER,
    COLOR_STATUS_WARNING, COLOR_STATUS_DANGER
)
from ui.controller_hud import get_button_icon_ctk
from gamepad_manager import get_connected_controller_family
from ui.dialogs.base_dialog import BaseGlassDialog


class GlassMessageBox(BaseGlassDialog):
    """
    Diálogo modal flotante estilo Glassmorphism (VisionOS / Liquid Glass Dark).
    Sustituye por completo los messageboxes nativos de Windows (MessageBoxW),
    garantizando operatividad 100% mediante mando (A / B / Start / Back / Cruceta),
    teclado y ratón, sin romper la inmersión en modo Big Picture o TV.
    """
    def __init__(
        self,
        parent: Optional[tk.Widget],
        title: str,
        message: str,
        kind: str = "info",  # 'info', 'warning', 'error', 'confirm'
        confirm_text: str = "Aceptar",
        cancel_text: str = "Cancelar",
        is_destructive: bool = False,
        family: Optional[str] = None
    ):
        self.result = False
        self.kind = kind
        self.is_destructive = is_destructive
        self.family = family or getattr(parent, "_current_controller_family", None) or get_connected_controller_family()

        # Determinar dimensiones según la longitud del mensaje
        msg_len = len(message)
        w = 460
        h = 240
        if msg_len > 120 or "\n" in message:
            h = min(420, 240 + (msg_len // 45) * 22)
            w = 480

        super().__init__(parent, title=title, width=w, height=h, corner_radius=22)

        # Foco inicial de botones
        # En confirmaciones destructivas el foco empieza en Cancelar (0) por seguridad; en las demás en Confirmar (1)
        self._focused_btn = 0 if is_destructive else 1
        self._btn_widgets = []

        self._build_ui(w, h, title, message, confirm_text, cancel_text)
        self._bind_events()
        self.focus_set()

    def _build_ui(self, w: int, h: int, title: str, message: str, confirm_text: str, cancel_text: str):
        pad = max(6, int(12 * self.scale_factor))
        self.card = ctk.CTkFrame(
            self, corner_radius=self.corner_radius,
            fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER, border_width=1.5
        )
        self.card.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.make_draggable(self.card)

        # Encabezado con icono temático
        header_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(16, 6))

        icon_map = {
            "info": ("💡", COLOR_CYAN_ACCENT),
            "warning": ("⚠️", COLOR_STATUS_WARNING),
            "error": ("❌", COLOR_STATUS_DANGER),
            "confirm": ("🗑️" if self.is_destructive else "❓", COLOR_STATUS_DANGER if self.is_destructive else COLOR_CYAN_ACCENT)
        }
        ic_char, ic_col = icon_map.get(self.kind, ("💡", COLOR_CYAN_ACCENT))

        self.lbl_icon = ctk.CTkLabel(
            header_frame, text=ic_char, font=("Segoe UI Emoji", 20), text_color=ic_col
        )
        self.lbl_icon.pack(side="left", padx=(0, 10))

        self.lbl_title = ctk.CTkLabel(
            header_frame, text=title, font=("Segoe UI Semibold", 16), text_color=COLOR_TEXT_MAIN
        )
        self.lbl_title.pack(side="left")

        # Cuerpo del mensaje
        msg_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        msg_frame.pack(fill="both", expand=True, padx=22, pady=(0, 10))

        self.lbl_msg = ctk.CTkLabel(
            msg_frame, text=message, font=font_body(12),
            text_color=COLOR_TEXT_MUTED_LIGHT, wraplength=w - 70, justify="left", anchor="nw"
        )
        self.lbl_msg.pack(fill="both", expand=True)

        # Botonera inferior
        btn_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 16))

        if self.kind == "confirm":
            btn_frame.grid_columnconfigure(0, weight=1)
            btn_frame.grid_columnconfigure(1, weight=1)

            self.btn_cancel = ctk.CTkButton(
                btn_frame,
                text=f"{cancel_text} ",
                image=get_button_icon_ctk("b", self.family, size=18),
                compound="right",
                height=38,
                corner_radius=19,
                font=font_button(12),
                fg_color=COLOR_BTN_SECONDARY_BG,
                hover_color=COLOR_BTN_SECONDARY_HOVER,
                border_color=COLOR_CYAN_ACCENT if self._focused_btn == 0 else COLOR_BTN_SECONDARY_BORDER,
                border_width=2.0 if self._focused_btn == 0 else 1.0,
                text_color=COLOR_TEXT_MUTED_LIGHT,
                command=self._on_cancel
            )
            self.btn_cancel.grid(row=0, column=0, padx=6, sticky="ew")

            # Botón de confirmación (rojo si es destructivo, azul iOS si es normal)
            conf_bg = COLOR_IOS_RED if self.is_destructive else COLOR_IOS_BLUE
            conf_hov = COLOR_IOS_RED_HOVER if self.is_destructive else COLOR_IOS_BLUE_HOVER
            conf_bor = COLOR_IOS_RED_BORDER if self.is_destructive else COLOR_IOS_BLUE_BORDER

            self.btn_confirm = ctk.CTkButton(
                btn_frame,
                text=f"{confirm_text} ",
                image=get_button_icon_ctk("a", self.family, size=18),
                compound="right",
                height=38,
                corner_radius=19,
                font=font_button(12),
                fg_color=conf_bg,
                hover_color=conf_hov,
                border_color=COLOR_TEXT_WHITE if self._focused_btn == 1 else conf_bor,
                border_width=2.0 if self._focused_btn == 1 else 1.2,
                text_color=COLOR_TEXT_WHITE,
                command=self._on_confirm
            )
            self.btn_confirm.grid(row=0, column=1, padx=6, sticky="ew")
            self._btn_widgets = [self.btn_cancel, self.btn_confirm]
            self._set_focus(self._focused_btn)
        else:
            # Modo informativo / alerta (botón único Aceptar)
            btn_col = COLOR_IOS_RED if self.kind == "error" else COLOR_IOS_BLUE
            btn_hov = COLOR_IOS_RED_HOVER if self.kind == "error" else COLOR_IOS_BLUE_HOVER

            self.btn_ok = ctk.CTkButton(
                btn_frame,
                text=f"{confirm_text} ",
                image=get_button_icon_ctk("a", self.family, size=18),
                compound="right",
                width=160,
                height=38,
                corner_radius=19,
                font=font_button(13),
                fg_color=btn_col,
                hover_color=btn_hov,
                border_color=COLOR_TEXT_WHITE,
                border_width=3,
                text_color=COLOR_TEXT_WHITE,
                command=self._on_confirm
            )
            self.btn_ok.pack(side="right")
            self._btn_widgets = [self.btn_ok]

        # Arrastre de ventana con el ratón
        self._drag_x = 0
        self._drag_y = 0
        for w_elem in (self.card, header_frame, self.lbl_title, self.lbl_icon):
            w_elem.bind("<ButtonPress-1>", self._start_drag)
            w_elem.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _bind_events(self):
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Return>", lambda e: self._activate_focused())
        self.bind("<space>", lambda e: self._activate_focused())
        if self.kind == "confirm":
            self.bind("<Left>", lambda e: self._set_focus(0))
            self.bind("<Right>", lambda e: self._set_focus(1))
            self.bind("<a>", lambda e: self._on_confirm())
            self.bind("<A>", lambda e: self._on_confirm())
            self.bind("<b>", lambda e: self._on_cancel())
            self.bind("<B>", lambda e: self._on_cancel())
        else:
            self.bind("<a>", lambda e: self._on_confirm())
            self.bind("<A>", lambda e: self._on_confirm())
            self.bind("<b>", lambda e: self._on_confirm())
            self.bind("<B>", lambda e: self._on_confirm())

    def _set_focus(self, idx: int):
        if self.kind != "confirm":
            return
        self._focused_btn = idx
        if hasattr(self, "btn_cancel") and hasattr(self, "btn_confirm"):
            apply_gamepad_focus(self.btn_cancel, idx == 0, role="secondary")
            apply_gamepad_focus(self.btn_confirm, idx == 1, role="danger" if self.is_destructive else "primary")

    def _activate_focused(self):
        if self.kind == "confirm":
            if self._focused_btn == 0:
                self._on_cancel()
            else:
                self._on_confirm()
        else:
            self._on_confirm()

    def _on_confirm(self):
        self.result = True
        self._close()

    def _on_cancel(self):
        self.result = False
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        if self.kind == "confirm":
            if inputs.get("left", False) and not prev_inputs.get("left", False):
                self._set_focus(0)
                return True
            if inputs.get("right", False) and not prev_inputs.get("right", False):
                self._set_focus(1)
                return True
            if (inputs.get("a", False) and not prev_inputs.get("a", False)) or \
               (inputs.get("start", False) and not prev_inputs.get("start", False)):
                self._activate_focused()
                return True
            if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
               (inputs.get("back", False) and not prev_inputs.get("back", False)):
                self._on_cancel()
                return True
        else:
            for k in ("a", "b", "start", "back", "x", "y"):
                if inputs.get(k, False) and not prev_inputs.get(k, False):
                    self._on_confirm()
                    return True
        return True


# =========================================================================
# FUNCIONES DE CONVENIENCIA (DROP-IN REPLACEMENT DE tkinter.messagebox)
# =========================================================================
def show_info(title: str, message: str, parent: Optional[tk.Widget] = None) -> bool:
    """Muestra un diálogo informativo estilo glass y espera a que el usuario lo cierre."""
    dlg = GlassMessageBox(parent, title, message, kind="info")
    dlg.wait_window()
    return True


def show_warning(title: str, message: str, parent: Optional[tk.Widget] = None) -> bool:
    """Muestra un diálogo de advertencia estilo glass y espera a que el usuario lo cierre."""
    dlg = GlassMessageBox(parent, title, message, kind="warning")
    dlg.wait_window()
    return True


def show_error(title: str, message: str, parent: Optional[tk.Widget] = None) -> bool:
    """Muestra un diálogo de error crítico estilo glass y espera a que el usuario lo cierre."""
    dlg = GlassMessageBox(parent, title, message, kind="error")
    dlg.wait_window()
    return True


def ask_yes_no(
    title: str,
    message: str,
    parent: Optional[tk.Widget] = None,
    confirm_text: str = "Aceptar",
    cancel_text: str = "Cancelar",
    is_destructive: bool = False
) -> bool:
    """
    Muestra un diálogo de confirmación con dos opciones (Cancelar / Aceptar o Cancelar / Eliminar).
    Retorna True si el usuario confirmó y False si canceló o cerró con B/Escape.
    """
    dlg = GlassMessageBox(
        parent, title, message, kind="confirm",
        confirm_text=confirm_text, cancel_text=cancel_text,
        is_destructive=is_destructive
    )
    dlg.wait_window()
    return bool(dlg.result)
