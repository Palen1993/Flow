import customtkinter as ctk

from ui.theme import (
    COLOR_BG_CARD, COLOR_GLASS_BORDER, COLOR_TEXT_MAIN, COLOR_TEXT_WHITE,
    COLOR_TEXT_MUTED_LIGHT, COLOR_CYAN_ACCENT,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_BTN_DANGER_BG, COLOR_BTN_DANGER_HOVER, COLOR_BTN_DANGER_BORDER,
    font_button, apply_gamepad_focus
)
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import BaseGlassDialog

class ConfirmExitDialog(BaseGlassDialog):
    """Diálogo modal flotante de confirmación para cerrar la aplicación con soporte para Modo Kiosco."""
    def __init__(self, parent, on_confirm=None):
        from core.kiosk_service import is_kiosk_shell_active
        self.kiosk_active = is_kiosk_shell_active()
        dialog_w = 490 if self.kiosk_active else 420
        dialog_h = 240 if self.kiosk_active else 220
        super().__init__(parent, title="¿Cerrar Lanzador?", width=dialog_w, height=dialog_h, corner_radius=22)
        self.on_confirm = on_confirm
        self.family = getattr(parent, "_current_controller_family", "xbox")
        self._focused_btn = 2 if self.kiosk_active else 1
        
        self.create_widgets()
        self.bind_events()
        self._update_focus()

    def create_widgets(self):
        sc = getattr(self, "scale_factor", 1.0)
        self.card = ctk.CTkFrame(
            self, width=self.dialog_width - int(24 * sc), height=self.dialog_height - int(24 * sc), corner_radius=self.corner_radius,
            fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER, border_width=1.5
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        
        title_text = "Modo Kiosco Activo: ¿Deseas salir?" if self.kiosk_active else "¿Cerrar el lanzador?"
        self.lbl_title = ctk.CTkLabel(
            self.card, text=title_text,
            font=font_button(16),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_title.place(relx=0.5, rely=0.30 if self.kiosk_active else 0.34, anchor="center")
        
        btn_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        btn_frame.place(relx=0.5, rely=0.68, anchor="center")

        btn_w = int(120 * sc) if self.kiosk_active else int(138 * sc)
        btn_h = int(38 * sc)
        btn_rad = int(19 * sc)
        
        self.btn_cancel = ctk.CTkButton(
            btn_frame, text="Cancelar ", image=get_button_icon_ctk("b", self.family, size=int(18 * sc)), compound="right",
            width=btn_w, height=btn_h,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0,
            corner_radius=btn_rad, text_color=COLOR_TEXT_MUTED_LIGHT, font=font_button(12),
            command=self.cancel
        )
        self.btn_cancel.pack(side="left", padx=6)

        if self.kiosk_active:
            self.btn_desktop = ctk.CTkButton(
                btn_frame, text="Escritorio ", image=get_button_icon_ctk("y", self.family, size=int(18 * sc)), compound="right",
                width=int(135 * sc), height=btn_h,
                fg_color="#182436", hover_color="#22334c",
                border_color="#2e4364", border_width=1.0,
                corner_radius=btn_rad, text_color=COLOR_CYAN_ACCENT, font=font_button(12),
                command=self.open_desktop_and_exit
            )
            self.btn_desktop.pack(side="left", padx=6)
        
        self.btn_exit = ctk.CTkButton(
            btn_frame, text="Cerrar ", image=get_button_icon_ctk("a", self.family, size=int(18 * sc)), compound="right",
            width=btn_w, height=btn_h,
            fg_color=COLOR_BTN_DANGER_BG, hover_color=COLOR_BTN_DANGER_HOVER,
            border_color=COLOR_BTN_DANGER_BORDER, border_width=1.2,
            corner_radius=btn_rad, text_color=COLOR_TEXT_WHITE, font=font_button(12),
            command=self.confirm
        )
        self.btn_exit.pack(side="left", padx=6)
        
        self.make_draggable(self.card)
        self.make_draggable(self.lbl_title)

    def bind_events(self):
        self.bind("<Return>", lambda e: self._activate_focused())
        self.bind("<space>", lambda e: self._activate_focused())
        max_idx = 2 if self.kiosk_active else 1
        self.bind("<Left>", lambda e: self._set_focus(max(0, self._focused_btn - 1)))
        self.bind("<Right>", lambda e: self._set_focus(min(max_idx, self._focused_btn + 1)))
        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<b>", lambda e: self.cancel())
        self.bind("<B>", lambda e: self.cancel())
        self.bind("<a>", lambda e: self._activate_focused())
        self.bind("<A>", lambda e: self._activate_focused())
        if self.kiosk_active:
            self.bind("<y>", lambda e: self.open_desktop_and_exit())
            self.bind("<Y>", lambda e: self.open_desktop_and_exit())

    def _set_focus(self, idx: int):
        self._focused_btn = idx
        self._update_focus()

    def _update_focus(self):
        max_idx = 2 if self.kiosk_active else 1
        if hasattr(self, "btn_cancel") and self.btn_cancel.winfo_exists():
            apply_gamepad_focus(self.btn_cancel, self._focused_btn == 0, role="secondary")
        if self.kiosk_active and hasattr(self, "btn_desktop") and self.btn_desktop.winfo_exists():
            apply_gamepad_focus(self.btn_desktop, self._focused_btn == 1, role="primary")
        if hasattr(self, "btn_exit") and self.btn_exit.winfo_exists():
            apply_gamepad_focus(self.btn_exit, self._focused_btn == max_idx, role="danger")

    def _activate_focused(self):
        if self._focused_btn == 0:
            self.cancel()
        elif self.kiosk_active and self._focused_btn == 1:
            self.open_desktop_and_exit()
        else:
            self.confirm()

    def open_desktop_and_exit(self):
        from core.kiosk_service import launch_windows_explorer
        launch_windows_explorer()
        self.confirm()
        
    def confirm(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if hasattr(self.master, "exit_dialog"):
            self.master.exit_dialog = None
        if self.on_confirm:
            self.on_confirm()
            
    def cancel(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if hasattr(self.master, "exit_dialog"):
            self.master.exit_dialog = None

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        max_idx = 2 if self.kiosk_active else 1
        if inputs.get("left", False) and not prev_inputs.get("left", False):
            self._set_focus(max(0, self._focused_btn - 1))
            return True
        if inputs.get("right", False) and not prev_inputs.get("right", False):
            self._set_focus(min(max_idx, self._focused_btn + 1))
            return True
        if inputs.get("y", False) and not prev_inputs.get("y", False) and self.kiosk_active:
            self.open_desktop_and_exit()
            return True
        if (inputs.get("a", False) and not prev_inputs.get("a", False)) or (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self._activate_focused()
            return True
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.cancel()
            return True
        return True
