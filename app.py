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
from core.library_service import GameLibraryService, format_monitor_label
from core.execution_service import GameExecutionService
from ui.window_manager import WindowStateService
from ui.gamepad_service import GamepadNavigationService
from ui.modal_manager import register_modal_stack, unregister_modal_stack

from ui.theme import bring_to_front_absolute, COLOR_BG_DARK
from ui.coverflow_canvas import CoverFlowCanvas
from ui.dropdowns import FloatingGlassMenu
from ui.dialogs import (
    AddEditGameDialog, SelectGameToEditDialog,
    GamepadConfigDialog, ConfirmExitDialog, CoverPickerDialog,
    ExternalImportDialog, BatchSteamGridDBDialog, CollectionsFilterDialog,
    KioskDialog,
    invalidate_thumb_cache, show_info, show_error, ask_yes_no
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

        # Cargar colección de juegos en memoria y preparar estanterías multi-carrusel
        self.library.load()
        self.current_filter_id = "all"
        self.available_filters = self.library.get_available_filters()
        self.active_shelves: List[Dict[str, Any]] = []
        self.current_shelf_idx: int = 0
        self._shelf_selected_indices: Dict[str, int] = {}
        self.games = self.library.games
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
        self.refresh_shelves(keep_selection=False)
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
            self.refresh_shelves(keep_selection=True)
        return res

    def _get_library_index_for_game(self, game: Optional[Dict[str, Any]]) -> int:
        """Resuelve el índice absoluto de un juego en la colección global library.games."""
        if not game:
            return 0
        for idx, lg in enumerate(self.library.games):
            if lg is game:
                return idx
        gp = game.get("path")
        norm_gp = os.path.normcase(os.path.abspath(gp)) if gp else ""
        if gp:
            for idx, lg in enumerate(self.library.games):
                lp = lg.get("path")
                if lp == gp or (lp and os.path.normcase(os.path.abspath(lp)) == norm_gp):
                    return idx
        gn = (game.get("name") or "").strip().lower()
        if gn:
            for idx, lg in enumerate(self.library.games):
                if (lg.get("name") or "").strip().lower() == gn:
                    return idx
        return 0

    def refresh_shelves(self, keep_selection: bool = True, transition_direction: int = 0):
        """Actualiza las estanterías del dashboard cargando la configuración y asigna el carrusel activo."""
        from core.collections_service import get_active_shelves
        prev_game = self.games[self.selected_index] if (hasattr(self, "games") and self.games and 0 <= self.selected_index < len(self.games)) else None
        self.active_shelves = get_active_shelves(self.library.games)

        if not self.active_shelves:
            all_sorted = sorted(self.library.games, key=lambda g: (g.get("name") or "").lower())
            self.active_shelves = [{
                "id": "all",
                "name": "Todos los Juegos",
                "icon": "🎮",
                "enabled": True,
                "count": len(all_sorted),
                "games": all_sorted
            }]

        prev_filter_id = getattr(self, "current_filter_id", None)
        if prev_filter_id:
            for s_idx, sh in enumerate(self.active_shelves):
                if sh.get("id") == prev_filter_id:
                    self.current_shelf_idx = s_idx
                    break

        if self.current_shelf_idx >= len(self.active_shelves):
            self.current_shelf_idx = 0

        cur_shelf = self.active_shelves[self.current_shelf_idx]
        self.games = cur_shelf["games"]
        self.current_filter_id = cur_shelf["id"]

        new_idx = 0
        if keep_selection and prev_game:
            pg_path = prev_game.get("path")
            pg_name = (prev_game.get("name") or "").strip().lower()
            for i, g in enumerate(self.games):
                if (pg_path and g.get("path") == pg_path) or (pg_name and (g.get("name") or "").strip().lower() == pg_name):
                    new_idx = i
                    break
        else:
            new_idx = self._shelf_selected_indices.get(cur_shelf["id"], 0)

        new_idx = max(0, min(new_idx, len(self.games) - 1)) if self.games else 0
        self.selected_index = new_idx

        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.ui_shelf_index = self.current_shelf_idx
            self.cover_stage.ui_total_shelves = len(self.active_shelves)
            self.cover_stage.ui_filter_label = cur_shelf["name"]
            self.cover_stage.ui_filter_count = len(self.games)
            self.cover_stage.set_shelves_context(
                self.active_shelves,
                self.current_shelf_idx,
                self._shelf_selected_indices,
            )
            self.cover_stage.set_games(self.games, target_index=self.selected_index, transition_direction=transition_direction)

        self.update_ui_details(self.selected_index)

    def cycle_shelf(self, direction: int):
        """
        Navega verticalmente entre los carruseles/listas de juegos habilitadas (↑ / ↓).
        Si solo hay 1 lista habilitada, no cambia de fila (tal como especificó el usuario).
        """
        if len(self.active_shelves) <= 1:
            return

        cur_shelf_id = self.active_shelves[self.current_shelf_idx]["id"]
        self._shelf_selected_indices[cur_shelf_id] = self.selected_index

        self.current_shelf_idx = (self.current_shelf_idx + direction) % len(self.active_shelves)
        try:
            from core.feedback import feedback_click, trigger_haptic
            feedback_click()
            trigger_haptic()
        except Exception:
            pass

        new_shelf = self.active_shelves[self.current_shelf_idx]
        self.games = new_shelf["games"]
        self.current_filter_id = new_shelf["id"]

        target_h = self._shelf_selected_indices.get(new_shelf["id"], 0)
        self.selected_index = max(0, min(target_h, len(self.games) - 1)) if self.games else 0

        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.ui_shelf_index = self.current_shelf_idx
            self.cover_stage.ui_total_shelves = len(self.active_shelves)
            self.cover_stage.ui_filter_label = new_shelf["name"]
            self.cover_stage.ui_filter_count = len(self.games)
            self.cover_stage.set_shelves_context(
                self.active_shelves,
                self.current_shelf_idx,
                self._shelf_selected_indices,
            )
            self.cover_stage._defer_redraw = True
            try:
                self.update_ui_details(self.selected_index)
                self.set_status(f"Fila {self.current_shelf_idx + 1}/{len(self.active_shelves)}: {new_shelf.get('icon', '')} {new_shelf['name']} ({len(self.games)} juegos)")
            finally:
                self.cover_stage._defer_redraw = False
            self.cover_stage.set_games(self.games, target_index=self.selected_index, transition_direction=direction)
        else:
            self.update_ui_details(self.selected_index)
            self.set_status(f"Fila {self.current_shelf_idx + 1}/{len(self.active_shelves)}: {new_shelf.get('icon', '')} {new_shelf['name']} ({len(self.games)} juegos)")

    def cycle_filter(self, direction: int):
        """Alias para cambiar de estantería verticalmente con LB/RB o atajos de hombros."""
        self.cycle_shelf(direction)

    def apply_filter(self, filter_id: str, keep_selection: bool = True):
        """Aplica un filtro o selecciona la estantería correspondiente en el dashboard."""
        old_idx = self.current_shelf_idx
        for idx, shelf in enumerate(self.active_shelves):
            if shelf["id"] == filter_id:
                direction = 1 if idx > old_idx else (-1 if idx < old_idx else 0)
                self.current_shelf_idx = idx
                self.current_filter_id = filter_id
                self.refresh_shelves(keep_selection=keep_selection, transition_direction=direction)
                return
        # Si no está en las estanterías activas, recargar estanterías
        self.current_filter_id = filter_id
        self.refresh_shelves(keep_selection=keep_selection)

    def _open_or_focus_dialog(self, attr_name: str, factory, use_bring_to_front: bool = False):
        """Garantiza instancia única por diálogo modal, trayendo al frente la existente si sigue abierta."""
        self.close_active_menu()
        existing = getattr(self, attr_name, None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    if use_bring_to_front:
                        bring_to_front_absolute(existing)
                    else:
                        existing.lift()
                        existing.focus_force()
                    return existing
            except Exception:
                pass
        dlg = factory()
        setattr(self, attr_name, dlg)
        return dlg

    def _on_game_metadata_updated(self, _updated_game=None):
        self.save_games()
        self.cover_stage.set_games(self.games, target_index=self.selected_index)
        self.update_ui_details(self.selected_index)

    def open_collections_dialog(self):
        """Abre el diálogo modal de configuración de estanterías y filtros del dashboard."""
        cur_shelf_id = self.active_shelves[self.current_shelf_idx]["id"] if self.active_shelves else "all"
        self._open_or_focus_dialog(
            "_collections_dialog",
            lambda: CollectionsFilterDialog(
                self,
                all_games=self.library.games,
                current_shelf_id=cur_shelf_id,
                on_shelves_updated=lambda: self.refresh_shelves(keep_selection=True)
            ),
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
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return
        game = self.games[self.selected_index]

        def _create():
            from ui.dialogs.game_stats_dialog import GameStatsDialog
            return GameStatsDialog(parent=self, game=game, on_game_updated=self._on_game_metadata_updated)

        self._open_or_focus_dialog("_stats_dialog", _create)

    def open_save_backup_dialog(self):
        """Abre la pantalla de copias de seguridad y restauración de partidas guardadas para el juego actual."""
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return
        game = self.games[self.selected_index]

        def _create():
            from ui.dialogs.save_backup_dialog import SaveBackupDialog
            return SaveBackupDialog(parent=self, game=game, on_game_updated=self._on_game_metadata_updated)

        self._open_or_focus_dialog("_backup_dialog", _create)

    def open_performance_dialog(self):
        """Abre el panel de Modos de Rendimiento y Energía (Handheld Mode / Perfiles de Batería)."""
        game = self.games[self.selected_index] if (self.games and 0 <= self.selected_index < len(self.games)) else None

        def _create():
            from ui.dialogs.performance_dialog import PerformanceProfileDialog
            return PerformanceProfileDialog(parent=self, game=game, on_game_updated=self._on_game_metadata_updated)

        self._open_or_focus_dialog("_perf_dialog", _create)

    def open_cloud_sync_dialog(self):
        """Abre el panel de Sincronización de Partidas en la Nube (Cloud Save Sync)."""
        def _create():
            from ui.dialogs.cloud_sync_dialog import CloudSyncDialog
            return CloudSyncDialog(
                parent=self,
                games=self.library.games,
                on_sync_completed=lambda: self.update_ui_details(self.selected_index)
            )

        self._open_or_focus_dialog("_cloud_sync_dialog", _create)

    def open_achievements_dialog(self):
        """Abre el panel de Logros y Trofeos (Steam & RetroAchievements) para el juego seleccionado."""
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            return
        game = self.games[self.selected_index]

        def _create():
            from ui.dialogs.achievements_dialog import AchievementsDialog
            return AchievementsDialog(parent=self, game=game, on_game_updated=self._on_game_metadata_updated)

        self._open_or_focus_dialog("_achievements_dialog", _create)

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
        self.grid_rowconfigure(0, weight=1)

        self._current_controller_family = get_connected_controller_family(self.gamepad_config)
        # Widgets de respaldo ocultos (sin mapear) por compatibilidad con anclas de menú y tests
        self.btn_menu = ctk.CTkButton(self, text="⚙", width=1, height=1, command=self.toggle_top_menu)
        self.btn_launch = ctk.CTkButton(self, text="▶", width=1, height=1, command=self.launch_current_game)

        # Escenario Central Cover Flow 3D + HUD RGBA superpuesto
        self.cover_stage = CoverFlowCanvas(
            self,
            on_selection_changed=self.on_cover_selected,
            on_launch_requested=self.launch_current_game,
            on_hud_action=self._on_canvas_hud_action,
            on_shelf_step=self.cycle_shelf
        )
        self.cover_stage.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self._status_reset_job = None

        self._sync_controller_family_ui(force=True)

        # Cargar juegos en el Cover Flow
        self.cover_stage.set_games(self.games, target_index=0)
        self.update_ui_details(0)

    def bind_events(self):
        self.bind("<Left>", lambda e: self.cover_stage.prev_cover())
        self.bind("<Right>", lambda e: self.cover_stage.next_cover())
        self.bind("<Up>", lambda e: self.cycle_shelf(-1))
        self.bind("<Down>", lambda e: self.cycle_shelf(1))
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
        self.bind("<t>", lambda e: self.open_achievements_dialog())
        self.bind("<T>", lambda e: self.open_achievements_dialog())
        self.bind("<Configure>", self._on_window_configure, add="+")

    def on_cover_selected(self, index: int):
        self.selected_index = index
        if getattr(self, "active_shelves", None) and 0 <= self.current_shelf_idx < len(self.active_shelves):
            cur_sid = self.active_shelves[self.current_shelf_idx].get("id")
            if cur_sid is not None:
                self._shelf_selected_indices[cur_sid] = index
        self.update_ui_details(index)

    def _on_canvas_hud_action(self, action: str):
        if action == "menu":
            if not getattr(self, "is_mini_mode", False):
                self.toggle_top_menu()
        elif action == "battery":
            self._show_battery_info()
        elif action == "launch":
            self.launch_current_game()
        elif action in ("filter_prev", "shelf_prev"):
            self.cycle_shelf(-1)
        elif action in ("filter_next", "shelf_next"):
            self.cycle_shelf(1)
        elif action == "filter_menu":
            self.open_filter_dropdown_menu()
        elif action == "start":
            self.toggle_size_mode()
        elif action == "select":
            self.toggle_minimize()
        elif action == "exit":
            self.open_exit_dialog()

    def _sync_controller_family_ui(self, force: bool = False):
        """Actualiza dinámicamente los glifos de mando del HUD según el controlador conectado."""
        try:
            fam = get_connected_controller_family(self.gamepad_config)
        except Exception:
            fam = "xbox"

        if not force and fam == getattr(self, "_current_controller_family", None):
            return

        self._current_controller_family = fam
        if hasattr(self, "cover_stage") and self.cover_stage:
            prev_fam = getattr(self.cover_stage, "controller_family", None)
            self.cover_stage.controller_family = fam
            if prev_fam != fam or force:
                self.cover_stage.redraw()

    def update_ui_details(self, index: int):
        n = len(self.games)
        if n == 0 or index >= n:
            if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                self.btn_launch.configure(state="disabled")
            if hasattr(self, "cover_stage") and self.cover_stage:
                self.cover_stage.ui_title = ""
                self.cover_stage.ui_status = "Añade o escanea tu carpeta de juegos desde el menú ⚙"
                self.cover_stage.ui_status_color = (100, 116, 139)
                self.cover_stage.ui_launch_disabled = True
                if not getattr(self.cover_stage, "_defer_redraw", False):
                    self.cover_stage.redraw()
            return

        game = self.games[index]
        title_str = game.get("name", "Juego")
        sub_str = self._get_game_subtitle(game)
        if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
            self.btn_launch.configure(state="normal")
        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.ui_title = title_str
            if not getattr(self, "_status_reset_job", None):
                self.cover_stage.ui_status = sub_str
                self.cover_stage.ui_status_color = (203, 213, 225)
            self.cover_stage.ui_launch_disabled = False
            if not getattr(self.cover_stage, "_defer_redraw", False):
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
        game_path = game.get("path", "")
        if game_path and os.path.exists(game_path):
            try:
                from core.stats_service import increment_game_play_count
                from core.config import increment_game_launch_count_atomic
                from core.power_service import apply_game_performance_profile
                increment_game_play_count(game)
                increment_game_launch_count_atomic(game_path or game.get("name", ""))
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
        deferred_callables = []
        seen_callable_ids = set()
        try:
            processed = 0
            while processed < 32:
                action, payload = self._action_queue.get_nowait()
                processed += 1
                if not self.winfo_exists():
                    return
                if action == "status":
                    self.set_status(payload)
                elif action == "launch_success":
                    if payload:
                        self.after(1200, lambda: self.close_application(from_game_launch=True))
                    elif hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                        self.btn_launch.configure(state="normal")
                elif action == "launch_error":
                    err_msg, close_on_launch = payload
                    try:
                        from core.power_service import restore_previous_performance_profile
                        restore_previous_performance_profile()
                    except Exception:
                        pass
                    if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                        self.btn_launch.configure(state="normal")
                    if close_on_launch:
                        self._handle_launch_error(err_msg)
                    else:
                        self.set_status(f"Error iniciando juego: {err_msg}")
                        show_error("Error al Iniciar", f"No se pudo iniciar el juego:\n{err_msg}", parent=self)
                elif action == "callable" and callable(payload):
                    pid = id(payload)
                    if pid not in seen_callable_ids:
                        seen_callable_ids.add(pid)
                        deferred_callables.append(payload)
        except queue.Empty:
            pass
        except Exception as e:
            logger.error(f"Error procesando cola de acciones UI: {e}")

        for fn in deferred_callables:
            try:
                if not self.winfo_exists():
                    return
                fn()
            except Exception as e:
                logger.error(f"Error ejecutando acción en cola UI: {e}")

        if self.winfo_exists():
            self.after(50, self._poll_action_queue)

    def _handle_launch_error(self, err_msg: str):
        try:
            from core.power_service import restore_previous_performance_profile
            restore_previous_performance_profile()
        except Exception:
            pass
        self.execution_service.reset()
        if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
            self.btn_launch.configure(state="normal")
        self.restore_window()
        self.set_status(f"Error iniciando juego: {err_msg}")
        show_error("Error al Iniciar", f"No se pudo iniciar el juego:\n{err_msg}", parent=self)

    def set_status(self, msg: str):
        if hasattr(self, "cover_stage") and self.cover_stage:
            try:
                if getattr(self, "_status_reset_job", None):
                    try:
                        self.after_cancel(self._status_reset_job)
                    except Exception:
                        pass
                    self._status_reset_job = None
                self.cover_stage.ui_status = msg
                self.cover_stage.ui_status_color = (56, 189, 248)
                if not getattr(self.cover_stage, "_defer_redraw", False):
                    self.cover_stage.redraw()

                def _restore_subtitle():
                    self._status_reset_job = None
                    if 0 <= self.selected_index < len(self.games):
                        sub_s = self._get_game_subtitle(self.games[self.selected_index])
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
        self.close_active_menu()
        self.window_manager.set_mini_mode(self.cover_stage)
        self._sync_controller_family_ui()

    def set_full_mode(self):
        self.window_manager.set_full_mode(self.cover_stage)
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
                    rgb_col = (255, 45, 85)
                elif lvl == "low":
                    rgb_col = (255, 149, 0)
                elif info.get("is_wired") or lvl == "directinput":
                    rgb_col = (56, 189, 248)
                else:
                    rgb_col = (52, 199, 89)
            else:
                txt = "🎮 Mando"
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
        def _create():
            from ui.dialogs import ControllerInfoDialog
            fam = getattr(self, "_current_controller_family", "xbox")
            return ControllerInfoDialog(self, family=fam)

        self._open_or_focus_dialog("_controller_info_dialog", _create)

    def open_cover_picker_for_selected_game(self, initial_mode: str = "cover"):
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            show_info("Carátula / Wallpaper", "No hay ningún juego seleccionado.", parent=self)
            return

        game = self.games[self.selected_index]
        game_name = game.get("name", "Juego")

        def _create():
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

            return CoverPickerDialog(
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

        self._open_or_focus_dialog("_cover_picker_dialog", _create)

    def open_external_import_dialog(self):
        self._open_or_focus_dialog(
            "_external_import_dialog",
            lambda: ExternalImportDialog(self, on_import_callback=self.on_games_imported, existing_games=self.library.games),
        )

    def _focus_game_in_shelves(self, target_game: Optional[Dict[str, Any]]) -> None:
        """Asegura que el juego dado sea visible y quede seleccionado en el carrusel activo."""
        if not target_game:
            return
        t_path = target_game.get("path")
        t_name = (target_game.get("name") or "").strip().lower()

        def _find_in(games_list: List[Dict[str, Any]]) -> Optional[int]:
            for idx, g in enumerate(games_list):
                if (t_path and g.get("path") == t_path) or (t_name and (g.get("name") or "").strip().lower() == t_name):
                    return idx
            return None

        found_idx = _find_in(self.games)
        if found_idx is None and getattr(self, "active_shelves", None):
            for s_idx, shelf in enumerate(self.active_shelves):
                if shelf.get("id") == "all":
                    self.current_shelf_idx = s_idx
                    self.current_filter_id = "all"
                    self.refresh_shelves(keep_selection=False)
                    found_idx = _find_in(self.games)
                    break

        if found_idx is not None:
            self.selected_index = found_idx
            if getattr(self, "current_filter_id", None):
                self._shelf_selected_indices[self.current_filter_id] = found_idx
            if hasattr(self, "cover_stage") and self.cover_stage:
                self.cover_stage.set_games(self.games, target_index=found_idx)
            self.update_ui_details(found_idx)

    def on_games_imported(self, new_games: List[Dict[str, Any]]):
        if not new_games:
            return
        added_count, updated_count, first_game = self.library.import_games(new_games)
        invalidate_thumb_cache()
        self.refresh_shelves(keep_selection=False)
        self._focus_game_in_shelves(first_game)
        msg_parts = []
        if added_count > 0:
            msg_parts.append(f"{added_count} juego(s) añadido(s)")
        if updated_count > 0:
            msg_parts.append(f"{updated_count} actualizado(s)")
        self.set_status(f"Biblioteca: {', '.join(msg_parts) if msg_parts else 'Sin cambios'}.")

    def close_active_menu(self):
        """Cierra y destruye inmediatamente el menú contextual flotante si está abierto."""
        self._last_menu_kind = ""
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
            was_options = (getattr(self, "_last_menu_kind", "options") == "options")
            self.close_active_menu()
            if was_options:
                return

        cur_game = self.games[self.selected_index] if 0 <= self.selected_index < len(self.games) else None
        cur_name = (cur_game.get("name") or "").strip() if cur_game else ""
        short_name = cur_name if len(cur_name) <= 16 else (cur_name[:15].rstrip() + "…")
        edit_label = f"Editar Juego ({short_name})..." if short_name else "Editar Juego..."
        is_fav = bool(cur_game.get("favorite", False)) if cur_game else False
        fav_label = "Quitar de Favoritos (F)" if is_fav else "Marcar como Favorito (F)"
        fav_icon = "★" if is_fav else "☆"

        items = [
            # Bloque 1: Juego Actual
            ("✏️", edit_label, self.open_edit_current_game_dialog),
            (fav_icon, fav_label, self.toggle_current_game_favorite),
            ("⏱", "Estadísticas y Metas (S)...", self.open_game_stats_dialog),
            ("🏆", "Logros y Trofeos (Tecla Y)...", self.open_achievements_dialog),
            ("💾", "Copias de Seguridad (C)...", self.open_save_backup_dialog),
            # Bloque 2: Biblioteca
            ("＋", "Añadir Juego Manualmente...", self.open_add_dialog),
            ("🚀", "Importar Juegos...", self.open_external_import_dialog),
            ("🎨", "Descargar Arte Masivo (SteamGridDB)...", self.open_batch_steamgriddb_dialog),
            ("📋", "Administrar Todos los Juegos...", self.open_select_game_dialog),
            # Bloque 3: Sistema y Consola
            ("☁️", "Sincronización en la Nube (Cloud Sync)...", self.open_cloud_sync_dialog),
            ("🎛️", "Modos de Rendimiento y Energía (P)...", self.open_performance_dialog),
            ("📺", "Modo Kiosco / Consola Dedicada...", self.open_kiosk_dialog),
            ("🎮", "Configurar Mando...", self.open_gamepad_config_dialog),
        ]
        self.glass_menu = FloatingGlassMenu(self, self.btn_menu, items)
        self._last_menu_kind = "options"

    def open_filter_dropdown_menu(self):
        """Abre el desplegable rápido de filtros y estanterías debajo de la píldora activa."""
        if getattr(self, "is_mini_mode", False):
            return

        if hasattr(self, "glass_menu") and self.glass_menu:
            was_filter = (getattr(self, "_last_menu_kind", "") == "filter")
            self.close_active_menu()
            if was_filter:
                return

        shelves = getattr(self, "active_shelves", None) or []
        cur_idx = getattr(self, "current_shelf_idx", 0)
        items = []
        for idx, shelf in enumerate(shelves):
            is_cur = (idx == cur_idx)
            icon = "✓" if is_cur else "•"
            cnt = len(shelf.get("games", []))
            name = shelf.get("name", "Estantería")
            sid = shelf.get("id", "all")
            items.append((icon, f"{name} ({cnt})", lambda s=sid: self.apply_filter(s)))
        items.append(("🏷", "Organizar estanterías y filtros...", self.open_collections_dialog))

        self.glass_menu = FloatingGlassMenu(self, None, items, anchor_hud_action="filter_menu")
        self._last_menu_kind = "filter"
        if items and hasattr(self.glass_menu, "_update_highlight"):
            self.glass_menu.selected_index = min(max(0, cur_idx), len(items) - 1)
            self.glass_menu._update_highlight()

    def open_kiosk_dialog(self):
        self._open_or_focus_dialog("_kiosk_dialog", lambda: KioskDialog(self))

    def open_batch_steamgriddb_dialog(self):
        def _create():
            if not self.library.games:
                show_info(
                    "SteamGridDB",
                    "No hay juegos en la biblioteca para actualizar.\nUsa 'Importar Juegos...' primero.",
                    parent=self
                )
                return None

            def _on_batch_complete():
                invalidate_thumb_cache()
                self.save_games()
                self.refresh_shelves(keep_selection=True)
                self.set_status(f"Arte actualizado con éxito desde SteamGridDB ({len(self.library.games)} juegos).")

            return BatchSteamGridDBDialog(
                self,
                self.library.games,
                on_complete_callback=_on_batch_complete
            )

        self._open_or_focus_dialog("_batch_sgdb_dialog", _create)

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
                        if hact in ("menu", "filter_menu") and (sx + hx1 <= event.x_root <= sx + hx2 and sy + hy1 <= event.y_root <= sy + hy2):
                            return

                self.close_active_menu()
            except Exception:
                self.close_active_menu()

    def open_gamepad_config_dialog(self):
        self._open_or_focus_dialog(
            "_gamepad_dialog",
            lambda: GamepadConfigDialog(self, on_save_callback=self.on_gamepad_config_saved),
        )

    def on_gamepad_config_saved(self, new_cfg):
        self.gamepad_config = new_cfg
        self._sync_controller_family_ui(force=True)
        dev_label = new_cfg.get("selected_controller_name", "Mando")
        self.set_status(f"Mando configurado: {dev_label}")

    def open_add_dialog(self):
        def _create():
            self.monitors = get_monitors()
            return AddEditGameDialog(self, self.monitors, callback=self.on_game_added)

        self._open_or_focus_dialog("_add_dialog", _create)

    def open_select_game_dialog(self):
        def _create():
            if not self.library.games:
                show_info(
                    "Editar Juego",
                    "No hay juegos registrados en la biblioteca.\nUsa '🚀 Importar Juegos...' en el menú ⚙ para añadir o escanear juegos primero.",
                    parent=self
                )
                return None
            return SelectGameToEditDialog(
                self,
                self.library.games,
                on_select_callback=self.open_edit_for_game_index,
                initial_index=self._get_library_index_for_game(self.games[self.selected_index]) if self.games else 0,
                on_library_changed=lambda games: self.apply_filter(self.current_filter_id, keep_selection=True),
            )

        self._open_or_focus_dialog("_select_dialog", _create)

    def open_edit_current_game_dialog(self):
        self.close_active_menu()
        cur_game = self.games[self.selected_index] if (
            hasattr(self, "games") and self.games and 0 <= self.selected_index < len(self.games)
        ) else None
        if cur_game is None:
            if self.library.games:
                self.open_select_game_dialog()
            else:
                show_info(
                    "Editar Juego",
                    "No hay juegos registrados en la biblioteca.\nUsa 'Importar Juegos...' para añadir juegos primero.",
                    parent=self
                )
            return
        real_idx = self._get_library_index_for_game(cur_game)
        self.open_edit_for_game_index(real_idx)

    def open_edit_for_game_index(self, index: int, return_callback=None):
        if index < 0 or index >= len(self.library.games):
            if return_callback:
                return_callback()
            return

        def _create():
            self.monitors = get_monitors()
            game = self.library.games[index]
            return AddEditGameDialog(
                self,
                self.monitors,
                game_data=game,
                callback=lambda name, path, mon, hp, cov, args="", wp=None, wpo=None, wpb=None, fav=False, st="Por jugar", gen="", plat="PC", colls=None: self.on_specific_game_edited(index, name, path, mon, hp, cov, args, wp, wpo, wpb, fav, st, gen, plat, colls),
                delete_callback=lambda: self.delete_specific_game(index, confirm=False),
                on_close_callback=return_callback
            )

        self._open_or_focus_dialog("_edit_dialog", _create)

    def on_game_added(
        self, name, path, monitor, high_priority, cover, launch_args: str = "",
        wallpaper: Optional[str] = None, wallpaper_opacity: Optional[float] = None, wallpaper_blur: Optional[float] = None,
        favorite: bool = False, status: str = "Por jugar", genre: str = "", platform: str = "PC", collections: Optional[List[str]] = None
    ):
        new_index = self.library.add_game(
            name, path, monitor, high_priority, cover, launch_args,
            wallpaper=wallpaper, wallpaper_opacity=wallpaper_opacity, wallpaper_blur=wallpaper_blur,
            favorite=favorite, status=status, genre=genre, platform=platform, collections=collections
        )
        invalidate_thumb_cache()
        self.refresh_shelves(keep_selection=False)
        added_game = self.library.games[new_index] if 0 <= new_index < len(self.library.games) else None
        self._focus_game_in_shelves(added_game)
        self.set_status(f"Juego '{name}' añadido con éxito.")

    def on_specific_game_edited(
        self, index: int, name: str, path: str, monitor: int, high_priority: bool, cover: str, launch_args: str = "",
        wallpaper: Optional[str] = None, wallpaper_opacity: Optional[float] = None, wallpaper_blur: Optional[float] = None,
        favorite: Optional[bool] = None, status: Optional[str] = None, genre: Optional[str] = None, platform: Optional[str] = None,
        collections: Optional[List[str]] = None
    ):
        if self.library.update_game(
            index, name, path, monitor, high_priority, cover, launch_args,
            wallpaper=wallpaper, wallpaper_opacity=wallpaper_opacity, wallpaper_blur=wallpaper_blur,
            favorite=favorite, status=status, genre=genre, platform=platform, collections=collections
        ):
            invalidate_thumb_cache()
            self.refresh_shelves(keep_selection=True)
            self.set_status(f"Juego '{name}' actualizado.")

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
        def _create():
            if self.is_minimized:
                self.restore_window()
            dlg = ConfirmExitDialog(self, on_confirm=self.close_application)
            bring_to_front_absolute(dlg)
            return dlg

        self._open_or_focus_dialog("exit_dialog", _create, use_bring_to_front=True)

    def close_application(self, from_game_launch: bool = False):
        if not from_game_launch:
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
