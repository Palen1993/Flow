"""
GameFlow - Diálogo de Gestión de Colecciones, Filtros y Estanterías del Dashboard
==================================================================================
Permite:
1. Habilitar o deshabilitar listas para que se muestren como carruseles navegables en la pantalla principal.
2. Reordenar el orden vertical (↑ / ↓) de cómo se presentan las filas (Favoritos, Recientes, Géneros, etc.).
3. Crear y eliminar listas personalizadas de juegos.
4. 100% operable con mando de consola (Cruceta ↑/↓ para navegar, (A) Activar/Desactivar, LB/RB Reordenar).
"""

import tkinter as tk
from typing import List, Dict, Any, Optional, Callable
import customtkinter as ctk

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
from core.collections_service import (
    load_collections_config, save_collections_config,
    get_available_shelf_definitions, add_custom_collection,
    delete_custom_collection, update_shelf_order_and_enabled
)
from core.feedback import feedback_click, trigger_haptic
from ui.controller_hud import get_button_icon_ctk
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
    font_button, font_body, font_title, scroll_to_widget
)


class CollectionsFilterDialog(BaseGlassDialog):
    """
    Diálogo modal Glassmorphism para configurar qué carruseles/listas se muestran en el launcher,
    ordenar su disposición vertical arriba/abajo y crear colecciones personalizadas.
    """

    def __init__(
        self,
        parent,
        all_games: List[Dict[str, Any]],
        current_shelf_id: str = "all",
        on_shelves_updated: Optional[Callable[[], None]] = None
    ):
        super().__init__(parent, title="🏷 Organizador de Listas y Carruseles", width=800, height=600, corner_radius=22)
        self.all_games = all_games
        self.current_shelf_id = current_shelf_id
        self.on_shelves_updated = on_shelves_updated
        self.family = getattr(parent, "_current_controller_family", "xbox")

        # Cargar lista de estanterías disponibles y ordenadas
        self.shelves_data: List[Dict[str, Any]] = []
        self._load_shelves_data()

        self.selected_row_idx: int = 0
        self._row_frames: List[ctk.CTkFrame] = []
        self._checkboxes: List[ctk.CTkCheckBox] = []
        self._check_vars: List[ctk.BooleanVar] = []

        self.create_widgets()

    _center_window = BaseGlassDialog.center_window

    def _load_shelves_data(self):
        cfg = load_collections_config()
        saved_shelves = cfg.get("shelves", [])
        available_defs = get_available_shelf_definitions(self.all_games)
        defs_map = {d["id"]: d for d in available_defs}

        ordered_list: List[Dict[str, Any]] = []
        seen = set()

        # 1. Conservar el orden guardado
        for s in saved_shelves:
            s_id = s.get("id")
            if s_id and s_id in defs_map and s_id not in seen:
                seen.add(s_id)
                d = dict(defs_map[s_id])
                d["enabled"] = bool(s.get("enabled", False))
                ordered_list.append(d)

        # 2. Agregar cualquier nueva definición disponible que no estuviera en la configuración
        for d in available_defs:
            s_id = d["id"]
            if s_id not in seen:
                seen.add(s_id)
                ordered_list.append(dict(d))

        self.shelves_data = ordered_list

    def create_widgets(self):
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)

        # ---------------- Cabecera ----------------
        header_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=44)
        header_bar.pack(fill="x", padx=20, pady=(12, 4))

        lbl_title = ctk.CTkLabel(
            header_bar,
            text="🏷  Organizador de Listas y Carruseles (Estanterías)",
            font=font_title(16),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")

        # Botón cerrar
        btn_close = ctk.CTkButton(
            header_bar,
            text="✕  Guardar y Salir (B)",
            width=135,
            height=30,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=10,
            command=self._save_and_close
        )
        btn_close.pack(side="right")

        # Subtítulo explicativo
        sub_text = "Navega ↑/↓  │  (A) Habilitar/Deshabilitar  │  (LB / RB) Subir/Bajar orden  │  (X) Nueva Lista"
        lbl_sub = ctk.CTkLabel(
            self.main_card,
            text=sub_text,
            font=font_body(11),
            text_color=COLOR_CYAN_ACCENT
        )
        lbl_sub.pack(anchor="w", padx=20, pady=(0, 6))

        for w in (header_bar, lbl_title, self.main_card):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # ---------------- Contenedor Desplazable de Estanterías ----------------
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.main_card,
            fg_color="transparent",
            corner_radius=14
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=16, pady=4)

        self._render_shelves_list()

        # ---------------- Barra Inferior de Acciones ----------------
        footer_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=42)
        footer_bar.pack(fill="x", padx=20, pady=(8, 14))

        btn_new_custom = ctk.CTkButton(
            footer_bar,
            text="＋ Nueva Lista Personalizada (X)",
            height=34,
            corner_radius=12,
            font=font_button(12),
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            command=self._prompt_new_collection
        )
        btn_new_custom.pack(side="left")

        lbl_hint = ctk.CTkLabel(
            footer_bar,
            text="Las listas marcadas con [✓] se mostrarán como carruseles verticales en el menú principal.",
            font=font_body(10),
            text_color=COLOR_TEXT_DIM
        )
        lbl_hint.pack(side="right", padx=8)

    def _render_shelves_list(self):
        # Limpiar widgets previos
        for w in self.scroll_frame.winfo_children():
            w.destroy()
        self._row_frames.clear()
        self._checkboxes.clear()
        self._check_vars.clear()

        for idx, shelf in enumerate(self.shelves_data):
            row_card = self._build_shelf_row(idx, shelf)
            row_card.pack(fill="x", pady=3)
            self._row_frames.append(row_card)

        self._highlight_selected_row()

    def _build_shelf_row(self, idx: int, shelf: Dict[str, Any]) -> ctk.CTkFrame:
        is_enabled = bool(shelf.get("enabled", False))
        is_sel = (idx == self.selected_row_idx)

        card = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=COLOR_BG_CARD_SECONDARY if is_enabled else COLOR_BG_DARK,
            border_color=COLOR_CYAN_ACCENT if is_sel else (COLOR_BORDER_CARD if is_enabled else COLOR_GLASS_BORDER),
            border_width=1.5 if is_sel else 1.0,
            corner_radius=12,
            height=44
        )

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=6)

        # Checkbox de activación
        chk_var = ctk.BooleanVar(value=is_enabled)
        chk = ctk.CTkCheckBox(
            inner,
            text="",
            variable=chk_var,
            width=24,
            checkbox_width=20,
            checkbox_height=20,
            corner_radius=6,
            fg_color=COLOR_IOS_BLUE,
            command=lambda i=idx: self._on_toggle_enabled(i)
        )
        chk.pack(side="left", padx=(0, 10))
        self._checkboxes.append(chk)
        self._check_vars.append(chk_var)

        # Icono y Nombre
        icon = shelf.get("icon", "🏷️")
        name = shelf.get("name", shelf.get("id"))
        count = shelf.get("count", 0)

        lbl_name = ctk.CTkLabel(
            inner,
            text=f"{icon}  {name}",
            font=font_button(12),
            text_color=COLOR_TEXT_MAIN if is_enabled else COLOR_TEXT_MUTED,
            anchor="w"
        )
        lbl_name.pack(side="left", fill="x", expand=True)

        # Badge de Tipo / Conteo
        type_str = shelf.get("type", "system").capitalize()
        badge_txt = f"{count} juego(s)  •  {type_str}"
        lbl_badge = ctk.CTkLabel(
            inner,
            text=badge_txt,
            font=font_body(10),
            text_color=COLOR_TEXT_DIM
        )
        lbl_badge.pack(side="left", padx=12)

        # Botones de Orden (▲ / ▼)
        btn_box = ctk.CTkFrame(inner, fg_color="transparent")
        btn_box.pack(side="right")

        btn_up = ctk.CTkButton(
            btn_box,
            text="▲",
            width=28,
            height=26,
            font=font_button(10),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            corner_radius=6,
            command=lambda i=idx: self._move_shelf(i, -1)
        )
        btn_up.pack(side="left", padx=2)

        btn_down = ctk.CTkButton(
            btn_box,
            text="▼",
            width=28,
            height=26,
            font=font_button(10),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            corner_radius=6,
            command=lambda i=idx: self._move_shelf(i, 1)
        )
        btn_down.pack(side="left", padx=2)

        # Botón Eliminar si es personalizada
        if shelf.get("type") == "custom":
            btn_del = ctk.CTkButton(
                btn_box,
                text="🗑",
                width=28,
                height=26,
                font=font_button(10),
                fg_color=COLOR_BTN_DANGER_BG,
                hover_color=COLOR_BTN_DANGER_HOVER,
                corner_radius=6,
                command=lambda i=idx: self._delete_shelf(i)
            )
            btn_del.pack(side="left", padx=(4, 0))

        # Evento de clic para seleccionar fila
        for w in (card, inner, lbl_name, lbl_badge):
            w.bind("<Button-1>", lambda e, i=idx: self._on_row_clicked(i))

        return card

    def _on_row_clicked(self, idx: int):
        self.selected_row_idx = idx
        self._highlight_selected_row()
        feedback_click()

    def _highlight_selected_row(self):
        for idx, card in enumerate(self._row_frames):
            is_sel = (idx == self.selected_row_idx)
            is_en = self.shelves_data[idx].get("enabled", False)
            if is_sel:
                card.configure(
                    border_color=COLOR_CYAN_ACCENT,
                    border_width=2.0,
                    fg_color=COLOR_GLASS_HOVER
                )
                scroll_to_widget(card, self.scroll_frame)
            else:
                card.configure(
                    border_color=COLOR_BORDER_CARD if is_en else COLOR_GLASS_BORDER,
                    border_width=1.0,
                    fg_color=COLOR_BG_CARD_SECONDARY if is_en else COLOR_BG_DARK
                )

    def _on_toggle_enabled(self, idx: int):
        if 0 <= idx < len(self.shelves_data):
            new_val = self._check_vars[idx].get()
            self.shelves_data[idx]["enabled"] = new_val
            feedback_click()
            self._render_shelves_list()

    def _move_shelf(self, idx: int, direction: int):
        new_idx = idx + direction
        if 0 <= new_idx < len(self.shelves_data):
            self.shelves_data[idx], self.shelves_data[new_idx] = (
                self.shelves_data[new_idx],
                self.shelves_data[idx]
            )
            self.selected_row_idx = new_idx
            feedback_click()
            trigger_haptic()
            self._render_shelves_list()

    def _delete_shelf(self, idx: int):
        if 0 <= idx < len(self.shelves_data):
            s = self.shelves_data[idx]
            delete_custom_collection(s["id"])
            self.shelves_data.pop(idx)
            self.selected_row_idx = max(0, min(self.selected_row_idx, len(self.shelves_data) - 1))
            feedback_click()
            self._render_shelves_list()

    def _prompt_new_collection(self):
        feedback_click()
        val = prompt_on_screen_keyboard(self, "Nueva Lista Personalizada", "Ej. Cooperativos")
        if val and val.strip():
            new_id = add_custom_collection(val.strip())
            if new_id:
                self._load_shelves_data()
                self._render_shelves_list()

    def _save_and_close(self):
        # Asegurarse de que al menos 1 lista permanezca habilitada
        if not any(s.get("enabled", False) for s in self.shelves_data):
            if self.shelves_data:
                self.shelves_data[0]["enabled"] = True

        update_shelf_order_and_enabled(self.shelves_data)
        feedback_click()

        if self.on_shelves_updated:
            self.on_shelves_updated()
        self.destroy()

    # ---------------- Soporte para Mando de Consola ----------------
    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        n = len(self.shelves_data)
        if n == 0:
            return False

        # Cruceta Arriba
        if inputs.get("dpad_up", False) and not prev_inputs.get("dpad_up", False):
            if self.selected_row_idx > 0:
                self.selected_row_idx -= 1
                self._highlight_selected_row()
                feedback_click()
            return True

        # Cruceta Abajo
        if inputs.get("dpad_down", False) and not prev_inputs.get("dpad_down", False):
            if self.selected_row_idx < n - 1:
                self.selected_row_idx += 1
                self._highlight_selected_row()
                feedback_click()
            return True

        # Botón A: Alternar habilitación de la fila seleccionada
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            cur_val = self.shelves_data[self.selected_row_idx].get("enabled", False)
            self._check_vars[self.selected_row_idx].set(not cur_val)
            self._on_toggle_enabled(self.selected_row_idx)
            return True

        # LB: Mover estantería hacia arriba
        if inputs.get("lb", False) and not prev_inputs.get("lb", False):
            self._move_shelf(self.selected_row_idx, -1)
            return True

        # RB: Mover estantería hacia abajo
        if inputs.get("rb", False) and not prev_inputs.get("rb", False):
            self._move_shelf(self.selected_row_idx, 1)
            return True

        # Botón X: Nueva Lista
        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self._prompt_new_collection()
            return True

        # Botón B o Back: Guardar y Salir
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self._save_and_close()
            return True

        return False
