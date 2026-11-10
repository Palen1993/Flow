import os
import sys
import tkinter as tk
from tkinter import filedialog
import customtkinter as ctk
from typing import Optional, List

from ui.theme import (
    font_button, font_body, scroll_to_widget,
    COLOR_BG_CARD, COLOR_BG_DARK, COLOR_GLASS_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_LIGHT, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT,
    COLOR_TEXT_MUTED, COLOR_TEXT_MUTED_LIGHT,
    COLOR_CYAN_ACCENT,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_STATUS_DANGER, COLOR_BG_INPUT_ACTIVE
)
from ui.controller_hud import get_button_icon_ctk
from gamepad_manager import get_connected_controller_family
from ui.dialogs.base_dialog import BaseGlassDialog


class GlassFolderBrowserDialog(BaseGlassDialog):
    """
    Explorador de carpetas y archivos estilo Glassmorphism navegable 100% con mando (D-Pad, A, B, X, Start, LB, RB, Y),
    teclado y ratón. Permite seleccionar carpetas de juegos o archivos (.exe, imágenes)
    sin necesidad de ratón en televisores, sofás o consolas portátiles.
    """
    W = 780
    H = 580

    def __init__(
        self,
        parent: Optional[tk.Widget],
        title: str = "Seleccionar Carpeta",
        initial_dir: Optional[str] = None,
        select_mode: str = "folder",  # 'folder' o 'file'
        file_extensions: Optional[List[str]] = None,
        family: Optional[str] = None
    ):
        self.selected_path: Optional[str] = None
        self.select_mode = select_mode
        self.file_extensions = [ext.lower() for ext in file_extensions] if file_extensions else None
        self.family = family or getattr(parent, "_current_controller_family", None) or get_connected_controller_family()

        # Detección de unidades de disco disponibles
        self.drives = self._detect_logical_drives()

        # Determinar directorio inicial válido (priorizar D:\Juegos si existe y no hay inicial)
        if initial_dir and os.path.isdir(initial_dir):
            self.current_path = os.path.abspath(initial_dir)
        elif initial_dir and os.path.isfile(initial_dir):
            self.current_path = os.path.dirname(os.path.abspath(initial_dir))
        elif os.path.isdir("D:\\Juegos"):
            self.current_path = "D:\\Juegos"
        elif os.path.isdir("D:\\"):
            self.current_path = "D:\\"
        else:
            self.current_path = "C:\\"

        super().__init__(parent, title=title, width=self.W, height=self.H, corner_radius=22)

        # Elementos en la lista: tuplas (tipo: 'up'|'dir'|'file', nombre_visible, ruta_completa)
        self._items: List[tuple] = []
        self._item_buttons: List[ctk.CTkButton] = []
        self._drive_buttons: dict = {}
        self._selected_index = 0

        self._build_ui(title)
        self._bind_events()
        self._refresh_contents()
        self.focus_set()

    def _detect_logical_drives(self) -> List[str]:
        from core.platform_layer import get_system_drives
        drives = get_system_drives()
        return drives if drives else ["/"]

    def _build_ui(self, title: str):
        pad = max(6, int(10 * self.scale_factor))
        self.card = ctk.CTkFrame(
            self, corner_radius=self.corner_radius,
            fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER, border_width=1.5
        )
        self.card.pack(fill="both", expand=True, padx=pad, pady=pad)
        self.make_draggable(self.card)

        # 1. Cabecera
        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 6))
        self.make_draggable(header)

        icon_hdr = "📁" if self.select_mode == "folder" else "🎮"
        lbl_t = ctk.CTkLabel(
            header, text=f"{icon_hdr}  {title}",
            font=("Segoe UI Semibold", 16), text_color=COLOR_TEXT_MAIN
        )
        lbl_t.pack(side="left")

        # Acceso rápido a carpeta Juegos con (Y)
        has_games_dir = os.path.isdir("D:\\Juegos") or os.path.isdir(os.path.expanduser("~\\Games"))
        btn_quick_txt = "📁 Ir a Juegos " if has_games_dir else "📁 Ir a Inicio "
        self.btn_quick_games = ctk.CTkButton(
            header, text=btn_quick_txt, width=130, height=28,
            image=get_button_icon_ctk("y", self.family, size=16), compound="right",
            corner_radius=14, font=font_button(11), fg_color="#1e2434",
            hover_color="#2a3348", text_color=COLOR_CYAN_ACCENT,
            command=self._jump_to_games_folder
        )
        self.btn_quick_games.pack(side="right", padx=(6, 0))

        btn_native = ctk.CTkButton(
            header, text="🗁 Windows", width=95, height=28,
            corner_radius=14, font=font_button(10), fg_color="#181e2b",
            hover_color="#242d3d", text_color=COLOR_TEXT_MUTED,
            command=self._use_native_picker
        )
        btn_native.pack(side="right")

        # 2. Barra de Unidades y Ruta Actual
        self.drive_bar = ctk.CTkFrame(self.card, fg_color="#10141d", corner_radius=12,
                                     border_width=1, border_color="#232b3c")
        self.drive_bar.pack(fill="x", padx=18, pady=(0, 6))

        drives_left = ctk.CTkFrame(self.drive_bar, fg_color="transparent")
        drives_left.pack(side="left", padx=4, pady=4)

        for d in self.drives:
            d_btn = ctk.CTkButton(
                drives_left, text=f"💾 {d}", width=70, height=28,
                corner_radius=10, font=font_button(11), fg_color="#1b212f",
                hover_color="#007aff", text_color=COLOR_TEXT_LIGHT,
                command=lambda p=d: self._change_directory(p)
            )
            d_btn.pack(side="left", padx=3)
            self._drive_buttons[d.upper()] = d_btn

        # Indicador de mando para cambiar de disco (RB)
        drive_hint = ctk.CTkLabel(
            self.drive_bar,
            text="Cambiar Disco ",
            image=get_button_icon_ctk("rb", self.family, size=16),
            compound="right",
            font=font_button(11),
            text_color="#64748b"
        )
        drive_hint.pack(side="right", padx=10, pady=4)

        # Ruta actual visible
        self.lbl_path = ctk.CTkLabel(
            self.card, text=f"📂  {self.current_path}", font=font_body(12),
            text_color=COLOR_CYAN_ACCENT, anchor="w"
        )
        self.lbl_path.pack(fill="x", padx=20, pady=(0, 6))

        # 3. Lista desplazable de carpetas / archivos
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.card, fg_color=COLOR_BG_DARK, corner_radius=14,
            border_width=1, border_color="#202533"
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        # 4. Barra inferior de confirmación y acciones
        footer = ctk.CTkFrame(self.card, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))

        btn_cancel = ctk.CTkButton(
            footer, text="Cancelar ", image=get_button_icon_ctk("b", self.family, size=18),
            compound="right", width=115, height=38, corner_radius=19,
            font=font_button(12), fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0, text_color=COLOR_TEXT_MUTED_LIGHT,
            command=self._on_cancel
        )
        btn_cancel.pack(side="left")

        btn_up_footer = ctk.CTkButton(
            footer, text="Subir Nivel ", image=get_button_icon_ctk("lb", self.family, size=18),
            compound="right", width=125, height=38, corner_radius=19,
            font=font_button(12), fg_color="#181e2b", hover_color="#242c3d",
            border_color="#2e384d", border_width=1.0, text_color="#38bdf8",
            command=self._go_up_directory
        )
        btn_up_footer.pack(side="left", padx=8)

        # Botón confirmar selección principal (Start / X)
        action_txt = "✓ Seleccionar Carpeta " if self.select_mode == "folder" else "✓ Seleccionar Archivo "
        self.btn_confirm_selection = ctk.CTkButton(
            footer, text=action_txt,
            image=get_button_icon_ctk("start", self.family, size=18), compound="right",
            height=38, corner_radius=19, font=font_button(12),
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER, border_width=1.2, text_color=COLOR_TEXT_WHITE,
            command=self._confirm_selection
        )
        self.btn_confirm_selection.pack(side="right")

        # Botón entrar en carpeta (A)
        self.btn_open = ctk.CTkButton(
            footer, text="Abrir / Entrar ", image=get_button_icon_ctk("a", self.family, size=18),
            compound="right", width=140, height=38, corner_radius=19,
            font=font_button(12), fg_color="#222838", hover_color="#2b3448",
            border_color="#38435d", border_width=1.0, text_color=COLOR_TEXT_BRIGHT,
            command=self._activate_selected_item
        )
        self.btn_open.pack(side="right", padx=8)

        self._drag_x = 0
        self._drag_y = 0
        for w_elem in (self.card, header, lbl_t):
            w_elem.bind("<ButtonPress-1>", self._start_drag)
            w_elem.bind("<B1-Motion>", self._on_drag)

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _bind_events(self):
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Up>", lambda e: self._navigate_list(-1))
        self.bind("<Down>", lambda e: self._navigate_list(1))
        self.bind("<Return>", lambda e: self._activate_selected_item())
        self.bind("<BackSpace>", lambda e: self._go_up_directory())

    def _update_drive_buttons_highlight(self):
        cur_drv = os.path.splitdrive(self.current_path)[0].upper() + "\\"
        for drv_key, btn in self._drive_buttons.items():
            if drv_key == cur_drv:
                btn.configure(
                    fg_color=COLOR_IOS_BLUE,
                    text_color=COLOR_TEXT_WHITE,
                    border_color="#ffffff",
                    border_width=2
                )
            else:
                btn.configure(
                    fg_color="#1b212f",
                    text_color=COLOR_TEXT_LIGHT,
                    border_width=0
                )

    def _cycle_drive(self, delta: int = 1):
        if not self.drives:
            return
        cur_drv = os.path.splitdrive(self.current_path)[0].upper() + "\\"
        try:
            norm_drives = [d.upper() for d in self.drives]
            idx = norm_drives.index(cur_drv) if cur_drv in norm_drives else 0
        except Exception:
            idx = 0
        next_drv = self.drives[(idx + delta) % len(self.drives)]
        self._change_directory(next_drv)
        try:
            from core.feedback import feedback_click
            feedback_click()
        except Exception:
            pass

    def _jump_to_games_folder(self):
        if os.path.isdir("D:\\Juegos"):
            target = "D:\\Juegos"
        elif os.path.isdir(os.path.expanduser("~\\Games")):
            target = os.path.expanduser("~\\Games")
        elif os.path.isdir("D:\\"):
            target = "D:\\"
        else:
            target = "C:\\"
        self._change_directory(target)
        try:
            from core.feedback import feedback_select
            feedback_select()
        except Exception:
            pass

    def _change_directory(self, new_dir: str):
        if os.path.isdir(new_dir):
            self.current_path = os.path.abspath(new_dir)
            self._selected_index = 0
            self._refresh_contents()

    def _go_up_directory(self):
        parent = os.path.dirname(self.current_path)
        if parent and parent != self.current_path and os.path.isdir(parent):
            self._change_directory(parent)
            try:
                from core.feedback import feedback_click
                feedback_click()
            except Exception:
                pass

    PAGE_SIZE = 60

    def _refresh_contents(self):
        self.lbl_path.configure(text=f"📂  {self.current_path}")
        self._update_drive_buttons_highlight()

        for w in self.scroll_frame.winfo_children():
            w.destroy()

        self._items.clear()
        self._item_buttons.clear()
        self._pending_entries = []
        self._load_more_btn = None
        self._prev_selected_index = -1

        # Botón subir nivel (..)
        parent_dir = os.path.dirname(self.current_path)
        has_parent = (parent_dir and parent_dir != self.current_path)
        if has_parent:
            self._items.append(("up", "..", parent_dir))
            btn_up = ctk.CTkButton(
                self.scroll_frame, text="  📁  ..  (Subir nivel) ",
                image=get_button_icon_ctk("lb", self.family, size=16), compound="right",
                anchor="w", height=36, corner_radius=10, font=font_button(12),
                fg_color="#181e2b", hover_color="#242c3d", text_color=COLOR_CYAN_ACCENT,
                command=self._go_up_directory
            )
            btn_up.pack(fill="x", padx=4, pady=2)
            self._item_buttons.append(btn_up)

        subdirs = []
        files = []
        try:
            with os.scandir(self.current_path) as entries:
                for entry in entries:
                    try:
                        name_low = entry.name.lower()
                        if name_low in ("$recycle.bin", "system volume information", "recovery") or entry.name.startswith("."):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            subdirs.append(entry.name)
                        elif self.select_mode == "file" and entry.is_file(follow_symlinks=False):
                            if not self.file_extensions or any(name_low.endswith(ext) for ext in self.file_extensions):
                                files.append(entry.name)
                    except Exception:
                        pass
        except PermissionError:
            lbl_err = ctk.CTkLabel(
                self.scroll_frame, text="⚠️ Acceso denegado por permisos de Windows",
                font=font_body(12), text_color=COLOR_STATUS_DANGER
            )
            lbl_err.pack(pady=30)
            return
        except Exception as e:
            lbl_err = ctk.CTkLabel(
                self.scroll_frame, text=f"Error: {e}",
                font=font_body(12), text_color=COLOR_STATUS_DANGER
            )
            lbl_err.pack(pady=30)
            return

        subdirs.sort(key=lambda s: s.lower())
        files.sort(key=lambda s: s.lower())

        if not subdirs and not files:
            lbl_empty = ctk.CTkLabel(
                self.scroll_frame,
                text="📂 Carpeta vacía o sin archivos coincidentes.\nPulsa Start o X para seleccionarla, o LB para subir de nivel.",
                font=font_body(12), text_color=COLOR_TEXT_MUTED
            )
            lbl_empty.pack(pady=30)

        for f_name in subdirs:
            self._pending_entries.append(("dir", f_name, os.path.join(self.current_path, f_name)))
        for f_name in files:
            self._pending_entries.append(("file", f_name, os.path.join(self.current_path, f_name)))

        self._load_next_page(initial=True)

    def _create_entry_button(self, entry_type: str, f_name: str, full_p: str, item_idx: int) -> ctk.CTkButton:
        if entry_type == "dir":
            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"  📁  {f_name}",
                anchor="w",
                height=36,
                corner_radius=10,
                font=font_body(12),
                fg_color="transparent",
                hover_color="#222838",
                text_color=COLOR_TEXT_LIGHT,
                command=lambda p=full_p: self._change_directory(p)
            )
            btn.pack(fill="x", padx=4, pady=1)
            btn.bind("<Double-Button-1>", lambda e, p=full_p: self._change_directory(p))
        else:
            f_icon = "🎮" if f_name.lower().endswith(".exe") else "🖼️"
            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"  {f_icon}  {f_name}",
                anchor="w",
                height=36,
                corner_radius=10,
                font=font_body(12),
                fg_color="transparent",
                hover_color="#1d263b",
                text_color="#93c5fd" if f_name.lower().endswith(".exe") else "#a7f3d0",
                command=lambda p=full_p: self._select_file_item(p)
            )
            btn.pack(fill="x", padx=4, pady=1)
            btn.bind("<Double-Button-1>", lambda e, p=full_p: self._confirm_file_path(p))

        btn.bind("<Button-1>", lambda e, i=item_idx: self._on_click_item(i))
        btn.bind("<Enter>", lambda e, i=item_idx: self._on_hover(i))
        return btn

    def _load_next_page(self, initial: bool = False):
        if self._load_more_btn is not None:
            try:
                if self._items and self._items[-1][0] == "load_more":
                    self._items.pop()
                if self._item_buttons and self._item_buttons[-1] == self._load_more_btn:
                    self._item_buttons.pop()
                self._load_more_btn.destroy()
            except Exception:
                pass
            self._load_more_btn = None
            self._prev_selected_index = -1

        batch = self._pending_entries[:self.PAGE_SIZE]
        self._pending_entries = self._pending_entries[self.PAGE_SIZE:]

        for entry_type, f_name, full_p in batch:
            item_idx = len(self._items)
            self._items.append((entry_type, f_name, full_p))
            btn = self._create_entry_button(entry_type, f_name, full_p, item_idx)
            self._item_buttons.append(btn)

        if self._pending_entries:
            more_idx = len(self._items)
            rem = len(self._pending_entries)
            self._items.append(("load_more", f"Mostrar {min(self.PAGE_SIZE, rem)} más ({rem} restantes)...", ""))
            btn_more = ctk.CTkButton(
                self.scroll_frame,
                text=f"  ➕  Mostrar más elementos ({rem} restantes)...",
                anchor="center",
                height=36,
                corner_radius=10,
                font=font_button(12),
                fg_color="#181e2b",
                hover_color="#242c3d",
                text_color=COLOR_CYAN_ACCENT,
                command=lambda: self._load_next_page(initial=False)
            )
            btn_more.pack(fill="x", padx=4, pady=4)
            btn_more.bind("<Enter>", lambda e, i=more_idx: self._on_hover(i))
            self._item_buttons.append(btn_more)
            self._load_more_btn = btn_more

        self._update_selection(scroll=not initial)

    def _on_click_item(self, idx: int):
        self._selected_index = idx
        self._update_selection(scroll=False)

    def _on_hover(self, idx: int):
        if idx == self._selected_index:
            return
        self._selected_index = idx
        self._update_selection(scroll=False)

    def _style_button_default(self, idx: int):
        if not (0 <= idx < len(self._item_buttons)):
            return
        b = self._item_buttons[idx]
        item_type = self._items[idx][0] if idx < len(self._items) else "dir"
        is_special = item_type in ("up", "load_more")
        is_file = (item_type == "file")
        def_color = "#38bdf8" if is_special else ("#93c5fd" if is_file else "#e2e8f0")
        b.configure(
            fg_color="#181e2b" if is_special else "transparent",
            border_width=0,
            text_color=def_color
        )

    def _update_selection(self, scroll: bool = True):
        prev = getattr(self, "_prev_selected_index", -1)
        if prev != self._selected_index and 0 <= prev < len(self._item_buttons):
            self._style_button_default(prev)
        elif prev == -1:
            for i in range(len(self._item_buttons)):
                if i != self._selected_index:
                    self._style_button_default(i)

        if 0 <= self._selected_index < len(self._item_buttons):
            b = self._item_buttons[self._selected_index]
            b.configure(
                fg_color="#1e3a5f",
                border_color="#00e5ff",
                border_width=3,
                text_color=COLOR_TEXT_WHITE
            )
            if scroll:
                scroll_to_widget(self.scroll_frame, b)
        self._prev_selected_index = self._selected_index

        # Actualizar texto del botón de confirmación según el elemento enfocado
        if self._items and 0 <= self._selected_index < len(self._items):
            item_type, name, _ = self._items[self._selected_index]
            if item_type == "dir":
                disp_name = (name[:22] + "...") if len(name) > 25 else name
                self.btn_confirm_selection.configure(text=f"✓ Seleccionar '{disp_name}' ")
                self.btn_open.configure(state="normal", text="Abrir / Entrar ")
            elif item_type == "up":
                cur_name = os.path.basename(self.current_path) or self.current_path
                disp_name = (cur_name[:20] + "...") if len(cur_name) > 23 else cur_name
                self.btn_confirm_selection.configure(text=f"✓ Seleccionar '{disp_name}' ")
                self.btn_open.configure(state="normal", text="Subir Nivel ")
            elif item_type == "load_more":
                cur_name = os.path.basename(self.current_path) or self.current_path
                disp_name = (cur_name[:20] + "...") if len(cur_name) > 23 else cur_name
                self.btn_confirm_selection.configure(text=f"✓ Seleccionar '{disp_name}' ")
                self.btn_open.configure(state="normal", text="Cargar Más ")
            elif item_type == "file":
                self.btn_confirm_selection.configure(text="✓ Seleccionar Archivo ")
                self.btn_open.configure(state="normal", text="Elegir ")
        else:
            cur_name = os.path.basename(self.current_path) or self.current_path
            disp_name = (cur_name[:20] + "...") if len(cur_name) > 23 else cur_name
            self.btn_confirm_selection.configure(text=f"✓ Seleccionar '{disp_name}' ")
            self.btn_open.configure(state="disabled")

    def _navigate_list(self, delta: int):
        if not self._item_buttons:
            return
        n = len(self._item_buttons)
        self._selected_index = max(0, min(n - 1, self._selected_index + delta))
        self._update_selection(scroll=True)
        try:
            from core.feedback import feedback_click
            feedback_click()
        except Exception:
            pass

    def _activate_selected_item(self):
        if not self._items or self._selected_index >= len(self._items):
            return
        item_type, _name, full_p = self._items[self._selected_index]
        if item_type == "up":
            self._go_up_directory()
        elif item_type == "load_more":
            self._load_next_page(initial=False)
        elif item_type == "dir":
            self._change_directory(full_p)
            try:
                from core.feedback import feedback_select
                feedback_select()
            except Exception:
                pass
        elif item_type == "file":
            self._confirm_file_path(full_p)

    def _select_file_item(self, file_path: str):
        if self.select_mode == "file":
            self._confirm_file_path(file_path)

    def _confirm_file_path(self, file_path: str):
        self.selected_path = file_path
        try:
            from core.feedback import feedback_menu
            feedback_menu()
        except Exception:
            pass
        self._close()

    def _confirm_selection(self):
        if self.select_mode == "folder":
            # Si el elemento enfocado es una subcarpeta ('dir'), el usuario desea seleccionar esa subcarpeta
            if self._items and 0 <= self._selected_index < len(self._items):
                item_type, _name, full_p = self._items[self._selected_index]
                if item_type == "dir" and os.path.isdir(full_p):
                    self.selected_path = full_p
                    try:
                        from core.feedback import feedback_menu
                        feedback_menu()
                    except Exception:
                        pass
                    self._close()
                    return

            # De lo contrario (ej: está sobre 'up' o lista vacía), seleccionar la carpeta actual
            self.selected_path = self.current_path
            try:
                from core.feedback import feedback_menu
                feedback_menu()
            except Exception:
                pass
            self._close()
        else:
            # Modo archivo (.exe o imagen)
            if self._items and 0 <= self._selected_index < len(self._items):
                item_type, _name, full_p = self._items[self._selected_index]
                if item_type == "file":
                    self.selected_path = full_p
                    try:
                        from core.feedback import feedback_menu
                        feedback_menu()
                    except Exception:
                        pass
                    self._close()
                    return
            self._activate_selected_item()

    def _use_native_picker(self):
        if self.select_mode == "folder":
            f = filedialog.askdirectory(title="Seleccionar Carpeta", initialdir=self.current_path)
        else:
            ext_filter = []
            if self.file_extensions:
                pattern = ";".join(f"*{e}" for e in self.file_extensions)
                ext_filter.append(("Archivos Compatibles", pattern))
            ext_filter.append(("Todos los Archivos", "*.*"))
            f = filedialog.askopenfilename(title="Seleccionar Archivo", initialdir=self.current_path, filetypes=ext_filter)
        if f:
            self.selected_path = f
            self._close()

    def _on_cancel(self):
        self.selected_path = None
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        # 1. Navegación en la lista vertical
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._navigate_list(-1)
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self._navigate_list(1)
            return True

        # 2. Navegación horizontal de discos (Izquierda / Derecha)
        if inputs.get("right", False) and not prev_inputs.get("right", False):
            self._cycle_drive(1)
            return True
        if inputs.get("left", False) and not prev_inputs.get("left", False):
            self._cycle_drive(-1)
            return True

        # 3. Gatillos o botones de hombro para discos (RB / RT para avanzar, LT para retroceder)
        if (inputs.get("rb", False) and not prev_inputs.get("rb", False)) or            (inputs.get("rt", False) and not prev_inputs.get("rt", False)):
            self._cycle_drive(1)
            return True
        if inputs.get("lt", False) and not prev_inputs.get("lt", False):
            self._cycle_drive(-1)
            return True

        # 4. Botón A: Abrir / Entrar en la subcarpeta resaltada
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            self._activate_selected_item()
            return True

        # 5. Botón B o Back: Cancelar y cerrar
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self._on_cancel()
            return True

        # 6. Botón LB o Back: Subir de nivel en la jerarquía de carpetas
        if inputs.get("lb", False) and not prev_inputs.get("lb", False):
            self._go_up_directory()
            return True
        if inputs.get("back", False) and not prev_inputs.get("back", False):
            self._go_up_directory()
            return True

        # 7. Start o X: Confirmar y seleccionar carpeta/archivo (inteligente)
        if (inputs.get("x", False) and not prev_inputs.get("x", False)) or            (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self._confirm_selection()
            return True

        # 8. Botón Y: Salto rápido a carpeta de Juegos (D:\Juegos)
        if inputs.get("y", False) and not prev_inputs.get("y", False):
            self._jump_to_games_folder()
            return True

        return True


def browse_folder(
    parent: Optional[tk.Widget] = None,
    title: str = "Seleccionar Carpeta",
    initial_dir: Optional[str] = None
) -> Optional[str]:
    """Abre el explorador de carpetas navegable con mando y retorna la ruta seleccionada o None."""
    dlg = GlassFolderBrowserDialog(parent=parent, title=title, initial_dir=initial_dir, select_mode="folder")
    dlg.wait_window()
    return dlg.selected_path


def browse_file(
    parent: Optional[tk.Widget] = None,
    title: str = "Seleccionar Archivo",
    initial_dir: Optional[str] = None,
    file_extensions: Optional[List[str]] = None
) -> Optional[str]:
    """Abre el explorador de archivos (.exe, imágenes, etc.) navegable con mando y retorna la ruta o None."""
    dlg = GlassFolderBrowserDialog(
        parent=parent, title=title, initial_dir=initial_dir,
        select_mode="file", file_extensions=file_extensions
    )
    dlg.wait_window()
    return dlg.selected_path