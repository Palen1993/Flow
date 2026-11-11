"""
GameFlow - Diálogo de Copias de Seguridad de Partidas (Save Backup Dialog)
==========================================================================
Diálogo modal Glassmorphism 100% navegable con mando para:
- Visualizar y cambiar la carpeta de guardado detectada (%APPDATA%, Saved Games, etc.).
- Crear copias de seguridad manuales instantáneas comprimidas en .zip.
- Listar copias anteriores con fecha, tamaño y cantidad de archivos.
- Restaurar cualquier copia guardada con backup preventivo automático.
- Eliminar copias obsoletas.
"""

import os
import subprocess
import tkinter as tk
from typing import Dict, Any, Optional, Callable, List
import customtkinter as ctk
from PIL import Image

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.dialogs.glass_message_box import ask_yes_no, show_info, show_error
from ui.dialogs.glass_folder_browser import browse_folder
from core.save_backup_service import (
    detect_game_save_candidates,
    get_effective_save_directory,
    create_save_backup,
    list_game_backups,
    restore_save_backup,
    delete_save_backup,
    format_bytes_size,
    get_game_backup_directory
)
from core.feedback import feedback_click, trigger_haptic
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_BTN_DANGER_BG, COLOR_BTN_DANGER_HOVER, COLOR_BTN_DANGER_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_DANGER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, font_title
)


class SaveBackupDialog(BaseGlassDialog):
    """
    Diálogo modal Glassmorphism para copias de seguridad y restauración de partidas.
    """

    def __init__(
        self,
        parent,
        game: Dict[str, Any],
        on_game_updated: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        super().__init__(
            parent,
            title=f"Copias de Seguridad - {game.get('name', 'Juego')}",
            width=840,
            height=600,
            corner_radius=22
        )
        self.game = game
        self.on_game_updated = on_game_updated

        # Detección inicial de carpeta de guardado
        self.current_save_path = game.get("save_path") or get_effective_save_directory(self.game)
        if self.current_save_path and not game.get("save_path"):
            self.game["save_path"] = self.current_save_path

        self.backups_list: List[Dict[str, Any]] = []
        self.selected_backup_idx: int = 0
        self._backup_cards: List[ctk.CTkFrame] = []

        self._build_ui()
        self._refresh_backups()

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

        # Miniatura o icono
        self._thumb_img = None
        cover_path = self.game.get("cover")
        if cover_path and os.path.isfile(cover_path):
            try:
                pil_img = Image.open(cover_path).resize((42, 42), Image.Resampling.LANCZOS)
                self._thumb_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(42, 42))
                lbl_icon = ctk.CTkLabel(self.header_bar, image=self._thumb_img, text="")
                lbl_icon.pack(side="left", padx=(0, 10))
            except Exception:
                lbl_icon = ctk.CTkLabel(self.header_bar, text="💾", font=font_title(20))
                lbl_icon.pack(side="left", padx=(0, 10))
        else:
            lbl_icon = ctk.CTkLabel(self.header_bar, text="💾", font=font_title(20))
            lbl_icon.pack(side="left", padx=(0, 10))

        # Info del juego
        info_col = ctk.CTkFrame(self.header_bar, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True)

        g_name = self.game.get("name", "Juego")
        lbl_title = ctk.CTkLabel(
            info_col,
            text=f"Copias de Seguridad: {g_name}",
            font=font_title(17),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            info_col,
            text="Protección automática de partidas en formato .zip con compresión segura",
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

        # ---------------- Barra de Ubicación de Guardado ----------------
        self.save_loc_card = ctk.CTkFrame(
            self.main_card,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1,
            corner_radius=12
        )
        self.save_loc_card.pack(fill="x", padx=20, pady=(4, 8))

        loc_info = ctk.CTkFrame(self.save_loc_card, fg_color="transparent")
        loc_info.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        lbl_loc_tag = ctk.CTkLabel(
            loc_info,
            text="📁  Carpeta de Partidas Guardadas Detectada:",
            font=font_button(11),
            text_color=COLOR_CYAN_ACCENT,
            anchor="w"
        )
        lbl_loc_tag.pack(anchor="w")

        self.lbl_loc_path = ctk.CTkLabel(
            loc_info,
            text="",
            font=font_body(11),
            text_color=COLOR_TEXT_WHITE,
            anchor="w",
            wraplength=520,
            justify="left"
        )
        self.lbl_loc_path.pack(anchor="w", pady=(2, 0))

        btn_change_loc = ctk.CTkButton(
            self.save_loc_card,
            text="Cambiar Carpeta (X)",
            width=140,
            height=30,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=8,
            command=self._change_save_location
        )
        btn_change_loc.pack(side="right", padx=12, pady=8)

        # ---------------- Acciones Principales ----------------
        actions_row = ctk.CTkFrame(self.main_card, fg_color="transparent", height=40)
        actions_row.pack(fill="x", padx=20, pady=(2, 8))

        self.btn_create_backup = ctk.CTkButton(
            actions_row,
            text="💾  Crear Copia de Seguridad Ahora (A)",
            font=font_button(13),
            height=38,
            corner_radius=12,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER,
            border_width=1.2,
            command=self._create_backup_action
        )
        self.btn_create_backup.pack(side="left", padx=(0, 10))

        self.lbl_backups_count = ctk.CTkLabel(
            actions_row,
            text="",
            font=font_body(12),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_backups_count.pack(side="left", padx=8)

        btn_open_folder = ctk.CTkButton(
            actions_row,
            text="📂  Abrir Carpeta",
            width=135,
            height=34,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=10,
            command=self._open_backup_folder_in_explorer
        )
        btn_open_folder.pack(side="right")

        self.btn_cloud_sync = ctk.CTkButton(
            actions_row,
            text="☁️  Nube / Cloud Sync (RB)",
            width=175,
            height=34,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_CYAN_BORDER,
            border_width=1,
            corner_radius=10,
            command=self._open_cloud_sync
        )
        self.btn_cloud_sync.pack(side="right", padx=(0, 8))

        # ---------------- Contenedor Desplazable de Copias ----------------
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.main_card,
            fg_color="transparent",
            corner_radius=12
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # ---------------- Pie con Atajos de Mando ----------------
        self.footer_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=28)
        self.footer_bar.pack(fill="x", padx=20, pady=(0, 8))

        self.lbl_shortcuts = ctk.CTkLabel(
            self.footer_bar,
            text="Cruceta (↑ / ↓): Navegar  │  (A): Crear Copia  │  (Start): Restaurar  │  (RB): Nube ☁️  │  (Y): Eliminar  │  (X): Carpeta  │  (B): Cerrar",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_shortcuts.pack(side="left")

    def _update_location_label(self):
        if self.current_save_path and os.path.isdir(self.current_save_path):
            self.lbl_loc_path.configure(
                text=self.current_save_path,
                text_color=COLOR_TEXT_WHITE
            )
        else:
            self.lbl_loc_path.configure(
                text="⚠️ No se detectó ninguna carpeta automáticamente. Pulsa 'Cambiar Carpeta (X)' para indicarla.",
                text_color="#f59e0b"
            )

    def _refresh_backups(self):
        self._update_location_label()
        self.backups_list = list_game_backups(self.game)

        total_b = len(self.backups_list)
        total_size = sum(b.get("size_bytes", 0) for b in self.backups_list)
        self.lbl_backups_count.configure(
            text=f"{total_b} copia(s) disponible(s) ({format_bytes_size(total_size)})"
        )

        # Limpiar lista gráfica
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._backup_cards.clear()

        if total_b == 0:
            empty_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=40)

            lbl_empty_icon = ctk.CTkLabel(empty_frame, text="💾", font=font_title(32))
            lbl_empty_icon.pack()

            lbl_empty = ctk.CTkLabel(
                empty_frame,
                text="No hay copias de seguridad creadas para este juego aún.\nPulsa 'Crear Copia de Seguridad Ahora (A)' para generar tu primer archivo .zip.",
                font=font_body(12),
                text_color=COLOR_TEXT_MUTED,
                justify="center"
            )
            lbl_empty.pack(pady=8)
            return

        from core.cloud_sync_service import load_cloud_config
        cloud_cfg = load_cloud_config()
        synced_map = cloud_cfg.get("synced_files", {})

        for idx, b in enumerate(self.backups_list):
            card = ctk.CTkFrame(
                self.scroll_frame,
                fg_color=COLOR_BG_CARD_SECONDARY,
                border_color=COLOR_CYAN_ACCENT if idx == self.selected_backup_idx else COLOR_BORDER_CARD,
                border_width=1.5 if idx == self.selected_backup_idx else 1,
                corner_radius=12,
                height=56
            )
            card.pack(fill="x", pady=4, padx=2)

            # Icono zip
            lbl_zip_icon = ctk.CTkLabel(card, text="📦", font=font_title(18))
            lbl_zip_icon.pack(side="left", padx=(12, 8), pady=10)

            # Columna con nombre y fecha
            info_subcol = ctk.CTkFrame(card, fg_color="transparent")
            info_subcol.pack(side="left", fill="both", expand=True, pady=6)

            lbl_zip_name = ctk.CTkLabel(
                info_subcol,
                text=b["name"],
                font=font_button(12),
                text_color=COLOR_TEXT_MAIN,
                anchor="w"
            )
            lbl_zip_name.pack(anchor="w")

            cloud_tag = "   •   ☁️ En la Nube" if b["name"] in synced_map else ""
            meta_line = f"📅 {b['date_formatted']}   •   💾 {b['size_formatted']}   •   📄 {b['total_files']} archivos   •   {b['comment']}{cloud_tag}"
            lbl_zip_meta = ctk.CTkLabel(
                info_subcol,
                text=meta_line,
                font=font_body(10),
                text_color=COLOR_CYAN_ACCENT if b["name"] in synced_map else COLOR_TEXT_DIM,
                anchor="w"
            )
            lbl_zip_meta.pack(anchor="w")

            # Botón Restaurar en tarjeta
            btn_restore = ctk.CTkButton(
                card,
                text="🔄  Restaurar",
                width=95,
                height=28,
                font=font_button(11),
                fg_color=COLOR_CYAN_BORDER,
                hover_color=COLOR_CYAN_ACCENT,
                text_color=COLOR_CYAN_ACCENT,
                border_color=COLOR_CYAN_BORDER,
                border_width=1,
                corner_radius=8,
                command=lambda p=b["path"], n=b["name"]: self._restore_backup_prompt(p, n)
            )
            btn_restore.pack(side="right", padx=(4, 12), pady=10)

            # Botón Eliminar en tarjeta
            btn_del = ctk.CTkButton(
                card,
                text="🗑",
                width=32,
                height=28,
                font=font_button(12),
                fg_color=COLOR_BTN_DANGER_BG,
                hover_color=COLOR_BTN_DANGER_HOVER,
                border_color=COLOR_BTN_DANGER_BORDER,
                border_width=1,
                corner_radius=8,
                command=lambda p=b["path"], n=b["name"]: self._delete_backup_prompt(p, n)
            )
            btn_del.pack(side="right", padx=(0, 4), pady=10)

            # Hacer interactivo por clic
            for w in (card, lbl_zip_icon, info_subcol, lbl_zip_name, lbl_zip_meta):
                w.bind("<Button-1>", lambda e, i=idx: self._select_card(i))

            self._backup_cards.append(card)

    def _select_card(self, idx: int):
        self.selected_backup_idx = idx
        self._highlight_selected_card()

    def _highlight_selected_card(self):
        for i, c in enumerate(self._backup_cards):
            if i == self.selected_backup_idx:
                c.configure(border_color=COLOR_CYAN_ACCENT, border_width=1.5)
            else:
                c.configure(border_color=COLOR_BORDER_CARD, border_width=1)

    def _create_backup_action(self):
        """Dispara la creación inmediata de una copia de seguridad en .zip."""
        if not self.current_save_path or not os.path.isdir(self.current_save_path):
            show_error(
                "Carpeta de Guardado No Encontrada",
                "No se ha detectado la carpeta de guardado para este juego.\n"
                "Por favor, pulsa 'Cambiar Carpeta (X)' e indica la ruta donde se guardan tus partidas.",
                parent=self
            )
            return

        self.btn_create_backup.configure(state="disabled", text="⏳ Creando copia en .zip...")
        self.update_idletasks()

        res = create_save_backup(self.game, save_path=self.current_save_path, comment="Copia manual")
        self.btn_create_backup.configure(state="normal", text="💾  Crear Copia de Seguridad Ahora (A)")

        if res.get("success"):
            try:
                feedback_click()
                trigger_haptic(0.2, 0.2, 60)
            except Exception:
                pass
            if self.on_game_updated:
                try:
                    self.on_game_updated(self.game)
                except Exception:
                    pass
            self.selected_backup_idx = 0
            self._refresh_backups()
            show_info(
                "Copia de Seguridad Creada",
                f"Se creó con éxito la copia '{res['zip_name']}'\n"
                f"Archivos respaldados: {res['files_count']} ({format_bytes_size(res['size_bytes'])} comprimidos).",
                parent=self
            )
        else:
            show_error("Error al Crear Copia", res.get("error", "Error desconocido"), parent=self)

    def _restore_backup_prompt(self, zip_path: str, zip_name: str):
        """Pide confirmación antes de restaurar una copia de seguridad."""
        if not self.current_save_path:
            show_error(
                "Destino No Encontrado",
                "No se ha definido la carpeta de guardado del juego donde restaurar las partidas.",
                parent=self
            )
            return

        confirmed = ask_yes_no(
            "Restaurar Partida Guardada",
            f"¿Estás seguro de que deseas restaurar '{zip_name}'?\n\n"
            f"Se sobrescribirán los archivos en:\n{self.current_save_path}\n\n"
            f"(Nota: GameFlow creará automáticamente un backup de protección de tus partidas actuales antes de restaurar).",
            parent=self
        )
        if not confirmed:
            return

        res = restore_save_backup(self.game, zip_path, target_dir=self.current_save_path, create_safety_backup=True)
        if res.get("success"):
            try:
                feedback_click()
            except Exception:
                pass
            self._refresh_backups()
            msg = f"Partida restaurada con éxito desde '{zip_name}'."
            if res.get("safety_backup"):
                msg += f"\n\nSe creó una copia preventiva: '{res['safety_backup']['zip_name']}'."
            show_info("Restauración Completada", msg, parent=self)
        else:
            show_error("Error de Restauración", res.get("error", "Error desconocido"), parent=self)

    def _delete_backup_prompt(self, zip_path: str, zip_name: str):
        """Pide confirmación antes de eliminar permanentemente un archivo de backup."""
        confirmed = ask_yes_no(
            "Eliminar Copia de Seguridad",
            f"¿Estás seguro de que deseas eliminar permanentemente '{zip_name}'?\nEsta acción no se puede deshacer.",
            parent=self
        )
        if not confirmed:
            return

        ok = delete_save_backup(zip_path)
        if ok:
            try:
                feedback_click()
            except Exception:
                pass
            if self.selected_backup_idx >= len(self.backups_list) - 1:
                self.selected_backup_idx = max(0, len(self.backups_list) - 2)
            self._refresh_backups()

    def _change_save_location(self):
        """Permite al usuario examinar y seleccionar la carpeta de guardado del juego."""
        init_p = self.current_save_path if (self.current_save_path and os.path.isdir(self.current_save_path)) else None
        folder = browse_folder(parent=self, title=f"Seleccionar Carpeta de Guardado ({self.game.get('name')})", initial_dir=init_p)
        if folder and os.path.isdir(folder):
            self.current_save_path = folder
            self.game["save_path"] = folder
            parent = self.parent
            if parent and hasattr(parent, "save_games"):
                try:
                    parent.save_games()
                except Exception:
                    pass
            if self.on_game_updated:
                try:
                    self.on_game_updated(self.game)
                except Exception:
                    pass
            self._update_location_label()

    def _open_backup_folder_in_explorer(self):
        b_dir = get_game_backup_directory(self.game)
        try:
            if os.name == "nt":
                os.startfile(b_dir)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", b_dir])
            else:
                subprocess.Popen(["xdg-open", b_dir])
        except Exception as e:
            show_info("Carpeta de Backups", f"Ubicación en disco:\n{b_dir}", parent=self)

    def _open_cloud_sync(self):
        feedback_click()
        from ui.dialogs.cloud_sync_dialog import CloudSyncDialog
        all_games = getattr(self.parent, "games", [self.game]) if self.parent else [self.game]
        CloudSyncDialog(parent=self, games=all_games, on_sync_completed=self._refresh_backups)

    # =========================================================================
    # MANEJADOR DE MANDO DE CONSOLA (GAMEPAD DISPATCHER)
    # =========================================================================
    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        """
        Navegación 100% por mando:
        - Cruceta Arriba/Abajo: Seleccionar copia en la lista
        - A: Si no hay copias, crea copia; si hay copias seleccionadas, botón crear o restaurar
        - Start: Restaurar la copia actualmente seleccionada
        - RB / LB: Abrir panel de Sincronización en la Nube (Cloud Sync)
        - Y: Eliminar la copia seleccionada
        - X: Cambiar carpeta de guardado (examinar)
        - B / Back: Cerrar diálogo
        """
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.close()
            return True

        # Botón RB / LB: Abrir panel de Cloud Sync
        if (inputs.get("rb", False) and not prev_inputs.get("rb", False)) or \
           (inputs.get("lb", False) and not prev_inputs.get("lb", False)):
            self._open_cloud_sync()
            return True

        # Cruceta arriba / abajo
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            if self.backups_list and self.selected_backup_idx > 0:
                self.selected_backup_idx -= 1
                self._highlight_selected_card()
            return True

        if inputs.get("down", False) and not prev_inputs.get("down", False):
            if self.backups_list and self.selected_backup_idx < len(self.backups_list) - 1:
                self.selected_backup_idx += 1
                self._highlight_selected_card()
            return True

        # Botón A: Crear copia de seguridad ahora
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            self._create_backup_action()
            return True

        # Botón Start: Restaurar copia seleccionada
        if inputs.get("start", False) and not prev_inputs.get("start", False):
            if self.backups_list and 0 <= self.selected_backup_idx < len(self.backups_list):
                b = self.backups_list[self.selected_backup_idx]
                self._restore_backup_prompt(b["path"], b["name"])
            return True

        # Botón Y: Eliminar copia seleccionada
        if inputs.get("y", False) and not prev_inputs.get("y", False):
            if self.backups_list and 0 <= self.selected_backup_idx < len(self.backups_list):
                b = self.backups_list[self.selected_backup_idx]
                self._delete_backup_prompt(b["path"], b["name"])
            return True

        # Botón X: Cambiar carpeta de guardado
        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self._change_save_location()
            return True

        return False
