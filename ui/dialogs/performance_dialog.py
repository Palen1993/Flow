"""
GameFlow - Diálogo de Perfiles de Rendimiento y Modos de Energía (Handheld Mode)
================================================================================
Diálogo modal Glassmorphism 100% navegable con mando diseñado para consolas portátiles
(ROG Ally, Steam Deck con Windows, Lenovo Legion Go, AYANEO, GPD Win) y portátiles gaming.

Permite:
- Visualizar telemetría de batería del sistema y modelo detectado.
- Cambiar en caliente el plan de energía activo de Windows:
  * 🌱 Modo Batería (Eco): ~9-15W, ahorro máximo.
  * ⚖️ Modo Equilibrado: ~15-20W, balance óptimo.
  * ⚡ Modo Turbo: ~25-30W+, máximo rendimiento para AAA.
- Configurar perfil preferido automático para el juego seleccionado.
"""

import os
import tkinter as tk
from typing import Dict, Any, Optional, Callable, List
import customtkinter as ctk

from ui.dialogs.base_dialog import BaseGlassDialog
from core.power_service import (
    POWER_PROFILES,
    get_system_battery_status,
    get_device_model_info,
    get_current_power_mode,
    set_power_mode
)
from core.config import save_games_data, update_game_fields_atomic
from core.feedback import feedback_click, trigger_haptic
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_DANGER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, font_title
)


class PerformanceProfileDialog(BaseGlassDialog):
    """
    Diálogo modal Glassmorphism para seleccionar perfiles de energía (Eco, Equilibrado, Turbo)
    y asignar el modo preferido al juego actual.
    """
    _mode_keys = ["eco", "balanced", "turbo"]

    def __init__(
        self,
        parent,
        game: Optional[Dict[str, Any]] = None,
        on_game_updated: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        super().__init__(
            parent,
            title="Perfiles de Rendimiento y Modos de Energía",
            width=840,
            height=600,
            corner_radius=22
        )
        self.game = game or {}
        self.on_game_updated = on_game_updated

        self.device_info = get_device_model_info()
        self.battery_info = get_system_battery_status()
        self.active_mode = get_current_power_mode()
        self.game_mode = self.game.get("performance_mode", "default")

        self.selected_profile_idx: int = ["eco", "balanced", "turbo"].index(self.active_mode) if self.active_mode in ("eco", "balanced", "turbo") else 1
        self._profile_cards: List[ctk.CTkFrame] = []
        self._mode_keys = ["eco", "balanced", "turbo"]

        self._build_ui()

    _center_window = BaseGlassDialog.center_window

    def _build_ui(self):
        # Tarjeta principal con efecto iOS Liquid Glass
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)

        # ---------------- Cabecera ----------------
        self.header_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=50)
        self.header_bar.pack(fill="x", padx=20, pady=(12, 6))

        lbl_icon = ctk.CTkLabel(self.header_bar, text="🎛️", font=font_title(22))
        lbl_icon.pack(side="left", padx=(0, 10))

        info_col = ctk.CTkFrame(self.header_bar, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True)

        lbl_title = ctk.CTkLabel(
            info_col,
            text="Perfiles de Rendimiento y Modos de Energía",
            font=font_title(17),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        lbl_title.pack(anchor="w")

        device_tag = self.device_info["display_name"]
        bat_tag = self.battery_info["status_label"]
        lbl_sub = ctk.CTkLabel(
            info_col,
            text=f"🎮 {device_tag}   •   {bat_tag}",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM,
            anchor="w"
        )
        lbl_sub.pack(anchor="w")

        btn_close = ctk.CTkButton(
            self.header_bar,
            text="✕  Cerrar (B)",
            width=90,
            height=28,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=10,
            command=self.close
        )
        btn_close.pack(side="right")

        for w in (self.header_bar, lbl_title, info_col, lbl_sub):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # ---------------- 3 Tarjetas de Perfil de Rendimiento ----------------
        self.cards_row = ctk.CTkFrame(self.main_card, fg_color="transparent")
        self.cards_row.pack(fill="x", padx=16, pady=(6, 12))
        self.cards_row.grid_columnconfigure((0, 1, 2), weight=1)

        for i, key in enumerate(self._mode_keys):
            prof = POWER_PROFILES[key]
            card = self._create_profile_card(self.cards_row, prof, i)
            card.grid(row=0, column=i, padx=6, sticky="nsew")
            self._profile_cards.append(card)

        # ---------------- Panel de Asignación por Juego ----------------
        self.game_panel = ctk.CTkFrame(
            self.main_card,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1,
            corner_radius=14
        )
        self.game_panel.pack(fill="x", padx=20, pady=(0, 10))

        game_header = ctk.CTkFrame(self.game_panel, fg_color="transparent")
        game_header.pack(fill="x", padx=16, pady=(10, 4))

        g_name = self.game.get("name") or "Juego Seleccionado"
        lbl_game_title = ctk.CTkLabel(
            game_header,
            text=f"🎯  Perfil Automático para '{g_name}':",
            font=font_button(12),
            text_color=COLOR_CYAN_ACCENT,
            anchor="w"
        )
        lbl_game_title.pack(side="left")

        lbl_game_hint = ctk.CTkLabel(
            game_header,
            text="(Se aplicará automáticamente al iniciar y se restaurará al salir)",
            font=font_body(10),
            text_color=COLOR_TEXT_DIM
        )
        lbl_game_hint.pack(side="right")

        # Fila de botones para elegir perfil de juego
        game_btn_row = ctk.CTkFrame(self.game_panel, fg_color="transparent")
        game_btn_row.pack(fill="x", padx=16, pady=(2, 10))

        self.game_mode_buttons = {}
        game_options = [
            ("default", "Predeterminado (Global)"),
            ("eco", "🌱 Eco"),
            ("balanced", "⚖️ Equilibrado"),
            ("turbo", "⚡ Turbo")
        ]

        for opt_key, opt_label in game_options:
            is_sel = (self.game_mode == opt_key)
            b = ctk.CTkButton(
                game_btn_row,
                text=opt_label,
                font=font_button(11),
                height=30,
                corner_radius=8,
                fg_color=COLOR_CYAN_BORDER if is_sel else COLOR_BTN_SECONDARY_BG,
                hover_color=COLOR_CYAN_ACCENT if is_sel else COLOR_BTN_SECONDARY_HOVER,
                text_color=COLOR_CYAN_ACCENT if is_sel else COLOR_TEXT_MUTED_LIGHT,
                border_color=COLOR_CYAN_BORDER if is_sel else COLOR_BTN_SECONDARY_BORDER,
                border_width=1,
                command=lambda k=opt_key: self._set_game_profile(k)
            )
            b.pack(side="left", padx=4, expand=True, fill="x")
            self.game_mode_buttons[opt_key] = b

        # ---------------- Telemetría y Consejos de Handheld ----------------
        telemetry_card = ctk.CTkFrame(
            self.main_card,
            fg_color=COLOR_BG_DARK,
            border_color=COLOR_BORDER_CARD,
            border_width=1,
            corner_radius=12
        )
        telemetry_card.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        telemetry_inner = ctk.CTkFrame(telemetry_card, fg_color="transparent")
        telemetry_inner.pack(fill="both", expand=True, padx=14, pady=10)

        lbl_tips_title = ctk.CTkLabel(
            telemetry_inner,
            text="💡  Guía de Rendimiento para Consolas Portátiles:",
            font=font_button(11),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        lbl_tips_title.pack(anchor="w")

        tips_text = (
            "• Modo Batería (Eco): Reduce consumo a ~9-15W, bajando temperatura y duplicando batería en indies y emuladores.\n"
            "• Modo Equilibrado: Ideal para uso general a 60 FPS con ventiladores en perfil silencioso (~15-20W).\n"
            "• Modo Turbo: Desbloquea el TDP completo del procesador (~25-30W+) para exprimir el máximo rendimiento en juegos AAA.\n"
            "• Consejo: Puedes alternar perfiles en caliente en cualquier momento desde el In-Game Overlay (botón Guía)."
        )
        lbl_tips = ctk.CTkLabel(
            telemetry_inner,
            text=tips_text,
            font=font_body(10),
            text_color=COLOR_TEXT_DIM,
            justify="left",
            anchor="w"
        )
        lbl_tips.pack(anchor="w", pady=(4, 0))

        # ---------------- Pie con Atajos de Mando ----------------
        self.footer_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=28)
        self.footer_bar.pack(fill="x", padx=20, pady=(0, 8))

        self.lbl_shortcuts = ctk.CTkLabel(
            self.footer_bar,
            text="Cruceta (← / →): Elegir Perfil  │  (A): Activar Perfil del Sistema  │  (X): Cambiar Perfil del Juego  │  (B): Cerrar",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_shortcuts.pack(side="left")

        self._highlight_selected_profile()

    def _create_profile_card(self, parent: ctk.CTkFrame, prof: Dict[str, Any], idx: int) -> ctk.CTkFrame:
        """Crea una tarjeta estilizada para uno de los 3 perfiles."""
        mode_key = prof["id"]
        is_active = (self.active_mode == mode_key)
        is_focused = (idx == self.selected_profile_idx)

        b_color = prof["color"] if (is_active or is_focused) else COLOR_BORDER_CARD
        b_width = 2.0 if is_active else (1.5 if is_focused else 1.0)

        card = ctk.CTkFrame(
            parent,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=b_color,
            border_width=b_width,
            corner_radius=14,
            height=200
        )

        # Cabecera de la tarjeta
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 4))

        lbl_icon = ctk.CTkLabel(header, text=prof["icon"], font=font_title(20))
        lbl_icon.pack(side="left")

        lbl_tdp = ctk.CTkLabel(
            header,
            text=prof["tdp_target"],
            font=font_body(9),
            text_color=prof["color"],
            fg_color=COLOR_BG_DARK,
            corner_radius=6,
            width=65,
            height=20
        )
        lbl_tdp.pack(side="right")

        # Nombre del perfil
        lbl_name = ctk.CTkLabel(
            card,
            text=prof["name"],
            font=font_button(13),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        lbl_name.pack(anchor="w", padx=12, pady=(2, 4))

        # Descripción
        lbl_desc = ctk.CTkLabel(
            card,
            text=prof["description"],
            font=font_body(10),
            text_color=COLOR_TEXT_MUTED,
            wraplength=210,
            justify="left",
            anchor="nw"
        )
        lbl_desc.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Botón o Badge de estado
        if is_active:
            btn_act = ctk.CTkLabel(
                card,
                text="✓  PERFIL ACTIVO",
                font=font_button(11),
                fg_color=prof["color"],
                text_color=COLOR_TEXT_WHITE if prof["color"] != "#00d2ff" else "#0f172a",
                corner_radius=8,
                height=28
            )
            btn_act.pack(fill="x", padx=12, pady=(0, 10))
        else:
            btn_act = ctk.CTkButton(
                card,
                text="Activar Ahora",
                font=font_button(11),
                height=28,
                corner_radius=8,
                fg_color=COLOR_BTN_SECONDARY_BG,
                hover_color=COLOR_BTN_SECONDARY_HOVER,
                border_color=COLOR_BTN_SECONDARY_BORDER,
                border_width=1,
                command=lambda k=mode_key: self._activate_profile(k)
            )
            btn_act.pack(fill="x", padx=12, pady=(0, 10))

        # Interactividad por clic de ratón
        for w in (card, header, lbl_icon, lbl_tdp, lbl_name, lbl_desc):
            w.bind("<Button-1>", lambda e, k=mode_key, i=idx: self._on_card_click(k, i))

        return card

    def _on_card_click(self, mode_key: str, idx: int):
        self.selected_profile_idx = idx
        self._highlight_selected_profile()
        self._activate_profile(mode_key)

    def _highlight_selected_profile(self):
        """Actualiza los bordes visuales según el modo activo y el cursor del mando."""
        for i, card in enumerate(self._profile_cards):
            mode_key = self._mode_keys[i]
            prof = POWER_PROFILES[mode_key]
            is_active = (self.active_mode == mode_key)
            is_sel = (i == self.selected_profile_idx)

            if is_active:
                card.configure(border_color=prof["color"], border_width=2.0)
            elif is_sel:
                card.configure(border_color=COLOR_CYAN_ACCENT, border_width=1.8)
            else:
                card.configure(border_color=COLOR_BORDER_CARD, border_width=1.0)

    def _activate_profile(self, mode_key: str):
        """Aplica el perfil de energía inmediatamente en el sistema operativo."""
        if mode_key == self.active_mode:
            return

        ok = set_power_mode(mode_key)
        if ok:
            try:
                feedback_click()
                trigger_haptic(0.2, 0.2, 60)
            except Exception:
                pass
            self.active_mode = mode_key
            self._rebuild_cards()

    def _rebuild_cards(self):
        for card in self._profile_cards:
            card.destroy()
        self._profile_cards.clear()

        for i, key in enumerate(self._mode_keys):
            prof = POWER_PROFILES[key]
            card = self._create_profile_card(self.cards_row, prof, i)
            card.grid(row=0, column=i, padx=6, sticky="nsew")
            self._profile_cards.append(card)

        self._highlight_selected_profile()

    def _set_game_profile(self, opt_key: str):
        """Asigna el modo preferido al juego seleccionado y lo persiste en games.json."""
        self.game_mode = opt_key
        self.game["performance_mode"] = opt_key

        # Actualizar aspecto de botones
        for k, b in self.game_mode_buttons.items():
            is_sel = (k == opt_key)
            b.configure(
                fg_color=COLOR_CYAN_BORDER if is_sel else COLOR_BTN_SECONDARY_BG,
                hover_color=COLOR_CYAN_ACCENT if is_sel else COLOR_BTN_SECONDARY_HOVER,
                text_color=COLOR_CYAN_ACCENT if is_sel else COLOR_TEXT_MUTED_LIGHT,
                border_color=COLOR_CYAN_BORDER if is_sel else COLOR_BTN_SECONDARY_BORDER
            )

        # Persistir
        parent = self.parent
        if parent and hasattr(parent, "save_games"):
            try:
                parent.save_games()
            except Exception:
                pass
        else:
            try:
                update_game_fields_atomic(
                    self.game.get("path") or self.game.get("name", ""),
                    {"performance_mode": opt_key}
                )
            except Exception:
                pass

        if self.on_game_updated:
            try:
                self.on_game_updated(self.game)
            except Exception:
                pass

        try:
            feedback_click()
        except Exception:
            pass

    # =========================================================================
    # MANEJADOR DE MANDO DE CONSOLA (GAMEPAD DISPATCHER)
    # =========================================================================
    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        """
        Navegación 100% por mando:
        - Cruceta Izquierda / Derecha: Navegar entre tarjetas Eco / Equilibrado / Turbo
        - Botón A: Activar el perfil seleccionado en el sistema
        - Botón X: Ciclar el perfil asignado al juego actual (Default -> Eco -> Balanced -> Turbo)
        - Botón B / Back: Cerrar diálogo
        """
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.close()
            return True

        # Cruceta izquierda / derecha
        if inputs.get("left", False) and not prev_inputs.get("left", False):
            if self.selected_profile_idx > 0:
                self.selected_profile_idx -= 1
                self._highlight_selected_profile()
            return True

        if inputs.get("right", False) and not prev_inputs.get("right", False):
            if self.selected_profile_idx < len(self._mode_keys) - 1:
                self.selected_profile_idx += 1
                self._highlight_selected_profile()
            return True

        # Botón A: Activar perfil seleccionado
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            target_mode = self._mode_keys[self.selected_profile_idx]
            self._activate_profile(target_mode)
            return True

        # Botón X: Ciclar perfil de juego
        if inputs.get("x", False) and not prev_inputs.get("x", False):
            all_opts = ["default", "eco", "balanced", "turbo"]
            curr_idx = all_opts.index(self.game_mode) if self.game_mode in all_opts else 0
            next_opt = all_opts[(curr_idx + 1) % len(all_opts)]
            self._set_game_profile(next_opt)
            return True

        return False
