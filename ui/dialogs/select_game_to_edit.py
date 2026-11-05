import os
from typing import List, Dict, Any, Optional
import tkinter as tk
import customtkinter as ctk
from PIL import Image

from core.system import get_monitors
from core.coverflow_engine import create_procedural_album
from core.cover_resolver import resolve_game_cover
from ui.dropdowns import GlassDropdownButton
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import BaseGlassDialog
from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER,
    COLOR_BTN_SECONDARY_BG,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget
)

class SelectGameToEditDialog(BaseGlassDialog):
    """Panel de gestión rápida, filtrado y edición masiva / individual de juegos."""
    def __init__(self, parent, games: List[Dict[str, Any]], on_select_callback=None, initial_index: int = 0):
        super().__init__(parent, title="⚙ Seleccionar Juego para Editar", width=920, height=640, corner_radius=26)
        self.games = games
        self.on_select = on_select_callback
        self._initial_target_idx = initial_index if 0 <= initial_index < len(self.games) else 0
        self.family = getattr(parent, "_current_controller_family", "xbox")
        
        # Opciones de monitores disponibles
        self.monitors = getattr(self.master, "monitors", None) or get_monitors()
        self.monitor_options = [
            f"Monitor {m['id']} - {m['name']} ({m['rect'][2]-m['rect'][0]}x{m['rect'][3]-m['rect'][1]})" 
            for m in self.monitors
        ]
        if not self.monitor_options:
            self.monitor_options = ["Monitor 0 - Predeterminado"]
            
        self.thumb_refs = {}
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.refresh_list())
        
        self.create_widgets()
        self.refresh_list()
        self.bind("<Up>", lambda e: self._step_row(-1))
        self.bind("<Down>", lambda e: self._step_row(1))
        self.bind("<Return>", lambda e: self._activate_selected_row())

    _center_window = BaseGlassDialog.center_window

    def _start_drag(self, event):
        if hasattr(self, "global_monitor_menu") and getattr(self.global_monitor_menu, "_active_dropdown", None):
            try:
                self.global_monitor_menu._active_dropdown.destroy()
                self.global_monitor_menu._active_dropdown = None
            except Exception:
                pass
        super()._start_drag(event)

    def destroy(self):
        if hasattr(self, "global_monitor_menu") and getattr(self.global_monitor_menu, "_active_dropdown", None):
            try:
                self.global_monitor_menu._active_dropdown.destroy()
                self.global_monitor_menu._active_dropdown = None
            except Exception:
                pass
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    def _save_changes(self):
        try:
            if hasattr(self.master, "save_games"):
                self.master.save_games()
        except Exception as e:
            print(f"Error guardando cambios globales: {e}")

    def _update_top_priority_state(self):
        if not self.games:
            self.all_priority_var.set(False)
            return
        all_high = all(g.get("high_priority", True) for g in self.games)
        self.all_priority_var.set(all_high)

    def _on_toggle_all_priority(self):
        val = bool(self.all_priority_var.get())
        for g in self.games:
            g["high_priority"] = val
        self._save_changes()
        self.refresh_list()

    def _on_toggle_single_priority(self, orig_idx: int, val: bool):
        if 0 <= orig_idx < len(self.games):
            self.games[orig_idx]["high_priority"] = val
            self._save_changes()
            self._update_top_priority_state()

    def _update_top_monitor_state(self):
        if not hasattr(self, "global_monitor_menu") or not self.games:
            if hasattr(self, "global_monitor_menu"):
                self.global_monitor_menu.set("")
            return
        first_id = self.games[0].get("monitor", 0)
        all_same = all(g.get("monitor", 0) == first_id for g in self.games)
        
        matched = None
        for opt in self.monitor_options:
            if f"Monitor {first_id} " in opt or f"Monitor {first_id}-" in opt:
                matched = opt
                break
                
        if all_same and matched:
            self.global_monitor_menu.set(matched)
        else:
            self.global_monitor_menu.set("")

    def _on_change_all_monitors(self, choice: str):
        if not choice or "Monitor " not in choice:
            return
        try:
            target_id = int(choice.split("Monitor ")[1].split(" - ")[0].split(" ")[0])
        except Exception:
            target_id = 0
            
        for g in self.games:
            g["monitor"] = target_id
            
        self._save_changes()
        self.refresh_list()
        try:
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.grab_set()
        except Exception:
            pass

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
        
        # 1. Cabecera superior arrastrable
        header_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 2))
        header_frame.grid_columnconfigure(0, weight=1)
        
        top_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=4, pady=(0, 2))
        
        lbl_title = ctk.CTkLabel(
            top_row, text="⚙  Editar Juegos",
            font=font_button(18), 
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")
        
        self.lbl_count = ctk.CTkLabel(
            top_row, text=f"{len(self.games)} juegos",
            font=font_body(12), text_color=COLOR_IOS_BLUE
        )
        self.lbl_count.pack(side="right")
        
        for w in (header_frame, top_row, lbl_title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
        
        lbl_sub = ctk.CTkLabel(
            header_frame, text="Ajusta la configuración global o selecciona un juego para modificar sus detalles individuales:",
            font=font_body(12), text_color=COLOR_TEXT_DIM, anchor="w"
        )
        lbl_sub.pack(fill="x", padx=4, pady=(0, 6))
        
        # 2. Barra de Herramientas Globales (Prioridad masiva + Monitor masivo)
        tools_card = ctk.CTkFrame(
            self.main_card,
            fg_color=COLOR_BG_CARD_SECONDARY,
            corner_radius=16,
            border_color=COLOR_BORDER_CARD,
            border_width=1.0
        )
        tools_card.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))
        
        # Checkbox global de prioridad
        self.all_priority_var = ctk.BooleanVar(value=False)
        self.chk_all_priority = ctk.CTkCheckBox(
            tools_card,
            text="Prioridad Alta en todos",
            variable=self.all_priority_var,
            command=self._on_toggle_all_priority,
            font=font_button(12),
            text_color=COLOR_TEXT_BRIGHT,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color="#3a455c",
            border_width=1.5,
            corner_radius=6
        )
        self.chk_all_priority.pack(side="left", padx=(14, 4), pady=8)
        ctk.CTkLabel(
            tools_card, text="", image=get_button_icon_ctk("lb", self.family, size=18)
        ).pack(side="left", padx=(0, 8), pady=8)
        
        # Selector global de monitor
        mon_box = ctk.CTkFrame(tools_card, fg_color="transparent")
        mon_box.pack(side="right", padx=(10, 14), pady=6)
        
        lbl_mon = ctk.CTkLabel(
            mon_box,
            text="Monitor para todos ",
            image=get_button_icon_ctk("rb", size=18),
            compound="right",
            font=font_button(12),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_mon.pack(side="left", padx=(0, 8))
        
        self.global_monitor_menu = GlassDropdownButton(
            mon_box,
            values=self.monitor_options,
            placeholder="Asignar monitor a todos...",
            command=self._on_change_all_monitors,
            width=310,
            height=32,
            item_icon="🖥  "
        )
        self.global_monitor_menu.pack(side="left")

        # 3. Barra de búsqueda en tiempo real (Cápsula Liquid Glass)
        search_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        search_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 6))
        search_frame.grid_columnconfigure(0, weight=1)
        
        search_entry = ctk.CTkEntry(
            search_frame, textvariable=self.search_var,
            placeholder_text="🔍  Filtrar juegos por nombre o ejecutable...",
            height=38, corner_radius=19,
            fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_BORDER, border_width=1.2,
            text_color=COLOR_TEXT_MAIN, placeholder_text_color=COLOR_TEXT_DIM,
            font=font_body(13)
        )
        search_entry.grid(row=0, column=0, sticky="ew")
        
        # 4. Lista scrolleable de juegos
        self.scroll_frame = ctk.CTkScrollableFrame(self.main_card, fg_color="transparent")
        self.scroll_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 8))
        self.scroll_frame.grid_columnconfigure(0, weight=1)
        
        # 5. Pie de página
        footer = ctk.CTkFrame(self.main_card, fg_color="transparent", height=48)
        footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 14))
        
        btn_close = ctk.CTkButton(
            footer, text="Cerrar ", image=get_button_icon_ctk("b", self.family, size=20), compound="right",
            width=128, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_MUTED,
            font=font_button(12), command=self.destroy
        )
        btn_close.pack(side="right", padx=4, pady=4)

        btn_search = ctk.CTkButton(
            footer, text="Buscar ", image=get_button_icon_ctk("select", self.family, size=20), compound="right",
            width=128, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d",
            border_color=COLOR_GLASS_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_MUTED,
            font=font_button(12), command=self._open_search_keyboard
        )
        btn_search.pack(side="right", padx=6, pady=4)

    def refresh_list(self):
        for child in self.scroll_frame.winfo_children():
            child.destroy()
        self.thumb_refs.clear()
        self._card_rows = []
        target_foc = getattr(self, "_initial_target_idx", 0)
        self._selected_row_idx = target_foc if 0 <= target_foc < len(self.games) else 0
        self._initial_target_idx = 0
            
        query = self.search_var.get().strip().lower()
        matches = []
        for idx, g in enumerate(self.games):
            name = g.get("name", "")
            path = g.get("path", "")
            if not query or query in name.lower() or query in path.lower():
                matches.append((idx, g))
                
        self.lbl_count.configure(text=f"{len(matches)} de {len(self.games)} juegos" if query else f"{len(self.games)} juegos")
        
        if not matches:
            lbl_empty = ctk.CTkLabel(
                self.scroll_frame,
                text="No se encontraron juegos que coincidan con la búsqueda." if query else "No hay juegos registrados en la biblioteca.",
                font=font_body(14), text_color="#64748b"
            )
            lbl_empty.pack(pady=40)
        else:
            for orig_idx, game in matches:
                self._create_game_card(orig_idx, game)
            self._highlight_row(self._selected_row_idx)
                
        self._update_top_priority_state()
        self._update_top_monitor_state()

    def _step_row(self, delta: int):
        rows = getattr(self, "_card_rows", [])
        if not rows:
            return
        new_idx = max(0, min(len(rows) - 1, self._selected_row_idx + delta))
        if new_idx != self._selected_row_idx:
            self._highlight_row(new_idx)
            try:
                from core.feedback import feedback_click
                feedback_click()
            except Exception:
                pass

    def _activate_selected_row(self):
        rows = getattr(self, "_card_rows", [])
        if rows and 0 <= self._selected_row_idx < len(rows):
            _, orig_idx = rows[self._selected_row_idx]
            self._select_game(orig_idx)

    def _highlight_row(self, row_idx: int):
        rows = getattr(self, "_card_rows", [])
        if not rows or row_idx < 0 or row_idx >= len(rows):
            return
        self._selected_row_idx = row_idx
        for i, (card, _) in enumerate(rows):
            if card.winfo_exists():
                if i == row_idx:
                    card.configure(border_color=COLOR_IOS_BLUE, border_width=2.0, fg_color="#1d2536")
                    edge = "top" if i == 0 else ("bottom" if i == len(rows) - 1 else None)
                    scroll_to_widget(self.scroll_frame, card, force_edge=edge)
                else:
                    card.configure(border_color=COLOR_BORDER_CARD, border_width=1.0, fg_color=COLOR_BG_CARD_SECONDARY)

    def _open_search_keyboard(self):
        from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
        def _on_confirm(val: str):
            self.search_var.set(val)
            self.refresh_list()
        prompt_on_screen_keyboard(self, title="Filtrar Juegos", initial_text=self.search_var.get(), on_confirm=_on_confirm)

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self.destroy()
            return True
        if (inputs.get("back", False) and not prev_inputs.get("back", False)) or \
           (inputs.get("select", False) and not prev_inputs.get("select", False)):
            self._open_search_keyboard()
            return True
        if (inputs.get("start", False) and not prev_inputs.get("start", False)) or \
           (inputs.get("a", False) and not prev_inputs.get("a", False)):
            self._activate_selected_row()
            return True
        if inputs.get("lb", False) and not prev_inputs.get("lb", False):
            self.chk_all_priority.toggle()
            return True
        if inputs.get("rb", False) and not prev_inputs.get("rb", False):
            self.global_monitor_menu._toggle_dropdown()
            return True

        rows = getattr(self, "_card_rows", [])
        if not rows:
            if inputs.get("y", False) and not prev_inputs.get("y", False):
                self._open_search_keyboard()
                return True
            return False

        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._step_row(-1)
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self._step_row(1)
            return True
        if inputs.get("x", False) and not prev_inputs.get("x", False):
            # Alternar prioridad alta del juego seleccionado
            if 0 <= self._selected_row_idx < len(rows):
                _, orig_idx = rows[self._selected_row_idx]
                cur_hp = self.games[orig_idx].get("high_priority", True)
                self._on_toggle_single_priority(orig_idx, not cur_hp)
                saved_row = self._selected_row_idx
                self.refresh_list()
                self._highlight_row(min(saved_row, len(self._card_rows) - 1))
            return True
        if inputs.get("y", False) and not prev_inputs.get("y", False):
            # Alternar monitor asignado al juego seleccionado
            if 0 <= self._selected_row_idx < len(rows) and self.monitors:
                _, orig_idx = rows[self._selected_row_idx]
                self._on_cycle_single_monitor(orig_idx)
            return True
        return False

    def _on_cycle_single_monitor(self, orig_idx: int):
        """Alterna el monitor asignado para un juego específico y actualiza la lista."""
        if 0 <= orig_idx < len(self.games) and self.monitors:
            cur_m = self.games[orig_idx].get("monitor", 0)
            mon_ids = [m["id"] for m in self.monitors]
            next_i = (mon_ids.index(cur_m) + 1) % len(mon_ids) if cur_m in mon_ids else 0
            self.games[orig_idx]["monitor"] = mon_ids[next_i]
            self._save_changes()
            saved_row = self._selected_row_idx
            self.refresh_list()
            self._highlight_row(min(saved_row, len(self._card_rows) - 1))
            try:
                from core.feedback import feedback_click
                feedback_click()
            except Exception:
                pass

    def _create_game_card(self, orig_idx: int, game: Dict[str, Any]):
        card = ctk.CTkFrame(self.scroll_frame, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=14, border_color=COLOR_BORDER_CARD, border_width=1.0)
        card.pack(fill="x", pady=4, padx=2)
        
        # Miniatura de carátula (extremo izquierdo)
        thumb_img = self.thumb_refs.get(orig_idx)
        if thumb_img is None:
            cover_path = resolve_game_cover(game)
            try:
                with Image.open(cover_path) as raw_im:
                    scaled = raw_im.copy().resize((48, 48), Image.Resampling.LANCZOS)
                thumb_img = ctk.CTkImage(light_image=scaled, dark_image=scaled, size=(48, 48))
            except Exception:
                proc = create_procedural_album(game.get("name", "Juego"), size=48)
                thumb_img = ctk.CTkImage(light_image=proc, dark_image=proc, size=(48, 48))
            self.thumb_refs[orig_idx] = thumb_img
            
        lbl_thumb = ctk.CTkLabel(card, image=thumb_img, text="", width=48, height=48)
        lbl_thumb.pack(side="left", padx=(12, 14), pady=8)
        
        # Controles de la derecha (empaquetados primero con ancho garantizado)
        # 1. Botón Editar (Píldora iOS azul con el botón real A / Cruz)
        btn_edit = ctk.CTkButton(
            card, text="Editar ", image=get_button_icon_ctk("a", self.family, size=18), compound="right",
            width=108, height=32,
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,
            corner_radius=16, text_color=COLOR_TEXT_WHITE,
            font=font_button(12),
            command=lambda i=orig_idx: self._select_game(i)
        )
        btn_edit.pack(side="right", padx=(8, 14), pady=8)

        # 2. Checkbox individual de prioridad alta
        is_hp = game.get("high_priority", True)
        hp_var = ctk.BooleanVar(value=is_hp)
        chk_hp = ctk.CTkCheckBox(
            card,
            text="Prioridad",
            variable=hp_var,
            font=font_button(11),
            text_color=COLOR_TEXT_MUTED,
            width=18,
            checkbox_width=18,
            checkbox_height=18,
            fg_color="#007aff",
            hover_color="#0062cc",
            border_color="#3a455c",
            border_width=1.5,
            corner_radius=4,
            command=lambda i=orig_idx, v=hp_var: self._on_toggle_single_priority(i, v.get())
        )
        chk_hp.pack(side="right", padx=(8, 12), pady=8)

        # 3. Badge indicador interactivo del monitor asignado (Píldora cristal + botón real Y / △)
        cur_mon = game.get("monitor", 0)
        mon_icon = get_button_icon_ctk("y", self.family, size=16)
        lbl_mon = ctk.CTkLabel(
            card,
            text=f"🖥  Mon {cur_mon} ",
            image=mon_icon,
            compound="right",
            font=font_button(11),
            fg_color="#1e2538",
            text_color="#93c5fd",
            corner_radius=12,
            width=112,
            height=32,
            padx=10,
            pady=2
        )
        lbl_mon._img_ref = mon_icon
        lbl_mon.pack(side="right", padx=(8, 12), pady=8)
        lbl_mon.bind("<Button-1>", lambda e, i=orig_idx: self._on_cycle_single_monitor(i))
        lbl_mon.configure(cursor="hand2")

        # Centro: Información de texto (ocupa todo el espacio restante disponible sin apretar nada)
        info_box = ctk.CTkFrame(card, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=6)
        
        lbl_name = ctk.CTkLabel(
            info_box, text=game.get("name", "Juego"),
            font=font_button(14),
            text_color=COLOR_TEXT_MAIN, anchor="w"
        )
        lbl_name.pack(fill="x")
        
        path_text = game.get("path", "")
        if len(path_text) > 75:
            path_text = path_text[:35] + "..." + path_text[-35:]
        lbl_p = ctk.CTkLabel(info_box, text=path_text, font=font_body(11), text_color="#64748b", anchor="w")
        lbl_p.pack(fill="x")
        
        # Clic en la tarjeta o su texto abre el editor individual
        for w in (card, lbl_thumb, info_box, lbl_name, lbl_p):
            w.bind("<Button-1>", lambda e, i=orig_idx: self._select_game(i))
            w.configure(cursor="hand2")
        if hasattr(self, "_card_rows"):
            self._card_rows.append((card, orig_idx))

    def _select_game(self, idx: int):
        if hasattr(self, "global_monitor_menu") and getattr(self.global_monitor_menu, "_active_dropdown", None):
            try:
                self.global_monitor_menu._active_dropdown.destroy()
                self.global_monitor_menu._active_dropdown = None
            except Exception:
                pass
        self.withdraw()
        try:
            self.grab_release()
        except Exception:
            pass
        if self.on_select:
            self.on_select(idx, return_callback=self._on_edit_finished)
        else:
            self.destroy()

    def _on_edit_finished(self):
        try:
            if not self.winfo_exists():
                return
            current_games = getattr(self.master, "games", [])
            if not current_games:
                self.destroy()
                return
            self.games = current_games
            self.deiconify()
            self.lift()
            self.focus_force()
            self.refresh_list()
            self._center_window()
            try:
                self.attributes("-topmost", True)
                self.grab_set()
            except Exception:
                pass
        except Exception:
            pass
