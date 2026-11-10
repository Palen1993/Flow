import tkinter as tk
from typing import List, Dict, Any, Optional, Callable, Tuple
import customtkinter as ctk

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.controller_hud import get_button_icon_ctk
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, apply_gamepad_focus, scroll_to_widget
)


class CollectionsFilterDialog(BaseGlassDialog):
    """
    Diálogo Glassmorphism para seleccionar rápidamente colecciones y filtros de biblioteca
    (Todos, Favoritos, Estados, Plataformas y Géneros). 100% navegable con mando de consola.
    """

    def __init__(
        self,
        parent,
        filters: List[Dict[str, Any]],
        current_filter_id: str = "all",
        on_select_filter: Optional[Callable[[str], None]] = None
    ):
        super().__init__(parent, title="🏷 Colecciones y Filtros", width=760, height=560, corner_radius=24)
        self.filters = filters
        self.current_filter_id = current_filter_id
        self.on_select_filter = on_select_filter
        self.family = getattr(parent, "_current_controller_family", "xbox")

        self._filter_buttons: List[Tuple[str, ctk.CTkButton]] = []
        self._selected_card_idx = 0

        self.create_widgets()
        self._highlight_active_filter()

    _center_window = BaseGlassDialog.center_window

    def create_widgets(self):
        # Tarjeta principal con efecto iOS Liquid Glass
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)

        # Cabecera arrastrable
        header_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=42)
        header_bar.pack(fill="x", padx=20, pady=(14, 4))

        lbl_title = ctk.CTkLabel(
            header_bar,
            text="🏷  Colecciones y Filtros de Biblioteca",
            font=font_button(17),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")

        # Subtítulo explicativo con atajos de mando
        sub_text = "Cruceta: Navegar  │  (A): Seleccionar  │  (B): Cerrar  │  Atajo rápido: (LB / RB)"
        lbl_sub = ctk.CTkLabel(
            self.main_card,
            text=sub_text,
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        lbl_sub.pack(anchor="w", padx=24, pady=(0, 8))

        for w in (header_bar, lbl_title, self.main_card):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # Contenedor desplazable de colecciones
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.main_card,
            fg_color="transparent",
            corner_radius=14
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=16, pady=4)
        self.scroll_frame.grid_columnconfigure(0, weight=1)
        self.scroll_frame.grid_columnconfigure(1, weight=1)

        # Agrupar filtros por categoría
        grouped: Dict[str, List[Dict[str, Any]]] = {
            "general": [],
            "favorite": [],
            "status": [],
            "platform": [],
            "genre": []
        }
        for f in self.filters:
            cat = f.get("category", "general")
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(f)

        row_idx = 0

        # Helper para dibujar secciones
        def add_section(title: str, items: List[Dict[str, Any]]):
            nonlocal row_idx
            if not items:
                return

            lbl_sec = ctk.CTkLabel(
                self.scroll_frame,
                text=title,
                font=font_button(13),
                text_color=COLOR_CYAN_ACCENT
            )
            lbl_sec.grid(row=row_idx, column=0, columnspan=2, sticky="w", padx=8, pady=(12, 4))
            row_idx += 1

            for i, item in enumerate(items):
                f_id = item["id"]
                label = item.get("label", f_id)
                icon = item.get("icon", "🏷️")
                count = item.get("count", 0)
                is_active = (f_id == self.current_filter_id)

                btn_text = f"  {icon}  {label}   ({count})"
                btn = ctk.CTkButton(
                    self.scroll_frame,
                    text=btn_text,
                    height=44,
                    anchor="w",
                    fg_color=COLOR_IOS_BLUE if is_active else COLOR_BG_CARD_SECONDARY,
                    hover_color=COLOR_IOS_BLUE_HOVER if is_active else COLOR_GLASS_HOVER,
                    border_color=COLOR_IOS_BLUE_BORDER if is_active else COLOR_BORDER_CARD,
                    border_width=1.5 if is_active else 1.0,
                    corner_radius=14,
                    text_color=COLOR_TEXT_WHITE if is_active else COLOR_TEXT_BRIGHT,
                    font=font_button(12),
                    command=lambda fid=f_id: self._select_filter_and_close(fid)
                )
                col = i % 2
                btn.grid(row=row_idx, column=col, sticky="ew", padx=6, pady=4)
                self._filter_buttons.append((f_id, btn))

                if col == 1 or i == len(items) - 1:
                    row_idx += 1

        # 1. Colecciones Principales
        main_items = grouped.get("general", []) + grouped.get("favorite", [])
        add_section("★ Colecciones Principales", main_items)

        # 2. Por Estado
        add_section("⏳ Por Estado de Juego", grouped.get("status", []))

        # 3. Por Plataforma
        add_section("🕹️ Por Plataforma", grouped.get("platform", []))

        # 4. Por Género
        add_section("🏷️ Por Género", grouped.get("genre", []))

        # Barra inferior de cierre
        btn_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(10, 16))

        self.btn_close = ctk.CTkButton(
            btn_frame,
            text="Volver ",
            image=get_button_icon_ctk("b", self.family, size=18),
            compound="right",
            width=130,
            height=38,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1.0,
            corner_radius=19,
            text_color=COLOR_TEXT_MUTED_LIGHT,
            font=font_button(12),
            command=self.destroy
        )
        self.btn_close.pack(side="right")

    def _highlight_active_filter(self):
        # Localizar el índice inicial de selección basado en el filtro activo
        for idx, (f_id, btn) in enumerate(self._filter_buttons):
            if f_id == self.current_filter_id:
                self._selected_card_idx = idx
                self._update_focus()
                scroll_to_widget(self.scroll_frame, btn)
                return

        if self._filter_buttons:
            self._selected_card_idx = 0
            self._update_focus()

    def _update_focus(self):
        for idx, (f_id, btn) in enumerate(self._filter_buttons):
            is_foc = (idx == self._selected_card_idx)
            is_active = (f_id == self.current_filter_id)
            if is_foc:
                apply_gamepad_focus(btn, True, role="primary" if is_active else "secondary")
            else:
                apply_gamepad_focus(btn, False, role="primary" if is_active else "secondary")

    def _select_filter_and_close(self, filter_id: str):
        try:
            from core.feedback import feedback_click
            feedback_click()
        except Exception:
            pass

        if self.on_select_filter:
            self.on_select_filter(filter_id)
        self.destroy()

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        # B o Back: Cerrar
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.destroy()
            return True

        n = len(self._filter_buttons)
        if n == 0:
            return False

        cur = self._selected_card_idx

        # D-pad Arriba
        if inputs.get("dpad_up", False) and not prev_inputs.get("dpad_up", False):
            self._selected_card_idx = max(0, cur - 2)
            self._update_focus()
            scroll_to_widget(self.scroll_frame, self._filter_buttons[self._selected_card_idx][1])
            return True

        # D-pad Abajo
        if inputs.get("dpad_down", False) and not prev_inputs.get("dpad_down", False):
            self._selected_card_idx = min(n - 1, cur + 2)
            self._update_focus()
            scroll_to_widget(self.scroll_frame, self._filter_buttons[self._selected_card_idx][1])
            return True

        # D-pad Izquierda
        if inputs.get("dpad_left", False) and not prev_inputs.get("dpad_left", False):
            if cur % 2 == 1:
                self._selected_card_idx = cur - 1
                self._update_focus()
                scroll_to_widget(self.scroll_frame, self._filter_buttons[self._selected_card_idx][1])
                return True

        # D-pad Derecha
        if inputs.get("dpad_right", False) and not prev_inputs.get("dpad_right", False):
            if cur % 2 == 0 and cur + 1 < n:
                self._selected_card_idx = cur + 1
                self._update_focus()
                scroll_to_widget(self.scroll_frame, self._filter_buttons[self._selected_card_idx][1])
                return True

        # Botón A: Confirmar selección
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            if 0 <= cur < n:
                target_f_id = self._filter_buttons[cur][0]
                self._select_filter_and_close(target_f_id)
            return True

        return False
