"""
In-Game Gamepad Overlay para GameFlow Launcher.

Menú flotante semitransparente estilo Liquid Glass / Glassmorphism invocable durante
una partida pulsando el botón Guía/Xbox/Nexus o mediante atajo de teclado:
- Reloj digital en tiempo real con fecha completa.
- Indicador de batería del mando (Xbox / DualSense / USB).
- Control de volumen maestro navegable con cruceta izquierda/derecha y botones superiores LB/RB.
- Botón rápido para volver a GameFlow sin perder la sesión.
- Botón para reanudar partida instantáneamente devolviendo el foco a la ventana del juego.
- Botón para cerrar el juego de forma segura y registrar el tiempo jugado.
"""

import time
import datetime
from typing import Optional, Dict, Any, Callable, List
import customtkinter as ctk

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED, COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_title, font_button, font_body, apply_gamepad_focus
)
from core.audio_service import get_master_volume, set_master_volume, change_master_volume, toggle_mute
from core.active_game_tracker import get_running_game, focus_running_game, terminate_running_game
from gamepad_manager import get_gamepad_battery_info, poll_active_gamepad
from core.feedback import feedback_click


class InGameOverlayDialog(BaseGlassDialog):
    """
    Diálogo Overlay estilo Glassmorphism flotante e interactivo en juego.
    100% navegable con mando de consola (cruceta, sticks, LB/RB, A, B, Y, Guía).
    """

    def __init__(
        self,
        parent=None,
        on_resume_callback: Optional[Callable[[], None]] = None,
        on_return_to_launcher_callback: Optional[Callable[[], None]] = None,
        on_exit_game_callback: Optional[Callable[[], None]] = None,
        on_open_settings_callback: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent, title="🎮 GameFlow Overlay", width=540, height=640, corner_radius=24)
        self.on_resume_cb = on_resume_callback
        self.on_return_to_launcher_cb = on_return_to_launcher_callback
        self.on_exit_game_cb = on_exit_game_callback
        self.on_open_settings_cb = on_open_settings_callback

        self.family = getattr(parent, "_current_controller_family", "xbox") if parent else "xbox"
        self.running_game = get_running_game()

        # Estado interno
        self._action_buttons: List[ctk.CTkButton] = []
        self._selected_action_idx = 0
        self._prev_gamepad_state = {}
        self._last_gamepad_action_time = 0.0
        self._is_active = True

        self.create_widgets()
        self._bind_events()
        self._highlight_selected_action()

        # Iniciar bucles periódicos de reloj, batería y mando
        self._update_clock()
        self._update_battery()
        self._poll_gamepad_loop()

    _center_window = BaseGlassDialog.center_window

    def create_widgets(self):
        scale = getattr(self, "scale_factor", 1.0)
        pad = max(6, int(10 * scale))

        # Tarjeta principal Liquid Glass
        self.card = ctk.CTkFrame(
            self,
            corner_radius=self.corner_radius,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_CYAN_BORDER,
            border_width=1.5
        )
        self.card.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.make_draggable(self.card)

        # 1. Cabecera con estado de juego activo
        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(14, 8))
        self.make_draggable(header)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left")

        lbl_app = ctk.CTkLabel(
            title_box,
            text="GAMEFLOW IN-GAME OVERLAY",
            font=font_body(11),
            text_color=COLOR_CYAN_ACCENT
        )
        lbl_app.pack(anchor="w")

        game_name = self.running_game.get("name") if self.running_game else "Menú de Acceso Rápido"
        lbl_game = ctk.CTkLabel(
            title_box,
            text=f"🎮 {game_name}",
            font=font_title(18),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_game.pack(anchor="w", pady=(1, 0))

        btn_close = ctk.CTkButton(
            header,
            text="✕",
            width=max(28, int(34 * scale)),
            height=max(28, int(34 * scale)),
            corner_radius=max(14, int(17 * scale)),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(13),
            command=self.resume_game
        )
        btn_close.pack(side="right")

        # 2. Panel Superior: Reloj Digital + Batería del Mando (2 columnas)
        dash_row = ctk.CTkFrame(self.card, fg_color="transparent")
        dash_row.pack(fill="x", padx=20, pady=(4, 10))

        # Cuadro Reloj Digital
        clock_card = ctk.CTkFrame(
            dash_row,
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1
        )
        clock_card.pack(side="left", fill="both", expand=True, padx=(0, 6), ipady=4)

        self.lbl_clock_time = ctk.CTkLabel(
            clock_card,
            text="--:--:--",
            font=font_title(24),
            text_color=COLOR_TEXT_BRIGHT
        )
        self.lbl_clock_time.pack(pady=(6, 0))

        self.lbl_clock_date = ctk.CTkLabel(
            clock_card,
            text="Cargando fecha...",
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_clock_date.pack(pady=(0, 6))

        # Cuadro Batería del Mando
        bat_card = ctk.CTkFrame(
            dash_row,
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1
        )
        bat_card.pack(side="right", fill="both", expand=True, padx=(6, 0), ipady=4)

        self.lbl_bat_icon = ctk.CTkLabel(
            bat_card,
            text="🔋 100%",
            font=font_title(20),
            text_color=COLOR_TEXT_BRIGHT
        )
        self.lbl_bat_icon.pack(pady=(6, 0))

        self.lbl_bat_name = ctk.CTkLabel(
            bat_card,
            text="Mando Conectado",
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_bat_name.pack(pady=(0, 6))

        # 3. Panel de Volumen Maestro
        vol_card = ctk.CTkFrame(
            self.card,
            corner_radius=18,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1
        )
        vol_card.pack(fill="x", padx=20, pady=(0, 12), ipady=6)

        vol_header = ctk.CTkFrame(vol_card, fg_color="transparent")
        vol_header.pack(fill="x", padx=14, pady=(6, 4))

        lb_glyph = "LB" if self.family == "xbox" else "L1"
        rb_glyph = "RB" if self.family == "xbox" else "R1"

        self.lbl_vol_title = ctk.CTkLabel(
            vol_header,
            text="🔊 VOLUMEN DEL SISTEMA",
            font=font_body(12),
            text_color=COLOR_TEXT_MUTED_LIGHT
        )
        self.lbl_vol_title.pack(side="left")

        self.lbl_mute_status = ctk.CTkLabel(
            vol_header,
            text="(Y) Silenciar",
            font=font_body(11),
            text_color=COLOR_CYAN_ACCENT
        )
        self.lbl_mute_status.pack(side="right")

        # Barra y controles de volumen
        vol_control_row = ctk.CTkFrame(vol_card, fg_color="transparent")
        vol_control_row.pack(fill="x", padx=14, pady=(2, 6))

        btn_vol_down = ctk.CTkButton(
            vol_control_row,
            text=f"◀ {lb_glyph}",
            width=max(46, int(54 * scale)),
            height=28,
            corner_radius=14,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(11),
            command=self.volume_down
        )
        btn_vol_down.pack(side="left", padx=(0, 8))

        self.vol_progress = ctk.CTkProgressBar(
            vol_control_row,
            height=14,
            corner_radius=7,
            progress_color=COLOR_IOS_BLUE,
            fg_color="#0F172A"
        )
        self.vol_progress.pack(side="left", fill="x", expand=True, padx=4)

        btn_vol_up = ctk.CTkButton(
            vol_control_row,
            text=f"{rb_glyph} ▶",
            width=max(46, int(54 * scale)),
            height=28,
            corner_radius=14,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(11),
            command=self.volume_up
        )
        btn_vol_up.pack(side="left", padx=(8, 8))

        self.lbl_vol_pct = ctk.CTkLabel(
            vol_control_row,
            text="70%",
            width=42,
            font=font_button(13),
            text_color=COLOR_TEXT_BRIGHT
        )
        self.lbl_vol_pct.pack(side="right")

        self._refresh_volume_display()

        # 3.5 Panel de Perfil de Rendimiento (Handheld / Power Mode)
        power_card = ctk.CTkFrame(
            self.card,
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1
        )
        power_card.pack(fill="x", padx=20, pady=(0, 10), ipady=4)

        power_header = ctk.CTkFrame(power_card, fg_color="transparent")
        power_header.pack(fill="x", padx=14, pady=(4, 2))

        lbl_power_title = ctk.CTkLabel(
            power_header,
            text="🎛️  PERFIL DE RENDIMIENTO (HANDHELD)",
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED_LIGHT
        )
        lbl_power_title.pack(side="left")

        x_glyph = "X" if self.family == "xbox" else "□"
        self.lbl_power_hint = ctk.CTkLabel(
            power_header,
            text=f"({x_glyph}) Cambiar Perfil",
            font=font_body(10),
            text_color=COLOR_CYAN_ACCENT
        )
        self.lbl_power_hint.pack(side="right")

        modes_row = ctk.CTkFrame(power_card, fg_color="transparent")
        modes_row.pack(fill="x", padx=12, pady=(2, 6))

        from core.power_service import get_current_power_mode, POWER_PROFILES
        self.current_overlay_power_mode = get_current_power_mode()
        self._power_mode_buttons = {}

        for m_key in ("eco", "balanced", "turbo"):
            m_prof = POWER_PROFILES[m_key]
            is_active = (self.current_overlay_power_mode == m_key)
            b = ctk.CTkButton(
                modes_row,
                text=f"{m_prof['icon']} {m_prof['short_name']}",
                font=font_button(11),
                height=26,
                corner_radius=8,
                fg_color=m_prof["color"] if is_active else COLOR_BTN_SECONDARY_BG,
                hover_color=m_prof["color"] if is_active else COLOR_BTN_SECONDARY_HOVER,
                text_color=COLOR_TEXT_WHITE if (is_active and m_prof["color"] != "#00d2ff") else (COLOR_BG_DARK if is_active else COLOR_TEXT_MUTED_LIGHT),
                border_color=m_prof["color"] if is_active else COLOR_BTN_SECONDARY_BORDER,
                border_width=1,
                command=lambda k=m_key: self.set_overlay_power_mode(k)
            )
            b.pack(side="left", padx=3, expand=True, fill="x")
            self._power_mode_buttons[m_key] = b

        # 4. Botones de Acción (Reanudar, Volver a GameFlow, Cerrar Juego, Ajustes)
        actions_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        actions_frame.pack(fill="both", expand=True, padx=20, pady=(0, 6))

        # Botón 1: Reanudar Partida
        b_glyph = "B" if self.family == "xbox" else "◯"
        btn_resume = ctk.CTkButton(
            actions_frame,
            text=f"▶  Reanudar Partida  ({b_glyph} / Guía)",
            height=max(42, int(48 * scale)),
            corner_radius=16,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER,
            border_width=1.5,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(14),
            command=self.resume_game
        )
        btn_resume.pack(fill="x", pady=4)
        self._action_buttons.append(btn_resume)

        # Botón 2: Volver a GameFlow
        btn_launcher = ctk.CTkButton(
            actions_frame,
            text="🏠  Volver a GameFlow Launcher",
            height=max(42, int(48 * scale)),
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            hover_color=COLOR_GLASS_HOVER,
            border_color=COLOR_BORDER_CARD,
            border_width=1.5,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(13),
            command=self.return_to_launcher
        )
        btn_launcher.pack(fill="x", pady=4)
        self._action_buttons.append(btn_launcher)

        # Botón 3: Cerrar Juego Activo
        btn_kill = ctk.CTkButton(
            actions_frame,
            text="🛑  Finalizar / Cerrar Juego",
            height=max(40, int(46 * scale)),
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            hover_color="#7F1D1D",
            border_color=COLOR_BORDER_CARD,
            border_width=1.5,
            text_color="#FCA5A5",
            font=font_button(13),
            command=self.terminate_game
        )
        btn_kill.pack(fill="x", pady=4)
        self._action_buttons.append(btn_kill)

        # 5. Pie de guía de botones
        a_glyph = "A" if self.family == "xbox" else "✕"
        x_glyph = "X" if self.family == "xbox" else "□"
        y_glyph = "Y" if self.family == "xbox" else "△"
        guide_bar = ctk.CTkFrame(self.card, fg_color="transparent")
        guide_bar.pack(fill="x", padx=16, pady=(6, 10))

        guide_text = f"[{a_glyph}] Seleccionar    [{b_glyph}/Guía] Reanudar    [{x_glyph}] Rendimiento    [◀/▶] Vol    [{y_glyph}] Mute"
        lbl_guide = ctk.CTkLabel(
            guide_bar,
            text=guide_text,
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_guide.pack(anchor="center")

    def _bind_events(self):
        self.bind("<Escape>", lambda e: self.resume_game())
        self.bind("<Up>", lambda e: self._navigate_actions(-1))
        self.bind("<Down>", lambda e: self._navigate_actions(1))
        self.bind("<Left>", lambda e: self.volume_down())
        self.bind("<Right>", lambda e: self.volume_up())
        self.bind("<bracketleft>", lambda e: self.volume_down())
        self.bind("<bracketright>", lambda e: self.volume_up())
        self.bind("<x>", lambda e: self.cycle_overlay_power_mode())
        self.bind("<X>", lambda e: self.cycle_overlay_power_mode())
        self.bind("<p>", lambda e: self.cycle_overlay_power_mode())
        self.bind("<P>", lambda e: self.cycle_overlay_power_mode())
        self.bind("<y>", lambda e: self.toggle_volume_mute())
        self.bind("<Y>", lambda e: self.toggle_volume_mute())
        self.bind("<m>", lambda e: self.toggle_volume_mute())
        self.bind("<M>", lambda e: self.toggle_volume_mute())
        self.bind("<Return>", lambda e: self._activate_selected_action())
        self.bind("<space>", lambda e: self._activate_selected_action())

    # ---------------------------------------------------------------------------
    # Lógica de Actualización Periódica (Reloj, Batería, Volumen)
    # ---------------------------------------------------------------------------

    def _update_clock(self):
        if not self._is_active or not self.winfo_exists():
            return
        now = datetime.datetime.now()
        self.lbl_clock_time.configure(text=now.strftime("%H:%M:%S"))

        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
        dia_nom = dias[now.weekday()]
        mes_nom = meses[now.month - 1]
        self.lbl_clock_date.configure(text=f"{dia_nom}, {now.day} de {mes_nom}.")
        self.after(1000, self._update_clock)

    def _update_battery(self):
        if not self._is_active or not self.winfo_exists():
            return
        try:
            from core.power_service import get_system_battery_status, get_device_model_info
            sys_bat = get_system_battery_status()
            bat = get_gamepad_battery_info()

            if sys_bat.get("has_battery"):
                pct = sys_bat.get("percent", 100)
                icon = "⚡" if sys_bat.get("charging") else sys_bat.get("icon", "🔋")
                dev_badge = get_device_model_info().get("badge", "Consola")
                txt = f"{icon} {pct}%"
                if bat.get("connected"):
                    sub = f"{dev_badge} • Mando {bat.get('percent', 100)}%"
                else:
                    sub = f"{dev_badge} ({sys_bat.get('status_label', '')})"
            elif bat.get("is_wired"):
                txt = "🔌 Cable USB"
                sub = "Cargando / Alimentado"
            elif bat.get("connected"):
                pct = bat.get("percent", 100)
                icon = bat.get("icon", "🔋")
                txt = f"{icon} {pct}%"
                dev = bat.get("device_name", "Mando Inalámbrico")
                sub = f"{dev}"
            else:
                txt = "🎮 Desconectado"
                sub = "Buscando mando..."

            self.lbl_bat_icon.configure(text=txt)
            self.lbl_bat_name.configure(text=sub)
        except Exception:
            pass
        self.after(2000, self._update_battery)

    def set_overlay_power_mode(self, mode: str):
        """Cambia el perfil de energía del sistema desde el overlay en caliente."""
        from core.power_service import set_power_mode, POWER_PROFILES
        feedback_click()
        if mode in POWER_PROFILES:
            set_power_mode(mode)
            self.current_overlay_power_mode = mode
            self._refresh_power_mode_ui()

    def cycle_overlay_power_mode(self):
        """Cicla el perfil de energía entre Eco -> Equilibrado -> Turbo."""
        modes = ["eco", "balanced", "turbo"]
        curr = getattr(self, "current_overlay_power_mode", "balanced") or "balanced"
        try:
            idx = modes.index(curr)
        except ValueError:
            idx = 1
        next_mode = modes[(idx + 1) % len(modes)]
        self.set_overlay_power_mode(next_mode)

    def _refresh_power_mode_ui(self):
        """Actualiza los estilos visuales de los botones de perfil en el overlay."""
        from core.power_service import POWER_PROFILES
        buttons = getattr(self, "_power_mode_buttons", {})
        curr = getattr(self, "current_overlay_power_mode", "balanced")
        for m_key, btn in buttons.items():
            m_prof = POWER_PROFILES.get(m_key, {})
            is_active = (curr == m_key)
            color = m_prof.get("color", COLOR_IOS_BLUE)
            btn.configure(
                fg_color=color if is_active else COLOR_BTN_SECONDARY_BG,
                hover_color=color if is_active else COLOR_BTN_SECONDARY_HOVER,
                text_color=COLOR_TEXT_WHITE if (is_active and color != "#00d2ff") else (COLOR_BG_DARK if is_active else COLOR_TEXT_MUTED_LIGHT),
                border_color=color if is_active else COLOR_BTN_SECONDARY_BORDER
            )

    def _refresh_volume_display(self):
        try:
            vol, is_muted = get_master_volume()
            self.vol_progress.set(max(0.0, min(1.0, vol / 100.0)))
            if is_muted:
                self.lbl_vol_pct.configure(text="MUTE", text_color="#F87171")
                self.lbl_mute_status.configure(text="(Y) Reactivar Sonido", text_color="#F87171")
                self.vol_progress.configure(progress_color="#64748B")
            else:
                self.lbl_vol_pct.configure(text=f"{vol}%", text_color=COLOR_TEXT_BRIGHT)
                self.lbl_mute_status.configure(text="(Y) Silenciar", text_color=COLOR_CYAN_ACCENT)
                self.vol_progress.configure(progress_color=COLOR_IOS_BLUE)
        except Exception:
            pass

    def volume_up(self):
        feedback_click()
        change_master_volume(5)
        self._refresh_volume_display()

    def volume_down(self):
        feedback_click()
        change_master_volume(-5)
        self._refresh_volume_display()

    def toggle_volume_mute(self):
        feedback_click()
        toggle_mute()
        self._refresh_volume_display()

    # ---------------------------------------------------------------------------
    # Navegación y Acciones
    # ---------------------------------------------------------------------------

    def _navigate_actions(self, direction: int):
        feedback_click()
        n = len(self._action_buttons)
        if n == 0:
            return
        self._selected_action_idx = (self._selected_action_idx + direction) % n
        self._highlight_selected_action()

    def _highlight_selected_action(self):
        for i, btn in enumerate(self._action_buttons):
            if i == self._selected_action_idx:
                apply_gamepad_focus(btn, is_focused=True, default_border=COLOR_BORDER_CARD)
                btn.configure(border_color=COLOR_CYAN_ACCENT, border_width=2)
            else:
                apply_gamepad_focus(btn, is_focused=False, default_border=COLOR_BORDER_CARD)
                btn.configure(border_color=COLOR_BORDER_CARD, border_width=1.5)

    def _activate_selected_action(self):
        if 0 <= self._selected_action_idx < len(self._action_buttons):
            btn = self._action_buttons[self._selected_action_idx]
            btn.invoke()

    def resume_game(self):
        """Cierra el overlay y restaura el foco a la ventana del juego activo."""
        self._is_active = False
        feedback_click()
        try:
            focus_running_game(self.running_game)
        except Exception:
            pass
        if self.on_resume_cb:
            try:
                self.on_resume_cb()
            except Exception:
                pass
        self.destroy()

    def return_to_launcher(self):
        """Minimiza/deja en segundo plano el juego y trae GameFlow Launcher al frente."""
        self._is_active = False
        feedback_click()
        if self.on_return_to_launcher_cb:
            try:
                self.on_return_to_launcher_cb()
            except Exception:
                pass
        else:
            # Traer al frente la ventana padre si existe
            if self.parent and hasattr(self.parent, "restore_window"):
                self.parent.restore_window()
        self.destroy()

    def terminate_game(self):
        """Cierra el juego en ejecución y vuelve a GameFlow."""
        self._is_active = False
        feedback_click()
        try:
            terminate_running_game(self.running_game)
        except Exception:
            pass
        try:
            from core.power_service import restore_previous_performance_profile
            restore_previous_performance_profile()
        except Exception:
            pass
        if self.on_exit_game_cb:
            try:
                self.on_exit_game_cb()
            except Exception:
                pass
        elif self.parent and hasattr(self.parent, "restore_window"):
            self.parent.restore_window()
        self.destroy()

    # ---------------------------------------------------------------------------
    # Bucle Polling de Mando para el Overlay
    # ---------------------------------------------------------------------------

    def _poll_gamepad_loop(self):
        if not self._is_active or not self.winfo_exists():
            return

        now = time.time()
        is_conn, _, inputs = poll_active_gamepad("any")
        prev = self._prev_gamepad_state

        if is_conn:
            self.handle_gamepad_input(inputs, prev)

        self._prev_gamepad_state = inputs
        self.after(16, self._poll_gamepad_loop)

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev: Optional[Dict[str, Any]] = None) -> None:
        """Procesa una pulsación de mando de forma determinista (usado por el bucle y tests)."""
        prev = prev or {}

        # Botón B o Guía: Reanudar partida y cerrar overlay
        if (inputs.get("b", False) and not prev.get("b", False)) or (inputs.get("guide", False) and not prev.get("guide", False)):
            self.resume_game()
            return

        # Botón X: Ciclar perfil de rendimiento en caliente (Eco -> Equilibrado -> Turbo)
        if inputs.get("x", False) and not prev.get("x", False):
            self.cycle_overlay_power_mode()
            return

        # Botón Y: Alternar silencio
        if inputs.get("y", False) and not prev.get("y", False):
            self.toggle_volume_mute()
            return

        # Cruceta Arriba / Abajo: Navegación de opciones
        if inputs.get("up", False) and not prev.get("up", False):
            self._navigate_actions(-1)
        elif inputs.get("down", False) and not prev.get("down", False):
            self._navigate_actions(1)

        # Cruceta Izquierda / Derecha o LB / RB: Control de volumen
        if (inputs.get("left", False) and not prev.get("left", False)) or (inputs.get("lb", False) and not prev.get("lb", False)):
            self.volume_down()
        elif (inputs.get("right", False) and not prev.get("right", False)) or (inputs.get("rb", False) and not prev.get("rb", False)):
            self.volume_up()

        # Botón A: Activar opción seleccionada
        if inputs.get("a", False) and not prev.get("a", False):
            self._activate_selected_action()
