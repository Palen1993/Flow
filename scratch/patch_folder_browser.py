import os

browser_path = "ui/dialogs/glass_folder_browser.py"
with open(browser_path, "r", encoding="utf-8") as f:
    content = f.read()

target = """from ui.theme import (
    font_button, font_body, apply_rounded_window_region, scroll_to_widget,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER
)
from ui.controller_hud import get_button_icon_ctk
from gamepad_manager import get_connected_controller_family


class GlassFolderBrowserDialog(ctk.CTkToplevel):
    \"\"\"
    Explorador de carpetas y archivos estilo Glassmorphism navegable 100% con mando (D-Pad, A, B, X, Start),
    teclado y ratón. Permite seleccionar carpetas de juegos o archivos (.exe, imágenes)
    sin necesidad de ratón en televisores, sofás o consolas portátiles.
    \"\"\"
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
        super().__init__(parent)
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
            self.current_path = "D:\\\\" if os.path.isdir("D:\\\\") else "C:\\\\"

        self.title(title)
        self.geometry(f"{self.W}x{self.H}")
        self.resizable(False, False)

        try:
            self.overrideredirect(True)
        except Exception:
            pass
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        self.configure(fg_color="#141722")
        if parent:
            self.transient(parent)

        # Elementos en la lista: tuplas (tipo: 'up'|'dir'|'file', nombre_visible, ruta_completa)
        self._items: List[tuple] = []
        self._item_buttons: List[ctk.CTkButton] = []
        self._selected_index = 0

        self._build_ui(title)
        self._bind_events()
        self._refresh_contents()

        self._center_window()
        self.after(20, self._center_window)
        self.after(30, lambda: apply_rounded_window_region(self, self.W, self.H, 22))

        try:
            self.grab_set()
        except Exception:
            pass
        self.focus_set()

    def _center_window(self):
        try:
            self.update_idletasks()
            if self.master and self.master.winfo_exists():
                pw, ph = self.master.winfo_width(), self.master.winfo_height()
                px, py = self.master.winfo_rootx(), self.master.winfo_rooty()
                x = px + max(0, (pw - self.W) // 2)
                y = py + max(0, (ph - self.H) // 2)
            else:
                sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                x = max(0, (sw - self.W) // 2)
                y = max(0, (sh - self.H) // 2)
            self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        except Exception:
            pass

    def _build_ui(self, title: str):
        self.card = ctk.CTkFrame(
            self, width=self.W - 20, height=self.H - 20, corner_radius=22,
            fg_color="#141722", border_color="#2b3345", border_width=1.5
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.pack_propagate(False)

        # 1. Cabecera
        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 6))"""

replacement = """from ui.theme import (
    font_button, font_body, scroll_to_widget,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER
)
from ui.controller_hud import get_button_icon_ctk
from gamepad_manager import get_connected_controller_family
from ui.dialogs.base_dialog import BaseGlassDialog


class GlassFolderBrowserDialog(BaseGlassDialog):
    \"\"\"
    Explorador de carpetas y archivos estilo Glassmorphism navegable 100% con mando (D-Pad, A, B, X, Start),
    teclado y ratón. Permite seleccionar carpetas de juegos o archivos (.exe, imágenes)
    sin necesidad de ratón en televisores, sofás o consolas portátiles.
    \"\"\"
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
            self.current_path = "D:\\\\" if os.path.isdir("D:\\\\") else "C:\\\\"

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
            fg_color="#141722", border_color="#2b3345", border_width=1.5
        )
        self.card.place(relx=0.5, rely=0.5, anchor="center")
        self.card.pack_propagate(False)
        self.make_draggable(self.card)

        # 1. Cabecera
        header = ctk.CTkFrame(self.card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(14, 6))
        self.make_draggable(header)"""

assert target in content, "target not found"
content = content.replace(target, replacement, 1)

with open(browser_path, "w", encoding="utf-8") as f:
    f.write(content)

print("ui/dialogs/glass_folder_browser.py successfully updated to BaseGlassDialog!")
