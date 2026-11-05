import os
import threading
import queue
from typing import List, Dict, Any, Optional
import tkinter as tk
from PIL import Image, ImageTk
import customtkinter as ctk

from ui.dialogs.base_dialog import BaseGlassDialog
from core.coverflow_engine import create_procedural_album
from core.scanner import scan_directory_for_games, get_detected_games_folders
from ui.controller_hud import get_button_icon_ctk
from core.external_launchers import get_all_external_games, scan_emulator_roms, EMULATOR_PROFILES
from core.cover_downloader import download_and_save_cover, download_and_save_wallpaper
from core.config import COVERS_DIR, WALLPAPERS_DIR
from ui.dialogs import browse_folder
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_GLASS_BORDER,
    COLOR_CYAN_ACCENT, COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER,
    COLOR_BTN_SECONDARY_BG, COLOR_STATUS_SUCCESS, COLOR_STATUS_WARNING,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget, apply_gamepad_focus
)
from core.logger import get_logger

logger = get_logger("ExternalImportDialog")


class ExternalImportDialog(BaseGlassDialog):
    """
    Diálogo modal de estilo Liquid Glass para importar juegos detectados automáticamente
    en plataformas externas (Steam, Epic Games Store, GOG Galaxy) y ROMs de emuladores.
    Totalmente navegable con mando de juego (D-Pad, A, X, Y, Start, B).
    """

    def __init__(self, parent, on_import_callback=None, existing_games: Optional[List[Dict[str, Any]]] = None):
        self.on_import = on_import_callback
        self.existing_games = existing_games or []
        self.existing_paths = {
            os.path.normcase(os.path.abspath(g["path"]))
            for g in self.existing_games
            if g.get("path")
        }
        self.family = getattr(parent, "_current_controller_family", "xbox")
        self.candidates: List[Dict[str, Any]] = []
        self.items_vars = []
        self._row_frames = []
        self.thumb_refs = []
        self._focused_row_idx = 0

        super().__init__(
            parent,
            title="Importar Juegos Externos",
            width=820,
            height=620,
            corner_radius=22
        )

        self._action_queue = queue.Queue()
        self._build_ui()
        self._bind_keys()
        self._poll_action_queue()
        self._start_scan_thread()

    def _build_ui(self):
        # Card contenedor
        self.card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.card.pack(fill="both", expand=True, padx=4, pady=4)
        self.card.grid_columnconfigure(0, weight=1)
        self.card.grid_rowconfigure(2, weight=1)

        # 1. Cabecera superior arrastrable
        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        header.grid_columnconfigure(0, weight=1)

        top_line = ctk.CTkFrame(header, fg_color="transparent")
        top_line.pack(fill="x")

        lbl_title = ctk.CTkLabel(
            top_line,
            text="🚀  Importar / Añadir Juegos a la Biblioteca",
            font=font_button(17),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")

        # Botón seleccionar todos
        self.btn_select_all = ctk.CTkButton(
            top_line,
            text="Todos ",
            image=get_button_icon_ctk("x", self.family, size=18),
            compound="right",
            width=95,
            height=30,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            corner_radius=15,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(11),
            command=self._toggle_select_all
        )
        self.btn_select_all.pack(side="right", padx=(6, 0))

        # Botón de emuladores
        self.btn_roms = ctk.CTkButton(
            top_line,
            text="ROMs ",
            image=get_button_icon_ctk("y", self.family, size=18),
            compound="right",
            width=100,
            height=30,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER,
            border_width=1.2,
            corner_radius=15,
            text_color=COLOR_CYAN_ACCENT,
            font=font_button(11),
            command=self._open_emulator_rom_scanner
        )
        self.btn_roms.pack(side="right", padx=4)

        # Botón de escanear carpeta de PC
        self.btn_scan_folder = ctk.CTkButton(
            top_line,
            text="📁 Carpeta PC ",
            image=get_button_icon_ctk("lb", self.family, size=18),
            compound="right",
            width=135,
            height=30,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER,
            border_width=1.2,
            corner_radius=15,
            text_color="#38bdf8",
            font=font_button(11),
            command=self._scan_custom_folder
        )
        self.btn_scan_folder.pack(side="right", padx=(0, 4))

        for w in (header, top_line, lbl_title):
            self.make_draggable(w)

        # 2. Barra de estado / Plataformas detectadas
        self.status_bar = ctk.CTkFrame(self.card, fg_color="transparent")
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 6))

        self.lbl_summary = ctk.CTkLabel(
            self.status_bar,
            text="Escaneando Steam, Epic Games Store y GOG Galaxy...",
            font=font_body(12),
            text_color=COLOR_TEXT_DIM,
            anchor="w"
        )
        self.lbl_summary.pack(side="left")

        # 3. Lista desplazable de juegos
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.card,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.0,
            corner_radius=14
        )
        self.scroll_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(2, 10))
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # 4. Pie con botones de acción
        bottom_bar = ctk.CTkFrame(self.card, fg_color="transparent")
        bottom_bar.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 16))

        self.lbl_count = ctk.CTkLabel(
            bottom_bar,
            text="0 juegos seleccionados",
            font=font_body(12),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_count.pack(side="left")

        self.btn_manual = ctk.CTkButton(
            bottom_bar,
            text="＋ Añadir Manual ",
            image=get_button_icon_ctk("rb", self.family, size=18),
            compound="right",
            width=165,
            height=36,
            corner_radius=18,
            fg_color="#1a202d",
            hover_color="#263044",
            border_color=COLOR_GLASS_BORDER,
            border_width=1.0,
            text_color="#93c5fd",
            font=font_button(11),
            command=self._open_manual_add
        )
        self.btn_manual.pack(side="left", padx=12)

        self.btn_import = ctk.CTkButton(
            bottom_bar,
            text="Importar Seleccionados ",
            image=get_button_icon_ctk("start", self.family, size=20),
            compound="right",
            width=210,
            height=38,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color="#ffffff",
            border_width=2,
            corner_radius=19,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(13),
            command=self.import_selected
        )
        self.btn_import.pack(side="right", padx=(8, 0))

        self.btn_cancel = ctk.CTkButton(
            bottom_bar,
            text="Cancelar ",
            image=get_button_icon_ctk("b", self.family, size=18),
            compound="right",
            width=115,
            height=38,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER,
            border_width=1.2,
            corner_radius=19,
            text_color=COLOR_TEXT_MUTED,
            font=font_button(13),
            command=self.close
        )
        self.btn_cancel.pack(side="right")

    def _bind_keys(self):
        self.bind("<Up>", lambda e: self._step_row(-1))
        self.bind("<Down>", lambda e: self._step_row(1))
        self.bind("<Return>", lambda e: self.import_selected())
        self.bind("<space>", lambda e: self._toggle_focused_row())

    def _poll_action_queue(self):
        try:
            while not self._action_queue.empty():
                action, args = self._action_queue.get_nowait()
                if action == "populate":
                    self._populate_candidates(args)
                elif action == "folder_scanned":
                    found, folder_name = args
                    if found:
                        for fg in found:
                            fg["platform"] = f"📁 {folder_name}"
                        self.candidates.extend(found)
                        self._populate_candidates(self.candidates)
                        self.lbl_summary.configure(text=f"¡Se añadieron {len(found)} juego(s) de '{folder_name}' a la lista!")
                    else:
                        self.lbl_summary.configure(text=f"No se encontraron nuevos ejecutables de juegos en '{folder_name}'.")
                elif action == "finish_import":
                    try:
                        if self.on_import:
                            self.on_import(args)
                    finally:
                        self.close()
        except Exception as e:
            logger.debug(f"Error procesando action_queue: {e}")

        if self.winfo_exists():
            self.after(50, self._poll_action_queue)

    def _start_scan_thread(self):
        def _worker():
            candidates: List[Dict[str, Any]] = []
            seen_paths = set()

            # 1. Escanear carpetas de PC detectadas automáticamente (ej: D:\Juegos)
            detected_folders = get_detected_games_folders(self.existing_games)
            for folder in detected_folders:
                try:
                    folder_games = scan_directory_for_games(folder, existing_paths=self.existing_paths)
                    folder_name = os.path.basename(os.path.abspath(folder)) or folder
                    for fg in folder_games:
                        p = fg.get("path")
                        norm_p = os.path.normcase(os.path.abspath(p)) if p else ""
                        if norm_p and norm_p not in seen_paths:
                            seen_paths.add(norm_p)
                            fg["platform"] = f"📁 {folder_name}"
                            candidates.append(fg)
                except Exception as e:
                    logger.warning(f"Error escaneando carpeta {folder}: {e}")

            # 2. Escanear clientes externos (Steam, Epic Games Store, GOG Galaxy)
            try:
                external_games = get_all_external_games(existing_paths=self.existing_paths)
                for eg in external_games:
                    p = eg.get("path")
                    norm_p = os.path.normcase(os.path.abspath(p)) if p else ""
                    if norm_p and norm_p not in seen_paths:
                        seen_paths.add(norm_p)
                        candidates.append(eg)
                    elif not norm_p:
                        candidates.append(eg)
            except Exception as e:
                logger.warning(f"Error escaneando plataformas externas: {e}")

            self._action_queue.put(("populate", candidates))

        threading.Thread(target=_worker, daemon=True).start()

    def _populate_candidates(self, games: List[Dict[str, Any]]):
        self.candidates = games
        self.items_vars.clear()
        self._row_frames.clear()
        self.thumb_refs.clear()

        # Limpiar widgets previos en el scroll_frame
        for w in self.scroll_frame.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        if not games:
            lbl_empty = ctk.CTkLabel(
                self.scroll_frame,
                text="No se encontraron juegos en carpetas locales ni clientes externos.\n"
                     "Puedes seleccionar una carpeta con '📁 Carpeta PC (LB)' o añadir manualmente con '＋ Añadir Manual (RB)'.",
                font=font_body(13),
                text_color=COLOR_TEXT_DIM
            )
            lbl_empty.pack(pady=40)
            self.lbl_summary.configure(text="0 juegos encontrados.")
            return

        # Resumen por plataforma
        counts = {}
        for g in games:
            p = g.get("platform", "Otro")
            counts[p] = counts.get(p, 0) + 1
        summary_parts = [f"{p}: {cnt}" for p, cnt in counts.items()]
        self.lbl_summary.configure(text="  ·  ".join(summary_parts))

        thumb_size = 36
        for idx, g in enumerate(games):
            row = ctk.CTkFrame(
                self.scroll_frame,
                fg_color="#18202e" if idx % 2 == 0 else "#141a26",
                corner_radius=10,
                border_width=1,
                border_color="#242e42"
            )
            row.pack(fill="x", padx=4, pady=3)
            row.grid_columnconfigure(3, weight=1)

            # Col 0: Checkbox variable (marcado por defecto solo si es NUEVO)
            is_new = not g.get("already_added", False)
            chk_var = ctk.BooleanVar(value=is_new)
            chk = ctk.CTkCheckBox(
                row,
                text="",
                variable=chk_var,
                width=24,
                checkbox_width=20,
                checkbox_height=20,
                corner_radius=6,
                fg_color=COLOR_CYAN_ACCENT,
                hover_color=COLOR_IOS_BLUE_HOVER,
                border_color="#455470",
                command=self._update_selected_count
            )
            chk.grid(row=0, column=0, padx=(10, 6), pady=6)

            # Col 1: Miniatura de carátula
            cov_path = g.get("cover", "")
            if cov_path and os.path.isfile(cov_path):
                try:
                    with Image.open(cov_path) as im_raw:
                        raw_im = im_raw.copy().convert("RGBA").resize((thumb_size, thumb_size), Image.Resampling.BILINEAR)
                except Exception:
                    raw_im = create_procedural_album(g.get("name", "Game"), size=thumb_size)
            else:
                raw_im = create_procedural_album(g.get("name", "Game"), size=thumb_size)

            photo_im = ImageTk.PhotoImage(raw_im)
            self.thumb_refs.append(photo_im)
            lbl_thumb = tk.Label(row, image=photo_im, bg=row.cget("fg_color"), width=thumb_size, height=thumb_size)
            lbl_thumb.grid(row=0, column=1, padx=(0, 8), pady=6)

            # Col 2: Badge de plataforma
            platform = g.get("platform", "App")
            if "Steam" in platform:
                plat_color = "#0078f2"
            elif "Epic" in platform:
                plat_color = "#1f2937"
            elif "GOG" in platform:
                plat_color = "#6a1b9a"
            elif "ROM" in platform:
                plat_color = "#7c3aed"
            else:
                plat_color = "#0284c7"

            badge = ctk.CTkLabel(
                row,
                text=f" {platform} ",
                font=("Segoe UI Semibold", 10),
                text_color="#ffffff",
                fg_color=plat_color,
                corner_radius=6
            )
            badge.grid(row=0, column=2, padx=(0, 8), pady=6)

            # Col 3: Campo de nombre editable
            name_entry = ctk.CTkEntry(
                row,
                font=("Segoe UI Semibold", 12),
                fg_color="#101520",
                border_color="#2e3b52",
                border_width=1,
                corner_radius=8,
                text_color=COLOR_TEXT_MAIN
            )
            name_entry.insert(0, g.get("name", "Juego"))
            name_entry.grid(row=0, column=3, sticky="ew", padx=4, pady=6)

            # Col 4: Estado (NUEVO vs YA EN BIBLIOTECA)
            if is_new:
                st_lbl = ctk.CTkLabel(
                    row,
                    text="● NUEVO",
                    font=("Segoe UI", 10, "bold"),
                    text_color=COLOR_STATUS_SUCCESS
                )
            else:
                st_lbl = ctk.CTkLabel(
                    row,
                    text="✓ EN BIBLIOTECA",
                    font=("Segoe UI", 10, "bold"),
                    text_color="#94a3b8"
                )
            st_lbl.grid(row=0, column=4, padx=(8, 12), pady=6)

            self.items_vars.append((chk_var, name_entry, g))
            self._row_frames.append(row)

        self._focused_row_idx = 0
        self._highlight_focused_row()
        self._update_selected_count()

    def _update_selected_count(self):
        sel = sum(1 for chk_var, _, _ in self.items_vars if chk_var.get())
        total = len(self.items_vars)
        self.lbl_count.configure(text=f"{sel} de {total} juego(s) seleccionados")
        self.btn_import.configure(state="normal" if sel > 0 else "disabled")

    def _toggle_select_all(self):
        new_vars = [chk_var for chk_var, _, orig in self.items_vars if not orig.get("already_added", False)]
        if not new_vars:
            new_vars = [chk_var for chk_var, _, _ in self.items_vars]
        any_unchecked = any(not v.get() for v in new_vars)
        for v in new_vars:
            v.set(any_unchecked)
        self._update_selected_count()

    def _step_row(self, delta: int):
        if not self._row_frames:
            return
        self._focused_row_idx = max(0, min(len(self._row_frames) - 1, self._focused_row_idx + delta))
        self._highlight_focused_row()
        scroll_to_widget(self.scroll_frame, self._row_frames[self._focused_row_idx])

    def _highlight_focused_row(self):
        for idx, r in enumerate(self._row_frames):
            apply_gamepad_focus(r, idx == self._focused_row_idx, role="card")

    def _toggle_focused_row(self):
        if 0 <= self._focused_row_idx < len(self.items_vars):
            chk_var, _, _ = self.items_vars[self._focused_row_idx]
            chk_var.set(not chk_var.get())
            self._update_selected_count()

    def handle_gamepad_input(self, inputs: dict, prev: dict) -> bool:
        # Cruceta Arriba / Abajo
        if inputs.get("up", False) and not prev.get("up", False):
            self._step_row(-1)
            return True
        if inputs.get("down", False) and not prev.get("down", False):
            self._step_row(1)
            return True

        # Botón A: marcar/desmarcar fila enfocada
        if inputs.get("a", False) and not prev.get("a", False):
            self._toggle_focused_row()
            return True

        # Botón X: alternar seleccionar todos
        if inputs.get("x", False) and not prev.get("x", False):
            self._toggle_select_all()
            return True

        # Botón Y: escanear ROMs de emulador
        if inputs.get("y", False) and not prev.get("y", False):
            self._open_emulator_rom_scanner()
            return True

        # LB: Escanear Carpeta PC
        if inputs.get("lb", False) and not prev.get("lb", False):
            self._scan_custom_folder()
            return True

        # RB: Añadir Manualmente
        if inputs.get("rb", False) and not prev.get("rb", False):
            self._open_manual_add()
            return True

        # Start: importar seleccionados
        if inputs.get("start", False) and not prev.get("start", False):
            self.import_selected()
            return True

        # B o Back: salir
        if (inputs.get("b", False) and not prev.get("b", False)) or \
           (inputs.get("back", False) and not prev.get("back", False)):
            self.close()
            return True

        return False

    def _scan_custom_folder(self):
        from ui.dialogs.glass_folder_browser import browse_folder
        from core.scanner import scan_directory_for_games
        folder = browse_folder(parent=self, title="Seleccionar Carpeta para Buscar Juegos")
        if not folder:
            return

        folder_name = os.path.basename(os.path.abspath(folder)) or folder
        self.lbl_summary.configure(text=f"Escaneando '{folder_name}' en busca de juegos...")
        self.update_idletasks()

        def _worker():
            existing = {os.path.normcase(os.path.abspath(g["path"])) for g in self.candidates if g.get("path")}
            existing.update(self.existing_paths)
            found = scan_directory_for_games(folder, existing_paths=existing)
            self._action_queue.put(("folder_scanned", (found, folder_name)))

        threading.Thread(target=_worker, daemon=True).start()

    def _open_manual_add(self):
        self.close()
        root = getattr(self, "parent", None) or getattr(self, "master", None)
        while root and not hasattr(root, "open_add_dialog"):
            root = getattr(root, "master", None) or getattr(root, "parent", None)
        if root and hasattr(root, "open_add_dialog"):
            root.open_add_dialog()

    def _open_emulator_rom_scanner(self):
        """Permite seleccionar una carpeta de ROMs para generar títulos de emulador."""
        folder = browse_folder(parent=self, title="Seleccionar Carpeta de ROMs")
        if not folder:
            return

        # Escanear por defecto con perfil RetroArch o el primer perfil coincidente
        # Si no hay emulador instalado, se asocia genéricamente
        roms = scan_emulator_roms(
            emulator_exe="retroarch.exe",
            roms_dir=folder,
            profile_name="RetroArch"
        )
        if not roms:
            roms = scan_emulator_roms(
                emulator_exe="emulator.exe",
                roms_dir=folder,
                profile_name="PCSX2 (PlayStation 2)"
            )

        if roms:
            self.candidates.extend(roms)
            self._populate_candidates(self.candidates)

    def import_selected(self):
        selected_games: List[Dict[str, Any]] = []
        for chk_var, name_entry, orig_game in self.items_vars:
            if chk_var.get():
                game_copy = dict(orig_game)
                edited_name = name_entry.get().strip()
                if edited_name:
                    game_copy["name"] = edited_name
                selected_games.append(game_copy)

        if not selected_games:
            return

        self.btn_import.configure(state="disabled", text="Descargando arte oficial...")
        self.update_idletasks()

        def _download_artwork_worker():
            for g in selected_games:
                name = g.get("name", "Game")
                # Si es de Steam y tiene URLs oficiales, descargar y guardar en disco
                cov_url = g.get("cover_url")
                if cov_url and not g.get("cover"):
                    target_cov = os.path.join(COVERS_DIR, f"{name}.png")
                    if download_and_save_cover(cov_url, target_cov):
                        g["cover"] = target_cov

                wp_url = g.get("wallpaper_url")
                if wp_url and not g.get("wallpaper"):
                    target_wp = os.path.join(WALLPAPERS_DIR, f"{name}_wallpaper.png")
                    if download_and_save_wallpaper(wp_url, target_wp):
                        g["wallpaper"] = target_wp

            self._action_queue.put(("finish_import", selected_games))

        threading.Thread(target=_download_artwork_worker, daemon=True).start()
