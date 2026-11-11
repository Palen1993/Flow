"""
GameFlow - Diálogo Modal de Modo Kiosco y Shell de Consola Dedicada
===================================================================
Permite transformar un PC o consola portátil (ROG Ally, Steam Deck, Legion Go)
en una consola de juegos dedicada estilo Steam Deck / Nintendo Switch:
1. Shell de Consola: Sustituye explorer.exe por GameFlow al iniciar sesión.
2. Inicio Automático: Arranca GameFlow automáticamente con Windows.
3. Respaldo Seguro: Botón directo para lanzar el Explorador de Windows (explorer.exe)
   en cualquier momento sin desinstalar nada.
4. Totalmente navegable con mando de consola (Cruceta, A, B).
"""

import sys
import tkinter as tk
from typing import Dict, Any, Optional
import customtkinter as ctk

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.glass_message_box import show_info, show_warning, show_error, ask_yes_no
from core.kiosk_service import (
    is_kiosk_shell_active, enable_kiosk_shell, disable_kiosk_shell,
    is_autostart_active, set_autostart, launch_windows_explorer,
    get_kiosk_status
)
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_BTN_DANGER_BG, COLOR_BTN_DANGER_HOVER, COLOR_BTN_DANGER_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_WARNING, COLOR_CYAN_ACCENT,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_button, font_body, apply_gamepad_focus
)


class KioskDialog(BaseGlassDialog):
    """
    Diálogo modal de configuración del Modo Kiosco y Shell de Consola en Windows.
    Permite arrancar GameFlow como la interfaz única del sistema para una experiencia
    inmersiva 100% de consola de salón o portátil.
    """

    def __init__(self, parent, on_status_changed=None):
        super().__init__(
            parent,
            title="🎮 Modo Kiosco / Consola Dedicada",
            width=640,
            height=540,
            corner_radius=24
        )
        self.on_status_changed = on_status_changed
        self.family = getattr(parent, "_current_controller_family", "xbox")
        self._focused_idx = 0
        self._nav_controls = []

        self._build_ui()
        self._refresh_status()
        self._update_focus_visuals()

    def _build_ui(self):
        # Card contenedor Liquid Glass
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)
        self.main_card.grid_columnconfigure(0, weight=1)

        # 1. Cabecera superior arrastrable
        header_bar = ctk.CTkFrame(self.main_card, fg_color="transparent")
        header_bar.pack(fill="x", padx=20, pady=(16, 6))

        lbl_title = ctk.CTkLabel(
            header_bar,
            text="🎮  Modo Kiosco / Consola Dedicada",
            font=font_button(18),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")

        self.make_draggable(header_bar)
        self.make_draggable(lbl_title)

        lbl_desc = ctk.CTkLabel(
            self.main_card,
            text="Convierte tu equipo o consola portátil en un dispositivo de videojuegos dedicado.\n"
                 "Al encender el PC, GameFlow cargará directamente sin barra de tareas ni escritorio de Windows.",
            font=font_body(12),
            text_color=COLOR_TEXT_DIM,
            justify="left",
            anchor="w"
        )
        lbl_desc.pack(fill="x", padx=22, pady=(0, 10))

        # 2. Tarjeta de Estado Actual
        status_card = ctk.CTkFrame(
            self.main_card,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1.0,
            corner_radius=16
        )
        status_card.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkLabel(
            status_card,
            text="Estado del Sistema:",
            font=font_button(13),
            text_color=COLOR_TEXT_BRIGHT
        ).pack(anchor="w", padx=16, pady=(10, 4))

        self.lbl_shell_status = ctk.CTkLabel(
            status_card,
            text="• Shell de Windows: Consultando...",
            font=font_body(12),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        self.lbl_shell_status.pack(fill="x", padx=20, pady=2)

        self.lbl_autostart_status = ctk.CTkLabel(
            status_card,
            text="• Inicio con Windows: Consultando...",
            font=font_body(12),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        self.lbl_autostart_status.pack(fill="x", padx=20, pady=(2, 10))

        # 3. Opciones y Acciones Principales
        actions_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        actions_frame.pack(fill="x", padx=20, pady=(0, 10))

        # Botón 1: Toggle Shell de Consola
        self.btn_toggle_shell = ctk.CTkButton(
            actions_frame,
            text="Configurar Modo Kiosco (Shell de Consola)",
            image=get_button_icon_ctk("a", self.family, size=18),
            compound="right",
            height=42,
            corner_radius=18,
            font=font_button(13),
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            command=self._on_toggle_shell_clicked
        )
        self.btn_toggle_shell.pack(fill="x", pady=5)

        # Botón 2: Toggle Autostart
        self.btn_toggle_autostart = ctk.CTkButton(
            actions_frame,
            text="Iniciar GameFlow al Encender Windows",
            image=get_button_icon_ctk("x", self.family, size=18),
            compound="right",
            height=38,
            corner_radius=18,
            font=font_button(12),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.0,
            text_color=COLOR_TEXT_BRIGHT,
            command=self._on_toggle_autostart_clicked
        )
        self.btn_toggle_autostart.pack(fill="x", pady=5)

        # Botón 3: Lanzar explorer.exe bajo demanda
        self.btn_launch_explorer = ctk.CTkButton(
            actions_frame,
            text="🖥  Abrir Escritorio de Windows (explorer.exe)",
            image=get_button_icon_ctk("y", self.family, size=18),
            compound="right",
            height=38,
            corner_radius=18,
            font=font_button(12),
            fg_color="#182234",
            hover_color="#223048",
            border_color="#2d3d5a",
            border_width=1.0,
            text_color=COLOR_CYAN_ACCENT,
            command=self._on_launch_explorer_clicked
        )
        self.btn_launch_explorer.pack(fill="x", pady=5)

        # 4. Pie de página con botón Cerrar
        bottom_bar = ctk.CTkFrame(self.main_card, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=20, pady=(10, 16))

        self.btn_close = ctk.CTkButton(
            bottom_bar,
            text="Cerrar ",
            image=get_button_icon_ctk("b", self.family, size=18),
            compound="right",
            width=130,
            height=36,
            corner_radius=18,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1.0,
            font=font_button(12),
            text_color=COLOR_TEXT_MUTED,
            command=self.destroy
        )
        self.btn_close.pack(side="right")

        self._nav_controls = [
            ("btn", self.btn_toggle_shell, self._on_toggle_shell_clicked),
            ("btn", self.btn_toggle_autostart, self._on_toggle_autostart_clicked),
            ("btn", self.btn_launch_explorer, self._on_launch_explorer_clicked),
            ("btn", self.btn_close, self.destroy),
        ]

    def _refresh_status(self):
        """Actualiza los textos e indicadores visuales de estado."""
        status = get_kiosk_status()
        is_win = status.get("is_windows", False)
        kiosk_on = status.get("kiosk_active", False)
        autostart_on = status.get("autostart_active", False)

        if not is_win:
            self.lbl_shell_status.configure(
                text="• Sistema: No es Windows (El Modo Kiosco requiere Windows 10/11).",
                text_color=COLOR_STATUS_WARNING
            )
            self.lbl_autostart_status.configure(
                text="• Autostart: No disponible en este sistema operativo.",
                text_color=COLOR_TEXT_MUTED
            )
            self.btn_toggle_shell.configure(state="disabled")
            self.btn_toggle_autostart.configure(state="disabled")
            self.btn_launch_explorer.configure(state="disabled")
            return

        if kiosk_on:
            self.lbl_shell_status.configure(
                text="• Shell de Windows: 🟢 ACTIVO (GameFlow es el shell exclusivo)",
                text_color=COLOR_STATUS_SUCCESS
            )
            self.btn_toggle_shell.configure(
                text="Desactivar Modo Kiosco (Restaurar explorer.exe)",
                fg_color=COLOR_BTN_DANGER_BG,
                hover_color=COLOR_BTN_DANGER_HOVER
            )
        else:
            self.lbl_shell_status.configure(
                text="• Shell de Windows: ⚪ Inactivo (Escritorio habitual explorer.exe)",
                text_color=COLOR_TEXT_BRIGHT
            )
            self.btn_toggle_shell.configure(
                text="Activar Modo Kiosco (Shell de Consola Dedicada)",
                fg_color=COLOR_IOS_BLUE,
                hover_color=COLOR_IOS_BLUE_HOVER
            )

        if autostart_on:
            self.lbl_autostart_status.configure(
                text="• Inicio con Windows: 🟢 HABILITADO (Arranca automáticamente al iniciar)",
                text_color=COLOR_STATUS_SUCCESS
            )
            self.btn_toggle_autostart.configure(
                text="Deshabilitar Inicio Automático con Windows"
            )
        else:
            self.lbl_autostart_status.configure(
                text="• Inicio con Windows: ⚪ Deshabilitado",
                text_color=COLOR_TEXT_MUTED
            )
            self.btn_toggle_autostart.configure(
                text="Habilitar Inicio Automático con Windows"
            )

    def _on_toggle_shell_clicked(self):
        kiosk_on = is_kiosk_shell_active()
        if not kiosk_on:
            # Confirmar activación
            confirm = ask_yes_no(
                "Activar Modo Kiosco",
                "¿Deseas activar el Modo Kiosco de Consola?\n\n"
                "Al iniciar sesión, Windows arrancará GameFlow directamente sin cargar la barra de tareas ni el explorador tradicional.\n\n"
                "• Podrás volver al escritorio en cualquier momento pulsando 'Abrir Escritorio'.\n"
                "• No requiere permisos de administrador.",
                parent=self,
                confirm_text="Activar Modo Kiosco"
            )
            if not confirm:
                return

            ok, msg = enable_kiosk_shell()
            if ok:
                show_info("Modo Kiosco Activado", msg, parent=self)
            else:
                show_error("Error", msg, parent=self)
        else:
            # Desactivar
            confirm = ask_yes_no(
                "Desactivar Modo Kiosco",
                "¿Deseas restaurar el Shell estándar de Windows (explorer.exe)?\n\n"
                "Al encender el equipo volverá a aparecer el escritorio clásico y la barra de tareas de Windows.",
                parent=self,
                confirm_text="Restaurar Escritorio"
            )
            if not confirm:
                return

            ok, msg = disable_kiosk_shell()
            if ok:
                show_info("Modo Kiosco Desactivado", msg, parent=self)
            else:
                show_error("Error", msg, parent=self)

        self._refresh_status()
        if self.on_status_changed:
            self.on_status_changed()

    def _on_toggle_autostart_clicked(self):
        auto_on = is_autostart_active()
        new_state = not auto_on
        ok, msg = set_autostart(new_state)
        if ok:
            show_info("Inicio con Windows", msg, parent=self)
        else:
            show_error("Error", msg, parent=self)
        self._refresh_status()

    def _on_launch_explorer_clicked(self):
        ok, msg = launch_windows_explorer()
        if ok:
            show_info("Escritorio de Windows", msg, parent=self)
        else:
            show_error("Error", msg, parent=self)

    def _update_focus_visuals(self):
        controls = getattr(self, "_nav_controls", [])
        for i, (kind, widget, _) in enumerate(controls):
            if not widget or not widget.winfo_exists():
                continue
            is_foc = (i == self._focused_idx)
            if widget == self.btn_toggle_shell:
                role = "danger" if is_kiosk_shell_active() else "primary"
                apply_gamepad_focus(widget, is_foc, role=role)
            elif widget == self.btn_close:
                apply_gamepad_focus(widget, is_foc, role="secondary")
            else:
                apply_gamepad_focus(widget, is_foc, role="secondary")

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.destroy()
            return True

        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self._on_toggle_autostart_clicked()
            return True

        if inputs.get("y", False) and not prev_inputs.get("y", False):
            self._on_launch_explorer_clicked()
            return True

        controls = getattr(self, "_nav_controls", [])
        if not controls:
            return False

        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._focused_idx = (self._focused_idx - 1) % len(controls)
            self._update_focus_visuals()
            return True
        elif inputs.get("down", False) and not prev_inputs.get("down", False):
            self._focused_idx = (self._focused_idx + 1) % len(controls)
            self._update_focus_visuals()
            return True

        if inputs.get("a", False) and not prev_inputs.get("a", False):
            _, _, action = controls[self._focused_idx]
            if action:
                action()
            return True

        return False
