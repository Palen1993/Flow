"""
On-Screen Keyboard (OSK) for GameFlow Launcher.
100% Gamepad & Handheld navigable Virtual Keyboard (SteamOS Big Picture / VisionOS style).
Allows editing text, paths, search filters, and arguments using D-Pad/Left Stick and Gamepad Buttons.
"""
from typing import Optional, Callable, List
import tkinter as tk
import customtkinter as ctk

from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_BTN_DANGER_BG, COLOR_BTN_DANGER_HOVER, COLOR_BTN_DANGER_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_DANGER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, font_title
)
from ui.controller_hud import get_button_icon_ctk
from gamepad_manager import get_connected_controller_family
from ui.dialogs.base_dialog import BaseGlassDialog
from core.feedback import feedback_click, trigger_haptic


class OnScreenKeyboardDialog(BaseGlassDialog):
    """
    Teclado Virtual en Pantalla estilo Liquid Glass / SteamOS Big Picture.
    Permite escribir textos cómodamente con mando o pantalla táctil en televisores y consolas portátiles.
    """
    W = 740
    H = 390

    def __init__(
        self,
        parent: Optional[tk.Widget],
        title: str = "Teclado en Pantalla",
        initial_text: str = "",
        on_confirm: Optional[Callable[[str], None]] = None,
        family: Optional[str] = None
    ):
        super().__init__(parent, title=title, width=self.W, height=self.H, corner_radius=22)
        self.on_confirm_cb = on_confirm
        self.family = family or getattr(parent, "_current_controller_family", None) or get_connected_controller_family()
        self.text_value = str(initial_text or "")
        
        self.is_uppercase = False
        self.is_symbols = False
        self.cursor_row = 1
        self.cursor_col = 0
        self._key_buttons = {}  # (row, col) -> CTkButton
        self._current_layout = []

        self._build_ui(title)
        self._bind_events()
        self._render_keyboard_matrix()
        self._update_focus_visuals()
        self.focus_set()

    def _build_ui(self, title: str):
        self.card = ctk.CTkFrame(
            self, width=self.W - 20, height=self.H - 20, corner_radius=22,
            fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER, border_width=1.5
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.pack_propagate(False)
        self.make_draggable(self.card)

        # 1. Cabecera con Título y visor del texto escrito
        head = ctk.CTkFrame(self.card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 4))

        self.lbl_title = ctk.CTkLabel(
            head, text=title, font=("Segoe UI Semibold", 14), text_color=COLOR_CYAN_ACCENT
        )
        self.lbl_title.pack(side="left")

        # 2. Caja de visualización del texto con cursor
        self.text_display_card = ctk.CTkFrame(
            self.card, fg_color=COLOR_BG_DARK, corner_radius=12,
            border_color=COLOR_GLASS_BORDER, border_width=1.2, height=44
        )
        self.text_display_card.pack(fill="x", padx=16, pady=(2, 8))
        self.text_display_card.pack_propagate(False)

        self.lbl_text = ctk.CTkLabel(
            self.text_display_card,
            text=self.text_value + " ▏",
            font=("Segoe UI Semibold", 17),
            text_color=COLOR_TEXT_WHITE,
            anchor="w"
        )
        self.lbl_text.pack(side="left", padx=14, fill="both", expand=True)

        # 3. Contenedor de la matriz del teclado
        self.keyboard_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.keyboard_frame.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # 4. Barra de Atajos de Mando Inferior (HUD)
        hud = ctk.CTkFrame(self.card, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=12, height=36)
        hud.pack(fill="x", padx=12, pady=(0, 10))
        hud.pack_propagate(False)

        hud_inner = ctk.CTkFrame(hud, fg_color="transparent")
        hud_inner.pack(expand=True)

        def _add_hud_item(btn_key: str, label_text: str):
            f = ctk.CTkFrame(hud_inner, fg_color="transparent")
            f.pack(side="left", padx=8)
            ic = get_button_icon_ctk(btn_key, self.family, size=16)
            if ic:
                ctk.CTkLabel(f, image=ic, text="").pack(side="left", padx=(0, 4))
            ctk.CTkLabel(f, text=label_text, font=font_body(11), text_color=COLOR_TEXT_MUTED_LIGHT).pack(side="left")

        _add_hud_item("a", "Escribir")
        _add_hud_item("x", "Borrar")
        _add_hud_item("y", "Espacio")
        _add_hud_item("lb", "Mayús")
        _add_hud_item("rt", "Símbolos")
        _add_hud_item("start", "Listo")
        _add_hud_item("b", "Cancelar")

    def _get_layout(self) -> List[List[str]]:
        if self.is_symbols:
            return [
                ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="],
                ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "_", "+"],
                ["~", "`", "{", "}", "[", "]", "\\", "/", ":", ";", "'", "\""],
                ["ABC", "<", ">", ",", ".", "?", "|", "BORRAR"],
                ["ABC", "ESPACIO", "LIMPIAR", "LISTO"]
            ]

        # Modo letras normales / mayúsculas
        shift = self.is_uppercase
        r0 = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="]
        r1 = [c.upper() if shift else c.lower() for c in ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"]]
        r2 = [c.upper() if shift else c.lower() for c in ["a", "s", "d", "f", "g", "h", "j", "k", "l", "_"]]
        r3 = ["MAYÚS"] + [c.upper() if shift else c.lower() for c in ["z", "x", "c", "v", "b", "n", "m", "."]] + ["BORRAR"]
        r4 = ["?123", "ESPACIO", "LIMPIAR", "LISTO"]
        return [r0, r1, r2, r3, r4]

    def _render_keyboard_matrix(self):
        # Limpiar botones anteriores
        for w in self.keyboard_frame.winfo_children():
            w.destroy()
        self._key_buttons.clear()

        self._current_layout = self._get_layout()

        for r_idx, row in enumerate(self._current_layout):
            row_frame = ctk.CTkFrame(self.keyboard_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)
            
            # Centrar fila de teclas
            row_inner = ctk.CTkFrame(row_frame, fg_color="transparent")
            row_inner.pack(anchor="center")

            for c_idx, key in enumerate(row):
                btn_w = 48
                btn_fg = COLOR_BTN_SECONDARY_BG
                btn_hover = COLOR_BTN_SECONDARY_HOVER
                btn_border = COLOR_BTN_SECONDARY_BORDER
                txt_col = COLOR_TEXT_MAIN
                fnt = font_button(13)

                if key in ("MAYÚS", "ABC"):
                    btn_w = 70
                    btn_fg = "#222c3d" if self.is_uppercase else COLOR_BTN_SECONDARY_BG
                    btn_border = COLOR_CYAN_ACCENT if self.is_uppercase else COLOR_BTN_SECONDARY_BORDER
                    txt_col = COLOR_CYAN_ACCENT if self.is_uppercase else COLOR_TEXT_MUTED_LIGHT
                    fnt = font_button(11)
                elif key == "?123":
                    btn_w = 70
                    fnt = font_button(11)
                    txt_col = COLOR_CYAN_ACCENT
                elif key == "BORRAR":
                    btn_w = 82
                    btn_fg = "#2c1c23"
                    btn_hover = COLOR_BTN_DANGER_HOVER
                    btn_border = "#442430"
                    txt_col = "#fca5a5"
                    fnt = font_button(11)
                elif key == "ESPACIO":
                    btn_w = 210
                    fnt = font_button(11)
                    txt_col = COLOR_TEXT_MUTED_LIGHT
                elif key == "LIMPIAR":
                    btn_w = 78
                    btn_fg = "#282024"
                    txt_col = COLOR_TEXT_MUTED
                    fnt = font_button(11)
                elif key == "LISTO":
                    btn_w = 90
                    btn_fg = COLOR_IOS_BLUE
                    btn_hover = COLOR_IOS_BLUE_HOVER
                    btn_border = COLOR_IOS_BLUE_BORDER
                    txt_col = COLOR_TEXT_WHITE
                    fnt = font_button(12)

                btn = ctk.CTkButton(
                    row_inner,
                    text=key,
                    width=btn_w,
                    height=36,
                    corner_radius=9,
                    fg_color=btn_fg,
                    hover_color=btn_hover,
                    border_color=btn_border,
                    border_width=1.0,
                    text_color=txt_col,
                    font=fnt,
                    command=lambda k=key: self._on_key_clicked(k)
                )
                btn.pack(side="left", padx=2)
                self._key_buttons[(r_idx, c_idx)] = btn

    def _update_focus_visuals(self):
        if not self._current_layout:
            return
        
        # Clampear índices a la matriz actual
        self.cursor_row = max(0, min(len(self._current_layout) - 1, self.cursor_row))
        cur_row_len = len(self._current_layout[self.cursor_row])
        self.cursor_col = max(0, min(cur_row_len - 1, self.cursor_col))

        for (r, c), btn in self._key_buttons.items():
            if not btn.winfo_exists():
                continue
            is_foc = (r == self.cursor_row and c == self.cursor_col)
            key_text = self._current_layout[r][c]

            if is_foc:
                btn.configure(
                    border_color=COLOR_CYAN_ACCENT,
                    border_width=2.5,
                    fg_color="#1d283c" if key_text != "LISTO" else COLOR_IOS_BLUE_HOVER,
                    text_color=COLOR_TEXT_WHITE
                )
            else:
                # Restaurar aspecto normal
                btn_fg = COLOR_BTN_SECONDARY_BG
                btn_border = COLOR_BTN_SECONDARY_BORDER
                txt_col = COLOR_TEXT_MAIN

                if key_text in ("MAYÚS", "ABC"):
                    btn_fg = "#222c3d" if self.is_uppercase else COLOR_BTN_SECONDARY_BG
                    btn_border = COLOR_CYAN_ACCENT if self.is_uppercase else COLOR_BTN_SECONDARY_BORDER
                    txt_col = COLOR_CYAN_ACCENT if self.is_uppercase else COLOR_TEXT_MUTED_LIGHT
                elif key_text == "BORRAR":
                    btn_fg = "#2c1c23"
                    btn_border = "#442430"
                    txt_col = "#fca5a5"
                elif key_text == "LISTO":
                    btn_fg = COLOR_IOS_BLUE
                    btn_border = COLOR_IOS_BLUE_BORDER
                    txt_col = COLOR_TEXT_WHITE

                btn.configure(
                    border_color=btn_border,
                    border_width=1.0,
                    fg_color=btn_fg,
                    text_color=txt_col
                )

    def _update_text_display(self):
        txt = self.text_value
        if not txt:
            self.lbl_text.configure(text="Escribe aquí... ▏", text_color=COLOR_TEXT_DIM)
        else:
            self.lbl_text.configure(text=txt + " ▏", text_color=COLOR_TEXT_WHITE)

    def _on_key_clicked(self, key: str):
        try:
            feedback_click()
        except Exception:
            pass

        if key in ("MAYÚS", "ABC"):
            self.is_uppercase = not self.is_uppercase
            self._render_keyboard_matrix()
            self._update_focus_visuals()
            return

        if key in ("?123", "SÍMBOLOS"):
            self.is_symbols = not self.is_symbols
            self._render_keyboard_matrix()
            self._update_focus_visuals()
            return

        if key == "BORRAR":
            self.action_backspace()
            return

        if key == "ESPACIO":
            self.action_space()
            return

        if key == "LIMPIAR":
            self.text_value = ""
            self._update_text_display()
            return

        if key == "LISTO":
            self.action_confirm()
            return

        # Tecla de carácter regular
        self.text_value += key
        self._update_text_display()

        # Si estaba en mayúscula de un solo uso, podemos mantener o revertir
        if self.is_uppercase and key.isalpha():
            # Auto-revertir a minúsculas estilo teclado de teléfono
            self.is_uppercase = False
            self._render_keyboard_matrix()
            self._update_focus_visuals()

    def action_backspace(self):
        if self.text_value:
            self.text_value = self.text_value[:-1]
            self._update_text_display()
            try:
                feedback_click()
                trigger_haptic(left=12000, right=24000, duration_ms=40)
            except Exception:
                pass

    def action_space(self):
        self.text_value += " "
        self._update_text_display()
        try:
            feedback_click()
        except Exception:
            pass

    def action_confirm(self):
        final_text = self.text_value
        self.close()
        if self.on_confirm_cb:
            try:
                self.on_confirm_cb(final_text)
            except Exception:
                pass

    def close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _bind_events(self):
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Return>", lambda e: self.action_confirm())
        self.bind("<BackSpace>", lambda e: self.action_backspace())
        self.bind("<Left>", lambda e: self._move_cursor(0, -1))
        self.bind("<Right>", lambda e: self._move_cursor(0, 1))
        self.bind("<Up>", lambda e: self._move_cursor(-1, 0))
        self.bind("<Down>", lambda e: self._move_cursor(1, 0))

        # Captura de caracteres físicos de teclado si el usuario teclea
        def _on_char(event):
            if event.char and event.char.isprintable() and event.char not in ("\r", "\n", "\t"):
                self.text_value += event.char
                self._update_text_display()

        self.bind("<Key>", _on_char, add="+")

    def _move_cursor(self, delta_row: int, delta_col: int):
        if not self._current_layout:
            return
        self.cursor_row = max(0, min(len(self._current_layout) - 1, self.cursor_row + delta_row))
        cur_row_len = len(self._current_layout[self.cursor_row])
        self.cursor_col = max(0, min(cur_row_len - 1, self.cursor_col + delta_col))
        self._update_focus_visuals()
        try:
            feedback_click()
        except Exception:
            pass

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        """Despacho directo desde el bucle de mando (O(1) modal stack)."""
        # Cancelar / Salir con botón B
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self.close()
            return True

        # Confirmar con botón Start
        if inputs.get("start", False) and not prev_inputs.get("start", False):
            self.action_confirm()
            return True

        # Borrado rápido con botón X
        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self.action_backspace()
            return True

        # Espacio rápido con botón Y
        if inputs.get("y", False) and not prev_inputs.get("y", False):
            self.action_space()
            return True

        # Alternar Mayúsculas con LB o RB
        if (inputs.get("lb", False) and not prev_inputs.get("lb", False)) or \
           (inputs.get("rb", False) and not prev_inputs.get("rb", False)):
            self.is_uppercase = not self.is_uppercase
            self._render_keyboard_matrix()
            self._update_focus_visuals()
            try:
                feedback_click()
            except Exception:
                pass
            return True

        # Alternar Símbolos con LT o RT
        if (inputs.get("lt", False) and not prev_inputs.get("lt", False)) or \
           (inputs.get("rt", False) and not prev_inputs.get("rt", False)):
            self.is_symbols = not self.is_symbols
            self._render_keyboard_matrix()
            self._update_focus_visuals()
            try:
                feedback_click()
            except Exception:
                pass
            return True

        # Pulsar la tecla actual con botón A
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            if self._current_layout and 0 <= self.cursor_row < len(self._current_layout):
                row = self._current_layout[self.cursor_row]
                if 0 <= self.cursor_col < len(row):
                    key = row[self.cursor_col]
                    self._on_key_clicked(key)
            return True

        # Navegación en cruz / joystick
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._move_cursor(-1, 0)
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self._move_cursor(1, 0)
            return True
        if inputs.get("left", False) and not prev_inputs.get("left", False):
            self._move_cursor(0, -1)
            return True
        if inputs.get("right", False) and not prev_inputs.get("right", False):
            self._move_cursor(0, 1)
            return True

        return True


def prompt_on_screen_keyboard(
    parent: Optional[tk.Widget],
    title: str = "Teclado en Pantalla",
    initial_text: str = "",
    on_confirm: Optional[Callable[[str], None]] = None,
    family: Optional[str] = None
) -> OnScreenKeyboardDialog:
    """Función de conveniencia para invocar el teclado virtual desde cualquier parte de la aplicación."""
    return OnScreenKeyboardDialog(parent, title=title, initial_text=initial_text, on_confirm=on_confirm, family=family)
