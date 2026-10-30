import customtkinter as ctk

from ui.theme import font_button
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import BaseGlassDialog

class ConfirmExitDialog(BaseGlassDialog):
    """Diálogo modal flotante de confirmación para cerrar la aplicación."""
    def __init__(self, parent, on_confirm=None):
        super().__init__(parent, title="¿Cerrar Lanzador?", width=420, height=220, corner_radius=22)
        self.on_confirm = on_confirm
        self._focused_btn = 1  # 0 = Cancelar, 1 = Cerrar
        
        self.create_widgets()
        self.bind_events()
        self._update_focus()

    def create_widgets(self):
        self.card = ctk.CTkFrame(
            self, width=390, height=190, corner_radius=22,
            fg_color="#141722", border_color="#2b3345", border_width=1.5
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        
        self.lbl_title = ctk.CTkLabel(
            self.card, text="¿Cerrar el lanzador?",
            font=("Segoe UI Semibold", 17),
            text_color="#f8fafc"
        )
        self.lbl_title.place(relx=0.5, rely=0.34, anchor="center")
        
        btn_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        btn_frame.place(relx=0.5, rely=0.68, anchor="center")
        
        self.btn_cancel = ctk.CTkButton(
            btn_frame, text="Cancelar ", image=get_button_icon_ctk("b", size=20), compound="right",
            width=138, height=38,
            fg_color="#1c212d", hover_color="#283040", border_color="#333c50", border_width=1.0,
            corner_radius=19, text_color="#cbd5e1", font=font_button(13),
            command=self.cancel
        )
        self.btn_cancel.pack(side="left", padx=8)
        
        self.btn_exit = ctk.CTkButton(
            btn_frame, text="Cerrar ", image=get_button_icon_ctk("a", size=20), compound="right",
            width=138, height=38,
            fg_color="#ff2d55", hover_color="#e02245",
            border_color="#ff6384", border_width=1.2,
            corner_radius=19, text_color="#ffffff", font=font_button(13),
            command=self.confirm
        )
        self.btn_exit.pack(side="left", padx=8)
        
        self.make_draggable(self.card)
        self.make_draggable(self.lbl_title)

    def bind_events(self):
        self.bind("<Return>", lambda e: self._activate_focused())
        self.bind("<space>", lambda e: self._activate_focused())
        self.bind("<Left>", lambda e: self._set_focus(0))
        self.bind("<Right>", lambda e: self._set_focus(1))
        self.bind("<Escape>", lambda e: self.cancel())
        self.bind("<b>", lambda e: self.cancel())
        self.bind("<B>", lambda e: self.cancel())
        self.bind("<a>", lambda e: self.confirm())
        self.bind("<A>", lambda e: self.confirm())
        self.bind("<y>", lambda e: self.confirm())
        self.bind("<Y>", lambda e: self.confirm())

    def _set_focus(self, idx: int):
        self._focused_btn = idx
        self._update_focus()

    def _update_focus(self):
        if hasattr(self, "btn_cancel") and self.btn_cancel.winfo_exists():
            self.btn_cancel.configure(
                border_color="#38bdf8" if self._focused_btn == 0 else "#333c50",
                border_width=2.0 if self._focused_btn == 0 else 1.0
            )
        if hasattr(self, "btn_exit") and self.btn_exit.winfo_exists():
            self.btn_exit.configure(
                border_color="#ffffff" if self._focused_btn == 1 else "#ff6384",
                border_width=2.0 if self._focused_btn == 1 else 1.2
            )

    def _activate_focused(self):
        if self._focused_btn == 0:
            self.cancel()
        else:
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
        if inputs.get("left", False) and not prev_inputs.get("left", False):
            self._set_focus(0)
            return True
        if inputs.get("right", False) and not prev_inputs.get("right", False):
            self._set_focus(1)
            return True
        if (inputs.get("a", False) and not prev_inputs.get("a", False)) or (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self._activate_focused()
            return True
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.cancel()
            return True
        return True
