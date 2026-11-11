import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import os
import time
import threading
import queue
import ctypes
from typing import List, Dict, Any, Optional
import customtkinter as ctk

from core.platform_layer import safe_set_app_user_model_id, is_windows
safe_set_app_user_model_id("gameflow.launcher.liquidglass.v1")

from core.logger import get_logger
logger = get_logger("App")

from core.system import get_monitors
from core.cover_resolver import resolve_game_cover
from core.scanner import scan_directory_for_games
from core.library_service import GameLibraryService, format_monitor_label
from core.execution_service import GameExecutionService
from ui.window_manager import WindowStateService
from ui.gamepad_service import GamepadNavigationService
from ui.modal_manager import register_modal_stack, unregister_modal_stack

from ui.theme import (
    bring_to_front_absolute,
    COLOR_BG_DARK, COLOR_BG_CANVAS, COLOR_BG_CARD,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER,
    COLOR_CYAN_ACCENT,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_STATUS_DANGER, COLOR_STATUS_WARNING, COLOR_STATUS_SUCCESS,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_title, font_button, font_body
)
from ui.coverflow_canvas import CoverFlowCanvas
from ui.controller_hud import render_controller_hud_strip, get_button_icon_ctk
from ui.dropdowns import FloatingGlassMenu
from ui.dialogs import (
    AddEditGameDialog, ScanResultsDialog, SelectGameToEditDialog,
    GamepadConfigDialog, ConfirmExitDialog, CoverPickerDialog,
    ExternalImportDialog, BatchSteamGridDBDialog, CollectionsFilterDialog,
    invalidate_thumb_cache, show_info, show_error, ask_yes_no, browse_folder
)
from gamepad_manager import (
    load_gamepad_config, poll_active_gamepad, get_connected_controller_family,
    ensure_gamebar_nexus_disabled, ensure_watcher_running, force_foreground_window
)


class App(ctk.CTk):
    """Aplicación principal GameFlow con interfaz iPod Cover Flow 3D y navegación por mando."""

    def __init__(self):
        super().__init__()
        self.title("GameFlow Launcher")
        self.geometry("1020x720")
        self.minsize(880, 620)
        self.configure(fg_color=COLOR_BG_DARK)

        # 1. Servicios desacoplados y especializados (Fase 3 Refactor)
        self.library = GameLibraryService()
        self.window_manager = WindowStateService(self)
        self.execution_service = GameExecutionService()
        self.gamepad_service = GamepadNavigationService(self)

        # Configurar icono personalizado en barra de tareas y ventana
        self.window_manager.setup_app_icon()

        # Cargar colección de juegos en memoria y preparar filtros
        self.library.load()
        self.current_filter_id = "all"
        self.available_filters = self.library.get_available_filters()
        self.filtered_games = self.library.filter_games(self.current_filter_id)
        self.games = self.filtered_games
        self.monitors = get_monitors()
        self.selected_index = 0
        self.exit_dialog = None
        self._collections_dialog = None
        self._modal_stack: List[Any] = []
        self._action_queue: queue.Queue = queue.Queue()
        self.gamepad_config = load_gamepad_config()

        self.protocol("WM_DELETE_WINDOW", self.open_exit_dialog)
        self.bind("<FocusIn>", lambda e: self.refresh_games_from_disk_if_modified() if e.widget == self else None)

        self.create_widgets()
        self.bind_events()
        self._start_gamepad_loop()
        self.after(50, self._poll_action_queue)

        # Liberar el botón Xbox de la Game Bar y asegurar el watcher de fondo
        try:
            ensure_gamebar_nexus_disabled()
            ensure_watcher_running()
        except Exception:
            pass

        # Si el mando está conectado al iniciar y la opción start_in_mini_mode está activa,
        # arrancar directamente en modo pequeño widget transparente
        if self.gamepad_config.get("start_in_mini_mode", True):
            target_id = self.gamepad_config.get("selected_controller_id", "any")
            is_conn, _, _ = poll_active_gamepad(target_id)
            if is_conn:
                self.after(80, self.set_mini_mode)

        # Forzar ventana a primer plano absoluto sobre cualquier juego o app activa
        self.after(60, lambda: force_foreground_window(self.winfo_id()))
        # Iniciar sondeo periódico de nivel de batería del mando (cada 4s)
        self.after(400, self._poll_battery_status)

    # -------------------------------------------------------------
    # Propiedades de Estado de Ventana (Compatibilidad con Servicios)
    # -------------------------------------------------------------
    @property
    def is_mini_mode(self) -> bool:
        return self.window_manager.is_mini_mode

    @is_mini_mode.setter
    def is_mini_mode(self, val: bool) -> None:
        self.window_manager.is_mini_mode = val

    @property
    def is_fullscreen(self) -> bool:
        return self.window_manager.is_fullscreen

    @is_fullscreen.setter
    def is_fullscreen(self, val: bool) -> None:
        self.window_manager.is_fullscreen = val

    @property
    def is_minimized(self) -> bool:
        return self.window_manager.is_minimized

    @is_minimized.setter
    def is_minimized(self, val: bool) -> None:
        self.window_manager.is_minimized = val

    @property
    def _is_launching(self) -> bool:
        return self.execution_service.is_launching

    # -------------------------------------------------------------
    # Gestión de Colección de Juegos (Delegación a GameLibraryService)
    # -------------------------------------------------------------
    def load_games(self) -> List[Dict[str, Any]]:
        self.library.load()
        self.available_filters = self.library.get_available_filters()
        self.filtered_games = self.library.filter_games(self.current_filter_id)
        self.games = self.filtered_games
        return self.games

    def save_games(self) -> None:
        self.library.save()

    def refresh_games_from_disk_if_modified(self) -> bool:
        """Sincroniza metadatos de juegos actualizados en disco por el centinela sin reiniciar la selección."""
        res = self.library.refresh_if_modified()
        if res:
            self.apply_filter(self.current_filter_id, keep_selection=True)
        return res

    def _get_library_index_for_game(self, game: Optional[Dict[str, Any]]) -> int:
        """Resuelve el índice absoluto de un juego en la colección global library.games."""
        if not game:
            return 0
        gp = game.get("path")
        gn = (game.get("name") or "").strip().lower()
        for idx, lg in enumerate(self.library.games):
            if gp and lg.get("path") == gp:
                return idx
            if gn and (lg.get("name") or "").strip().lower() == gn:
                return idx
        return 0

    def apply_filter(self, filter_id: str, keep_selection: bool = True):
        """Aplica un filtro o colección a la biblioteca (Todos, Favoritos, Estado, Plataforma o Género)."""
        prev_game = self.games[self.selected_index] if 0 <= self.selected_index < len(self.games) else None
        self.current_filter_id = filter_id
        self.available_filters = self.library.get_available_filters()
        self.filtered_games = self.library.filter_games(filter_id)
        self.games = self.filtered_games

        new_idx = 0
        if keep_selection and prev_game:
            pg_path = prev_game.get("path")
            pg_name = (prev_game.get("name") or "").strip().lower()
            for i, g in enumerate(self.games):
                if (pg_path and g.get("path") == pg_path) or (pg_name and (g.get("name") or "").strip().lower() == pg_name):
                    new_idx = i
                    break

        active_filt = next(
            (f for f in self.available_filters if f["id"] == filter_id),
            {"label": "Todos", "count": len(self.games), "icon": "🎮"}
        )

        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.ui_filter_label = active_filt.get("label", "Todos")
            self.cover_stage.ui_filter_count = len(self.games)
            self.cover_stage.set_games(self.games, target_index=new_idx)

        self.selected_index = new_idx if self.games else 0
        self.update_ui_details(self.selected_index)

    def cycle_filter(self, direction: int):
        """Cambia cíclicamente de colección/filtro con los botones LB/RB del mando o teclas Q/E."""
        filters = self.library.get_available_filters()
        if not filters:
            return
        cur_id = self.current_filter_id
        cur_idx = 0
        for i, f in enumerate(filters):
            if f["id"] == cur_id:
                cur_idx = i
                break
        next_idx = (cur_idx + direction) % len(filters)
        next_filt = filters[next_idx]
        try:
            from core.feedback import feedback_click
            feedback_click()
        except Exception:
            pass
        self.apply_filter(next_filt["id"], keep_selection=True)
        self.set_status(f"Colección: {next_filt.get('icon', '🏷️')} {next_filt.get('label', 'Todos')} ({len(self.games)} juegos)")

    def open_collections_dialog(self):
        """Abre el diálogo modal de exploración y filtrado rápido de colecciones."""
        self.close_active_menu()
        if hasattr(self, "_collections_dialog") and self._collections_dialog and self._collections_dialog.winfo_exists():
            try:
                self._collections_dialog.lift()
                self._collections_dialog.focus_force()
            except Exception:
                pass
            return
        filters = self.library.get_available_filters()
        self._collections_dialog = CollectionsFilterDialog(
            self,
            filters=filters,
            current_filter_id=self.current_filter_id,
            on_select_filter=lambda fid: self.apply_filter(fid, keep_selection=True)
        )

    def open_in_game_overlay(self):
        """Abre o alterna el In-Game Overlay flotante con reloj, bateria y volumen al pulsar el boton Guia."""
        self.close_active_menu()
        if hasattr(self, "_in_game_overlay") and self._in_game_overlay and self._in_game_overlay.winfo_exists():
            self._in_game_overlay.resume_game()
            return

        from ui.dialogs.in_game_overlay import InGameOverlayDialog
        self._in_game_overlay = InGameOverlayDialog(
            parent=self,
            on_resume_callback=lambda: setattr(self, "_in_game_overlay", None),
            on_return_to_launcher_callback=lambda: self.restore_window(),
            on_exit_game_callback=lambda: self.restore_window()
        )

    def open_game_stats_dialog(self):
        """Abre la pantalla de estadísticas avanzadas, gráficas de tiempo y metas para el juego actual."""
        self.close_active_menu()
        if hasattr(self, "_stats_dialog") and self._stats_dialog and self._stats_dialog.winfo_exists():
            try:
                self._stats_dialog.lift()
                self._stats_dialog.focus_force()
            except Exception:
                pass
            return

        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return

        game = self.games[self.selected_index]
        from ui.dialogs.game_stats_dialog import GameStatsDialog

        def _on_updated(updated_game):
            self.save_games()
            self.cover_stage.set_games(self.games, target_index=self.selected_index)
            self.update_ui_details(self.selected_index)

        self._stats_dialog = GameStatsDialog(
            parent=self,
            game=game,
            on_game_updated=_on_updated
        )

    def open_save_backup_dialog(self):
        """Abre la pantalla de copias de seguridad y restauración de partidas guardadas para el juego actual."""
        self.close_active_menu()
        if hasattr(self, "_backup_dialog") and self._backup_dialog and self._backup_dialog.winfo_exists():
            try:
                self._backup_dialog.lift()
                self._backup_dialog.focus_force()
            except Exception:
                pass
            return

        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return

        game = self.games[self.selected_index]
        from ui.dialogs.save_backup_dialog import SaveBackupDialog

        def _on_updated(updated_game):
            self.save_games()
            self.cover_stage.set_games(self.games, target_index=self.selected_index)
            self.update_ui_details(self.selected_index)

        self._backup_dialog = SaveBackupDialog(
            parent=self,
            game=game,
            on_game_updated=_on_updated
        )

    def open_performance_dialog(self):
        """Abre el panel de Modos de Rendimiento y Energía (Handheld Mode / Perfiles de Batería)."""
        self.close_active_menu()
        if hasattr(self, "_perf_dialog") and self._perf_dialog and self._perf_dialog.winfo_exists():
            try:
                self._perf_dialog.lift()
                self._perf_dialog.focus_force()
            except Exception:
                pass
            return

        game = None
        if self.games and 0 <= self.selected_index < len(self.games):
            game = self.games[self.selected_index]

        from ui.dialogs.performance_dialog import PerformanceProfileDialog

        def _on_updated(updated_game):
            self.save_games()
            self.cover_stage.set_games(self.games, target_index=self.selected_index)
            self.update_ui_details(self.selected_index)

        self._perf_dialog = PerformanceProfileDialog(
            parent=self,
            game=game,
            on_game_updated=_on_updated
        )

    def open_cloud_sync_dialog(self):
        """Abre el panel de Sincronización de Partidas en la Nube (Cloud Save Sync)."""
        self.close_active_menu()
        if hasattr(self, "_cloud_sync_dialog") and self._cloud_sync_dialog and self._cloud_sync_dialog.winfo_exists():
            try:
                self._cloud_sync_dialog.lift()
                self._cloud_sync_dialog.focus_force()
            except Exception:
                pass
            return

        from ui.dialogs.cloud_sync_dialog import CloudSyncDialog

        def _on_sync_done():
            self.update_ui_details(self.selected_index)

        self._cloud_sync_dialog = CloudSyncDialog(
            parent=self,
            games=self.games,
            on_sync_completed=_on_sync_done
        )

    def open_achievements_dialog(self):
        """Abre el panel de Logros y Trofeos (Steam & RetroAchievements) para el juego seleccionado."""
        self.close_active_menu()
        if hasattr(self, "_achievements_dialog") and self._achievements_dialog and self._achievements_dialog.winfo_exists():
            try:
                self._achievements_dialog.lift()
                self._achievements_dialog.focus_force()
            except Exception:
                pass
            return

        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return

        game = self.games[self.selected_index]
        from ui.dialogs.achievements_dialog import AchievementsDialog

        def _on_updated(updated_game):
            self.save_games()
            self.cover_stage.set_games(self.games, target_index=self.selected_index)
            self.update_ui_details(self.selected_index)

        self._achievements_dialog = AchievementsDialog(
            parent=self,
            game=game,
            on_game_updated=_on_updated
        )

    def toggle_current_game_favorite(self):
        """Alterna el estado favorito del juego actualmente seleccionado."""
        self.close_active_menu()
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return
        target_game = self.games[self.selected_index]
        real_idx = self._get_library_index_for_game(target_game)
        new_fav = self.library.toggle_favorite(real_idx)
        try:
            from core.feedback import feedback_click
            feedback_click()
        except Exception:
            pass
        status_msg = f"★ '{target_game.get('name')}' añadido a Favoritos" if new_fav else f"'{target_game.get('name')}' quitado de Favoritos"
        self.set_status(status_msg)
        self.apply_filter(self.current_filter_id, keep_selection=True)

    def _format_monitor_full_label(self, mon_idx: int) -> str:
        """Devuelve el texto completo del monitor (ej: 'Monitor 2 - SAMSUNG (1920x1080)')."""
        return format_monitor_label(mon_idx, self.monitors)

    def _get_game_subtitle(self, game: Dict[str, Any]) -> str:
        return self.library.format_subtitle(game, self.monitors)

    def _on_quick_letter_jump(self, event=None, direction: int = 0):
        """Salto alfabético instantáneo al pulsar una letra en teclado o los gatillos LT/RT en el mando."""
        if not self.games or self._get_topmost_active_modal() is not None:
            return
        ch = getattr(event, "char", "") if event else ""
        next_idx = self.library.find_alphabetical_jump(self.selected_index, direction=direction, char=ch, games_list=self.games)
        if next_idx is not None:
            self.cover_stage.select_index(next_idx)
            target_game = self.games[next_idx]
            g_name = (target_game.get("name") or "Juego").strip()
            initial = g_name[0].upper() if g_name else "#"
            self.set_status(f"Salto rápido [{initial}]  •  {g_name}")

    def _on_window_configure(self, event=None):
        """Detecta en caliente cambios de monitor o DPI (WM_DPICHANGED / arrastre multi-monitor) y reescala la UI."""
        if event is not None and event.widget is not self:
            return
        now = time.perf_counter()
        if now - getattr(self, "_last_dpi_check_ts", 0.0) < 0.25:
            return
        self._last_dpi_check_ts = now
        try:
            from ui.display_scale import (
                get_monitor_work_area_for_window,
                get_window_dpi,
                get_display_scale_factor,
                set_active_display_scale
            )
            work_w, work_h, mon_rc = get_monitor_work_area_for_window(self)
            dpi = get_window_dpi(self)
            sig = (work_w, work_h, mon_rc, dpi)
            prev_sig = getattr(self, "_active_monitor_sig", None)
            if prev_sig != sig:
                self._active_monitor_sig = sig
                scale = get_display_scale_factor(self)
                set_active_display_scale(scale)
                if prev_sig is not None:
                    self.monitors = get_monitors()
                    self._sync_controller_family_ui(force=True)
                    if hasattr(self, "cover_stage") and self.cover_stage:
                        cw = self.cover_stage.winfo_width()
                        ch = self.cover_stage.winfo_height()
                        if cw > 60 and ch > 60:
                            self.cover_stage.last_w = 0
                            self.cover_stage.last_h = 0
                            self.cover_stage._on_resize(type("Event", (), {"width": cw, "height": ch})())
        except Exception:
            pass

    # -------------------------------------------------------------
    # Creación de Componentes Gráficos de Interfaz
    # -------------------------------------------------------------
    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # 1. Barra Superior (instanciada pero desmapeada para que el CoverFlowCanvas llegue a y=0)
        top_bar = ctk.CTkFrame(self, height=52, fg_color="transparent", corner_radius=0)
        top_bar.grid_columnconfigure(0, weight=1)
        self.top_bar = top_bar

        actions_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        actions_box.pack(side="right", padx=0, pady=2)

        self._current_controller_family = get_connected_controller_family(self.gamepad_config)
        self.btn_menu = ctk.CTkButton(
            actions_box,
            text="⚙ ",
            image=get_button_icon_ctk("x", self._current_controller_family, size=18),
            compound="right",
            width=58,
            height=36,
            corner_radius=18,
            fg_color=COLOR_BG_CARD,
            hover_color=COLOR_GLASS_HOVER,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.2,
            text_color=COLOR_TEXT_MAIN,
            font=("Segoe UI", 15, "bold"),
            command=self.toggle_top_menu
        )
        self.btn_menu.pack(side="left", padx=2, pady=0)

        self.btn_battery = ctk.CTkButton(
            actions_box,
            text="🔋 --",
            width=78,
            height=36,
            corner_radius=18,
            fg_color=COLOR_BG_CARD,
            hover_color=COLOR_GLASS_HOVER,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.2,
            text_color=COLOR_CYAN_ACCENT,
            font=font_button(12),
            command=self._show_battery_info
        )
        self.btn_battery.pack(side="left", padx=2, pady=0)

        self._hud_ctk_images = {}
        self._top_hud_boxes = []

        self.hud_strip_label = ctk.CTkLabel(
            actions_box,
            text="",
            fg_color="transparent",
            cursor="hand2"
        )
        self.hud_strip_label.pack(side="left", padx=(2, 2), pady=0)
        self.hud_strip_label.bind("<Button-1>", self._on_top_hud_click)

        # 2. Escenario Central a Pantalla Completa 100% (de y=0 a y=h sin barras grises)
        self.cover_stage = CoverFlowCanvas(
            self,
            on_selection_changed=self.on_cover_selected,
            on_launch_requested=self.launch_current_game,
            on_hud_action=self._on_canvas_hud_action
        )
        self.cover_stage.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # 3. Panel Inferior (instanciado sin mapear para eliminar cualquier barra inferior)
        bottom_panel = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bottom_panel.grid_columnconfigure(0, weight=1)
        self.bottom_panel = bottom_panel

        self.lbl_game_title = ctk.CTkLabel(
            bottom_panel, text="",
            font=font_title(26),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_game_title.grid(row=0, column=0, pady=(0, 2))

        self.lbl_status = ctk.CTkLabel(
            bottom_panel, text="",
            font=font_body(12),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_status.grid(row=1, column=0, pady=(0, 10))
        self._status_reset_job = None

        self.btn_launch = ctk.CTkButton(
            bottom_panel, text="▶  INICIAR JUEGO ",
            image=get_button_icon_ctk("a", self._current_controller_family, size=22),
            compound="right",
            width=245, height=48,
            font=font_button(14),
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER,
            border_width=1.2,
            corner_radius=24,
            text_color=COLOR_TEXT_WHITE,
            command=self.launch_current_game
        )
        self.btn_launch.grid(row=2, column=0, pady=(0, 4))
        self._sync_controller_family_ui(force=True)

        # Cargar juegos en el Cover Flow
        self.cover_stage.set_games(self.games, target_index=0)
        self.update_ui_details(0)

    def bind_events(self):
        self.bind("<Left>", lambda e: self.cover_stage.prev_cover())
        self.bind("<Right>", lambda e: self.cover_stage.next_cover())
        self.bind("<Return>", lambda e: self.launch_current_game())
        self.bind("<space>", lambda e: self.launch_current_game())
        self.bind("<Home>", lambda e: self.cover_stage.select_index(0))
        self.bind("<End>", lambda e: self.cover_stage.select_index(len(self.games) - 1))
        self.bind("<Delete>", lambda e: self.delete_current_game())
        self.bind_all("<Button-1>", self._on_global_click, add="+")
        self.bind("<F11>", lambda e: self.toggle_size_mode())
        self.bind("<Tab>", lambda e: self.toggle_size_mode())
        self.bind("<Escape>", lambda e: self.set_mini_mode() if not self.is_mini_mode else None)
        self.bind("<Key>", self._on_quick_letter_jump, add="+")
        self.bind("<q>", lambda e: self.cycle_filter(-1))
        self.bind("<Q>", lambda e: self.cycle_filter(-1))
        self.bind("<e>", lambda e: self.cycle_filter(1))
        self.bind("<E>", lambda e: self.cycle_filter(1))
        self.bind("<bracketleft>", lambda e: self.cycle_filter(-1))
        self.bind("<bracketright>", lambda e: self.cycle_filter(1))
        self.bind("<f>", lambda e: self.toggle_current_game_favorite())
        self.bind("<F>", lambda e: self.toggle_current_game_favorite())
        self.bind("<s>", lambda e: self.open_game_stats_dialog())
        self.bind("<S>", lambda e: self.open_game_stats_dialog())
        self.bind("<c>", lambda e: self.open_save_backup_dialog())
        self.bind("<C>", lambda e: self.open_save_backup_dialog())
        self.bind("<Control-b>", lambda e: self.open_save_backup_dialog())
        self.bind("<o>", lambda e: self.open_in_game_overlay())
        self.bind("<O>", lambda e: self.open_in_game_overlay())
        self.bind("<F1>", lambda e: self.open_in_game_overlay())
        self.bind("<p>", lambda e: self.open_performance_dialog())
        self.bind("<P>", lambda e: self.open_performance_dialog())
        self.bind("<y>", lambda e: self.open_achievements_dialog())
        self.bind("<Y>", lambda e: self.open_achievements_dialog())
        self.bind("<Configure>", self._on_window_configure, add="+")

    def on_cover_selected(self, index: int):
        self.selected_index = index
        self.update_ui_details(index)

    def _on_canvas_hud_action(self, action: str):
        if action == "menu":
            if not getattr(self, "is_mini_mode", False):
                self.toggle_top_menu()
        elif action == "battery":
            self._show_battery_info()
        elif action == "launch":
            self.launch_current_game()
        elif action == "filter_prev":
            self.cycle_filter(-1)
        elif action == "filter_next":
            self.cycle_filter(1)
        elif action == "filter_menu":
            self.open_collections_dialog()
        elif action == "start":
            self.toggle_size_mode()
        elif action == "select":
            self.toggle_minimize()
        elif action == "exit":
            self.open_exit_dialog()

    def _on_top_hud_click(self, event):
        x = event.x
        for (bx1, _by1, bx2, _by2, act) in getattr(self, "_top_hud_boxes", []):
            if bx1 <= x <= bx2:
                self._on_canvas_hud_action(act)
                return

    def _sync_controller_family_ui(self, force: bool = False):
        """Actualiza dinámicamente la cápsula superior derecha e iconos según el mando conectado."""
        try:
            fam = get_connected_controller_family(self.gamepad_config)
        except Exception:
            fam = "xbox"

        if not force and fam == getattr(self, "_current_controller_family", None) and getattr(self, "_hud_ctk_images", None):
            return

        self._current_controller_family = fam
        if hasattr(self, "cover_stage") and self.cover_stage:
            prev_fam = getattr(self.cover_stage, "controller_family", None)
            self.cover_stage.controller_family = fam
            if prev_fam != fam or force:
                self.cover_stage.redraw()

        try:
            strip_img, boxes = render_controller_hud_strip(fam, height=36)
            self._top_hud_boxes = boxes
            ctk_strip = ctk.CTkImage(
                light_image=strip_img,
                dark_image=strip_img,
                size=(strip_img.width, strip_img.height)
            )
            self._hud_ctk_images["strip"] = ctk_strip
            if hasattr(self, "hud_strip_label") and self.hud_strip_label.winfo_exists():
                self.hud_strip_label.configure(image=ctk_strip, text="", width=strip_img.width, height=strip_img.height)

            if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                self.btn_launch.configure(image=get_button_icon_ctk("a", fam, size=22), compound="right")
            if hasattr(self, "btn_menu") and self.btn_menu.winfo_exists():
                self.btn_menu.configure(image=get_button_icon_ctk("x", fam, size=18), compound="right")
        except Exception:
            pass

    def update_ui_details(self, index: int):
        n = len(self.games)
        if n == 0 or index >= n:
            self.lbl_game_title.configure(text="")
            if hasattr(self, "lbl_status") and self.lbl_status:
                self.lbl_status.configure(text="Añade o escanea tu carpeta de juegos desde el menú ⚙", text_color=COLOR_TEXT_DIM)
            self.btn_launch.configure(state="disabled")
            if hasattr(self, "cover_stage") and self.cover_stage:
                self.cover_stage.ui_title = ""
                self.cover_stage.ui_status = "Añade o escanea tu carpeta de juegos desde el menú ⚙"
                self.cover_stage.ui_status_color = (100, 116, 139)
                self.cover_stage.ui_launch_disabled = True
                self.cover_stage.redraw()
            return

        game = self.games[index]
        title_str = game.get("name", "Juego")
        sub_str = self._get_game_subtitle(game)
        self.lbl_game_title.configure(text=title_str)
        if hasattr(self, "lbl_status") and self.lbl_status and not getattr(self, "_status_reset_job", None):
            self.lbl_status.configure(text=sub_str, text_color=COLOR_TEXT_MUTED)
        self.btn_launch.configure(state="normal")
        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.ui_title = title_str
            if not getattr(self, "_status_reset_job", None):
                self.cover_stage.ui_status = sub_str
                self.cover_stage.ui_status_color = (203, 213, 225)
            self.cover_stage.ui_launch_disabled = False
            self.cover_stage.redraw()

    # -------------------------------------------------------------
    # Orquestación de Ejecución (Delegación a GameExecutionService)
    # -------------------------------------------------------------
    def launch_current_game(self):
        if self.execution_service.is_launching:
            logger.warning("Lanzamiento ignorado: ya hay un juego iniciando.")
            return

        n = len(self.games)
        if n == 0 or self.selected_index >= n:
            return

        game = self.games[self.selected_index]
        try:
            from core.stats_service import increment_game_play_count
            from core.config import increment_game_launch_count_atomic
            from core.power_service import apply_game_performance_profile
            increment_game_play_count(game)
            increment_game_launch_count_atomic(game.get("path") or game.get("name", ""))
            apply_game_performance_profile(game)
        except Exception:
            pass

        self.btn_launch.configure(state="disabled")
        self.set_status(f"Iniciando {game['name']}...")

        close_on_launch = self.gamepad_config.get("close_on_game_launch", True)
        if close_on_launch:
            try:
                self.withdraw()
            except Exception:
                pass

        def status_cb(msg):
            self._action_queue.put(("status", msg))

        def on_success():
            self._action_queue.put(("launch_success", close_on_launch))

        def on_error(err_msg):
            self._action_queue.put(("launch_error", (err_msg, close_on_launch)))

        self.execution_service.launch(
            game,
            status_cb=status_cb,
            on_success_cb=on_success,
            on_error_cb=on_error
        )

    def _poll_action_queue(self):
        try:
            while True:
                action, payload = self._action_queue.get_nowait()
                if not self.winfo_exists():
                    return
                if action == "status":
                    self.set_status(payload)
                elif action == "launch_success":
                    if payload:
                        self.after(1200, self.close_application)
                    elif hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                        self.btn_launch.configure(state="normal")
                elif action == "launch_error":
                    err_msg, close_on_launch = payload
                    if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                        self.btn_launch.configure(state="normal")
                    if close_on_launch:
                        self._handle_launch_error(err_msg)
                    else:
                        self.set_status(f"Error iniciando juego: {err_msg}")
                        show_error("Error al Iniciar", f"No se pudo iniciar el juego:\n{err_msg}", parent=self)
                elif action == "callable" and callable(payload):
                    payload()
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"Error procesando cola de acciones UI: {e}")
        if self.winfo_exists():
            self.after(50, self._poll_action_queue)

    def _handle_launch_error(self, err_msg: str):
        self.execution_service.reset()
        if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
            self.btn_launch.configure(state="normal")
        self.restore_window()
        self.set_status(f"Error iniciando juego: {err_msg}")
        show_error("Error al Iniciar", f"No se pudo iniciar el juego:\n{err_msg}", parent=self)

    def set_status(self, msg: str):
        if hasattr(self, "lbl_status") and self.lbl_status:
            try:
                if getattr(self, "_status_reset_job", None):
                    try:
                        self.after_cancel(self._status_reset_job)
                    except Exception:
                        pass
                    self._status_reset_job = None
                self.lbl_status.configure(text=msg, text_color=COLOR_CYAN_ACCENT)
                if hasattr(self, "cover_stage") and self.cover_stage:
                    self.cover_stage.ui_status = msg
                    self.cover_stage.ui_status_color = (56, 189, 248)
                    self.cover_stage.redraw()

                def _restore_subtitle():
                    self._status_reset_job = None
                    if 0 <= self.selected_index < len(self.games):
                        sub_s = self._get_game_subtitle(self.games[self.selected_index])
                        self.lbl_status.configure(text=sub_s, text_color=COLOR_TEXT_DIM)
                        if hasattr(self, "cover_stage") and self.cover_stage:
                            self.cover_stage.ui_status = sub_s
                            self.cover_stage.ui_status_color = (203, 213, 225)
                            self.cover_stage.redraw()
                self._status_reset_job = self.after(4200, _restore_subtitle)
            except Exception:
                pass
        logger.info(msg)

    # -------------------------------------------------------------
    # Gestión de Estados de Ventana (Delegación a WindowStateService)
    # -------------------------------------------------------------
    def set_mini_mode(self):
        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            self.glass_menu.destroy()
            self.glass_menu = None
        self.window_manager.set_mini_mode(self.cover_stage, self.top_bar, self.bottom_panel)
        self._sync_controller_family_ui()

    def set_full_mode(self):
        self.window_manager.set_full_mode(self.cover_stage, self.top_bar, self.bottom_panel)
        self._sync_controller_family_ui()

    def toggle_size_mode(self):
        if self.is_mini_mode:
            self.set_full_mode()
        else:
            self.set_mini_mode()

    def toggle_fullscreen(self):
        self.toggle_size_mode()

    def minimize_window(self):
        self.window_manager.minimize_window()

    def minimize_to_taskbar(self):
        try:
            self.iconify()
        except Exception:
            pass

    def restore_window(self):
        self.window_manager.restore_window()
        self.refresh_games_from_disk_if_modified()

    def toggle_minimize(self):
        if self.is_minimized:
            self.restore_window()
        else:
            self.minimize_window()

    # -------------------------------------------------------------
    # Pila de Modales O(1) y Bucle de Mando (Delegación a GamepadNavigationService)
    # -------------------------------------------------------------
    def push_modal(self, modal):
        if modal not in self._modal_stack:
            self._modal_stack.append(modal)

    def pop_modal(self, modal):
        if modal in self._modal_stack:
            try:
                self._modal_stack.remove(modal)
            except ValueError:
                pass
        # Restaurar foco y captura (grab) al modal padre en la cima de la pila si existe
        top = self._get_topmost_active_modal()
        if top is not None and top != getattr(self, "glass_menu", None):
            try:
                top.grab_set()
                top.focus_force()
            except Exception:
                pass

    def _get_topmost_active_modal(self):
        while self._modal_stack:
            top = self._modal_stack[-1]
            try:
                if top.winfo_exists():
                    return top
            except Exception:
                pass
            self._modal_stack.pop()

        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            try:
                return self.glass_menu
            except Exception:
                pass
        return None

    def _start_gamepad_loop(self):
        self._gamepad_tick()

    def _gamepad_tick(self):
        # Programar el siguiente ciclo ANTES de ejecutar tick() para que bucles modales anidados
        # (wait_window en exploradores de carpetas ROMs/PC o cuadros de confirmación) jamás congelen el mando a 40 Hz
        if self.winfo_exists():
            self.after(25, self._gamepad_tick)
        target_id = self.gamepad_config.get("selected_controller_id", "any")
        enable_nav = self.gamepad_config.get("enable_controller_nav", True)
        self.gamepad_service.tick(target_id=target_id, enable_nav=enable_nav)

    def on_gamepad_connected(self, dev_name: str):
        self.set_status(f"🎮 {dev_name} conectado")
        if self.gamepad_config.get("auto_launch_on_connect", True):
            self.restore_window()
        if self.gamepad_config.get("start_in_mini_mode", True):
            if not self.is_mini_mode:
                self.set_mini_mode()
        elif self.gamepad_config.get("auto_fullscreen", True) and not self.is_fullscreen:
            self.set_full_mode()

    # -------------------------------------------------------------
    # Batería y Diálogos de Configuración
    # -------------------------------------------------------------
    def _poll_battery_status(self):
        try:
            from gamepad_manager import get_gamepad_battery_info
            info = get_gamepad_battery_info()
            if info.get("connected"):
                txt = f"{info['icon']} {info['text']}"
                lvl = info.get("level", "")
                if lvl == "empty":
                    t_color = COLOR_STATUS_DANGER
                    rgb_col = (255, 45, 85)
                elif lvl == "low":
                    t_color = COLOR_STATUS_WARNING
                    rgb_col = (255, 149, 0)
                elif info.get("is_wired") or lvl == "directinput":
                    t_color = COLOR_IOS_BLUE
                    rgb_col = (56, 189, 248)
                else:
                    t_color = COLOR_STATUS_SUCCESS
                    rgb_col = (52, 199, 89)
            else:
                txt = "🎮 Mando"
                t_color = COLOR_TEXT_DIM
                rgb_col = (100, 116, 139)

            sec = info.get("secondary") if info.get("connected") else None
            if sec and sec.get("connected"):
                if sec.get("is_wired"):
                    sec_txt = "USB"
                elif sec.get("level") in ("directinput", "unknown"):
                    sec_txt = "OK"
                else:
                    sec_txt = sec.get("text", "--")
                txt = f"{txt}  ·  2º {sec_txt}"

            if hasattr(self, "btn_battery") and self.btn_battery.winfo_exists():
                self.btn_battery.configure(text=txt, text_color=t_color)
            if hasattr(self, "cover_stage") and self.cover_stage:
                changed = (self.cover_stage.ui_battery_text != txt or self.cover_stage.ui_battery_color != rgb_col)
                self.cover_stage.ui_battery_text = txt
                self.cover_stage.ui_battery_color = rgb_col
                if changed and not getattr(self.cover_stage, "is_transparent_mode", False):
                    self.cover_stage.redraw()
        except Exception:
            pass
        self.refresh_games_from_disk_if_modified()
        self.after(4000, self._poll_battery_status)

    def _show_battery_info(self):
        from ui.dialogs import ControllerInfoDialog
        existing = getattr(self, "_controller_info_dialog", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_set()
                return
        except Exception:
            pass
        fam = getattr(self, "_current_controller_family", "xbox")
        self._controller_info_dialog = ControllerInfoDialog(self, family=fam)

    def open_cover_picker_for_selected_game(self, initial_mode: str = "cover"):
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            show_info("Carátula / Wallpaper", "No hay ningún juego seleccionado.", parent=self)
            return

        game = self.games[self.selected_index]
        game_name = game.get("name", "Juego")

        cur_cover_pil = None
        try:
            from PIL import Image
            c_path = resolve_game_cover(game)
            if c_path and os.path.isfile(c_path):
                with Image.open(c_path) as im:
                    cur_cover_pil = im.convert("RGBA").copy()
        except Exception:
            pass

        def _on_cover_chosen(new_cover_path: str):
            if new_cover_path and os.path.isfile(new_cover_path):
                game["cover"] = new_cover_path
                self.save_games()
                if hasattr(self, "cover_stage") and self.cover_stage:
                    self.cover_stage.update_game_cover(game)
                self.update_ui_details(self.selected_index)
                self.set_status(f"¡Carátula oficial actualizada para '{game_name}'!")

        def _on_wallpaper_chosen(new_wp_path: str, wp_opacity: float, wp_blur: float = 1.5):
            if new_wp_path and os.path.isfile(new_wp_path):
                game["wallpaper"] = new_wp_path
                game["wallpaper_opacity"] = round(float(wp_opacity), 2)
                game["wallpaper_blur"] = round(float(wp_blur), 2)
                self.save_games()
                if hasattr(self, "cover_stage") and self.cover_stage:
                    self.cover_stage.update_game_wallpaper(game)
                self.set_status(
                    f"¡Wallpaper 16:9 aplicado para '{game_name}' ({int(round(wp_opacity * 100))}% opacidad, desenfoque {wp_blur:.1f})!"
                )
            elif new_wp_path == "":
                game.pop("wallpaper", None)
                game.pop("wallpaper_opacity", None)
                game.pop("wallpaper_blur", None)
                self.save_games()
                if hasattr(self, "cover_stage") and self.cover_stage:
                    self.cover_stage.update_game_wallpaper(game)
                self.set_status(f"Wallpaper de fondo eliminado para '{game_name}'.")

        if hasattr(self, "_cover_picker_dialog") and self._cover_picker_dialog and self._cover_picker_dialog.winfo_exists():
            try:
                self._cover_picker_dialog.lift()
                self._cover_picker_dialog.focus_force()
            except Exception:
                pass
            return
        self._cover_picker_dialog = CoverPickerDialog(
            self,
            initial_query=game_name,
            game_name=game_name,
            on_selected_callback=_on_cover_chosen,
            initial_mode=initial_mode,
            on_wallpaper_selected_callback=_on_wallpaper_chosen,
            initial_wallpaper_opacity=float(game.get("wallpaper_opacity", 0.30)),
            initial_wallpaper_blur=float(game.get("wallpaper_blur", 1.8)),
            current_cover_pil=cur_cover_pil,
            current_wallpaper_path=game.get("wallpaper", "")
        )

    def open_external_import_dialog(self):
        self.close_active_menu()
        if hasattr(self, "_external_import_dialog") and self._external_import_dialog and self._external_import_dialog.winfo_exists():
            try:
                self._external_import_dialog.lift()
                self._external_import_dialog.focus_force()
            except Exception:
                pass
            return
        self._external_import_dialog = ExternalImportDialog(self, on_import_callback=self.on_games_imported, existing_games=self.games)

    def scan_folder_for_games(self):
        folder = browse_folder(parent=self, title="Seleccionar Carpeta de Juegos")
        if not folder:
            return

        folder_name = os.path.basename(os.path.abspath(folder)) or folder
        self.set_status(f"Escaneando '{folder_name}' en busca de juegos...")

        existing_paths = {
            os.path.normcase(os.path.abspath(g["path"]))
            for g in self.games if g.get("path")
        }

        scan_q = queue.Queue()

        def _scan_worker():
            candidates = scan_directory_for_games(folder, existing_paths=existing_paths)
            scan_q.put(candidates)

        def _poll_scan():
            try:
                candidates = scan_q.get_nowait()
                if not self.winfo_exists():
                    return
                if not candidates:
                    show_info(
                        "Escanear Carpeta",
                        f"No se encontraron ejecutables correspondientes a juegos en:\n{folder}\n\n"
                        "Consejo: Selecciona la carpeta donde tienes instalados tus juegos (por ej. C:/Juegos o la carpeta de un juego).",
                        parent=self
                    )
                    self.set_status("Escaneo finalizado sin juegos encontrados.")
                    return
                self.set_status(f"¡Se encontraron {len(candidates)} juegos en '{folder_name}'!")
                if hasattr(self, "_scan_results_dialog") and self._scan_results_dialog and self._scan_results_dialog.winfo_exists():
                    try:
                        self._scan_results_dialog.lift()
                        self._scan_results_dialog.focus_force()
                    except Exception:
                        pass
                    return
                self._scan_results_dialog = ScanResultsDialog(self, folder, candidates, on_import_callback=self.on_games_imported)
                return
            except queue.Empty:
                if self.winfo_exists():
                    self.after(50, _poll_scan)

        self.after(50, _poll_scan)
        threading.Thread(target=_scan_worker, daemon=True).start()

    def on_games_imported(self, new_games: List[Dict[str, Any]]):
        if not new_games:
            return
        initial_count = len(self.games)
        existing_map = {
            os.path.normcase(os.path.abspath(g["path"])): idx
            for idx, g in enumerate(self.games) if g.get("path")
        }
        added_count = 0
        updated_count = 0
        for ng in new_games:
            norm_p = os.path.normcase(os.path.abspath(ng.get("path", ""))) if ng.get("path") else ""
            if norm_p and norm_p in existing_map:
                idx = existing_map[norm_p]
                self.games[idx].update({k: v for k, v in ng.items() if v is not None and k != "already_added"})
                updated_count += 1
            else:
                self.games.append(ng)
                if norm_p:
                    existing_map[norm_p] = len(self.games) - 1
                added_count += 1

        self.save_games()
        invalidate_thumb_cache()
        target_idx = initial_count if initial_count < len(self.games) else 0
        self.cover_stage.set_games(self.games, target_index=target_idx)
        self.update_ui_details(target_idx)
        msg_parts = []
        if added_count > 0:
            msg_parts.append(f"{added_count} juego(s) añadido(s)")
        if updated_count > 0:
            msg_parts.append(f"{updated_count} actualizado(s)")
        self.set_status(f"Biblioteca: {', '.join(msg_parts) if msg_parts else 'Sin cambios'}.")

    def close_active_menu(self):
        """Cierra y destruye inmediatamente el menú contextual flotante si está abierto."""
        if hasattr(self, "glass_menu") and self.glass_menu:
            try:
                if self.glass_menu.winfo_exists():
                    self.glass_menu.destroy()
            except Exception:
                pass
            self.glass_menu = None

    def toggle_top_menu(self):
        # El menú de opciones solo está disponible en Modo Big Picture (Pantalla Completa)
        if getattr(self, "is_mini_mode", False):
            return

        if hasattr(self, "glass_menu") and self.glass_menu:
            self.close_active_menu()
            return

        cur_game = self.games[self.selected_index] if 0 <= self.selected_index < len(self.games) else None
        is_fav = bool(cur_game.get("favorite", False)) if cur_game else False
        fav_label = "Quitar de Favoritos (F)" if is_fav else "Marcar como Favorito (F)"
        fav_icon = "★" if is_fav else "☆"

        items = [
            (fav_icon, fav_label, self.toggle_current_game_favorite),
            ("⏱", "Estadísticas y Metas (S)...", self.open_game_stats_dialog),
            ("🏆", "Logros y Trofeos (Y)...", self.open_achievements_dialog),
            ("💾", "Copias de Seguridad (Save Backup)...", self.open_save_backup_dialog),
            ("☁️", "Sincronización en la Nube (Cloud Sync)...", self.open_cloud_sync_dialog),
            ("🏷", "Colecciones y Filtros (LB/RB)...", self.open_collections_dialog),
            ("🎛️", "Modos de Rendimiento y Energía (P)...", self.open_performance_dialog),
            ("🪟", "In-Game Overlay (Reloj / Batería / Volumen)...", self.open_in_game_overlay),
            ("🚀", "Importar Juegos...", self.open_external_import_dialog),
            ("🎨", "Descargar Arte Masivo (SteamGridDB)...", self.open_batch_steamgriddb_dialog),
            ("📋", "Administrar Todos los Juegos...", self.open_select_game_dialog),
            ("🎮", "Configurar Mando...", self.open_gamepad_config_dialog),
        ]
        self.glass_menu = FloatingGlassMenu(self, self.btn_menu, items)

    def open_batch_steamgriddb_dialog(self):
        self.close_active_menu()
        if hasattr(self, "_batch_sgdb_dialog") and self._batch_sgdb_dialog and self._batch_sgdb_dialog.winfo_exists():
            try:
                self._batch_sgdb_dialog.lift()
                self._batch_sgdb_dialog.focus_force()
            except Exception:
                pass
            return
        if not self.games:
            show_info(
                "SteamGridDB",
                "No hay juegos en la biblioteca para actualizar.\nUsa 'Importar Juegos...' primero.",
                parent=self
            )
            return

        def _on_batch_complete():
            invalidate_thumb_cache()
            self.save_games()
            self.cover_stage.set_games(self.games, target_index=self.selected_index)
            self.update_ui_details(self.selected_index)
            self.set_status(f"Arte actualizado con éxito desde SteamGridDB ({len(self.games)} juegos).")

        self._batch_sgdb_dialog = BatchSteamGridDBDialog(
            self,
            self.games,
            on_complete_callback=_on_batch_complete
        )

    def _on_global_click(self, event):
        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            try:
                mx = self.glass_menu.winfo_rootx()
                my = self.glass_menu.winfo_rooty()
                mw = self.glass_menu.winfo_width()
                mh = self.glass_menu.winfo_height()
                if (mx <= event.x_root <= mx + mw and my <= event.y_root <= my + mh):
                    return

                if hasattr(self, "btn_menu") and self.btn_menu and self.btn_menu.winfo_exists():
                    bx = self.btn_menu.winfo_rootx()
                    by = self.btn_menu.winfo_rooty()
                    bw = self.btn_menu.winfo_width()
                    bh = self.btn_menu.winfo_height()
                    if (bx <= event.x_root <= bx + bw and by <= event.y_root <= by + bh):
                        return

                stage = getattr(self, "cover_stage", None)
                if stage is not None and getattr(stage, "hud_hitboxes", None) and stage.winfo_exists():
                    sx = stage.winfo_rootx()
                    sy = stage.winfo_rooty()
                    for (hx1, hy1, hx2, hy2, hact) in stage.hud_hitboxes:
                        if hact == "menu" and (sx + hx1 <= event.x_root <= sx + hx2 and sy + hy1 <= event.y_root <= sy + hy2):
                            return

                self.close_active_menu()
            except Exception:
                self.close_active_menu()

    def open_gamepad_config_dialog(self):
        self.close_active_menu()
        if hasattr(self, "_gamepad_dialog") and self._gamepad_dialog and self._gamepad_dialog.winfo_exists():
            try:
                self._gamepad_dialog.lift()
                self._gamepad_dialog.focus_force()
            except Exception:
                pass
            return
        self._gamepad_dialog = GamepadConfigDialog(self, on_save_callback=self.on_gamepad_config_saved)

    def on_gamepad_config_saved(self, new_cfg):
        self.gamepad_config = new_cfg
        self._sync_controller_family_ui(force=True)
        dev_label = new_cfg.get("selected_controller_name", "Mando")
        self.set_status(f"Mando configurado: {dev_label}")

    def open_add_dialog(self):
        self.close_active_menu()
        if hasattr(self, "_add_dialog") and self._add_dialog and self._add_dialog.winfo_exists():
            try:
                self._add_dialog.lift()
                self._add_dialog.focus_force()
            except Exception:
                pass
            return
        self.monitors = get_monitors()
        self._add_dialog = AddEditGameDialog(self, self.monitors, callback=self.on_game_added)

    def open_select_game_dialog(self):
        self.close_active_menu()
        if hasattr(self, "_select_dialog") and self._select_dialog and self._select_dialog.winfo_exists():
            try:
                self._select_dialog.lift()
                self._select_dialog.focus_force()
            except Exception:
                pass
            return
        if not self.library.games:
            show_info(
                "Editar Juego",
                "No hay juegos registrados en la biblioteca.\nUsa '＋ Agregar Juego' o '📁 Escanear Carpeta' para añadir juegos primero.",
                parent=self
            )
            return
        self._select_dialog = SelectGameToEditDialog(
            self,
            self.library.games,
            on_select_callback=self.open_edit_for_game_index,
            initial_index=self._get_library_index_for_game(self.games[self.selected_index]) if self.games else 0,
            on_library_changed=lambda games: self.apply_filter(self.current_filter_id, keep_selection=True),
        )

    def open_edit_for_game_index(self, index: int, return_callback=None):
        if index < 0 or index >= len(self.library.games):
            if return_callback:
                return_callback()
            return
        self.monitors = get_monitors()
        game = self.library.games[index]
        AddEditGameDialog(
            self,
            self.monitors,
            game_data=game,
            callback=lambda name, path, mon, hp, cov, args="", wp=None, wpo=None, wpb=None, fav=False, st="Por jugar", gen="", plat="PC": self.on_specific_game_edited(index, name, path, mon, hp, cov, args, wp, wpo, wpb, fav, st, gen, plat),
            delete_callback=lambda: self.delete_specific_game(index, confirm=False),
            on_close_callback=return_callback
        )

    def open_edit_dialog(self):
        self.open_select_game_dialog()

    def on_game_added(
        self, name, path, monitor, high_priority, cover, launch_args: str = "",
        wallpaper: Optional[str] = None, wallpaper_opacity: Optional[float] = None, wallpaper_blur: Optional[float] = None,
        favorite: bool = False, status: str = "Por jugar", genre: str = "", platform: str = "PC"
    ):
        new_index = self.library.add_game(
            name, path, monitor, high_priority, cover, launch_args,
            wallpaper=wallpaper, wallpaper_opacity=wallpaper_opacity, wallpaper_blur=wallpaper_blur,
            favorite=favorite, status=status, genre=genre, platform=platform
        )
        invalidate_thumb_cache()
        self.apply_filter(self.current_filter_id, keep_selection=False)
        self.set_status(f"Juego '{name}' añadido con éxito.")

    def on_specific_game_edited(
        self, index: int, name: str, path: str, monitor: int, high_priority: bool, cover: str, launch_args: str = "",
        wallpaper: Optional[str] = None, wallpaper_opacity: Optional[float] = None, wallpaper_blur: Optional[float] = None,
        favorite: Optional[bool] = None, status: Optional[str] = None, genre: Optional[str] = None, platform: Optional[str] = None
    ):
        if self.library.update_game(
            index, name, path, monitor, high_priority, cover, launch_args,
            wallpaper=wallpaper, wallpaper_opacity=wallpaper_opacity, wallpaper_blur=wallpaper_blur,
            favorite=favorite, status=status, genre=genre, platform=platform
        ):
            invalidate_thumb_cache()
            self.apply_filter(self.current_filter_id, keep_selection=True)
            self.set_status(f"Juego '{name}' actualizado.")

    def on_game_edited(self, name, path, monitor, high_priority, cover, launch_args: str = "", wallpaper: Optional[str] = None, wallpaper_opacity: Optional[float] = None, wallpaper_blur: Optional[float] = None):
        target_game = self.games[self.selected_index] if 0 <= self.selected_index < len(self.games) else None
        real_idx = self._get_library_index_for_game(target_game) if target_game else self.selected_index
        self.on_specific_game_edited(real_idx, name, path, monitor, high_priority, cover, launch_args, wallpaper=wallpaper, wallpaper_opacity=wallpaper_opacity, wallpaper_blur=wallpaper_blur)

    def delete_specific_game(self, index: int, confirm: bool = False):
        if index < 0 or index >= len(self.library.games):
            return
        game = self.library.games[index]
        if not confirm or ask_yes_no("Eliminar Juego", f"¿Estás seguro de que deseas eliminar '{game['name']}' de la biblioteca?", parent=self, confirm_text="Eliminar", is_destructive=True):
            self.library.delete_game(index)
            invalidate_thumb_cache()
            self.apply_filter(self.current_filter_id, keep_selection=False)
            self.set_status(f"Juego '{game['name']}' eliminado.")

    def delete_current_game(self, confirm: bool = True):
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return
        cur_game = self.games[self.selected_index]
        real_idx = self._get_library_index_for_game(cur_game)
        self.delete_specific_game(real_idx, confirm=confirm)

    def refresh_monitors(self):
        self.monitors = get_monitors(force_refresh=True)
        self.update_ui_details(self.selected_index)
        self.set_status(f"Monitores detectados: {len(self.monitors)}")

    def open_exit_dialog(self):
        self.close_active_menu()
        if hasattr(self, "exit_dialog") and self.exit_dialog and self.exit_dialog.winfo_exists():
            try:
                bring_to_front_absolute(self.exit_dialog)
            except Exception:
                pass
            return
        if self.is_minimized:
            self.restore_window()
        self.exit_dialog = ConfirmExitDialog(self, on_confirm=self.close_application)
        bring_to_front_absolute(self.exit_dialog)

    def close_application(self):
        try:
            from core.power_service import restore_previous_performance_profile
            restore_previous_performance_profile()
        except Exception:
            pass
        try:
            ensure_watcher_running()
        except Exception:
            pass
        time.sleep(0.15)
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)
