import os
from typing import List, Dict, Any, Optional
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk

from core.coverflow_engine import create_procedural_album
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack
from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER,
    COLOR_BTN_SECONDARY_BG,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_WARNING,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget, apply_rounded_window_region, hide_from_taskbar
)

class ScanResultsDialog(ctk.CTkToplevel):
    def _windows_set_titlebar_color(self, color_mode: str):
        pass

    def _windows_set_titlebar_icon(self):
        pass
    """Diálogo modal para previsualizar, renombrar e importar juegos escaneados."""
    def __init__(self, parent, scanned_folder: str, candidates: List[Dict[str, Any]], on_import_callback=None):
        super().__init__(parent)
        self.on_import = on_import_callback
        self.candidates = candidates
        self.scanned_folder = scanned_folder
        
        self.dialog_width = 760
        self.dialog_height = 580
        self.title("📁 Juegos Detectados")
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
        
        self.items_vars = []  # Lista de tuplas: (checkbox_var, name_entry, candidate_data)
        self._row_frames = []
        self._focused_row_idx = 0
        self.thumb_refs = []  # Referencias para evitar recolección de basura de PhotoImage
        
        self.drag_x = 0
        self.drag_y = 0
        
        self.create_widgets()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Up>", lambda e: self._step_row(-1))
        self.bind("<Down>", lambda e: self._step_row(1))
        self.bind("<Return>", lambda e: self.import_selected())
        
        self._center_window()
        self.after(20, self._center_window)
        self.after(30, lambda: apply_rounded_window_region(self, self.dialog_width, self.dialog_height, 26))
        register_modal_stack(self)
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
        self.drag_x = event.x_root - self.winfo_x()
        self.drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.geometry(f"+{x}+{y}")

    def destroy(self):
        unregister_modal_stack(self)
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
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        header_frame.grid_columnconfigure(0, weight=1)
        
        top_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=0, pady=(0, 4))
        
        lbl_title = ctk.CTkLabel(
            top_row, text="📁  Juegos Detectados en Carpeta",
            font=font_button(18), 
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")
        
        for w in (header_frame, top_row, lbl_title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
        
        btn_sel_all = ctk.CTkButton(
            top_row, text="Marcar todos ", image=get_button_icon_ctk("x", size=18), compound="right",
            width=125, height=30,
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,
            corner_radius=15, text_color=COLOR_TEXT_WHITE,
            font=font_button(11), command=lambda: self.select_all(True)
        )
        btn_sel_all.pack(side="right", padx=(6, 0))
        
        btn_desel_all = ctk.CTkButton(
            top_row, text="Desmarcar ", image=get_button_icon_ctk("y", size=18), compound="right",
            width=115, height=30,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d", border_color=COLOR_GLASS_BORDER, border_width=1.2,
            corner_radius=15, text_color=COLOR_TEXT_MUTED,
            font=font_button(11), command=lambda: self.select_all(False)
        )
        btn_desel_all.pack(side="right")
        
        # Ruta escaneada
        folder_display = self.scanned_folder
        if len(folder_display) > 75:
            folder_display = folder_display[:38] + "..." + folder_display[-34:]
            
        lbl_path = ctk.CTkLabel(
            header_frame, text=f"Carpeta: {folder_display}",
            font=font_body(12), text_color=COLOR_TEXT_DIM, anchor="w"
        )
        lbl_path.pack(fill="x", padx=0, pady=(0, 6))
        
        # 2. Lista scrolleable de juegos encontrados
        scroll_frame = ctk.CTkScrollableFrame(self.main_card, fg_color="transparent")
        scroll_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=4)
        scroll_frame.grid_columnconfigure(0, weight=1)
        self.scroll_frame = scroll_frame
        
        thumb_size = 48
        for cand in self.candidates:
            row_frame = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=14, border_color=COLOR_BORDER_CARD, border_width=1.0)
            row_frame.pack(fill="x", pady=4, padx=2)
            self._row_frames.append(row_frame)
            
            # Checkbox estilo iOS
            is_already = cand.get("already_added", False)
            var = ctk.BooleanVar(value=not is_already)
            cb = ctk.CTkCheckBox(
                row_frame, text="", variable=var, width=24,
                fg_color="#007aff", hover_color="#0062cc", border_color="#3a455c", border_width=1.5,
                corner_radius=6,
                command=self.update_selected_count
            )
            cb.pack(side="left", padx=(12, 8), pady=10)
            
            # Miniatura de carátula
            cov_path = cand.get("cover", "")
            if cov_path and os.path.isfile(cov_path):
                try:
                    with Image.open(cov_path) as im_raw:
                        raw_im = im_raw.copy().resize((thumb_size, thumb_size), Image.Resampling.BILINEAR)
                except Exception:
                    raw_im = create_procedural_album(cand["name"], size=thumb_size)
            else:
                raw_im = create_procedural_album(cand["name"], size=thumb_size)
                
            photo_im = ImageTk.PhotoImage(raw_im)
            self.thumb_refs.append(photo_im)
            
            lbl_thumb = tk.Label(row_frame, image=photo_im, bg=COLOR_BG_CARD_SECONDARY, width=thumb_size, height=thumb_size)
            lbl_thumb.pack(side="left", padx=(0, 12))
            
            # Centro: Nombre editable y ruta del ejecutable
            info_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, pady=6)
            
            name_entry = ctk.CTkEntry(
                info_frame, height=32, corner_radius=16,
                font=font_button(13),
                fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_BORDER, border_width=1.2,
                text_color=COLOR_TEXT_MAIN
            )
            name_entry.insert(0, cand["name"])
            name_entry.pack(fill="x", pady=(2, 2))
            
            exe_disp = cand["path"]
            if len(exe_disp) > 65:
                exe_disp = "..." + exe_disp[-62:]
            lbl_exe = ctk.CTkLabel(
                info_frame, text=f"Ejecutable: {exe_disp}",
                font=font_body(11), text_color=COLOR_TEXT_DIM, anchor="w"
            )
            lbl_exe.pack(fill="x")
            
            # Badge de estado derecha (Píldoras iOS)
            if is_already:
                lbl_badge = ctk.CTkLabel(
                    row_frame, text="En biblioteca",
                    font=font_button(11),
                    fg_color="#2d2215", text_color=COLOR_STATUS_WARNING,
                    corner_radius=10, padx=8, pady=3
                )
                lbl_badge.pack(side="right", padx=12)
            else:
                lbl_badge = ctk.CTkLabel(
                    row_frame, text="Nuevo",
                    font=font_button(11),
                    fg_color="#142c1f", text_color=COLOR_STATUS_SUCCESS,
                    corner_radius=10, padx=8, pady=3
                )
                lbl_badge.pack(side="right", padx=12)
                
            self.items_vars.append((var, name_entry, cand))
            
        # 3. Panel inferior
        bottom_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 14))
        
        self.lbl_selected = ctk.CTkLabel(
            bottom_frame, text="",
            font=font_button(12), text_color=COLOR_TEXT_MUTED
        )
        self.lbl_selected.pack(side="left", padx=4, pady=8)
        
        self.btn_import = ctk.CTkButton(
            bottom_frame, text="＋  Añadir a la Biblioteca ", image=get_button_icon_ctk("start", size=20), compound="right",
            height=38,
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,
            corner_radius=19, text_color=COLOR_TEXT_WHITE,
            font=font_button(13),
            command=self.import_selected
        )
        self.btn_import.pack(side="right", padx=(8, 0), pady=8)
        
        btn_cancel = ctk.CTkButton(
            bottom_frame, text="Cancelar ", image=get_button_icon_ctk("b", size=20), compound="right",
            width=125, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d", border_color=COLOR_GLASS_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_MUTED, font=font_button(12),
            command=self.destroy
        )
        btn_cancel.pack(side="right", pady=8)
        
        self.update_selected_count()
        self.after(50, lambda: self._highlight_row(0))

    def _step_row(self, delta: int):
        if not self._row_frames:
            return
        new_idx = max(0, min(len(self._row_frames) - 1, self._focused_row_idx + delta))
        if new_idx != self._focused_row_idx:
            self._highlight_row(new_idx)
            try:
                from core.feedback import feedback_click
                feedback_click()
            except Exception:
                pass

    def _highlight_row(self, idx: int):
        if not self._row_frames or idx < 0 or idx >= len(self._row_frames):
            return
        self._focused_row_idx = idx
        for i, rf in enumerate(self._row_frames):
            if rf.winfo_exists():
                if i == idx:
                    rf.configure(border_color=COLOR_IOS_BLUE, border_width=2.0, fg_color="#1d2536")
                    edge = "top" if i == 0 else ("bottom" if i == len(self._row_frames) - 1 else None)
                    scroll_to_widget(self.scroll_frame, rf, force_edge=edge)
                else:
                    rf.configure(border_color=COLOR_BORDER_CARD, border_width=1.0, fg_color=COLOR_BG_CARD_SECONDARY)

    def select_all(self, val: bool):
        for var, _, _ in self.items_vars:
            var.set(val)
        self.update_selected_count()

    def update_selected_count(self):
        count = sum(1 for var, _, _ in self.items_vars if var.get())
        self.lbl_selected.configure(text=f"{count} juego(s) seleccionado(s)")
        if count > 0:
            self.btn_import.configure(state="normal", text=f"＋ Añadir a la Biblioteca ({count}) ")
        else:
            self.btn_import.configure(state="disabled", text="＋ Añadir a la Biblioteca (0) ")

    def import_selected(self):
        selected_games = []
        default_mon = 0
        parent_games = getattr(self.master, "games", [])
        if parent_games:
            default_mon = parent_games[0].get("monitor", 0)

        for var, name_entry, cand in self.items_vars:
            if var.get():
                user_name = name_entry.get().strip() or cand["name"]
                selected_games.append({
                    "name": user_name,
                    "path": cand["path"],
                    "monitor": cand.get("monitor", default_mon),
                    "high_priority": cand.get("high_priority", True),
                    "cover": cand.get("cover", "")
                })
        if selected_games and self.on_import:
            self.on_import(selected_games)
        self.destroy()

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self.destroy()
            return True
        if inputs.get("start", False) and not prev_inputs.get("start", False):
            self.import_selected()
            return True
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._step_row(-1)
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self._step_row(1)
            return True
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            if 0 <= self._focused_row_idx < len(self.items_vars):
                var, _, _ = self.items_vars[self._focused_row_idx]
                var.set(not var.get())
                self.update_selected_count()
            else:
                self.import_selected()
            return True
        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self.select_all(True)
            return True
        if inputs.get("y", False) and not prev_inputs.get("y", False):
            self.select_all(False)
            return True
        return False
