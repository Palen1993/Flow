from typing import Optional
import customtkinter as ctk

from gamepad_manager import (
    load_gamepad_config, save_gamepad_config, get_paired_gamepads,
    poll_active_gamepad, is_windows_startup_enabled, set_windows_startup
)
from ui.dropdowns import GlassDropdownButton
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack
from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_DANGER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget, apply_rounded_window_region, hide_from_taskbar, bring_to_front_absolute
)

class GamepadConfigDialog(ctk.CTkToplevel):
    def _windows_set_titlebar_color(self, color_mode: str):
        pass

    def _windows_set_titlebar_icon(self):
        pass
    """Diálogo modal para emparejamiento, calibración y automatización del mando."""
    def __init__(self, parent, on_save_callback=None):
        super().__init__(parent)
        self.on_save_callback = on_save_callback
        self.cfg = load_gamepad_config()
        self.paired_devices = get_paired_gamepads()
        
        self.dialog_width = 650
        self.dialog_height = 600
        self.title("🎮 Configurar Mando")
        self.geometry(f"{self.dialog_width}x{self.dialog_height}")
        self.resizable(False, False)
        
        try:
            self.overrideredirect(True)
        except Exception:
            pass
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
            
        self.configure(fg_color=COLOR_BG_CARD)
        self.transient(parent)
        hide_from_taskbar(self)
        bring_to_front_absolute(self)
        self.family = getattr(parent, "_current_controller_family", "xbox")
        
        self.is_monitoring = True
        self.drag_x = 0
        self.drag_y = 0
        
        self.create_widgets()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Up>", lambda e: self._step_focus(-1))
        self.bind("<Down>", lambda e: self._step_focus(1))
        self.bind("<Return>", lambda e: self._activate_focused())
        self.bind("<space>", lambda e: self._activate_focused())
        
        self._center_window()
        self.after(20, self._center_window)
        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))
        register_modal_stack(self)
        self.after(100, self._poll_status)
        try:
            self.grab_set()
        except Exception:
            pass

    def _center_window(self):
        try:
            self.update_idletasks()
            pw = self.master.winfo_width()
            ph = self.master.winfo_height()
            px = self.master.winfo_rootx()
            py = self.master.winfo_rooty()
            w = self.dialog_width
            h = self.dialog_height
            x = max(10, px + max(0, (pw - w) // 2))
            y = max(10, py + max(0, (ph - h) // 2))
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _start_drag(self, event):
        if hasattr(self, "device_combo") and getattr(self.device_combo, "_active_dropdown", None):
            try:
                self.device_combo._active_dropdown.destroy()
                self.device_combo._active_dropdown = None
            except Exception:
                pass
        self.drag_x = event.x_root - self.winfo_x()
        self.drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.geometry(f"+{x}+{y}")

    def destroy(self):
        unregister_modal_stack(self)
        if hasattr(self, "device_combo") and getattr(self.device_combo, "_active_dropdown", None):
            try:
                self.device_combo._active_dropdown.destroy()
                self.device_combo._active_dropdown = None
            except Exception:
                pass
        self.is_monitoring = False
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    def create_widgets(self):
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)
        self.main_card.grid_columnconfigure(0, weight=1)
        self.main_card.grid_rowconfigure(1, weight=1)
        
        # 1. Cabecera superior arrastrable
        header_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        header_frame.grid_columnconfigure(0, weight=1)
        
        top_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=4, pady=(0, 2))
        
        lbl_title = ctk.CTkLabel(
            top_row, text="🎮  Configurar Mando",
            font=font_button(18), 
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")
        
        for w in (header_frame, top_row, lbl_title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
        
        lbl_sub = ctk.CTkLabel(
            header_frame, text="Sincroniza tu mando para que cuando se encienda se lance la app y puedas controlarla desde el sofá:",
            font=font_body(12), text_color=COLOR_TEXT_DIM, anchor="w"
        )
        lbl_sub.pack(fill="x", padx=4, pady=(0, 6))
        
        # 2. Contenido Scrolleable
        scroll = ctk.CTkScrollableFrame(self.main_card, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(2, 6))
        scroll.grid_columnconfigure(0, weight=1)
        self.scroll = scroll
        
        # Tarjeta 1: Selección de Mando
        card_dev = ctk.CTkFrame(scroll, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=16, border_color=COLOR_BORDER_CARD, border_width=1.0)
        card_dev.pack(fill="x", pady=6)
        self.card_dev = card_dev
        
        ctk.CTkLabel(
            card_dev, text="Mando asignado para encendido y control:",
            font=font_button(14),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(12, 6))
        
        device_labels = [d["name"] for d in self.paired_devices]
        current_id = self.cfg.get("selected_controller_id", "any")
        
        default_label = device_labels[0]
        for d in self.paired_devices:
            if d["id"] == current_id:
                default_label = d["name"]
                break
                
        self.device_combo = GlassDropdownButton(
            card_dev,
            values=device_labels,
            height=36,
            corner_radius=18,
            fg_color="#222838",
            hover_color="#2d354a",
            border_color="#343f55",
            border_width=1.0,
            text_color=COLOR_TEXT_BRIGHT,
            font=font_button(13),
            item_icon="🎮  "
        )
        self.device_combo.set(default_label)
        self.device_combo.pack(fill="x", padx=16, pady=(0, 10))
        
        self.lbl_live_status = ctk.CTkLabel(
            card_dev, text="⚪ Verificando estado del mando...",
            font=font_button(12),
            text_color=COLOR_TEXT_MUTED, anchor="w"
        )
        self.lbl_live_status.pack(fill="x", padx=16, pady=(0, 12))
        
        # Tarjeta 2: Automatización
        card_switches = ctk.CTkFrame(scroll, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=16, border_color=COLOR_BORDER_CARD, border_width=1.0)
        card_switches.pack(fill="x", pady=6)
        
        ctk.CTkLabel(
            card_switches, text="Opciones de Automatización:",
            font=font_button(14),
            text_color=COLOR_TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(12, 8))
        
        self.sw_auto_launch = ctk.CTkSwitch(
            card_switches, text="Abrir o traer al frente la aplicación al conectar/encender el mando",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS
        )
        if self.cfg.get("auto_launch_on_connect", True):
            self.sw_auto_launch.select()
        else:
            self.sw_auto_launch.deselect()
        self.sw_auto_launch.pack(anchor="w", padx=16, pady=6)
        
        self.sw_mini_mode = ctk.CTkSwitch(
            card_switches, text="Iniciar en Modo Pequeño (Flotante y Transparente) al conectar el mando",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS,
            command=self._on_toggle_mini_mode
        )
        if self.cfg.get("start_in_mini_mode", True):
            self.sw_mini_mode.select()
        else:
            self.sw_mini_mode.deselect()
        self.sw_mini_mode.pack(anchor="w", padx=16, pady=6)

        self.sw_fullscreen = ctk.CTkSwitch(
            card_switches, text="Activar pantalla completa automáticamente al conectar el mando (Modo Consola)",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS,
            command=self._on_toggle_fullscreen
        )
        if self.cfg.get("auto_fullscreen", False) and not self.cfg.get("start_in_mini_mode", True):
            self.sw_fullscreen.select()
        else:
            self.sw_fullscreen.deselect()
        self.sw_fullscreen.pack(anchor="w", padx=16, pady=6)

        self.sw_nav = ctk.CTkSwitch(
            card_switches, text="Habilitar control de interfaz con mando (Stick, cruceta, botón A para jugar)",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS
        )
        if self.cfg.get("enable_controller_nav", True):
            self.sw_nav.select()
        else:
            self.sw_nav.deselect()
        self.sw_nav.pack(anchor="w", padx=16, pady=6)

        self.sw_xbox_btn = ctk.CTkSwitch(
            card_switches, text="Invocar lanzador con el botón Xbox / Guía (incluso con la app cerrada)",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS
        )
        if self.cfg.get("launch_on_xbox_button", True):
            self.sw_xbox_btn.select()
        else:
            self.sw_xbox_btn.deselect()
        self.sw_xbox_btn.pack(anchor="w", padx=16, pady=6)

        self.sw_startup = ctk.CTkSwitch(
            card_switches, text="Iniciar detector en segundo plano al arrancar Windows (Watcher)",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS
        )
        if self.cfg.get("start_with_windows", False) or is_windows_startup_enabled():
            self.sw_startup.select()
        else:
            self.sw_startup.deselect()
        self.sw_startup.pack(anchor="w", padx=16, pady=6)

        self.sw_close_on_launch = ctk.CTkSwitch(
            card_switches, text="Cerrar el lanzador automáticamente al iniciar un juego (libera 100% de RAM)",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS
        )
        if self.cfg.get("close_on_game_launch", True):
            self.sw_close_on_launch.select()
        else:
            self.sw_close_on_launch.deselect()
        self.sw_close_on_launch.pack(anchor="w", padx=16, pady=6)

        self.sw_haptics = ctk.CTkSwitch(
            card_switches, text="Vibración háptica (Rumble) en el mando al pasar carátulas e interactuar",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS
        )
        if self.cfg.get("enable_haptics", True):
            self.sw_haptics.select()
        else:
            self.sw_haptics.deselect()
        self.sw_haptics.pack(anchor="w", padx=16, pady=6)

        self.sw_sound_fx = ctk.CTkSwitch(
            card_switches, text="Efectos acústicos retro 'iPod Click Wheel' al navegar por el carrusel",
            font=font_body(13), progress_color=COLOR_STATUS_SUCCESS
        )
        if self.cfg.get("enable_sound_fx", True):
            self.sw_sound_fx.select()
        else:
            self.sw_sound_fx.deselect()
        self.sw_sound_fx.pack(anchor="w", padx=16, pady=(6, 14))

        self._nav_switches = [
            self.sw_auto_launch,
            self.sw_mini_mode,
            self.sw_fullscreen,
            self.sw_nav,
            self.sw_xbox_btn,
            self.sw_startup,
            self.sw_close_on_launch,
            self.sw_haptics,
            self.sw_sound_fx
        ]
        self._focused_switch_idx = 0

        # Tarjeta 3: Guía rápida de controles
        card_guide = ctk.CTkFrame(scroll, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=16, border_color=COLOR_BORDER_CARD, border_width=1.0)
        card_guide.pack(fill="x", pady=6)
        self.card_guide = card_guide
        
        ctk.CTkLabel(
            card_guide, text="Guía de Controles en el Lanzador:",
            font=font_button(13),
            text_color="#93c5fd"
        ).pack(anchor="w", padx=16, pady=(10, 4))
        
        guide_text = (
            "• 🎮 Botón Xbox / Guía: Invocar / restaurar el lanzador (incluso estando cerrado)\n"
            "• 🕹️ Stick Izquierdo / ◀ ▶ Cruceta: Navegar por las carátulas (con repetición fluida)\n"
            "• 🟢 Botón A / ✕ (Cruz): Iniciar el juego seleccionado inmediatamente\n"
            "• 🔴 Botón B / ◯ (Círculo): Cerrar menús o volver a Modo Pequeño transparente\n"
            "• ⚙️ Botón Start / Options: Alternar Modo Pequeño Transparente / Pantalla Completa\n"
            "• 🔲 Botón Select / Back / Share: Minimizar y restaurar/maximizar el lanzador\n"
            "• 🟡 Botón Y / △ (Triángulo): Cerrar el lanzador (con diálogo de confirmación)\n"
            "• 🎮 Botones LB / RB (L1 / R1): Saltar 5 carátulas hacia atrás o adelante\n"
            "• 🚨 Emergencia (Back + Start sostenidos 2.5s): Cerrar juego colgado y volver al menú"
        )
        ctk.CTkLabel(
            card_guide, text=guide_text,
            font=font_body(11),
            text_color="#64748b", justify="left", anchor="w"
        ).pack(fill="x", padx=16, pady=(0, 10))

        # 3. Pie de página (Píldoras iOS)
        footer = ctk.CTkFrame(self.main_card, fg_color="transparent", height=48)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        
        self.btn_save = ctk.CTkButton(
            footer, text="Guardar Configuración ", image=get_button_icon_ctk("start", self.family, size=20), compound="right",
            width=210, height=38,
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER, border_color=COLOR_IOS_BLUE_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_WHITE, font=font_button(13),
            command=self._save_settings
        )
        self.btn_save.pack(side="right", padx=(8, 0), pady=4)

        self.btn_cancel = ctk.CTkButton(
            footer, text="Cancelar ", image=get_button_icon_ctk("b", self.family, size=20), compound="right",
            width=128, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER, border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0,
            corner_radius=19, text_color=COLOR_TEXT_MUTED_LIGHT, font=font_body(12),
            command=self.destroy
        )
        self.btn_cancel.pack(side="right", pady=4)

        # Lista completa de elementos navegables con mando (acompañando el scroll de arriba a abajo)
        self._nav_items = [
            ("dropdown", self.device_combo, self.card_dev),
            ("switch", self.sw_auto_launch, self.sw_auto_launch),
            ("switch", self.sw_mini_mode, self.sw_mini_mode),
            ("switch", self.sw_fullscreen, self.sw_fullscreen),
            ("switch", self.sw_nav, self.sw_nav),
            ("switch", self.sw_xbox_btn, self.sw_xbox_btn),
            ("switch", self.sw_startup, self.sw_startup),
            ("switch", self.sw_close_on_launch, self.sw_close_on_launch),
            ("switch", self.sw_haptics, self.sw_haptics),
            ("switch", self.sw_sound_fx, self.sw_sound_fx),
            ("guide", self.card_guide, self.card_guide),
            ("btn_save", self.btn_save, None),
            ("btn_cancel", self.btn_cancel, None),
        ]
        self._focused_idx = 0
        self.after(50, self._update_focus_highlight)

    def _on_toggle_mini_mode(self):
        if self.sw_mini_mode.get():
            self.sw_fullscreen.deselect()

    def _on_toggle_fullscreen(self):
        if self.sw_fullscreen.get():
            self.sw_mini_mode.deselect()

    def _step_focus(self, delta: int):
        items = getattr(self, "_nav_items", [])
        if not items:
            return
        self._focused_idx = (self._focused_idx + delta) % len(items)
        self._update_focus_highlight()
        try:
            from core.feedback import feedback_click
            feedback_click()
        except Exception:
            pass

    def _activate_focused(self):
        items = getattr(self, "_nav_items", [])
        if not items or not (0 <= self._focused_idx < len(items)):
            return
        kind, widget, _ = items[self._focused_idx]
        if kind == "dropdown":
            widget._toggle_dropdown()
        elif kind == "switch":
            widget.toggle()
        elif kind in ("guide", "btn_save"):
            self._save_settings()
        elif kind == "btn_cancel":
            self.destroy()

    def _update_focus_highlight(self):
        items = getattr(self, "_nav_items", [])
        if not items:
            return

        for i, (kind, widget, scroll_target) in enumerate(items):
            is_foc = (i == self._focused_idx)
            if kind == "dropdown":
                self.card_dev.configure(
                    border_color="#007aff" if is_foc else "#242c3d",
                    border_width=2.0 if is_foc else 1.0
                )
                widget.configure(border_color="#38bdf8" if is_foc else "#343f55", border_width=1.8 if is_foc else 1.0)
            elif kind == "switch":
                widget.configure(text_color=COLOR_CYAN_ACCENT if is_foc else COLOR_TEXT_MAIN)
            elif kind == "guide":
                self.card_guide.configure(
                    border_color="#007aff" if is_foc else "#242c3d",
                    border_width=2.0 if is_foc else 1.0
                )
            elif kind == "btn_save":
                widget.configure(border_color=COLOR_CYAN_ACCENT if is_foc else COLOR_IOS_BLUE_BORDER, border_width=2.4 if is_foc else 1.2)
            elif kind == "btn_cancel":
                widget.configure(border_color=COLOR_IOS_BLUE if is_foc else COLOR_BTN_SECONDARY_BORDER, border_width=2.2 if is_foc else 1.0)

            if is_foc and scroll_target is not None and hasattr(self, "scroll"):
                force_edge = "top" if i == 0 else ("bottom" if kind == "guide" else None)
                scroll_to_widget(self.scroll, scroll_target, force_edge=force_edge)

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.destroy()
            return True
        if (inputs.get("start", False) and not prev_inputs.get("start", False)) or \
           (inputs.get("y", False) and not prev_inputs.get("y", False)):
            self._save_settings()
            return True

        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._step_focus(-1)
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self._step_focus(1)
            return True

        items = getattr(self, "_nav_items", [])
        if items and 0 <= self._focused_idx < len(items):
            kind, widget, _ = items[self._focused_idx]
            if inputs.get("left", False) and not prev_inputs.get("left", False):
                if kind == "dropdown":
                    vals = widget.values
                    if vals:
                        cur_i = vals.index(widget.get()) if widget.get() in vals else 0
                        widget.set(vals[(cur_i - 1) % len(vals)])
                    return True
                elif kind == "switch":
                    if widget.get():
                        widget.toggle()
                    return True
                elif kind == "btn_cancel":
                    self._focused_idx = len(items) - 2
                    self._update_focus_highlight()
                    return True
            if inputs.get("right", False) and not prev_inputs.get("right", False):
                if kind == "dropdown":
                    vals = widget.values
                    if vals:
                        cur_i = vals.index(widget.get()) if widget.get() in vals else 0
                        widget.set(vals[(cur_i + 1) % len(vals)])
                    return True
                elif kind == "switch":
                    if not widget.get():
                        widget.toggle()
                    return True
                elif kind == "btn_save":
                    self._focused_idx = len(items) - 1
                    self._update_focus_highlight()
                    return True

        if inputs.get("a", False) and not prev_inputs.get("a", False):
            self._activate_focused()
            return True
        return False

    def _poll_status(self):
        if not self.winfo_exists() or not getattr(self, "is_monitoring", False):
            return

        sel_label = self.device_combo.get() if hasattr(self, "device_combo") else ""
        sel_id = "any"
        for d in self.paired_devices:
            if d["name"] == sel_label:
                sel_id = d["id"]
                break

        is_conn, dev_name, inputs = poll_active_gamepad(sel_id)
        if is_conn:
            active_btn_text = ""
            if inputs.get("guide"): active_btn_text = " [Botón Xbox / Guía]"
            elif inputs.get("a"): active_btn_text = " [Botón A / ✕ Cruz]"
            elif inputs.get("b"): active_btn_text = " [Botón B / ◯ Círculo]"
            elif inputs.get("x"): active_btn_text = " [Botón X / ▢ Cuadrado]"
            elif inputs.get("y"): active_btn_text = " [Botón Y / △ Triángulo]"
            elif inputs.get("left"): active_btn_text = " [◀ Izquierda]"
            elif inputs.get("right"): active_btn_text = " [▶ Derecha]"
            elif inputs.get("back"): active_btn_text = " [Select / Back]"
            elif inputs.get("start"): active_btn_text = " [Start / Options]"
            
            self.lbl_live_status.configure(
                text=f"🟢 Conectado: {dev_name}{active_btn_text}",
                text_color=COLOR_STATUS_SUCCESS
            )
        else:
            self.lbl_live_status.configure(
                text="🔴 Desconectado (Enciende o conecta tu mando por Bluetooth/USB para probarlo)",
                text_color=COLOR_STATUS_DANGER
            )
        self.after(150, self._poll_status)

    def _save_settings(self):
        self.is_monitoring = False
        sel_label = self.device_combo.get()
        sel_id = "any"
        for d in self.paired_devices:
            if d["name"] == sel_label:
                sel_id = d["id"]
                break
                
        new_cfg = {
            "selected_controller_id": sel_id,
            "selected_controller_name": sel_label,
            "auto_launch_on_connect": bool(self.sw_auto_launch.get()),
            "close_on_game_launch": bool(self.sw_close_on_launch.get()),
            "launch_on_xbox_button": bool(self.sw_xbox_btn.get()),
            "start_in_mini_mode": bool(self.sw_mini_mode.get()),
            "auto_fullscreen": bool(self.sw_fullscreen.get()),
            "enable_controller_nav": bool(self.sw_nav.get()),
            "enable_haptics": bool(self.sw_haptics.get()),
            "enable_sound_fx": bool(self.sw_sound_fx.get()),
            "start_with_windows": bool(self.sw_startup.get())
        }
        save_gamepad_config(new_cfg)
        set_windows_startup(new_cfg["start_with_windows"])
        
        self.destroy()
        if self.on_save_callback:
            self.on_save_callback(new_cfg)
