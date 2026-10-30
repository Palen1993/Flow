import customtkinter as ctk

from ui.theme import (
    font_button,
    COLOR_BG_CARD, COLOR_GLASS_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_LIGHT, COLOR_TEXT_WHITE,
    COLOR_TEXT_MUTED, COLOR_TEXT_DIM, COLOR_TEXT_EXTRA_DIM,
    COLOR_CYAN_ACCENT,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_WARNING, COLOR_STATUS_DANGER,
    COLOR_BTN_PRIMARY_BG, COLOR_BTN_PRIMARY_HOVER
)
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import BaseGlassDialog


class _ControllerRow(ctk.CTkFrame):
    """Fila con el estado de un mando: rol, nombre, porcentaje y barra de batería."""

    def __init__(self, parent, role_text: str):
        super().__init__(parent, fg_color="#10141d", corner_radius=14, border_width=1, border_color="#232b3c")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(8, 0))
        self.lbl_role = ctk.CTkLabel(top, text=role_text, anchor="w",
                                     font=("Segoe UI Semibold", 11), text_color=COLOR_CYAN_ACCENT)
        self.lbl_role.pack(side="left")
        self.lbl_dot = ctk.CTkLabel(top, text="●", font=("Segoe UI", 12), text_color=COLOR_TEXT_EXTRA_DIM)
        self.lbl_dot.pack(side="right")

        self.lbl_device = ctk.CTkLabel(self, text="", anchor="w",
                                       font=("Segoe UI", 11), text_color=COLOR_TEXT_MUTED)
        self.lbl_device.pack(fill="x", padx=14)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(2, 10))
        self.lbl_percent = ctk.CTkLabel(body, text="--", width=70, anchor="w",
                                        font=("Segoe UI Semibold", 20), text_color=COLOR_TEXT_DIM)
        self.lbl_percent.pack(side="left")
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.lbl_state = ctk.CTkLabel(right, text="", anchor="w",
                                      font=("Segoe UI Semibold", 11), text_color=COLOR_TEXT_LIGHT)
        self.lbl_state.pack(fill="x")
        self.bar = ctk.CTkProgressBar(right, height=9, corner_radius=5,
                                      fg_color="#1e2636", progress_color=COLOR_TEXT_EXTRA_DIM)
        self.bar.pack(fill="x", pady=(3, 0))
        self.bar.set(0)

    def update_info(self, info):
        if not info or not info.get("connected"):
            self.lbl_device.configure(text=(info or {}).get("device_name") or "Ningún mando detectado")
            self.lbl_dot.configure(text_color=COLOR_STATUS_DANGER)
            self.lbl_percent.configure(text="--", text_color=COLOR_TEXT_DIM)
            self.lbl_state.configure(text="Desconectado")
            self.bar.configure(progress_color=COLOR_TEXT_EXTRA_DIM)
            self.bar.set(0)
            return

        dev = (info.get("device_name") or "").strip()
        if not dev or dev.lower() in ("ninguno", "none", "--"):
            dev = "Mando PlayStation" if info.get("family") == "playstation" else "Mando Xbox / XInput"
        self.lbl_device.configure(text=dev)
        self.lbl_dot.configure(text_color=COLOR_STATUS_SUCCESS)

        lvl = info.get("level", "")
        pct = int(info.get("percent", 0) or 0)
        is_charging = info.get("is_charging", False)
        if lvl == "directinput":
            col, pct_txt, state, val = COLOR_CYAN_ACCENT, "OK", "Conectado · batería no disponible (DirectInput)", 1.0
        elif is_charging:
            if pct >= 100 or lvl == "full":
                col, pct_txt, state, val = COLOR_STATUS_SUCCESS, "100%", "Batería completamente cargada (⚡)", 1.0
            else:
                col, pct_txt, state, val = COLOR_CYAN_ACCENT, f"{pct}%", f"Cargando batería (⚡) · {pct}%", max(0.0, min(1.0, pct / 100.0))
        elif info.get("is_wired"):
            col, pct_txt, state, val = COLOR_CYAN_ACCENT, "USB", "Conectado por cable USB", 1.0
        elif lvl == "unknown":
            col, pct_txt, state, val = COLOR_CYAN_ACCENT, "OK", "Conectado · batería desconocida", 1.0
        else:
            if lvl == "empty":
                col, state = COLOR_STATUS_DANGER, "Batería crítica · conecta el cable"
            elif lvl == "low":
                col, state = COLOR_STATUS_WARNING, "Batería baja"
            elif lvl == "medium":
                col, state = COLOR_STATUS_SUCCESS, "Batería media · inalámbrico"
            else:
                col, state = COLOR_STATUS_SUCCESS, "Batería llena · inalámbrico"
            pct_txt = f"{pct}%"
            val = max(0.0, min(1.0, pct / 100.0))

        self.lbl_percent.configure(text=pct_txt, text_color=col)
        self.lbl_state.configure(text=state)
        self.bar.configure(progress_color=col)
        self.bar.set(val)


class ControllerInfoDialog(BaseGlassDialog):
    """
    Popup flotante con el estilo oscuro/glass de la aplicación que muestra el estado de los mandos:
      - Mando principal (el primero en conectarse; es el único que maneja la aplicación).
      - Mando secundario (solo lectura: conexión y batería).
    Se cierra con A / B / Start / Back del mando principal, Enter / Escape o el botón 'Aceptar'.
    Se refresca solo cada 2 s mientras está abierto.
    """
    W = 440
    H = 392

    def __init__(self, parent, family: str = "xbox"):
        self.family = family or "xbox"
        super().__init__(parent, title="Estado de los Mandos", width=self.W, height=self.H, corner_radius=22)
        self._refresh_job = None

        self._build_ui()
        self._bind_events()
        self._refresh_info()
        self.focus_set()

    def _build_ui(self):
        self.card = ctk.CTkFrame(
            self, width=self.W - 24, height=self.H - 24, corner_radius=22,
            fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER, border_width=1.5
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.pack_propagate(False)

        self.lbl_title = ctk.CTkLabel(
            self.card, text="Estado de los Mandos",
            font=("Segoe UI Semibold", 17), text_color=COLOR_TEXT_MAIN
        )
        self.lbl_title.pack(pady=(16, 0))
        self.lbl_sub = ctk.CTkLabel(
            self.card, text="Solo el mando principal maneja el lanzador",
            font=("Segoe UI", 11), text_color=COLOR_TEXT_DIM
        )
        self.lbl_sub.pack(pady=(0, 8))

        self.row_primary = _ControllerRow(self.card, "MANDO PRINCIPAL  ·  controla la aplicación")
        self.row_primary.pack(fill="x", padx=20, pady=(0, 8))
        self.row_secondary = _ControllerRow(self.card, "MANDO SECUNDARIO  ·  solo lectura")
        self.row_secondary.pack(fill="x", padx=20, pady=(0, 8))

        self.btn_ok = ctk.CTkButton(
            self.card, text="Aceptar ", image=get_button_icon_ctk("a", self.family, size=20),
            compound="right", width=150, height=38,
            fg_color=COLOR_BTN_PRIMARY_BG, hover_color=COLOR_BTN_PRIMARY_HOVER,
            border_color=COLOR_TEXT_WHITE, border_width=2.0,
            corner_radius=19, text_color=COLOR_TEXT_WHITE, font=font_button(13),
            command=self.close
        )
        self.btn_ok.pack(pady=(4, 0))

        for w in (self.card, self.lbl_title, self.lbl_sub):
            self.make_draggable(w)

    def _bind_events(self):
        for key in ("<Return>", "<space>", "<Escape>", "<a>", "<A>", "<b>", "<B>"):
            self.bind(key, lambda e: self.close())

    # ------------------------------------------------------------------
    def _refresh_info(self):
        try:
            import gamepad_manager as gm
            pads = gm.get_all_gamepads_info()
        except Exception:
            pads = []

        primary = pads[0] if len(pads) > 0 else None
        secondary = pads[1] if len(pads) > 1 else None
        self.row_primary.update_info(primary)
        if secondary is None:
            self.row_secondary.update_info({"connected": False, "device_name": "Ningún mando secundario conectado"})
        else:
            self.row_secondary.update_info(secondary)

        try:
            self._refresh_job = self.after(2000, self._refresh_info)
        except Exception:
            self._refresh_job = None

    # ------------------------------------------------------------------
    def close(self):
        if self._refresh_job:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        for k in ("a", "b", "start", "back", "y"):
            if inputs.get(k, False) and not prev_inputs.get(k, False):
                self.close()
                return True
        return True
