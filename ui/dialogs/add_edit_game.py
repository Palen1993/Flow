import os
from typing import List, Dict, Any, Optional
import tkinter as tk
from tkinter import filedialog
from ui.dialogs.glass_message_box import show_warning, show_error, ask_yes_no
from ui.dialogs.glass_folder_browser import browse_file
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from core.coverflow_engine import create_procedural_album, create_jewel_case
from core.cover_resolver import resolve_game_cover
from ui.dropdowns import GlassDropdownButton
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack
from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_BTN_DANGER_BG, COLOR_BTN_DANGER_HOVER, COLOR_BTN_DANGER_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED_LIGHT,
    font_button, font_body, apply_rounded_window_region
)

class AddEditGameDialog(ctk.CTkToplevel):
    def __init__(self, parent, monitors: List[Dict[str, Any]], game_data: Optional[Dict[str, Any]] = None, callback=None, delete_callback=None, on_close_callback=None):
        super().__init__(parent)
        self.callback = callback
        self.delete_callback = delete_callback
        self.on_close_callback = on_close_callback
        self.monitors = monitors
        self.game_data = game_data
        
        self.dialog_width = 650
        self.dialog_height = 560
        self.title("Editar Juego" if game_data else "Agregar Juego")
        self.geometry(f"{self.dialog_width}x{self.dialog_height}")
        self.resizable(False, False)
        
        # Fondo transparente sin barra de título del sistema operativo
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
        
        self.current_cover_path = game_data.get("cover", "") if game_data else ""
        self.current_wallpaper_path = game_data.get("wallpaper", "") if game_data else ""
        self.current_wallpaper_opacity = float(game_data.get("wallpaper_opacity", 0.25)) if game_data else 0.25
        self.current_wallpaper_blur = float(game_data.get("wallpaper_blur", 1.5)) if game_data else 1.5
        self.preview_image_ref = None
        
        self.drag_x = 0
        self.drag_y = 0
        
        self.create_widgets()
        self.bind("<Escape>", lambda e: self.destroy())
        
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
        if hasattr(self, "monitor_dropdown") and getattr(self.monitor_dropdown, "_active_dropdown", None):
            try:
                self.monitor_dropdown._active_dropdown.destroy()
                self.monitor_dropdown._active_dropdown = None
            except Exception:
                pass
        self.drag_x = event.x_root - self.winfo_x()
        self.drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self.drag_x
        y = event.y_root - self.drag_y
        self.geometry(f"+{x}+{y}")

    def destroy(self):
        unregister_modal_stack(self)
        self._cleanup_temp_preview()
        if hasattr(self, "monitor_dropdown") and getattr(self.monitor_dropdown, "_active_dropdown", None):
            try:
                self.monitor_dropdown._active_dropdown.destroy()
                self.monitor_dropdown._active_dropdown = None
            except Exception:
                pass
        try:
            self.grab_release()
        except Exception:
            pass
        cb = getattr(self, "on_close_callback", None)
        master = self.master
        super().destroy()
        if cb and master:
            try:
                master.after(50, cb)
            except Exception:
                pass

    def create_widgets(self):
        # Tarjeta principal iOS Liquid Glass con curvatura y bisel sutil
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)
        
        # Cabecera integrada arrastrable
        header_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=42)
        header_bar.pack(fill="x", padx=20, pady=(14, 4))
        
        title_text = "⚙  Editar Juego" if self.game_data else "＋  Agregar Juego a la Biblioteca"
        lbl_title = ctk.CTkLabel(
            header_bar,
            text=title_text,
            font=font_button(17),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_title.pack(side="left")
        
        for w in (header_bar, lbl_title, self.main_card):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        content_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=16, pady=4)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=2)
        content_frame.grid_rowconfigure(0, weight=1)
        
        # Panel izquierdo: Previsualización de carátula
        left_frame = ctk.CTkFrame(content_frame, fg_color=COLOR_BG_CARD_SECONDARY, border_color=COLOR_BORDER_CARD, border_width=1.0, corner_radius=16)
        left_frame.grid(row=0, column=0, padx=(0, 10), pady=8, sticky="nsew")
        
        ctk.CTkLabel(left_frame, text="Carátula", font=font_button(14), text_color=COLOR_TEXT_BRIGHT).pack(pady=(12, 6))
        
        self.cover_canvas = tk.Canvas(left_frame, width=180, height=220, bg="#0d0f14", highlightthickness=0)
        self.cover_canvas.pack(pady=5)
        
        self.btn_cover = ctk.CTkButton(
            left_frame, text="Cambiar carátula...", width=155, height=30,
            fg_color="#222838", hover_color="#2d354a", border_color="#343f55", border_width=1.0,
            corner_radius=15, text_color=COLOR_TEXT_BRIGHT, font=font_button(12),
            command=self.browse_cover
        )
        self.btn_cover.pack(pady=(8, 4))

        self.btn_online = ctk.CTkButton(
            left_frame, text="🌐 Buscar Online HD ", image=get_button_icon_ctk("x", size=18), compound="right",
            width=165, height=30,
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER, border_color=COLOR_IOS_BLUE_BORDER, border_width=1.0,
            corner_radius=15, text_color=COLOR_TEXT_WHITE, font=font_button(12),
            command=self.download_online_hd_cover
        )
        self.btn_online.pack(pady=4)
        
        self.btn_autodetect = ctk.CTkButton(
            left_frame, text="Autodetectar (.exe)", width=155, height=30,
            fg_color="#1b202c", hover_color="#252d3d", border_color="#2c3649", border_width=1.0,
            corner_radius=15, text_color=COLOR_TEXT_MUTED_LIGHT, font=font_body(12),
            command=self.autodetect_cover
        )
        self.btn_autodetect.pack(pady=4)

        # Panel derecho: Configuración del juego
        right_frame = ctk.CTkFrame(content_frame, fg_color=COLOR_BG_CARD_SECONDARY, border_color=COLOR_BORDER_CARD, border_width=1.0, corner_radius=16)
        right_frame.grid(row=0, column=1, padx=(6, 0), pady=8, sticky="nsew")
        right_frame.grid_columnconfigure(1, weight=1)
        
        # Título del juego
        ctk.CTkLabel(right_frame, text="Nombre:").grid(row=0, column=0, padx=12, pady=(15, 8), sticky="w")
        self.name_entry = ctk.CTkEntry(
            right_frame, placeholder_text="Ej. Assassin's Creed",
            fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_HOVER, corner_radius=12, text_color=COLOR_TEXT_MAIN
        )
        self.name_entry.grid(row=0, column=1, padx=(0, 12), pady=(15, 8), sticky="ew")
        
        # Ruta del ejecutable
        ctk.CTkLabel(right_frame, text="Ejecutable:").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.path_entry = ctk.CTkEntry(
            right_frame, placeholder_text="C:/Juegos/.../game.exe",
            fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_HOVER, corner_radius=12, text_color=COLOR_TEXT_MAIN
        )
        self.path_entry.grid(row=1, column=1, padx=(0, 12), pady=8, sticky="ew")
        
        self.btn_browse_exe = ctk.CTkButton(
            right_frame, text="Explorar .exe...", width=125, height=30,
            fg_color="#222838", hover_color="#2d354a", border_color="#343f55", border_width=1.0,
            corner_radius=15, text_color=COLOR_TEXT_BRIGHT, font=font_body(12),
            command=self.browse_exe
        )
        self.btn_browse_exe.grid(row=2, column=1, padx=(0, 12), pady=(0, 8), sticky="e")

        # Argumentos opcionales de lanzamiento
        ctk.CTkLabel(right_frame, text="Argumentos:").grid(row=3, column=0, padx=12, pady=6, sticky="w")
        self.args_entry = ctk.CTkEntry(
            right_frame, placeholder_text="Opcional: ej. -dx11 -skipintro",
            fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_HOVER, corner_radius=12, text_color=COLOR_TEXT_MAIN
        )
        self.args_entry.grid(row=3, column=1, padx=(0, 12), pady=6, sticky="ew")
        
        # Monitor
        ctk.CTkLabel(right_frame, text="Monitor:").grid(row=4, column=0, padx=12, pady=8, sticky="w")
        monitor_options = [
            f"Monitor {m['id']} - {m['name']} ({m['rect'][2]-m['rect'][0]}x{m['rect'][3]-m['rect'][1]})" 
            for m in self.monitors
        ]
        if not monitor_options:
            monitor_options = ["Monitor 0 - Predeterminado"]
            
        initial_monitor = monitor_options[0]
        if self.game_data:
            target_id = self.game_data.get("monitor", 0)
            for opt in monitor_options:
                if f"Monitor {target_id} " in opt or f"Monitor {target_id}-" in opt:
                    initial_monitor = opt
                    break
        else:
            master_games = getattr(self.master, "games", [])
            if master_games:
                pref_id = master_games[0].get("monitor", 0)
                for opt in monitor_options:
                    if f"Monitor {pref_id} " in opt or f"Monitor {pref_id}-" in opt:
                        initial_monitor = opt
                        break
                    
        self.monitor_var = ctk.StringVar(value=initial_monitor)
        self.monitor_dropdown = GlassDropdownButton(
            right_frame,
            values=monitor_options,
            variable=self.monitor_var,
            width=240,
            height=32,
            item_icon="🖥  "
        )
        self.monitor_dropdown.grid(row=4, column=1, padx=(0, 12), pady=8, sticky="ew")
        
        # Prioridad alta
        self.priority_var = ctk.BooleanVar(value=self.game_data.get("high_priority", True) if self.game_data else True)
        self.priority_check = ctk.CTkCheckBox(right_frame, text="Asignar prioridad 'Alta' en Windows", variable=self.priority_var)
        self.priority_check.grid(row=5, column=0, columnspan=2, padx=12, pady=10, sticky="w")
        
        # Botones inferiores Glassmorphism (Píldoras iOS emblemáticas)
        btn_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(12, 22))
        
        self.btn_delete = None
        if self.game_data and self.delete_callback:
            self.btn_delete = ctk.CTkButton(
                btn_frame, text="🗑  Eliminar Juego ", image=get_button_icon_ctk("a", size=18), compound="right",
                width=160, height=38,
                fg_color=COLOR_BTN_DANGER_BG, hover_color=COLOR_BTN_DANGER_HOVER, border_color=COLOR_BTN_DANGER_BORDER, border_width=1.2,
                corner_radius=19, text_color=COLOR_TEXT_WHITE, font=font_button(12),
                command=self.confirm_delete
            )
            self.btn_delete.pack(side="left")

        self.btn_cancel = ctk.CTkButton(
            btn_frame, text="Cancelar ", image=get_button_icon_ctk("b", size=20), compound="right",
            width=125, height=38,
            fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER, border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0,
            corner_radius=19, text_color=COLOR_TEXT_MUTED_LIGHT, font=font_body(12),
            command=self.destroy
        )
        self.btn_cancel.pack(side="right", padx=(10, 0))
        
        self.btn_save = ctk.CTkButton(
            btn_frame, text="Guardar ", image=get_button_icon_ctk("start", size=20), compound="right",
            width=135, height=38,
            fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER, border_color=COLOR_IOS_BLUE_BORDER, border_width=1.2,
            corner_radius=19, text_color=COLOR_TEXT_WHITE, font=font_button(12),
            command=self.save
        )
        self.btn_save.pack(side="right")

        self._nav_controls = [
            ("btn", self.btn_online, self.download_online_hd_cover),
            ("btn", self.btn_cover, self.browse_cover),
            ("btn", self.btn_autodetect, self.autodetect_cover),
            ("entry", self.name_entry, lambda: self._open_keyboard_for_entry(self.name_entry, "Nombre del Juego")),
            ("entry", self.path_entry, lambda: self._open_keyboard_for_entry(self.path_entry, "Ruta del Ejecutable")),
            ("btn", self.btn_browse_exe, self.browse_exe),
            ("entry", self.args_entry, lambda: self._open_keyboard_for_entry(self.args_entry, "Parámetros de Ejecución")),
            ("dropdown", self.monitor_dropdown, self.monitor_dropdown._toggle_dropdown),
            ("check", self.priority_check, self.priority_check.toggle),
            ("btn", self.btn_save, self.save),
            ("btn", self.btn_cancel, self.destroy),
        ]
        if self.btn_delete is not None:
            self._nav_controls.append(("btn", self.btn_delete, self.confirm_delete))
        self._focused_idx = 0
        self.after(50, self._update_focus_visuals)
        
        if self.game_data:
            self.name_entry.insert(0, self.game_data.get("name", ""))
            self.path_entry.insert(0, self.game_data.get("path", ""))
            if self.game_data.get("launch_args"):
                self.args_entry.insert(0, self.game_data.get("launch_args", ""))
            
        self._temp_preview_cover = None
        self.update_cover_preview()
        
    def update_cover_preview(self):
        size = 140
        refl_h = 60
        tot_h = size + refl_h
        
        if self.current_cover_path and os.path.isfile(self.current_cover_path):
            try:
                with Image.open(self.current_cover_path) as im_raw:
                    raw_img = im_raw.copy().convert("RGBA")
            except Exception:
                raw_img = create_procedural_album(self.name_entry.get() or "Juego", size=200)
        else:
            raw_img = create_procedural_album(self.name_entry.get() or "Juego", size=200)
            
        jewel = create_jewel_case(raw_img, size=size)
        refl = jewel.transpose(Image.Transpose.FLIP_TOP_BOTTOM).resize((size, refl_h), Image.Resampling.BILINEAR)
        mask = Image.new('L', (size, refl_h), 0)
        m_draw = ImageDraw.Draw(mask)
        for y in range(refl_h):
            m_draw.line([(0, y), (size, y)], fill=int(((1.0 - (y / refl_h)) ** 1.6) * 115))
        refl.putalpha(mask)
        
        preview = Image.new('RGBA', (180, 220), (13, 15, 20, 255))
        preview.paste(jewel, (20, 10))
        preview.paste(refl, (20, 10 + size), refl)
        
        self.preview_image_ref = ImageTk.PhotoImage(preview)
        self.cover_canvas.delete("all")
        self.cover_canvas.create_image(0, 0, image=self.preview_image_ref, anchor="nw")

    def browse_exe(self):
        cur_p = self.path_entry.get().strip()
        filename = browse_file(parent=self, title="Seleccionar Ejecutable del Juego", initial_dir=cur_p, file_extensions=[".exe"])
        if filename:
            self.path_entry.delete(0, 'end')
            self.path_entry.insert(0, filename)
            if not self.name_entry.get().strip():
                base = os.path.basename(filename)
                name = os.path.splitext(base)[0]
                self.name_entry.insert(0, name)
            if not self.current_cover_path or not os.path.isfile(self.current_cover_path):
                self.autodetect_cover()

    def browse_cover(self):
        cur_c = self.current_cover_path
        filename = browse_file(
            parent=self,
            title="Seleccionar Imagen de Carátula",
            initial_dir=cur_c,
            file_extensions=[".png", ".jpg", ".jpeg", ".ico", ".webp"]
        )
        if filename:
            self.current_cover_path = filename
            self.update_cover_preview()

    def autodetect_cover(self):
        from core.config import COVERS_DIR
        exe_path = self.path_entry.get().strip()
        name = self.name_entry.get().strip() or "Juego"
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip() or "game"
        preview_target = os.path.join(COVERS_DIR, f"_preview_{safe_name}.png")
        fake_game = {"name": name, "path": exe_path}
        detected = resolve_game_cover(fake_game, force_rescan=True, target_path=preview_target)
        if detected and os.path.isfile(detected):
            self._temp_preview_cover = detected
            self.current_cover_path = detected
            self.update_cover_preview()

    def download_online_hd_cover(self):
        """Abre el selector interactivo de carátulas y wallpapers 16:9 encontrados en Google, Steam y GOG."""
        name = self.name_entry.get().strip()
        if not name:
            show_warning("Descargar Carátula", "Escribe primero el nombre del juego en el campo 'Nombre'.", parent=self)
            return

        def _on_cover_chosen(new_path: str):
            if new_path and os.path.isfile(new_path):
                self.current_cover_path = new_path
                self._temp_preview_cover = None
                self.update_cover_preview()

        def _on_wp_chosen(new_wp: str, wp_op: float, wp_blur: float = 1.5):
            self.current_wallpaper_path = new_wp or ""
            self.current_wallpaper_opacity = float(wp_op)
            self.current_wallpaper_blur = float(wp_blur)
            if self.game_data is not None:
                if new_wp:
                    self.game_data["wallpaper"] = new_wp
                    self.game_data["wallpaper_opacity"] = round(float(wp_op), 2)
                    self.game_data["wallpaper_blur"] = round(float(wp_blur), 1)
                else:
                    self.game_data.pop("wallpaper", None)
                    self.game_data.pop("wallpaper_opacity", None)
                    self.game_data.pop("wallpaper_blur", None)

        from ui.dialogs.cover_picker_dialog import CoverPickerDialog
        CoverPickerDialog(
            self,
            initial_query=name,
            game_name=name,
            on_selected_callback=_on_cover_chosen,
            on_wallpaper_selected_callback=_on_wp_chosen,
            initial_wallpaper_opacity=self.current_wallpaper_opacity,
            initial_wallpaper_blur=self.current_wallpaper_blur,
            current_wallpaper_path=self.current_wallpaper_path
        )

    def _update_focus_visuals(self):
        controls = getattr(self, "_nav_controls", [])
        for i, (kind, widget, _) in enumerate(controls):
            if not widget or not widget.winfo_exists():
                continue
            is_foc = (i == self._focused_idx)
            if kind in ("btn", "dropdown"):
                widget.configure(
                    border_color="#38bdf8" if is_foc else "#343f55",
                    border_width=2.2 if is_foc else 1.0
                )
            elif kind == "entry":
                widget.configure(
                    border_color="#007aff" if is_foc else "#242a3a",
                    border_width=2.0 if is_foc else 1.0
                )
                if is_foc:
                    try:
                        widget.focus_set()
                    except Exception:
                        pass
            elif kind == "check":
                widget.configure(text_color=COLOR_CYAN_ACCENT if is_foc else COLOR_TEXT_MAIN)

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self._cleanup_temp_preview()
            self.destroy()
            return True
        if inputs.get("start", False) and not prev_inputs.get("start", False):
            self.save()
            return True
        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self.download_online_hd_cover()
            return True

        controls = getattr(self, "_nav_controls", [])
        if not controls:
            return False

        if (inputs.get("up", False) and not prev_inputs.get("up", False)) or \
           (inputs.get("left", False) and not prev_inputs.get("left", False)):
            self._focused_idx = (self._focused_idx - 1) % len(controls)
            self._update_focus_visuals()
            try:
                from core.feedback import feedback_click
                feedback_click()
            except Exception:
                pass
            return True

        if (inputs.get("down", False) and not prev_inputs.get("down", False)) or \
           (inputs.get("right", False) and not prev_inputs.get("right", False)):
            self._focused_idx = (self._focused_idx + 1) % len(controls)
            self._update_focus_visuals()
            try:
                from core.feedback import feedback_click
                feedback_click()
            except Exception:
                pass
            return True

        if inputs.get("a", False) and not prev_inputs.get("a", False):
            _, widget, action = controls[self._focused_idx]
            if action:
                action()
            elif widget:
                try:
                    widget.focus_set()
                except Exception:
                    pass
            return True
        return False

    def _cleanup_temp_preview(self):
        tmp = getattr(self, "_temp_preview_cover", None)
        if tmp and os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
            self._temp_preview_cover = None

    def _open_keyboard_for_entry(self, entry_widget: ctk.CTkEntry, title: str):
        from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
        def _on_confirm(new_val: str):
            entry_widget.delete(0, "end")
            entry_widget.insert(0, new_val)
            if entry_widget == self.path_entry:
                self.auto_fill_name_from_exe()
        prompt_on_screen_keyboard(self, title=title, initial_text=entry_widget.get(), on_confirm=_on_confirm)

    def save(self):
        from core.config import COVERS_DIR
        name = self.name_entry.get().strip()
        path = self.path_entry.get().strip()
        launch_args = self.args_entry.get().strip() if hasattr(self, "args_entry") else ""
        monitor_str = self.monitor_var.get()
        high_priority = self.priority_var.get()
        
        if not name or not path:
            show_error("Error de Validación", "Debes ingresar un nombre y la ruta del ejecutable.", parent=self)
            return
            
        monitor_index = 0
        if "Monitor " in monitor_str:
            try:
                monitor_index = int(monitor_str.split("Monitor ")[1].split(" - ")[0].split(" ")[0])
            except Exception:
                pass
                
        if not self.current_cover_path:
            self.autodetect_cover()

        # Si la carátula proviene de una previsualización temporal (_preview_), promoverla al archivo definitivo
        if getattr(self, "_temp_preview_cover", None) and self.current_cover_path == self._temp_preview_cover:
            safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip() or "game"
            final_cover = os.path.join(COVERS_DIR, f"{safe_name}.png")
            try:
                if os.path.isfile(self._temp_preview_cover):
                    os.replace(self._temp_preview_cover, final_cover)
                    self.current_cover_path = final_cover
                    self._temp_preview_cover = None
            except Exception:
                pass
            
        if self.callback:
            try:
                self.callback(name, path, monitor_index, high_priority, self.current_cover_path, launch_args)
            except TypeError:
                self.callback(name, path, monitor_index, high_priority, self.current_cover_path)
        self.destroy()

    def confirm_delete(self):
        name = self.game_data.get("name", "este juego") if self.game_data else "este juego"
        if ask_yes_no("Confirmar Eliminación", f"¿Estás seguro de que deseas eliminar '{name}' de la biblioteca?", parent=self, confirm_text="Eliminar", is_destructive=True):
            self._cleanup_temp_preview()
            if self.delete_callback:
                self.delete_callback()
            self.destroy()
