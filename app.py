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
import ctypes
from typing import List, Dict, Any
from tkinter import filedialog, messagebox
import customtkinter as ctk
import win32api
import win32con

# Asignar AppUserModelID explícito para que Windows muestre el icono en la barra de tareas
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("gameflow.launcher.liquidglass.v1")
except Exception:
    pass

from core.config import load_games_data, save_games_data, get_games_file_mtime
from core.system import get_monitors
from core.logger import get_logger

logger = get_logger("App")
from core.launcher import launch_game_thread
from core.cover_resolver import resolve_game_cover
from core.scanner import scan_directory_for_games

from ui.theme import (
    COLOR_BG_DARK, COLOR_BG_CANVAS, COLOR_TRANS_KEY,
    COLOR_CYAN_ACCENT, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    font_title, font_button, font_body
)
from ui.coverflow_canvas import CoverFlowCanvas
from ui.controller_hud import render_controller_hud_strip, get_button_icon_ctk
from ui.dropdowns import FloatingGlassMenu
from ui.dialogs import (
    AddEditGameDialog, ScanResultsDialog, SelectGameToEditDialog,
    GamepadConfigDialog, ConfirmExitDialog, CoverPickerDialog,
    show_info, show_error, ask_yes_no, browse_folder
)
from gamepad_manager import (
    load_gamepad_config, poll_active_gamepad, get_connected_controller_family,
    ensure_gamebar_nexus_disabled, ensure_watcher_running, force_foreground_window
)

class App(ctk.CTk):
    """Aplicación principal GameFlow con interfaz iPod Cover Flow 3D y navegación por mando."""
    def __init__(self):
        super().__init__()
        self.title(" iPod GameFlow • Lanzador de Juegos")
        self.geometry("1020x720")
        self.minsize(880, 620)
        
        # Configurar icono personalizado en barra de tareas y ventana
        self._setup_app_icon()
        
        # Color de fondo general oscuro metálico
        self.configure(fg_color=COLOR_BG_DARK)
        self.title("GameFlow Launcher")
        
        self._games_file_mtime = get_games_file_mtime()
        self.games = self.load_games()
        self.monitors = get_monitors()
        self.selected_index = 0
        self.is_fullscreen = False
        self.is_mini_mode = False
        self.is_minimized = False
        self.exit_dialog = None
        self._modal_stack = []
        self.gamepad_config = load_gamepad_config()
        self.protocol("WM_DELETE_WINDOW", self.open_exit_dialog)
        self.bind("<FocusIn>", lambda e: self.refresh_games_from_disk_if_modified() if e.widget == self else None)
        
        self.create_widgets()
        self.bind_events()
        self._start_gamepad_loop()

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

    def _setup_app_icon(self):
        """Asigna el icono Liquid Glass personalizado a la ventana y barra de tareas de Windows."""
        try:
            base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            ico_path = os.path.join(base_dir, "assets", "icon.ico")
            png_path = os.path.join(base_dir, "assets", "icon.png")
            if not os.path.isfile(ico_path):
                ico_path = os.path.join(base_dir, "_internal", "assets", "icon.ico")
            if not os.path.isfile(png_path):
                png_path = os.path.join(base_dir, "_internal", "assets", "icon.png")

            if os.path.isfile(ico_path):
                try:
                    self.iconbitmap(ico_path)
                except Exception:
                    pass

            if os.path.isfile(png_path):
                try:
                    from PIL import Image, ImageTk
                    with Image.open(png_path) as raw_im:
                        photo = ImageTk.PhotoImage(raw_im.resize((64, 64), Image.Resampling.LANCZOS))
                        self.iconphoto(True, photo)
                        self._app_icon_ref = photo
                except Exception:
                    pass
        except Exception:
            pass
        
    def load_games(self) -> List[Dict[str, Any]]:
        games = load_games_data()
        for g in games:
            resolve_game_cover(g)
        self._games_file_mtime = get_games_file_mtime()
        return games

    def save_games(self):
        save_games_data(self.games)
        self._games_file_mtime = get_games_file_mtime()

    def refresh_games_from_disk_if_modified(self) -> bool:
        """
        Comprueba si games.json ha sido modificado externamente (por el centinela o sincronización).
        Si es así, recarga y actualiza los metadatos (playtime, last_played) en self.games
        sin reiniciar la posición ni la selección del usuario en el Cover Flow.
        """
        try:
            current_mtime = get_games_file_mtime()
            if current_mtime <= getattr(self, "_games_file_mtime", 0.0):
                return False

            fresh_games = load_games_data()
            if not fresh_games:
                return False

            self._games_file_mtime = current_mtime
            fresh_by_path = {}
            fresh_by_name = {}
            for fg in fresh_games:
                resolve_game_cover(fg)
                p = fg.get("path")
                if p:
                    fresh_by_path[os.path.normcase(os.path.normpath(p))] = fg
                n = fg.get("name", "").strip().lower()
                if n:
                    fresh_by_name[n] = fg

            for g in self.games:
                gp = g.get("path")
                norm_p = os.path.normcase(os.path.normpath(gp)) if gp else ""
                fg = fresh_by_path.get(norm_p) or fresh_by_name.get(g.get("name", "").strip().lower())
                if fg:
                    g["playtime_minutes"] = fg.get("playtime_minutes", g.get("playtime_minutes", 0))
                    g["last_played"] = fg.get("last_played", g.get("last_played"))

            self.update_ui_details(self.selected_index)
            return True
        except Exception as e:
            logger.error(f"Error al refrescar juegos desde disco: {e}", exc_info=True)
            return False

    def create_widgets(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # 1. Barra Superior (se mantiene instanciada pero no se mapea con grid para que el CoverFlowCanvas y el wallpaper lleguen hasta y=0 sin barra gris)
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
            fg_color="#141722",
            hover_color="#242a3a",
            border_color="#2b3345",
            border_width=1.2,
            text_color="#f8fafc",
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
            fg_color="#141722",
            hover_color="#242a3a",
            border_color="#2b3345",
            border_width=1.2,
            text_color="#38bdf8",
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

        # 2. Escenario Central a Pantalla Completa 100% (de y=0 a y=h sin barras grises arriba ni abajo)
        self.cover_stage = CoverFlowCanvas(
            self,
            on_selection_changed=self.on_cover_selected,
            on_launch_requested=self.launch_current_game,
            on_hud_action=self._on_canvas_hud_action
        )
        self.cover_stage.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        
        # 3. Panel Inferior (se mantiene instanciado sin mapear para eliminar cualquier barra gris inferior)
        bottom_panel = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        bottom_panel.grid_columnconfigure(0, weight=1)
        self.bottom_panel = bottom_panel
        
        self.lbl_game_title = ctk.CTkLabel(
            bottom_panel, text="",
            font=font_title(26),
            text_color="#f8fafc"
        )
        self.lbl_game_title.grid(row=0, column=0, pady=(0, 2))

        self.lbl_status = ctk.CTkLabel(
            bottom_panel, text="",
            font=font_body(12),
            text_color="#64748b"
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
            text_color="#ffffff",
            command=self.launch_current_game
        )
        self.btn_launch.grid(row=2, column=0, pady=(0, 4))
        self._sync_controller_family_ui(force=True)
        
        # Cargar los juegos en el Cover Flow
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
        self.bind("<Button-1>", self._on_global_click, add="+")
        self.bind("<F11>", lambda e: self.toggle_size_mode())
        self.bind("<Tab>", lambda e: self.toggle_size_mode())
        self.bind("<Escape>", lambda e: self.set_mini_mode() if not getattr(self, "is_mini_mode", False) else None)
        self.bind("<Key>", self._on_quick_letter_jump, add="+")

    def _on_quick_letter_jump(self, event=None, direction: int = 0):
        """Salto alfabético instantáneo al pulsar una letra en teclado o los gatillos LT/RT en el mando."""
        if not self.games or self._get_topmost_active_modal() is not None:
            return
        n = len(self.games)
        if direction != 0:
            cur_idx = max(0, min(n - 1, int(round(self.cover_stage.target_pos))))
            cur_name = (self.games[cur_idx].get("name") or "").strip().lower()
            cur_initial = cur_name[0] if cur_name else ""
            step = 1 if direction > 0 else -1
            for offset in range(1, n):
                idx = (cur_idx + offset * step) % n
                cand_name = (self.games[idx].get("name") or "").strip().lower()
                cand_initial = cand_name[0] if cand_name else ""
                if cand_initial != cur_initial:
                    self.cover_stage.select_index(idx)
                    return
            return

        if not event or not getattr(event, "char", None) or len(event.char) != 1 or not event.char.isalnum():
            return
        ch = event.char.lower()
        start = (self.selected_index + 1) % n
        for offset in range(n):
            idx = (start + offset) % n
            g_name = (self.games[idx].get("name") or "").strip().lower()
            if g_name.startswith(ch):
                self.cover_stage.select_index(idx)
                return

    def on_cover_selected(self, index: int):
        self.selected_index = index
        self.update_ui_details(index)

    def _format_monitor_full_label(self, mon_idx: int) -> str:
        """Devuelve el texto completo del monitor igual que en el selector (ej: 'Monitor 2 - SAMSUNG (1920x1080)')."""
        if not getattr(self, "monitors", None):
            try:
                self.monitors = get_monitors()
            except Exception:
                self.monitors = []
        matched = None
        for m in (self.monitors or []):
            if m.get("id") == mon_idx:
                matched = m
                break
        if matched is None and self.monitors and 0 <= mon_idx < len(self.monitors):
            matched = self.monitors[mon_idx]
        if matched:
            rect = matched.get("rect", (0, 0, 1920, 1080))
            mw = rect[2] - rect[0]
            mh = rect[3] - rect[1]
            return f"🖥 Monitor {matched['id']} - {matched['name']} ({mw}x{mh})"
        return f"🖥 Monitor {mon_idx} - Predeterminado"

    def _get_game_subtitle(self, game: Dict[str, Any]) -> str:
        mon_idx = int(game.get("monitor", 0) or 0)
        parts = [self._format_monitor_full_label(mon_idx)]
        mins = int(game.get("playtime_minutes", 0) or 0)
        if mins >= 60:
            hours = mins / 60.0
            parts.append(f"⏱ {hours:.1f} h jugadas")
        elif mins > 0:
            parts.append(f"⏱ {mins} min jugados")
        last_p = game.get("last_played")
        if last_p:
            parts.append(f"Última sesión: {last_p.split(' ')[0]}")
        return "   •   ".join(parts)

    def _on_canvas_hud_action(self, action: str):
        """Ejecuta las acciones de los botones visuales superpuestos en el lienzo."""
        if action == "menu":
            self.toggle_top_menu()
        elif action == "battery":
            self._show_battery_info()
        elif action == "launch":
            self.launch_current_game()
        elif action == "start":
            self.toggle_size_mode()
        elif action == "select":
            self.toggle_minimize()
        elif action == "exit":
            self.open_exit_dialog()

    def _on_top_hud_click(self, event):
        """Detecta en cuál de las 3 secciones (Vista, Ocultar, Salir) de la cápsula unificada se hizo clic."""
        x = event.x
        for (bx1, _by1, bx2, _by2, act) in getattr(self, "_top_hud_boxes", []):
            if bx1 <= x <= bx2:
                self._on_canvas_hud_action(act)
                return

    def _sync_controller_family_ui(self, force: bool = False):
        """
        Actualiza dinámicamente la cápsula única superior derecha (Vista | Ocultar | Salir) y los iconos
        de botones según el mando conectado (Xbox vs PlayStation).
        """
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
                self.lbl_status.configure(text="Añade o escanea tu carpeta de juegos desde el menú ⚙", text_color="#64748b")
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
            self.lbl_status.configure(text=sub_str, text_color="#94a3b8")
        self.btn_launch.configure(state="normal")
        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.ui_title = title_str
            if not getattr(self, "_status_reset_job", None):
                self.cover_stage.ui_status = sub_str
                self.cover_stage.ui_status_color = (203, 213, 225)
            self.cover_stage.ui_launch_disabled = False
            self.cover_stage.redraw()

    def launch_current_game(self):
        if getattr(self, "_is_launching", False):
            logger.warning("Lanzamiento ignorado: ya hay un juego iniciando.")
            return

        n = len(self.games)
        if n == 0 or self.selected_index >= n:
            return

        self._is_launching = True
        self.btn_launch.configure(state="disabled")

        try:
            from core.feedback import feedback_launch
            feedback_launch()
        except Exception:
            pass

        game = self.games[self.selected_index]
        self.set_status(f"Iniciando {game['name']}...")
        
        close_on_launch = self.gamepad_config.get("close_on_game_launch", True)
        if close_on_launch:
            # Ocultar la ventana de inmediato para una transición limpia e instantánea al juego
            try:
                self.withdraw()
            except Exception:
                pass

        def status_cb(msg):
            self.after(0, lambda: self.set_status(msg))

        def on_success():
            if close_on_launch:
                # El juego ya arrancó, centinela desacoplado activo: terminar el lanzador limpiamente
                self.after(1200, self.close_application)
            else:
                def _ui_reset():
                    self._is_launching = False
                    if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                        self.btn_launch.configure(state="normal")
                self.after(0, _ui_reset)

        def on_error(err_msg):
            def _ui_err():
                self._is_launching = False
                if hasattr(self, "btn_launch") and self.btn_launch.winfo_exists():
                    self.btn_launch.configure(state="normal")
                if close_on_launch:
                    self._handle_launch_error(err_msg)
                else:
                    self.set_status(f"Error iniciando juego: {err_msg}")
                    show_error("Error al Iniciar", f"No se pudo iniciar el juego:\n{err_msg}", parent=self)
            self.after(0, _ui_err)

        threading.Thread(
            target=launch_game_thread,
            args=(game["path"], game.get("monitor", 0), game.get("high_priority", True)),
            kwargs={
                "status_cb": status_cb,
                "on_success_cb": on_success,
                "on_error_cb": on_error,
                "custom_args": game.get("launch_args", "")
            },
            daemon=True
        ).start()

    def _handle_launch_error(self, err_msg: str):
        self._is_launching = False
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
                self.lbl_status.configure(text=msg, text_color="#38bdf8")
                if hasattr(self, "cover_stage") and self.cover_stage:
                    self.cover_stage.ui_status = msg
                    self.cover_stage.ui_status_color = (56, 189, 248)
                    self.cover_stage.redraw()

                def _restore_subtitle():
                    self._status_reset_job = None
                    if 0 <= self.selected_index < len(self.games):
                        sub_s = self._get_game_subtitle(self.games[self.selected_index])
                        self.lbl_status.configure(text=sub_s, text_color="#64748b")
                        if hasattr(self, "cover_stage") and self.cover_stage:
                            self.cover_stage.ui_status = sub_s
                            self.cover_stage.ui_status_color = (203, 213, 225)
                            self.cover_stage.redraw()
                self._status_reset_job = self.after(4200, _restore_subtitle)
            except Exception:
                pass
        logger.info(msg)

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
        
        def _scan_worker():
            candidates = scan_directory_for_games(folder, existing_paths=existing_paths)
            def _apply_scan():
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
                ScanResultsDialog(self, folder, candidates, on_import_callback=self.on_games_imported)
            self.after(0, _apply_scan)

        threading.Thread(target=_scan_worker, daemon=True).start()

    def on_games_imported(self, new_games: List[Dict[str, Any]]):
        if not new_games:
            return
        initial_count = len(self.games)
        self.games.extend(new_games)
        self.save_games()
        
        target_idx = initial_count if initial_count < len(self.games) else 0
        self.cover_stage.set_games(self.games, target_index=target_idx)
        self.update_ui_details(target_idx)
        self.set_status(f"Se añadieron {len(new_games)} juego(s) a la biblioteca.")

    def toggle_top_menu(self):
        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            self.glass_menu.destroy()
            self.glass_menu = None
            return
            
        items = [
            ("＋", "Agregar Juego", self.open_add_dialog),
            ("📁", "Escanear Carpeta", self.scan_folder_for_games),
            ("⚙", "Editar Juegos...", self.open_select_game_dialog),
            ("🎨", "Cambiar Carátula del Juego...", lambda: self.open_cover_picker_for_selected_game(initial_mode="cover")),
            ("🖼", "Cambiar Wallpaper de Fondo (16:9)...", lambda: self.open_cover_picker_for_selected_game(initial_mode="wallpaper")),
            ("🎮", "Configurar Mando...", self.open_gamepad_config_dialog)
        ]
        self.glass_menu = FloatingGlassMenu(self, self.btn_menu, items)

    def _poll_battery_status(self):
        """Consulta periódicamente (cada 4s) la batería del mando principal y, si existe, del secundario."""
        try:
            from gamepad_manager import get_gamepad_battery_info
            info = get_gamepad_battery_info()
            if info.get("connected"):
                txt = f"{info['icon']} {info['text']}"
                lvl = info.get("level", "")
                if lvl == "empty":
                    t_color = "#ff2d55"   # Rojo crítico iOS (<15%)
                    rgb_col = (255, 45, 85)
                elif lvl == "low":
                    t_color = "#ff9500"   # Ámbar advertencia iOS (<35%)
                    rgb_col = (255, 149, 0)
                elif info.get("is_wired") or lvl == "directinput":
                    t_color = "#007aff"   # Azul USB/DirectInput iOS
                    rgb_col = (56, 189, 248)
                else:
                    t_color = "#34c759"   # Verde iOS (>70%)
                    rgb_col = (52, 199, 89)
            else:
                txt = "🎮 Mando"
                t_color = "#64748b"
                rgb_col = (100, 116, 139)

            # Mando secundario (solo lectura): mostrar su batería junto a la del principal
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
        """Muestra el popup con estilo de la app (oscuro/glass) con los detalles de energía del mando."""
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
        """Abre el selector interactivo de carátulas y wallpapers 16:9 para el juego seleccionado."""
        if not self.games or self.selected_index < 0 or self.selected_index >= len(self.games):
            show_info("Carátula / Wallpaper", "No hay ningún juego seleccionado.", parent=self)
            return

        game = self.games[self.selected_index]
        game_name = game.get("name", "Juego")

        # Obtener carátula actual en PIL para la vista previa de Big Picture en vivo
        cur_cover_pil = None
        try:
            from core.cover_resolver import resolve_game_cover
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

        CoverPickerDialog(
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

    def open_gamepad_config_dialog(self):
        GamepadConfigDialog(self, on_save_callback=self.on_gamepad_config_saved)

    def on_gamepad_config_saved(self, new_cfg):
        self.gamepad_config = new_cfg
        self._sync_controller_family_ui(force=True)
        dev_label = new_cfg.get("selected_controller_name", "Mando")
        self.set_status(f"Mando configurado: {dev_label}")

    def toggle_minimize(self):
        """Alterna entre minimizar/ocultar el lanzador y restaurarlo/maximizarlo al frente."""
        if getattr(self, "is_minimized", False):
            self.restore_window()
        else:
            self.minimize_window()

    def minimize_window(self):
        """Minimiza/oculta el lanzador sin detener la escucha del mando."""
        self.is_minimized = True
        try:
            self.withdraw()
        except Exception:
            pass

    def minimize_to_taskbar(self):
        """Minimiza la ventana a la barra de herramientas de Windows para permanecer visible y accesible en la barra de tareas."""
        try:
            self.iconify()
        except Exception:
            pass

    def restore_window(self):
        """Restaura el lanzador y lo devuelve al frente activo por encima de cualquier juego o aplicación."""
        self.is_minimized = False
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            force_foreground_window(self.winfo_id(), keep_topmost=getattr(self, "is_mini_mode", False))
            # Refrescar metadatos de tiempo de juego si el centinela los actualizó en segundo plano
            self.refresh_games_from_disk_if_modified()
        except Exception:
            pass

    def set_mini_mode(self):
        """Activa el modo widget pequeño y flotante: UI 100% transparente sin marco ni reflejo."""
        self.is_mini_mode = True
        self.is_fullscreen = False
        self.is_minimized = False
        
        # Ocultar barra superior y panel de información inferior
        if hasattr(self, "top_bar") and self.top_bar:
            self.top_bar.grid_remove()
        if hasattr(self, "bottom_panel") and self.bottom_panel:
            self.bottom_panel.grid_remove()
            
        # Ocultar menú si estaba abierto
        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            self.glass_menu.destroy()
            self.glass_menu = None
            
        # Desactivar pantalla completa primero si estaba activa
        try:
            self.attributes("-fullscreen", False)
        except Exception:
            pass

        # Quitar marco de ventana para que sea flotante pura sin bordes ni barra de título
        try:
            self.overrideredirect(True)
        except Exception:
            pass

        # Mantener siempre en primer plano mientras esté en modo widget flotante
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        # Configurar clave de transparencia en Windows
        try:
            self.configure(fg_color=COLOR_TRANS_KEY)
            self.wm_attributes("-transparentcolor", COLOR_TRANS_KEY)
        except Exception:
            pass

        # Configurar canvas transparente
        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.configure(bg=COLOR_TRANS_KEY)
            self.cover_stage.is_transparent_mode = True

        # Reducir minsize para permitir tamaño de widget compacto
        self.minsize(400, 200)

        # Centrar ventana flotante con tamaño más generoso y amplio en el monitor actual
        try:
            hmon = win32api.MonitorFromWindow(self.winfo_id(), win32con.MONITOR_DEFAULTTONEAREST)
            mon_info = win32api.GetMonitorInfo(hmon)
            rc = mon_info.get("Work", mon_info.get("Monitor", (0, 0, self.winfo_screenwidth(), self.winfo_screenheight())))
            screen_w = rc[2] - rc[0]
            screen_h = rc[3] - rc[1]
            win_w = min(1440, max(1000, int(screen_w * 0.84)))
            win_h = min(540, max(460, int(screen_h * 0.48)))
            x = rc[0] + max(0, (screen_w - win_w) // 2)
            y = rc[1] + max(0, (screen_h - win_h) // 2)
        except Exception:
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            win_w = min(1440, max(1000, int(screen_w * 0.84)))
            win_h = min(540, max(460, int(screen_h * 0.48)))
            x = max(0, (screen_w - win_w) // 2)
            y = max(0, (screen_h - win_h) // 2)

        self.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.update_idletasks()
        
        # Forzar recálculo en canvas sin reflejo/sombra inferior
        self._sync_controller_family_ui()
        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.last_w = 0
            self.cover_stage.last_h = 0
            self.cover_stage._rebuild_rendered_cache()
            cw = self.cover_stage.winfo_width()
            ch = self.cover_stage.winfo_height()
            if cw > 60 and ch > 60:
                self.cover_stage._on_resize(type('Event', (), {'width': cw, 'height': ch})())
            else:
                self.cover_stage.redraw()

    def set_full_mode(self):
        """Restaura el modo pantalla completa completo con UI visible y fondo cinematográfico."""
        self.is_mini_mode = False
        self.is_fullscreen = True
        self.is_minimized = False
        
        try:
            self.wm_attributes("-transparentcolor", "")
        except Exception:
            pass
            
        try:
            self.attributes("-topmost", False)
        except Exception:
            pass
            
        try:
            self.overrideredirect(False)
        except Exception:
            pass
            
        self.configure(fg_color=COLOR_BG_DARK)
        
        if hasattr(self, "top_bar") and self.top_bar:
            self.top_bar.grid_remove()
        if hasattr(self, "bottom_panel") and self.bottom_panel:
            self.bottom_panel.grid_remove()
            
        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.configure(bg=COLOR_BG_CANVAS)
            self.cover_stage.is_transparent_mode = False
            
        self.minsize(880, 620)
        try:
            self.attributes("-fullscreen", True)
        except Exception:
            pass
            
        self.update_idletasks()
        self._sync_controller_family_ui()
        
        if hasattr(self, "cover_stage") and self.cover_stage:
            self.cover_stage.last_w = 0
            self.cover_stage.last_h = 0
            self.cover_stage._rebuild_rendered_cache()
            cw = self.cover_stage.winfo_width()
            ch = self.cover_stage.winfo_height()
            if cw > 60 and ch > 60:
                self.cover_stage._on_resize(type('Event', (), {'width': cw, 'height': ch})())
            else:
                self.cover_stage.redraw()

    def toggle_size_mode(self):
        """Alterna entre Modo Pequeño (Transparente) y Modo Grande (Pantalla Completa)."""
        if getattr(self, "is_mini_mode", False):
            self.set_full_mode()
        else:
            self.set_mini_mode()

    def toggle_fullscreen(self):
        self.toggle_size_mode()

    def push_modal(self, modal):
        """Registra una ventana modal en la cima de la pila en tiempo O(1)."""
        if modal not in self._modal_stack:
            self._modal_stack.append(modal)

    def pop_modal(self, modal):
        """Elimina una ventana modal de la pila al destruirse en tiempo O(1)."""
        if modal in self._modal_stack:
            self._modal_stack.remove(modal)

    def _start_gamepad_loop(self):
        self._last_gamepad_move = 0.0
        self._gamepad_was_connected = False
        self._prev_gamepad_buttons = {}
        self._gamepad_tick()

    def _get_topmost_active_modal(self):
        """
        Devuelve la ventana modal activa en primer plano en tiempo O(1) usando la pila de modales.
        Elimina por completo la sobrecarga de consultas recursivas de widgets (ahorro 4% CPU constante).
        """
        while self._modal_stack:
            top = self._modal_stack[-1]
            try:
                if top.winfo_exists():
                    state = getattr(top, "state", lambda: "normal")()
                    if state not in ("withdrawn", "iconic"):
                        return top
            except Exception:
                pass
            self._modal_stack.pop()

        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            try:
                state = getattr(self.glass_menu, "state", lambda: "normal")()
                if state not in ("withdrawn", "iconic"):
                    return self.glass_menu
            except Exception:
                pass

        return None

    def _gamepad_tick(self):
        try:
            target_id = self.gamepad_config.get("selected_controller_id", "any")
            is_conn, dev_name, inputs = poll_active_gamepad(target_id)
            now = time.time()
            
            # 1. Detección de conexión y sincronización del tipo de mando (Xbox vs PlayStation)
            if is_conn and not self._gamepad_was_connected:
                self._gamepad_was_connected = True
                self._sync_controller_family_ui()
                self.on_gamepad_connected(dev_name)
            elif not is_conn:
                self._gamepad_was_connected = False

            if now - getattr(self, "_last_fam_sync_ts", 0.0) > 1.5:
                self._last_fam_sync_ts = now
                self._sync_controller_family_ui()
                
            # 2. Control y navegación en todos los niveles de la aplicación
            if is_conn and self.gamepad_config.get("enable_controller_nav", True):
                prev = dict(self._prev_gamepad_buttons)

                # Auto-repetición fluida al mantener pulsada la cruceta o el stick en cualquier pantalla o scroll
                held_dirs = ("up", "down", "left", "right", "lb", "rb")
                any_dir_held = any(inputs.get(k, False) for k in held_dirs)
                if not any_dir_held:
                    self._modal_hold_start = 0.0
                    self._modal_last_repeat = 0.0
                else:
                    if not any(prev.get(k, False) for k in held_dirs):
                        self._modal_hold_start = now
                        self._modal_last_repeat = now
                    elif (now - getattr(self, "_modal_hold_start", 0.0) > 0.28) and \
                         (now - getattr(self, "_modal_last_repeat", 0.0) > 0.14):
                        for k in held_dirs:
                            if inputs.get(k, False):
                                prev[k] = False
                        self._modal_last_repeat = now

                # 1. Comprobar recursivamente si hay cualquier menú, desplegable o diálogo modal activo (incluso anidado)
                top_modal = self._get_topmost_active_modal()
                if top_modal is not None:
                    if hasattr(top_modal, "handle_gamepad_input") and callable(top_modal.handle_gamepad_input):
                        top_modal.handle_gamepad_input(inputs, prev)
                    elif inputs.get("b", False) and not prev.get("b", False):
                        try:
                            top_modal.destroy()
                        except Exception:
                            pass
                    self._prev_gamepad_buttons = inputs
                    self.after(25, self._gamepad_tick)
                    return

                # Si está minimizado, responder a Select, Start o botón Xbox para restaurar/maximizar
                if getattr(self, "is_minimized", False):
                    if (inputs.get("back", False) and not prev.get("back", False)) or \
                       (inputs.get("start", False) and not prev.get("start", False)) or \
                       (inputs.get("guide", False) and not prev.get("guide", False)):
                        self.restore_window()
                    self._prev_gamepad_buttons = inputs
                    self.after(25, self._gamepad_tick)
                    return
                
                # Botón Xbox / Guide / Nexus: Invocar y traer al frente
                if inputs.get("guide", False) and not prev.get("guide", False):
                    self.restore_window()
                    try:
                        self.lift()
                        self.focus_force()
                    except Exception:
                        pass

                # Movimiento horizontal (Stick / Cruceta) con repetición fluida en el carrusel
                move_left = inputs.get("left", False)
                move_right = inputs.get("right", False)
                
                if move_left and not move_right:
                    if not prev.get("left", False) or (now - self._last_gamepad_move > 0.20):
                        self.cover_stage.prev_cover()
                        self._last_gamepad_move = now
                elif move_right and not move_left:
                    if not prev.get("right", False) or (now - self._last_gamepad_move > 0.20):
                        self.cover_stage.next_cover()
                        self._last_gamepad_move = now

                # Cruceta Arriba en pantalla principal: abrir selector rápido de Monitor (o Menú si está en modo mini)
                if inputs.get("up", False) and not prev.get("up", False):
                    if not getattr(self, "is_mini_mode", False) and hasattr(self, "monitor_dropdown"):
                        self.monitor_dropdown._toggle_dropdown()
                    else:
                        self.toggle_top_menu()
                        
                # Botón A / Cruz: Iniciar juego
                if inputs.get("a", False) and not prev.get("a", False):
                    if not getattr(self, "_is_launching", False):
                        self.launch_current_game()
                    
                # Botón Select / Back / Share / View: Minimizar y restaurar/maximizar ventana
                if inputs.get("back", False) and not prev.get("back", False):
                    self.toggle_minimize()
                    
                # Botón Start / Options: Alternar entre modo transparente y pantalla completa
                if inputs.get("start", False) and not prev.get("start", False):
                    self.toggle_size_mode()
                    
                # Botón B / Círculo: Volver a modo pequeño si está en pantalla completa
                if inputs.get("b", False) and not prev.get("b", False):
                    if not getattr(self, "is_mini_mode", False):
                        self.set_mini_mode()
                        
                # Botón Y / Triángulo: Pedir confirmación para cerrar el programa
                if inputs.get("y", False) and not prev.get("y", False):
                    self.open_exit_dialog()
                    
                # Botón X / Cuadrado: Abrir menú opciones
                if inputs.get("x", False) and not prev.get("x", False):
                    self.toggle_top_menu()
                    
                # LB / RB: Salto rápido de 5 carátulas
                if inputs.get("lb", False) and not prev.get("lb", False):
                    n = len(self.games)
                    if n > 0:
                        cur = int(round(self.cover_stage.target_pos))
                        self.cover_stage.select_index(max(0, cur - 5))
                if inputs.get("rb", False) and not prev.get("rb", False):
                    n = len(self.games)
                    if n > 0:
                        cur = int(round(self.cover_stage.target_pos))
                        self.cover_stage.select_index(min(n - 1, cur + 5))

                # LT / RT: Salto alfabético por inicial (A-Z)
                if inputs.get("lt", False) and not prev.get("lt", False):
                    self._on_quick_letter_jump(direction=-1)
                if inputs.get("rt", False) and not prev.get("rt", False):
                    self._on_quick_letter_jump(direction=1)
                        
                self._prev_gamepad_buttons = inputs
            else:
                self._prev_gamepad_buttons = {}
        except Exception:
            pass
            
        self.after(25, self._gamepad_tick)

    def on_gamepad_connected(self, dev_name: str):
        self.set_status(f"🎮 {dev_name} conectado")
        if self.gamepad_config.get("auto_launch_on_connect", True):
            self.restore_window()
        if self.gamepad_config.get("start_in_mini_mode", True):
            if not getattr(self, "is_mini_mode", False):
                self.set_mini_mode()
        elif self.gamepad_config.get("auto_fullscreen", True) and not self.is_fullscreen:
            self.set_full_mode()

    def _on_global_click(self, event):
        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            bx = self.btn_menu.winfo_rootx()
            by = self.btn_menu.winfo_rooty()
            bw = self.btn_menu.winfo_width()
            bh = self.btn_menu.winfo_height()
            if not (bx <= event.x_root <= bx + bw and by <= event.y_root <= by + bh):
                self.glass_menu.destroy()
                self.glass_menu = None

    def open_add_dialog(self):
        self.monitors = get_monitors()
        AddEditGameDialog(self, self.monitors, callback=self.on_game_added)

    def open_select_game_dialog(self):
        if not self.games:
            show_info(
                "Editar Juego", 
                "No hay juegos registrados en la biblioteca.\nUsa '＋ Agregar Juego' o '📁 Escanear Carpeta' para añadir juegos primero.",
                parent=self
            )
            return
        SelectGameToEditDialog(self, self.games, on_select_callback=self.open_edit_for_game_index)

    def open_edit_for_game_index(self, index: int, return_callback=None):
        if index < 0 or index >= len(self.games):
            if return_callback:
                return_callback()
            return
        self.monitors = get_monitors()
        game = self.games[index]
        AddEditGameDialog(
            self, 
            self.monitors, 
            game_data=game, 
            callback=lambda name, path, mon, hp, cov, args="": self.on_specific_game_edited(index, name, path, mon, hp, cov, args),
            delete_callback=lambda: self.delete_specific_game(index, confirm=False),
            on_close_callback=return_callback
        )

    def open_edit_dialog(self):
        self.open_select_game_dialog()

    def on_game_added(self, name, path, monitor, high_priority, cover, launch_args: str = ""):
        new_game = {
            "name": name,
            "path": path,
            "monitor": monitor,
            "high_priority": high_priority,
            "cover": cover
        }
        if launch_args:
            new_game["launch_args"] = launch_args
        self.games.append(new_game)
        self.save_games()
        new_index = len(self.games) - 1
        self.cover_stage.set_games(self.games, target_index=new_index)
        self.update_ui_details(new_index)
        self.set_status(f"Juego '{name}' añadido con éxito.")

    def on_specific_game_edited(self, index: int, name: str, path: str, monitor: int, high_priority: bool, cover: str, launch_args: str = ""):
        if 0 <= index < len(self.games):
            existing = dict(self.games[index])
            existing.update({
                "name": name,
                "path": path,
                "monitor": monitor,
                "high_priority": high_priority,
                "cover": cover,
                "launch_args": launch_args
            })
            self.games[index] = existing
            self.save_games()
            self.cover_stage.set_games(self.games, target_index=index)
            self.update_ui_details(index)
            self.set_status(f"Juego '{name}' actualizado.")

    def on_game_edited(self, name, path, monitor, high_priority, cover, launch_args: str = ""):
        self.on_specific_game_edited(self.selected_index, name, path, monitor, high_priority, cover, launch_args)

    def delete_specific_game(self, index: int, confirm: bool = False):
        if index < 0 or index >= len(self.games):
            return
        game = self.games[index]
        if not confirm or ask_yes_no("Eliminar Juego", f"¿Estás seguro de que deseas eliminar '{game['name']}' de la biblioteca?", parent=self, confirm_text="Eliminar", is_destructive=True):
            self.games.pop(index)
            self.save_games()
            new_idx = max(0, min(len(self.games) - 1, index))
            self.cover_stage.set_games(self.games, target_index=new_idx)
            self.update_ui_details(new_idx)
            self.set_status(f"Juego '{game['name']}' eliminado.")

    def delete_current_game(self, confirm: bool = True):
        self.delete_specific_game(self.selected_index, confirm=confirm)

    def refresh_monitors(self):
        self.monitors = get_monitors(force_refresh=True)
        self.update_ui_details(self.selected_index)
        self.set_status(f"Monitores detectados: {len(self.monitors)}")

    def open_exit_dialog(self):
        """Abre el diálogo modal de confirmación para salir del lanzador."""
        if hasattr(self, "exit_dialog") and self.exit_dialog and self.exit_dialog.winfo_exists():
            try:
                self.exit_dialog.lift()
                self.exit_dialog.focus_force()
            except Exception:
                pass
            return
        if getattr(self, "is_minimized", False):
            self.restore_window()
        self.exit_dialog = ConfirmExitDialog(self, on_confirm=self.close_application)

    def close_application(self):
        """Cierra la aplicación por completo y asegura el watcher en segundo plano."""
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
