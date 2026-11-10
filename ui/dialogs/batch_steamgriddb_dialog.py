import os
import queue
import threading
from typing import List, Dict, Any, Optional
import tkinter as tk
import customtkinter as ctk
from PIL import Image

from core.cover_downloader import download_and_apply_steamgriddb_media
from core.cover_resolver import resolve_game_cover
from core.coverflow_engine import create_procedural_album
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import BaseGlassDialog
from ui.dialogs.select_game_to_edit import get_game_thumbnail_ctk
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_WARNING,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget, apply_gamepad_focus
)


class BatchSteamGridDBDialog(BaseGlassDialog):
    """
    Diálogo modal de descarga masiva de carátulas 3D y wallpapers 16:9 desde SteamGridDB.com.
    Permite actualizar toda la biblioteca de juegos en un solo clic o con el mando (A / B).
    """

    def __init__(self, parent, games: List[Dict[str, Any]], on_complete_callback=None):
        super().__init__(parent, title="🎨 Descargar Arte Masivo — SteamGridDB", width=780, height=620, corner_radius=26)
        self.games = games
        self.on_complete_callback = on_complete_callback
        self.family = getattr(parent, "_current_controller_family", "xbox")
        self._action_queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._is_running = False
        self._completed_count = 0
        self._updated_games_count = 0

        self.create_widgets()
        self._bind_events()
        self.after(50, self._poll_queue)

    def destroy(self):
        self._cancel_event.set()
        self._is_running = False
        if hasattr(self, "_chunk_timer") and self._chunk_timer is not None:
            try:
                self.after_cancel(self._chunk_timer)
            except Exception:
                pass
            self._chunk_timer = None
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    _center_window = BaseGlassDialog.center_window

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
        self.main_card.grid_rowconfigure(3, weight=1)

        # 1. Cabecera superior
        header_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        header_frame.grid_columnconfigure(0, weight=1)

        top_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=4, pady=(0, 2))

        lbl_title = ctk.CTkLabel(
            top_row,
            text="🎨  Descargar Arte Masivo — SteamGridDB",
            font=font_button(18),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")

        self.lbl_count = ctk.CTkLabel(
            top_row,
            text=f"{len(self.games)} juegos",
            font=font_body(12),
            text_color=COLOR_IOS_BLUE
        )
        self.lbl_count.pack(side="right")

        for w in (header_frame, top_row, lbl_title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        lbl_sub = ctk.CTkLabel(
            header_frame,
            text="Aplica carátulas verticales 3D (600x900) y wallpapers 16:9 oficiales de SteamGridDB a todos tus juegos:",
            font=font_body(12),
            text_color=COLOR_TEXT_DIM,
            anchor="w"
        )
        lbl_sub.pack(fill="x", padx=4, pady=(0, 6))

        # 2. Opciones de descarga
        options_card = ctk.CTkFrame(
            self.main_card,
            fg_color=COLOR_BG_CARD_SECONDARY,
            corner_radius=16,
            border_color=COLOR_BORDER_CARD,
            border_width=1.0
        )
        options_card.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        self.opt_covers_var = ctk.BooleanVar(value=True)
        self.chk_covers = ctk.CTkCheckBox(
            options_card,
            text="Carátulas 3D (Grids)",
            variable=self.opt_covers_var,
            font=font_button(12),
            text_color=COLOR_TEXT_BRIGHT,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color="#3a455c",
            border_width=1.5,
            corner_radius=6
        )
        self.chk_covers.pack(side="left", padx=(14, 12), pady=10)

        self.opt_wallpapers_var = ctk.BooleanVar(value=True)
        self.chk_wallpapers = ctk.CTkCheckBox(
            options_card,
            text="Wallpapers 16:9 (Heroes)",
            variable=self.opt_wallpapers_var,
            font=font_button(12),
            text_color=COLOR_TEXT_BRIGHT,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color="#3a455c",
            border_width=1.5,
            corner_radius=6
        )
        self.chk_wallpapers.pack(side="left", padx=12, pady=10)

        self.opt_overwrite_var = ctk.BooleanVar(value=True)
        self.chk_overwrite = ctk.CTkCheckBox(
            options_card,
            text="Sobrescribir arte existente",
            variable=self.opt_overwrite_var,
            font=font_button(12),
            text_color=COLOR_TEXT_BRIGHT,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color="#3a455c",
            border_width=1.5,
            corner_radius=6
        )
        self.chk_overwrite.pack(side="left", padx=12, pady=10)

        # 3. Barra de Progreso y Estado en Vivo
        progress_card = ctk.CTkFrame(self.main_card, fg_color="transparent")
        progress_card.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 6))
        progress_card.grid_columnconfigure(0, weight=1)

        self.lbl_progress_status = ctk.CTkLabel(
            progress_card,
            text="Pulsa 'Iniciar Descarga Masiva' para conectar con SteamGridDB.",
            font=font_body(12),
            text_color=COLOR_TEXT_BRIGHT,
            anchor="w"
        )
        self.lbl_progress_status.grid(row=0, column=0, sticky="w", padx=2, pady=(0, 4))

        self.progress_bar = ctk.CTkProgressBar(
            progress_card,
            height=10,
            corner_radius=5,
            fg_color="#1c212d",
            progress_color=COLOR_IOS_BLUE
        )
        self.progress_bar.set(0.0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 2))

        # 4. Lista scrolleable de juegos
        self.scroll_frame = ctk.CTkScrollableFrame(self.main_card, fg_color="transparent")
        self.scroll_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(2, 6))
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        self._game_rows = []
        self._thumb_refs = {}
        self._chunk_timer = None
        initial_count = min(len(self.games), 25)
        for idx in range(initial_count):
            self._create_game_row(idx, self.games[idx])

        # Transmisión en diferido si hay más de 25 juegos para no bloquear la UI
        if initial_count < len(self.games):
            def _stream_batch_rows(start_idx: int):
                if not self.winfo_exists():
                    return
                end_idx = min(start_idx + 25, len(self.games))
                for k in range(start_idx, end_idx):
                    self._create_game_row(k, self.games[k])
                if end_idx < len(self.games):
                    self._chunk_timer = self.after(15, lambda: _stream_batch_rows(end_idx))
                else:
                    self._chunk_timer = None

            self._chunk_timer = self.after(15, lambda: _stream_batch_rows(initial_count))

        # 5. Pie de página con botones de acción
        footer = ctk.CTkFrame(self.main_card, fg_color="transparent", height=48)
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 14))

        self.btn_start = ctk.CTkButton(
            footer,
            text="Iniciar Descarga Masiva ",
            image=get_button_icon_ctk("a", self.family, size=20),
            compound="right",
            width=230,
            height=38,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER,
            border_width=1.2,
            corner_radius=19,
            text_color=COLOR_TEXT_WHITE,
            font=font_button(13),
            command=self._start_batch_process
        )
        self.btn_start.pack(side="right", padx=(8, 0), pady=4)

        self.btn_cancel = ctk.CTkButton(
            footer,
            text="Cerrar ",
            image=get_button_icon_ctk("b", self.family, size=20),
            compound="right",
            width=128,
            height=38,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1.0,
            corner_radius=19,
            text_color=COLOR_TEXT_MUTED,
            font=font_button(12),
            command=self.destroy
        )
        self.btn_cancel.pack(side="right", pady=4)

        # Navegación con mando
        self._nav_elements = [
            ("chk_covers", self.chk_covers),
            ("chk_wallpapers", self.chk_wallpapers),
            ("chk_overwrite", self.chk_overwrite),
            ("btn_start", self.btn_start),
            ("btn_cancel", self.btn_cancel)
        ]
        self._focused_nav_idx = 3  # Inicia enfocado en btn_start
        self._update_focus_visuals()

    def _create_game_row(self, idx: int, game: Dict[str, Any]):
        card = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=COLOR_BG_CARD_SECONDARY,
            corner_radius=14,
            border_color=COLOR_BORDER_CARD,
            border_width=1.0
        )
        card.pack(fill="x", pady=3, padx=2)

        # Miniatura de carátula actual con caché en memoria ultra rápido
        thumb_im = get_game_thumbnail_ctk(game, size=44)
        self._thumb_refs[idx] = thumb_im

        lbl_icon = ctk.CTkLabel(card, image=thumb_im, text="", width=44, height=44)
        lbl_icon.pack(side="left", padx=(10, 12), pady=6)

        info_box = ctk.CTkFrame(card, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True, pady=6)

        lbl_name = ctk.CTkLabel(
            info_box,
            text=game.get("name", "Juego"),
            font=font_button(13),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        lbl_name.pack(fill="x")

        lbl_sub = ctk.CTkLabel(
            info_box,
            text="⚪ En espera...",
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        lbl_sub.pack(fill="x")

        # Insignia de estado
        lbl_badge = ctk.CTkLabel(
            card,
            text="Pendiente",
            font=font_body(11),
            text_color="#94a3b8",
            width=120,
            anchor="e"
        )
        lbl_badge.pack(side="right", padx=(8, 14), pady=6)

        self._game_rows.append({
            "card": card,
            "lbl_icon": lbl_icon,
            "lbl_name": lbl_name,
            "lbl_sub": lbl_sub,
            "lbl_badge": lbl_badge,
            "game": game,
            "index": idx
        })

    def _bind_events(self):
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Return>", lambda e: self._activate_focused())
        self.bind("<space>", lambda e: self._activate_focused())
        self.bind("<Left>", lambda e: self._step_nav(-1))
        self.bind("<Right>", lambda e: self._step_nav(1))
        self.bind("<Up>", lambda e: self._step_nav(-1))
        self.bind("<Down>", lambda e: self._step_nav(1))

    def _step_nav(self, delta: int):
        if not self._nav_elements:
            return
        self._focused_nav_idx = (self._focused_nav_idx + delta) % len(self._nav_elements)
        self._update_focus_visuals()

    def _update_focus_visuals(self):
        for i, (tag, widget) in enumerate(self._nav_elements):
            is_focused = (i == self._focused_nav_idx)
            if tag.startswith("chk_"):
                apply_gamepad_focus(widget, is_focused, role="check")
            elif tag == "btn_start":
                apply_gamepad_focus(widget, is_focused, role="primary")
            elif tag == "btn_cancel":
                apply_gamepad_focus(widget, is_focused, role="secondary")

    def _activate_focused(self):
        if not self._nav_elements:
            return
        tag, widget = self._nav_elements[self._focused_nav_idx]
        if tag.startswith("chk_"):
            widget.toggle()
        elif tag == "btn_start":
            self._start_batch_process()
        elif tag == "btn_cancel":
            self.destroy()

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self.destroy()
            return True
        if (inputs.get("a", False) and not prev_inputs.get("a", False)) or \
           (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self._activate_focused()
            return True
        if (inputs.get("up", False) and not prev_inputs.get("up", False)) or \
           (inputs.get("left", False) and not prev_inputs.get("left", False)):
            self._step_nav(-1)
            return True
        if (inputs.get("down", False) and not prev_inputs.get("down", False)) or \
           (inputs.get("right", False) and not prev_inputs.get("right", False)):
            self._step_nav(1)
            return True
        return False

    def _start_batch_process(self):
        if self._is_running:
            return

        if self._completed_count >= len(self.games):
            # Proceso ya terminado: cerrar diálogo
            self.destroy()
            return

        do_covers = self.opt_covers_var.get()
        do_wallpapers = self.opt_wallpapers_var.get()
        do_overwrite = self.opt_overwrite_var.get()

        if not do_covers and not do_wallpapers:
            self.lbl_progress_status.configure(text="Selecciona al menos Carátulas o Wallpapers para iniciar.")
            return

        self._is_running = True
        self.btn_start.configure(state="disabled", text="Descargando arte...")
        self.chk_covers.configure(state="disabled")
        self.chk_wallpapers.configure(state="disabled")
        self.chk_overwrite.configure(state="disabled")

        def _worker():
            total = len(self.games)
            for i, game in enumerate(self.games):
                if self._cancel_event.is_set():
                    return
                g_name = game.get("name", "Juego")
                self._action_queue.put(("game_start", (i, g_name)))

                try:
                    res = download_and_apply_steamgriddb_media(
                        game,
                        download_cover=do_covers,
                        download_wallpaper=do_wallpapers,
                        overwrite=do_overwrite
                    )
                except Exception as e:
                    res = {"success": False, "error": str(e), "cover_applied": False, "wallpaper_applied": False}

                if self._cancel_event.is_set():
                    return
                self._action_queue.put(("game_finish", (i, game, res)))

            if not self._cancel_event.is_set():
                self._action_queue.put(("all_finished", None))

        threading.Thread(target=_worker, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                msg_type, payload = self._action_queue.get_nowait()
                total = len(self.games)

                if msg_type == "game_start":
                    idx, g_name = payload
                    self.lbl_progress_status.configure(
                        text=f"[{idx+1}/{total}] Buscando en SteamGridDB: '{g_name}'..."
                    )
                    if idx < len(self._game_rows):
                        row = self._game_rows[idx]
                        row["lbl_sub"].configure(text="⏳ Conectando con SteamGridDB...", text_color="#38bdf8")
                        row["lbl_badge"].configure(text="Descargando...", text_color="#38bdf8")
                        scroll_to_widget(self.scroll_frame, row["card"])

                elif msg_type == "game_finish":
                    idx, game, res = payload
                    self._completed_count += 1
                    prog = self._completed_count / max(1, total)
                    self.progress_bar.set(prog)

                    if idx < len(self._game_rows):
                        row = self._game_rows[idx]
                        if res.get("success"):
                            self._updated_games_count += 1
                            cov = res.get("cover_applied")
                            wp = res.get("wallpaper_applied")
                            m_name = res.get("matched_name") or game.get("name")
                            
                            badge_txt = "✓ Arte completo" if (cov and wp) else ("✓ Carátula" if cov else "✓ Wallpaper")
                            row["lbl_sub"].configure(
                                text=f"✓ Coincidencia: '{m_name}'",
                                text_color=COLOR_STATUS_SUCCESS
                            )
                            row["lbl_badge"].configure(text=badge_txt, text_color=COLOR_STATUS_SUCCESS)

                            # Actualizar miniatura si se descargó nueva carátula
                            new_cov = game.get("cover")
                            if new_cov and os.path.isfile(new_cov):
                                try:
                                    with Image.open(new_cov) as raw_im:
                                        scaled = raw_im.copy().resize((44, 44), Image.Resampling.LANCZOS)
                                    new_thumb = ctk.CTkImage(light_image=scaled, dark_image=scaled, size=(44, 44))
                                    self._thumb_refs[idx] = new_thumb
                                    row["lbl_icon"].configure(image=new_thumb)
                                except Exception:
                                    pass
                        else:
                            err = res.get("error") or "No encontrado"
                            row["lbl_sub"].configure(text=f"⚠ {err}", text_color=COLOR_STATUS_WARNING)
                            row["lbl_badge"].configure(text="Sin cambios", text_color="#94a3b8")

                elif msg_type == "all_finished":
                    self._is_running = False
                    self.progress_bar.set(1.0)
                    self.lbl_progress_status.configure(
                        text=f"¡Descarga masiva completada! {self._updated_games_count} de {total} juegos actualizados con SteamGridDB.",
                        text_color=COLOR_STATUS_SUCCESS
                    )
                    self.btn_start.configure(
                        state="normal",
                        text="✓ Listo / Cerrar ",
                        fg_color=COLOR_STATUS_SUCCESS,
                        hover_color="#16a34a"
                    )
                    self._focused_nav_idx = 3
                    self._update_focus_visuals()

                    # Notificar al lanzador para guardar y refrescar Cover Flow en vivo
                    if self.on_complete_callback:
                        try:
                            self.on_complete_callback()
                        except Exception:
                            pass

        except queue.Empty:
            pass
        except Exception:
            pass

        if self.winfo_exists():
            self.after(50, self._poll_queue)
