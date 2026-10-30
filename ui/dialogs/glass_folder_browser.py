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
    Explorador de carpetas y archivos estilo Glassmorphism navegable 100% con mando (D-Pad, A, B, X, Start),
    teclado y ratón. Permite seleccionar carpetas de juegos o archivos (.exe, imágenes)
    sin necesidad de ratón en televisores, sofás o consolas portátiles.
    """
    W = 640
    H = 520

    def __init__(
        self,
        parent: Optional[tk.Widget],
        title: str = "Seleccionar",
        initial_dir: Optional[str] = None,
        select_mode: str = "folder",  # 'folder' o 'file'
        file_extensions: Optional[List[str]] = None,
        family: Optional[str] = None
    ):
        self.selected_path: Optional[str] = None
        self.select_mode = select_mode
        self.file_extensions = [ext.lower() for ext in file_extensions] if file_extensions else None
        self.family = family or getattr(parent, "_current_controller_family", None) or get_connected_controller_family()

        # Determinar directorio inicial válido
        if initial_dir and os.path.isdir(initial_dir):
            self.current_path = os.path.abspath(initial_dir)
        elif initial_dir and os.path.isfile(initial_dir):
            self.current_path = os.path.dirname(os.path.abspath(initial_dir))
        else:
            self.current_path = "D:\\" if os.path.isdir("D:\\") else "C:\\"

        super().__init__(parent, title=title, width=self.W, height=self.H, corner_radius=22)

        # Elementos en la lista: tuplas (tipo: 'up'|'dir'|'file', nombre_visible, ruta_completa)
        self._items: List[tuple] = []
        self._item_buttons: List[ctk.CTkButton] = []
        self._selected_index = 0

        self._build_ui(title)
        self._bind_events()
        self._refresh_contents()
        self.focus_set()

    def _build_ui(self, title: str):
        self.card = ctk.CTkFrame(
            self, width=self.W - 20, height=self.H - 20, corner_radius=22,
            fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER, border_width=1.5
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.pack_propagate(False)
        self.make_draggable(self.card)

        # 1. Cabecera
        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 6))
        self.make_draggable(header)

        icon_hdr = "📁" if self.select_mode == "folder" else "🎮"
        lbl_t = ctk.CTkLabel(
            header, text=f"{icon_hdr}  {title}",
            font=("Segoe UI Semibold", 15), text_color=COLOR_TEXT_MAIN
        )
        lbl_t.pack(side="left")

        btn_native = ctk.CTkButton(
            header, text="Explorador Windows 🗁", width=140, height=26,
            corner_radius=13, font=font_button(10), fg_color="#1e2434",
            hover_color="#2a3348", text_color=COLOR_TEXT_MUTED,
            command=self._use_native_picker
        )
        btn_native.pack(side="right")

        # 2. Barra de Unidades y Ruta Actual
        drive_bar = ctk.CTkFrame(self.card, fg_color="#10141d", corner_radius=12,
                                 border_width=1, border_color="#232b3c")
        drive_bar.pack(fill="x", padx=18, pady=(0, 6))

        drives = []
        try:
            import win32api
            drives = [d for d in win32api.GetLogicalDriveStrings().split('\x00') if d]
        except Exception:
            drives = ["C:\\", "D:\\"] if os.path.exists("D:\\") else ["C:\\"]

        for d in drives:
            d_btn = ctk.CTkButton(
                drive_bar, text=f"💾 {d}", width=64, height=26,
                corner_radius=10, font=font_button(10), fg_color="#1b212f",
                hover_color="#007aff", text_color=COLOR_TEXT_LIGHT,
                command=lambda p=d: self._change_directory(p)
            )
            d_btn.pack(side="left", padx=4, pady=4)

        self.lbl_path = ctk.CTkLabel(
            self.card, text=self.current_path, font=font_body(11),
            text_color=COLOR_CYAN_ACCENT, anchor="w"
        )
        self.lbl_path.pack(fill="x", padx=20, pady=(0, 4))

        # 3. Lista desplazable de elementos
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.card, fg_color=COLOR_BG_DARK, corner_radius=14,
            border_width=1, border_color="#202533"
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        # 4. Barra inferior de confirmación
        footer = ctk.CTkFrame(self.card, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))

        btn_cancel = ctk.CTkButton(
            footer, text="Cancelar ", image=get_button_icon_ctk("b", self.family, size=18),
            compound="right", width=110, height=36, corner_radius=18,
            font=font_button(12), fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0, text_color=COLOR_TEXT_MUTED_LIGHT,
            command=self._on_cancel
        )
        btn_cancel.pack(side="left")

        action_txt = "Seleccionar Carpeta " if self.select_mode == "folder" else "Seleccionar Archivo "
        self.btn_confirm_selection = ctk.CTkButton(
            footer, text=action_txt,
            image=get_button_icon_ctk("x", self.family, size=18), compound="right",
            height=36, corner_radius=18, font=font_button(12),
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER, border_width=1.2, text_color=COLOR_TEXT_WHITE,
            command=self._confirm_selection
        )
        self.btn_confirm_selection.pack(side="right")

        self.btn_open = ctk.CTkButton(
            footer, text="Abrir / Entrar ", image=get_button_icon_ctk("a", self.family, size=18),
            compound="right", width=130, height=36, corner_radius=18,
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

    def _change_directory(self, new_dir: str):
        if os.path.isdir(new_dir):
            self.current_path = os.path.abspath(new_dir)
            self._selected_index = 0
            self._refresh_contents()

    def _go_up_directory(self):
        parent = os.path.dirname(self.current_path)
        if parent and parent != self.current_path and os.path.isdir(parent):
            self._change_directory(parent)

    def _refresh_contents(self):
        self.lbl_path.configure(text=f"📂  {self.current_path}")
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        self._items.clear()
        self._item_buttons.clear()

        # Botón subir nivel (..)
        parent_dir = os.path.dirname(self.current_path)
        has_parent = (parent_dir and parent_dir != self.current_path)
        if has_parent:
            self._items.append(("up", "..", parent_dir))
            btn_up = ctk.CTkButton(
                self.scroll_frame, text="  📁  ..  (Subir nivel) ",
                anchor="w", height=34, corner_radius=10, font=font_button(11),
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
                font=font_body(11), text_color=COLOR_STATUS_DANGER
            )
            lbl_err.pack(pady=20)
            return
        except Exception as e:
            lbl_err = ctk.CTkLabel(
                self.scroll_frame, text=f"Error: {e}",
                font=font_body(11), text_color=COLOR_STATUS_DANGER
            )
            lbl_err.pack(pady=20)
            return

        subdirs.sort(key=lambda s: s.lower())
        files.sort(key=lambda s: s.lower())

        # Añadir carpetas
        for f_name in subdirs:
            full_p = os.path.join(self.current_path, f_name)
            item_idx = len(self._items)
            self._items.append(("dir", f_name, full_p))

            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"  📁  {f_name}",
                anchor="w",
                height=34,
                corner_radius=10,
                font=font_body(11),
                fg_color="transparent",
                hover_color="#222838",
                text_color=COLOR_TEXT_LIGHT,
                command=lambda p=full_p: self._change_directory(p)
            )
            btn.pack(fill="x", padx=4, pady=1)
            btn.bind("<Double-Button-1>", lambda e, p=full_p: self._change_directory(p))
            btn.bind("<Enter>", lambda e, i=item_idx: self._on_hover(i))
            self._item_buttons.append(btn)

        # Añadir archivos si estamos en modo selector de archivo
        for f_name in files:
            full_p = os.path.join(self.current_path, f_name)
            item_idx = len(self._items)
            self._items.append(("file", f_name, full_p))

            f_icon = "🎮" if f_name.lower().endswith(".exe") else "🖼️"
            btn = ctk.CTkButton(
                self.scroll_frame,
                text=f"  {f_icon}  {f_name}",
                anchor="w",
                height=34,
                corner_radius=10,
                font=font_body(11),
                fg_color="transparent",
                hover_color="#1d263b",
                text_color="#93c5fd" if f_name.lower().endswith(".exe") else "#a7f3d0",
                command=lambda p=full_p: self._select_file_item(p)
            )
            btn.pack(fill="x", padx=4, pady=1)
            btn.bind("<Double-Button-1>", lambda e, p=full_p: self._confirm_file_path(p))
            btn.bind("<Enter>", lambda e, i=item_idx: self._on_hover(i))
            self._item_buttons.append(btn)

        self._update_selection()

    def _on_hover(self, idx: int):
        self._selected_index = idx
        self._update_selection(scroll=False)

    def _update_selection(self, scroll: bool = True):
        for i, b in enumerate(self._item_buttons):
            if i == self._selected_index:
                b.configure(
                    fg_color=COLOR_BG_INPUT_ACTIVE,
                    border_color=COLOR_CYAN_ACCENT,
                    border_width=1.2,
                    text_color=COLOR_TEXT_WHITE
                )
                if scroll:
                    scroll_to_widget(self.scroll_frame, b)
            else:
                is_up = (i < len(self._items) and self._items[i][0] == "up")
                is_file = (i < len(self._items) and self._items[i][0] == "file")
                def_color = "#38bdf8" if is_up else ("#93c5fd" if is_file else "#e2e8f0")
                b.configure(
                    fg_color="#181e2b" if is_up else "transparent",
                    border_width=0,
                    text_color=def_color
                )

    def _navigate_list(self, delta: int):
        if not self._item_buttons:
            return
        n = len(self._item_buttons)
        self._selected_index = max(0, min(n - 1, self._selected_index + delta))
        self._update_selection(scroll=True)

    def _activate_selected_item(self):
        if not self._items or self._selected_index >= len(self._items):
            return
        item_type, _name, full_p = self._items[self._selected_index]
        if item_type == "up":
            self._go_up_directory()
        elif item_type == "dir":
            self._change_directory(full_p)
        elif item_type == "file":
            self._confirm_file_path(full_p)

    def _select_file_item(self, file_path: str):
        if self.select_mode == "file":
            self._confirm_file_path(file_path)

    def _confirm_file_path(self, file_path: str):
        self.selected_path = file_path
        self._close()

    def _confirm_selection(self):
        if self.select_mode == "folder":
            self.selected_path = self.current_path
            self._close()
        else:
            # En modo archivo, si hay un archivo seleccionado en la lista, usarlo
            if self._items and 0 <= self._selected_index < len(self._items):
                item_type, _name, full_p = self._items[self._selected_index]
                if item_type == "file":
                    self.selected_path = full_p
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
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._navigate_list(-1)
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self._navigate_list(1)
            return True
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            self._activate_selected_item()
            return True
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            parent = os.path.dirname(self.current_path)
            if parent and parent != self.current_path:
                self._go_up_directory()
            else:
                self._on_cancel()
            return True
        if (inputs.get("x", False) and not prev_inputs.get("x", False)) or \
           (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self._confirm_selection()
            return True
        if (inputs.get("y", False) and not prev_inputs.get("y", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self._on_cancel()
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
