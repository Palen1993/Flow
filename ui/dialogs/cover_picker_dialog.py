import os
import sys
import ctypes
import threading
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk
from typing import Optional, List, Dict, Any, Callable

from core.config import COVERS_DIR, WALLPAPERS_DIR
from core.cover_downloader import (
    search_cover_candidates,
    download_and_save_cover,
    search_wallpaper_candidates,
    download_and_save_wallpaper,
    fetch_image_from_url
)
from core.coverflow_engine import (
    create_jewel_case,
    prepare_flat_cover,
    create_procedural_album,
    adapt_cover_to_square,
    adapt_wallpaper_to_widescreen,
    compose_big_picture_wallpaper_bg
)
from core.feedback import feedback_click, feedback_cover_applied
from ui.controller_hud import get_button_icon_ctk
from ui.dialogs.base_dialog import register_modal_stack, unregister_modal_stack
from ui.theme import (
    COLOR_TRANS_KEY, COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_BG_DARK, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY,
    COLOR_GLASS_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_title, font_body
)

_GLOBAL_THUMB_CACHE: Dict[str, Image.Image] = {}


class CoverPickerDialog(ctk.CTkToplevel):
    """
    Diálogo modal visual e interactivo para buscar, previsualizar en vivo y adaptar carátulas HD.
    
    Utiliza un motor de renderizado de lienzo virtual (Double-Buffered Pillow Viewport) para la cuadrícula
    de carátulas que elimina al 100% el emborronado (GDI ScrollWindowEx smearing) al arrastrar la barra lateral,
    y un panel lateral de Vista Previa en Cover Flow con adaptación interactiva en tiempo real.
    """
    GRID_COLS = 3
    CARD_W = 228
    CARD_H = 236
    CARD_PAD_X = 12
    CARD_PAD_Y = 12
    # Rango de opacidad del wallpaper (8% .. 85%) — el slider 0..1 se mapea linealmente a este rango
    WP_OP_MIN = 0.08
    WP_OP_MAX = 0.85

    def __init__(
        self,
        parent: tk.Widget,
        initial_query: str,
        game_name: Optional[str] = None,
        on_selected_callback: Optional[Callable[[str], None]] = None,
        initial_mode: str = "cover",
        on_wallpaper_selected_callback: Optional[Callable[..., None]] = None,
        initial_wallpaper_opacity: float = 0.25,
        initial_wallpaper_blur: float = 1.5,
        current_cover_pil: Optional[Image.Image] = None,
        current_wallpaper_path: str = ""
    ):
        super().__init__(parent)
        self.parent = parent
        self.initial_query = initial_query.strip()
        self.game_name = (game_name or initial_query).strip()
        self.on_selected_callback = on_selected_callback
        self.on_wallpaper_selected_callback = on_wallpaper_selected_callback
        self.asset_mode = "wallpaper" if initial_mode == "wallpaper" else "cover"
        self.wp_opacity = max(self.WP_OP_MIN, min(self.WP_OP_MAX, float(initial_wallpaper_opacity if initial_wallpaper_opacity is not None else 0.25)))
        self.wp_blur = max(0.0, min(12.0, float(initial_wallpaper_blur if initial_wallpaper_blur is not None else 1.5)))
        self.current_cover_pil = current_cover_pil
        self.current_wallpaper_path = current_wallpaper_path or ""
        self.current_wallpaper_pil: Optional[Image.Image] = None
        if self.current_wallpaper_path and os.path.isfile(self.current_wallpaper_path):
            try:
                with Image.open(self.current_wallpaper_path) as _wp_im:
                    self.current_wallpaper_pil = _wp_im.convert("RGB")
            except Exception:
                self.current_wallpaper_pil = None

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.dialog_width = min(1140, int(screen_w * 0.85))
        self.dialog_height = min(860, int(screen_h * 0.88))
        self.title("Selector de Carátula y Wallpaper HD")
        self.geometry(f"{self.dialog_width}x{self.dialog_height}")
        self.resizable(False, False)

        # Ventana sin barra nativa de Windows, SIN -transparentcolor (evita artefactos GDI WS_EX_LAYERED al hacer scroll)
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

        # Estado interno de candidatos y caché de imágenes
        self.all_candidates: List[Dict[str, Any]] = []
        self.filtered_candidates: List[Dict[str, Any]] = []
        self.raw_pil_by_idx: Dict[int, Image.Image] = {}
        self.card_thumb_by_idx: Dict[int, Image.Image] = {}
        self.hd_pil_by_idx: Dict[int, Image.Image] = {}
        self.full_res_loaded: Dict[int, bool] = {}
        self.selected_card_idx = 0
        self.is_searching = False
        self._search_generation = 0
        self._thumb_cache = _GLOBAL_THUMB_CACHE
        self._thumb_executor: Optional[ThreadPoolExecutor] = None

        # Estado del motor de scroll virtual (0 artefactos / 0 emborronado)
        self.scroll_y = 0
        self.total_scroll_h = 1
        self.view_w = 735
        self.view_h = 640
        self._grid_master_img: Optional[Image.Image] = None
        self._grid_slice_tk: Optional[ImageTk.PhotoImage] = None
        self._grid_img_item: Optional[int] = None
        self._redraw_pending = False

        # Fuentes Pillow cacheadas para dibujar las tarjetas en el buffer maestro
        try:
            self._pil_font_title = ImageFont.truetype("segoeuib.ttf", 12)
            self._pil_font_badge = ImageFont.truetype("segoeuib.ttf", 11)
            self._pil_font_btn = ImageFont.truetype("segoeuib.ttf", 11)
        except Exception:
            self._pil_font_title = ImageFont.load_default()
            self._pil_font_badge = ImageFont.load_default()
            self._pil_font_btn = ImageFont.load_default()

        # Estado del Modo de Adaptación al Cuadro (Vista Previa Lateral)
        self.fit_mode = "auto"          # 'auto' | 'stretch' | 'crop'
        self.crop_anchor = "center"     # 'top' | 'center' | 'bottom'
        self.crop_offset: Optional[float] = None
        self._fit_presets = [
            ("✨ Auto", "auto", "center", None),
            ("↔ Completo", "stretch", "center", None),
            ("⬆ Arriba", "crop", "top", 0.0),
            ("🎯 Centro", "crop", "center", 0.5),
            ("⬇ Abajo", "crop", "bottom", 1.0),
        ]
        # (etiqueta, opacidad, borrosidad) — ordenados de más visible a más sutil
        self._wp_presets = [
            ("💎 Nítido", 0.75, 0.0),     # 75% opacidad, 0 desenfoque: imagen completamente clara
            ("🔆 Vivo", 0.50, 0.5),       # 50% opacidad, desenfoque mínimo
            ("✨ Suave", 0.30, 1.8),      # 30% opacidad, desenfoque suave (por defecto)
            ("🌫 Sutil", 0.18, 4.5),      # 18% opacidad, muy difuminado de fondo
            ("🗑 Sin Fondo", -1.0, 0.0),
        ]
        self._fit_preset_idx = 0
        self._wp_preset_idx = self._match_wp_preset_idx()
        self._fit_buttons: List[ctk.CTkButton] = []
        self._preview_tk_ref = None
        self._preview_drag_start_y = 0
        self._preview_drag_start_offset = 0.5

        # Variables de arrastre de ventana
        self._drag_x = 0
        self._drag_y = 0

        self._build_ui()
        self._sync_mode_ui(trigger_search=False)
        self._bind_events()
        self._center_window()
        self.after(30, self._apply_rounded_window_region)

        try:
            self.grab_set()
        except Exception:
            pass

        register_modal_stack(self)
        # Disparar búsqueda automática tras abrir
        self.after(60, self._start_search)

    def _match_wp_preset_idx(self) -> int:
        """Devuelve el preset de wallpaper que coincide con la opacidad/borrosidad actual (o -1 si es personalizado)."""
        for i, (_, op_v, bl_v) in enumerate(self._wp_presets):
            if op_v >= 0 and abs(op_v - self.wp_opacity) < 0.02 and abs(bl_v - self.wp_blur) < 0.15:
                return i
        return -1

    def _opacity_to_slider(self, op: float) -> float:
        return max(0.0, min(1.0, (op - self.WP_OP_MIN) / (self.WP_OP_MAX - self.WP_OP_MIN)))

    def _slider_to_opacity(self, value: float) -> float:
        return round(self.WP_OP_MIN + float(value) * (self.WP_OP_MAX - self.WP_OP_MIN), 2)

    def _apply_rounded_window_region(self):
        """Aplica esquinas redondeadas nativas Win32 sin usar WS_EX_LAYERED (-transparentcolor) para máxima fluidez GDI."""
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, self.dialog_width + 1, self.dialog_height + 1, 28, 28)
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except Exception:
            pass

    def _center_window(self):
        try:
            self.update_idletasks()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            w = self.dialog_width
            h = self.dialog_height
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # Contenedor principal con borde elegante
        self.card = ctk.CTkFrame(
            self,
            corner_radius=20,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5
        )
        self.card.pack(fill="both", expand=True, padx=2, pady=2)

        # -------------------------------------------------------------
        # 1. Barra de Cabecera Personalizada (Arrastrable con Selector de Modo y botón ✕)
        # -------------------------------------------------------------
        header_frame = ctk.CTkFrame(self.card, fg_color="#181d28", corner_radius=14, height=46)
        header_frame.pack(fill="x", padx=14, pady=(12, 8))

        self.lbl_title = ctk.CTkLabel(
            header_frame,
            text="🎨  Selector de Carátula y Wallpaper (Google • Steam • GOG)",
            font=("Segoe UI Semibold", 15),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_title.pack(side="left", padx=16, pady=8)

        self.btn_close_x = ctk.CTkButton(
            header_frame,
            text="✕",
            width=32,
            height=32,
            corner_radius=16,
            fg_color="#222838",
            hover_color="#ff2d55",
            text_color=COLOR_TEXT_WHITE,
            font=("Segoe UI", 13, "bold"),
            command=self.destroy
        )
        self.btn_close_x.pack(side="right", padx=10, pady=8)

        # Selector de pestaña (Carátula 3D vs Wallpaper 16:9 de Fondo Big Picture)
        mode_switch_frame = ctk.CTkFrame(header_frame, fg_color="#10141d", corner_radius=14, border_width=1, border_color="#2b3548")
        mode_switch_frame.pack(side="right", padx=(0, 12), pady=6)

        self.btn_mode_cover = ctk.CTkButton(
            mode_switch_frame,
            text="💿 Carátula (Caja 3D)",
            height=28,
            width=152,
            corner_radius=11,
            font=("Segoe UI Semibold", 11),
            fg_color="#007aff",
            hover_color="#0062cc",
            text_color=COLOR_TEXT_WHITE,
            command=lambda: self._switch_asset_mode("cover")
        )
        self.btn_mode_cover.pack(side="left", padx=(3, 2), pady=3)

        self.btn_mode_wallpaper = ctk.CTkButton(
            mode_switch_frame,
            text="🖼 Wallpaper 16:9 ",
            image=get_button_icon_ctk("select", size=17),
            compound="right",
            height=28,
            width=168,
            corner_radius=11,
            font=("Segoe UI Semibold", 11),
            fg_color="transparent",
            hover_color="#1e2638",
            text_color=COLOR_TEXT_MUTED,
            command=lambda: self._switch_asset_mode("wallpaper")
        )
        self.btn_mode_wallpaper.pack(side="left", padx=(2, 3), pady=3)

        for w in (header_frame, self.lbl_title):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # -------------------------------------------------------------
        # 2. Barra de Búsqueda
        # -------------------------------------------------------------
        search_bar = ctk.CTkFrame(self.card, fg_color="#181d28", corner_radius=14, border_width=1.2, border_color=COLOR_GLASS_BORDER)
        search_bar.pack(fill="x", padx=16, pady=(0, 8))

        self.entry_search = ctk.CTkEntry(
            search_bar,
            placeholder_text="Escribe el nombre o palabras clave del juego (ej. 'Black Flag', 'Snake Eater')...",
            font=("Segoe UI", 13),
            fg_color="#0f1218",
            border_color="#242a3a",
            text_color=COLOR_TEXT_MAIN,
            corner_radius=10,
            height=36
        )
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(12, 10), pady=7)
        self.entry_search.insert(0, self.initial_query)
        self.entry_search.bind("<Return>", lambda e: self._start_search())

        self.btn_search = ctk.CTkButton(
            search_bar,
            text="🔍 Buscar ",
            image=get_button_icon_ctk("x", size=18),
            compound="right",
            font=("Segoe UI Semibold", 12),
            fg_color="#007aff",
            hover_color="#0062cc",
            border_color="#3894ff",
            border_width=1.0,
            corner_radius=14,
            text_color=COLOR_TEXT_WHITE,
            height=36,
            width=120,
            command=self._start_search
        )
        self.btn_search.pack(side="right", padx=(0, 10), pady=7)

        self.lbl_status = ctk.CTkLabel(
            self.card,
            text="Consultando Google, Steam y GOG...",
            font=("Segoe UI", 11),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_status.pack(anchor="w", padx=20, pady=(0, 6))

        # -------------------------------------------------------------
        # 3. Cuerpo Dividido: Lienzo Virtual (Izquierda) + Vista Previa (Derecha)
        # -------------------------------------------------------------
        body_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        body_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        body_frame.grid_columnconfigure(0, weight=1)
        body_frame.grid_columnconfigure(1, weight=0)
        body_frame.grid_rowconfigure(0, weight=1)

        # Contenedor Izquierdo: Lienzo Virtual de Doble Buffer (sin CTkScrollableFrame para 0 emborronado)
        grid_container = ctk.CTkFrame(
            body_frame,
            fg_color="#0f1218",
            corner_radius=16,
            border_width=1.2,
            border_color="#202533"
        )
        grid_container.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        grid_container.grid_columnconfigure(0, weight=1)
        grid_container.grid_rowconfigure(0, weight=1)

        self.grid_canvas = tk.Canvas(
            grid_container,
            bg="#0f1218",
            highlightthickness=0,
            bd=0
        )
        self.grid_canvas.grid(row=0, column=0, sticky="nsew", padx=(8, 2), pady=8)

        self.scrollbar = ctk.CTkScrollbar(
            grid_container,
            orientation="vertical",
            command=self._on_scrollbar_command,
            fg_color="#0f1218",
            button_color="#283246",
            button_hover_color="#007aff"
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=8)
        self.scrollbar.set(0.0, 1.0)

        self.grid_canvas.bind("<Configure>", self._on_grid_canvas_configure)
        self.grid_canvas.bind("<Button-1>", self._on_grid_canvas_click)
        self.grid_canvas.bind("<Double-Button-1>", self._on_grid_canvas_double_click)
        self.grid_canvas.bind("<MouseWheel>", self._on_mousewheel)

        # -------------------------------------------------------------
        # Panel Lateral Derecho: Vista Previa en Vivo + Adaptación al Cuadro
        # -------------------------------------------------------------
        self.preview_panel = ctk.CTkFrame(
            body_frame,
            width=310,
            fg_color="#0f1218",
            corner_radius=16,
            border_width=1.2,
            border_color="#242c3d"
        )
        self.preview_panel.grid(row=0, column=1, sticky="ns")
        self.preview_panel.pack_propagate(False)

        self.lbl_prev_hdr = ctk.CTkLabel(
            self.preview_panel,
            text="👁  Vista Previa en Cover Flow",
            font=("Segoe UI Semibold", 13),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_prev_hdr.pack(pady=(10, 1))

        self.lbl_prev_sub = ctk.CTkLabel(
            self.preview_panel,
            text="Arrastra la imagen o usa los botones para encuadrar",
            font=("Segoe UI", 10),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_prev_sub.pack(pady=(0, 4))

        # Lienzo interactivo de la caja cuadrada 200x200 + reflejo (o escenario 16:9 Big Picture)
        self.preview_canvas = tk.Canvas(
            self.preview_panel,
            width=240,
            height=248,
            bg="#0b0d13",
            highlightthickness=1,
            highlightbackground="#1e2636",
            cursor="fleur"
        )
        self.preview_canvas.pack(padx=16, pady=(2, 4))
        self.preview_canvas.bind("<ButtonPress-1>", self._on_preview_drag_start)
        self.preview_canvas.bind("<B1-Motion>", self._on_preview_drag_motion)

        self.lbl_prev_info = ctk.CTkLabel(
            self.preview_panel,
            text="Selecciona una carátula para previsualizar",
            font=("Segoe UI Semibold", 10),
            text_color=COLOR_CYAN_ACCENT,
            wraplength=275,
            justify="center"
        )
        self.lbl_prev_info.pack(padx=10, pady=(1, 4))

        # Botones de Modo de Adaptación al Cuadro / Presets de Wallpaper
        self.lbl_fit_title = ctk.CTkLabel(
            self.preview_panel,
            text="Modo de adaptación al cuadro ",
            image=get_button_icon_ctk("y", size=18),
            compound="right",
            font=("Segoe UI Semibold", 10),
            text_color=COLOR_TEXT_MUTED_LIGHT
        )
        self.lbl_fit_title.pack(pady=(2, 3))

        # Fila superior: ✨ Auto | ↔ Completo
        fit_row1 = ctk.CTkFrame(self.preview_panel, fg_color="transparent")
        fit_row1.pack(padx=14, pady=(0, 3), fill="x")
        fit_row1.grid_columnconfigure(0, weight=1)
        fit_row1.grid_columnconfigure(1, weight=1)

        # Fila inferior: ⬆ Arriba | 🎯 Centro | ⬇ Abajo
        fit_row2 = ctk.CTkFrame(self.preview_panel, fg_color="transparent")
        fit_row2.pack(padx=14, pady=(0, 4), fill="x")
        fit_row2.grid_columnconfigure(0, weight=1)
        fit_row2.grid_columnconfigure(1, weight=1)
        fit_row2.grid_columnconfigure(2, weight=1)

        self._fit_buttons.clear()
        for p_idx, (label_txt, _, _, _) in enumerate(self._fit_presets):
            parent_row = fit_row1 if p_idx < 2 else fit_row2
            col_idx = p_idx if p_idx < 2 else (p_idx - 2)
            b = ctk.CTkButton(
                parent_row,
                text=label_txt,
                height=28,
                corner_radius=10,
                font=("Segoe UI Semibold", 10),
                fg_color="#007aff" if p_idx == 0 else "#1a202c",
                hover_color="#0062cc",
                text_color=COLOR_TEXT_WHITE if p_idx == 0 else "#cbd5e1",
                command=lambda idx=p_idx: self._set_fit_preset(idx)
            )
            b.grid(row=0, column=col_idx, padx=3, pady=2, sticky="ew")
            self._fit_buttons.append(b)

        # Deslizador 1: Encuadre (modo carátula) u Opacidad (modo wallpaper)
        self.slider_frame = ctk.CTkFrame(self.preview_panel, fg_color="transparent")
        self.slider_frame.pack(padx=16, pady=(2, 4), fill="x")

        self.lbl_sl = ctk.CTkLabel(
            self.slider_frame,
            text="Ajuste fino de encuadre (LB / RB):",
            font=("Segoe UI", 9),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_sl.pack(anchor="w")

        self.offset_slider = ctk.CTkSlider(
            self.slider_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=100,
            command=self._on_offset_slider_changed,
            fg_color="#1e2636",
            progress_color="#007aff",
            button_color="#38bdf8",
            button_hover_color="#007aff",
            height=15
        )
        self.offset_slider.set(0.35)
        self.offset_slider.pack(fill="x", pady=(3, 0))

        # Deslizador 2: Borrosidad / Desenfoque del Wallpaper (solo visible en modo Wallpaper 16:9)
        self.blur_slider_frame = ctk.CTkFrame(self.preview_panel, fg_color="transparent")
        self.blur_slider_frame.pack(padx=16, pady=(2, 4), fill="x")

        self.lbl_blur_sl = ctk.CTkLabel(
            self.blur_slider_frame,
            text="Borrosidad / Desenfoque (LT / RT): 1.5 (Suave)",
            font=("Segoe UI", 9),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_blur_sl.pack(anchor="w")

        self.blur_slider = ctk.CTkSlider(
            self.blur_slider_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=120,
            command=self._on_blur_slider_changed,
            fg_color="#1e2636",
            progress_color="#007aff",
            button_color="#38bdf8",
            button_hover_color="#007aff",
            height=15
        )
        self.blur_slider.set(max(0.0, min(1.0, self.wp_blur / 12.0)))
        self.blur_slider.pack(fill="x", pady=(3, 0))

        # -------------------------------------------------------------
        # 4. Pie de Página con Controles
        # -------------------------------------------------------------
        footer_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        footer_frame.pack(fill="x", padx=20, pady=(0, 14))

        self.btn_cancel = ctk.CTkButton(
            footer_frame,
            text="Cancelar ",
            image=get_button_icon_ctk("b", size=20),
            compound="right",
            font=("Segoe UI Semibold", 12),
            fg_color="#1c212d",
            hover_color="#283040",
            border_color="#333c50",
            border_width=1.0,
            text_color=COLOR_TEXT_MUTED_LIGHT,
            height=38,
            corner_radius=19,
            width=128,
            command=self.destroy
        )
        self.btn_cancel.pack(side="right", padx=(8, 0))

        self.btn_confirm = ctk.CTkButton(
            footer_frame,
            text="✓ Aplicar Esta Carátula ",
            image=get_button_icon_ctk("a", size=20),
            compound="right",
            font=("Segoe UI Semibold", 12),
            fg_color="#007aff",
            hover_color="#0062cc",
            border_color="#3894ff",
            border_width=1.2,
            text_color=COLOR_TEXT_WHITE,
            height=38,
            corner_radius=19,
            width=235,
            command=self._confirm_selected
        )
        self.btn_confirm.pack(side="right")

        self._update_live_preview(None)

    def _switch_asset_mode(self, new_mode: str):
        """Cambia entre el selector de Carátula (Caja 3D) y el de Wallpaper 16:9 (Fondo Big Picture)."""
        target = "wallpaper" if new_mode == "wallpaper" else "cover"
        if target == self.asset_mode and self.all_candidates:
            return
        feedback_click()
        self.asset_mode = target
        self.is_searching = False
        self._sync_mode_ui(trigger_search=True)

    def _sync_mode_ui(self, trigger_search: bool = False):
        """Actualiza pestañas, etiquetas, presets y deslizadores según estemos en Carátula o Wallpaper 16:9."""
        is_wp = (self.asset_mode == "wallpaper")
        if is_wp:
            self.btn_mode_cover.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED)
            self.btn_mode_wallpaper.configure(fg_color="#007aff", text_color=COLOR_TEXT_WHITE)
            self.lbl_prev_hdr.configure(text="👁  Vista Previa en Big Picture")
            self.lbl_prev_sub.configure(text="Fondo 16:9 a pantalla completa (sin barras)")
            self.lbl_fit_title.configure(text="Ajustes rápidos de Fondo ")
            pct_op = int(round(self.wp_opacity * 100))
            blur_tag = "Nítido" if self.wp_blur < 0.3 else ("Suave" if self.wp_blur <= 2.5 else "Borroso")
            self.lbl_sl.configure(text=f"Opacidad del fondo (LB / RB): {pct_op}%")
            self.lbl_blur_sl.configure(text=f"Borrosidad / Desenfoque (LT / RT): {self.wp_blur:.1f} ({blur_tag})")
            self.blur_slider_frame.pack(padx=16, pady=(2, 4), fill="x")
            self.btn_confirm.configure(text="✓ Aplicar Wallpaper 16:9 ")

            for i, b in enumerate(self._fit_buttons):
                lbl_t, _, _ = self._wp_presets[i]
                is_active = (i == self._wp_preset_idx)
                b.configure(
                    text=lbl_t,
                    fg_color="#ff3b30" if (i == 4 and is_active) else ("#007aff" if is_active else "#1a202c"),
                    text_color=COLOR_TEXT_WHITE if is_active else ("#fca5a5" if i == 4 else "#cbd5e1")
                )
            norm_slider = self._opacity_to_slider(self.wp_opacity)
            self.offset_slider.set(norm_slider)
            self.blur_slider.set(max(0.0, min(1.0, self.wp_blur / 12.0)))
        else:
            self.btn_mode_cover.configure(fg_color="#007aff", text_color=COLOR_TEXT_WHITE)
            self.btn_mode_wallpaper.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED)
            self.lbl_prev_hdr.configure(text="👁  Vista Previa en Cover Flow")
            self.lbl_prev_sub.configure(text="Arrastra la imagen o usa los botones para encuadrar")
            self.lbl_fit_title.configure(text="Modo de adaptación al cuadro ")
            self.lbl_sl.configure(text="Ajuste fino de encuadre (LB / RB):")
            self.blur_slider_frame.pack_forget()
            self.btn_confirm.configure(text="✓ Aplicar Esta Carátula ")

            for i, b in enumerate(self._fit_buttons):
                lbl_t, _, _, _ = self._fit_presets[i]
                is_active = (i == self._fit_preset_idx)
                b.configure(
                    text=lbl_t,
                    fg_color="#007aff" if is_active else "#1a202c",
                    text_color=COLOR_TEXT_WHITE if is_active else "#cbd5e1"
                )
            self.offset_slider.set(self.crop_offset if self.crop_offset is not None else 0.35)

        if trigger_search:
            self._start_search()
        else:
            self._update_live_preview(self.raw_pil_by_idx.get(self.selected_card_idx))

    def _bind_events(self):
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Left>", lambda e: self._navigate_grid(-1, 0))
        self.bind("<Right>", lambda e: self._navigate_grid(1, 0))
        self.bind("<Up>", lambda e: self._navigate_grid(0, -1))
        self.bind("<Down>", lambda e: self._navigate_grid(0, 1))
        self.bind("<MouseWheel>", self._on_mousewheel)

    # =================================================================
    # MOTOR DE SCROLL VIRTUAL (CERO EMBORRONADO / 120 FPS)
    # =================================================================
    def _on_grid_canvas_configure(self, event):
        if event.width > 50 and event.height > 50:
            self.view_w = event.width
            self.view_h = event.height
            self._schedule_grid_redraw(rebuild_master=True)

    def _on_scrollbar_command(self, *args):
        """Manejador directo de la barra lateral que actualiza la vista recortada sin usar ScrollWindowEx."""
        if not args:
            return
        max_scroll = max(0, self.total_scroll_h - self.view_h)
        if args[0] == "moveto" and len(args) >= 2:
            fraction = max(0.0, min(1.0, float(args[1])))
            self.scroll_y = int(round(fraction * self.total_scroll_h))
        elif args[0] == "scroll" and len(args) >= 3:
            amt = int(args[1])
            unit = args[2]
            step = 65 if unit == "units" else int(self.view_h * 0.8)
            self.scroll_y += amt * step

        self.scroll_y = max(0, min(max_scroll, self.scroll_y))
        self._blit_viewport_slice()

    def _on_mousewheel(self, event):
        # Si el cursor está sobre la vista previa derecha, no desplazar la cuadrícula izquierda
        try:
            wx, wy = event.x_root, event.y_root
            px = self.preview_panel.winfo_rootx()
            if wx >= px:
                return
        except Exception:
            pass

        max_scroll = max(0, self.total_scroll_h - self.view_h)
        if max_scroll <= 0:
            return
        delta = -int(event.delta / 120) * 75
        self.scroll_y = max(0, min(max_scroll, self.scroll_y + delta))
        self._blit_viewport_slice()

    def _ensure_card_visible(self, idx: int):
        n = len(self.filtered_candidates)
        if n == 0:
            self.scroll_y = 0
            return
        rows = (n + self.GRID_COLS - 1) // self.GRID_COLS
        row_h = self.CARD_H + self.CARD_PAD_Y
        self.total_scroll_h = max(self.view_h, self.CARD_PAD_Y + rows * row_h + 12)
        max_scroll = max(0, self.total_scroll_h - self.view_h)

        row = idx // self.GRID_COLS
        if row <= 0:
            self.scroll_y = 0
        elif row >= rows - 1:
            self.scroll_y = max_scroll
        else:
            card_top = self.CARD_PAD_Y + row * row_h
            card_center = card_top + (self.CARD_H // 2)
            target_scroll = card_center - int(self.view_h * 0.45)
            self.scroll_y = max(0, min(max_scroll, target_scroll))

    def _schedule_grid_redraw(self, rebuild_master: bool = True):
        if rebuild_master or self._grid_master_img is None:
            self._rebuild_master_grid_image()
        self._blit_viewport_slice()

    def _request_coalesced_blit(self):
        """Agrupa múltiples llegadas asíncronas de miniaturas en un único volcado de 60 FPS para no bloquear la UI."""
        if self._redraw_pending:
            return
        self._redraw_pending = True

        def _flush():
            self._redraw_pending = False
            if self.winfo_exists():
                self._blit_viewport_slice()

        self.after(14, _flush)

    def _draw_single_card_on_master(self, idx: int):
        """Dibuja o actualiza instantáneamente (< 0.1ms) una única tarjeta sobre el lienzo maestro usando su miniatura pre-escalada."""
        if self._grid_master_img is None or idx < 0 or idx >= len(self.filtered_candidates):
            return
        w = max(300, self.view_w)
        avail_w = w - self.CARD_PAD_X * (self.GRID_COLS + 1)
        card_w = max(180, avail_w // self.GRID_COLS)
        self._computed_card_w = card_w
        row_h = self.CARD_H + self.CARD_PAD_Y
        is_wp = (self.asset_mode == "wallpaper")

        r = idx // self.GRID_COLS
        c = idx % self.GRID_COLS
        x0 = self.CARD_PAD_X + c * (card_w + self.CARD_PAD_X)
        y0 = self.CARD_PAD_Y + r * row_h
        x1 = x0 + card_w
        y1 = y0 + self.CARD_H

        img = self._grid_master_img
        draw = ImageDraw.Draw(img)
        item = self.filtered_candidates[idx]

        # Limpiar área de la tarjeta antes de redibujarla
        draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], fill=(15, 18, 24))

        is_sel = (idx == self.selected_card_idx)
        bg_col = (24, 34, 54) if is_sel else (20, 23, 34)
        border_col = (0, 122, 255) if is_sel else (36, 44, 61)
        border_w = 2 if is_sel else 1

        draw.rounded_rectangle([x0, y0, x1, y1], radius=14, fill=bg_col, outline=border_col, width=border_w)

        cx = (x0 + x1) // 2
        card_thumb = self.card_thumb_by_idx.get(idx)
        pil_im = self.raw_pil_by_idx.get(idx)

        if card_thumb is not None:
            tw, th = card_thumb.size
            tx = cx - tw // 2
            ty = (y0 + 14 + (118 - th) // 2) if is_wp else (y0 + 10 + (132 - th) // 2)
            img.paste(card_thumb, (tx, ty))
            outline_c = ((56, 189, 248) if is_sel else (55, 65, 85)) if is_wp else (55, 65, 85)
            draw.rectangle([tx - 1, ty - 1, tx + tw, ty + th], outline=outline_c, width=1)
        else:
            box_hw = 76 if is_wp else 55
            draw.rounded_rectangle([cx - box_hw, y0 + 18, cx + box_hw, y0 + 132], radius=8, fill=(13, 15, 22), outline=(32, 38, 52))
            draw.text((cx, y0 + 75), "Cargando...", fill=(100, 116, 139), anchor="mm", font=self._pil_font_badge)

        title_str = item.get("name", "Juego")
        if len(title_str) > 25:
            title_str = title_str[:23] + "…"
        draw.text((cx, y0 + 156), title_str, fill=(248, 250, 252), anchor="mm", font=self._pil_font_title)

        src = item.get("source", "Web")
        if pil_im is not None:
            iw, ih = item.get("orig_size", pil_im.size)
            if is_wp:
                b_txt = f"✦ 16:9 Apaisado ({iw}×{ih})"
                b_col = (56, 189, 248)
            else:
                adiff = abs(iw - ih) / float(max(1, max(iw, ih)))
                if adiff <= 0.14:
                    b_txt = f"✦ 1:1 Cuadrada ({iw}×{ih})"
                    b_col = (52, 199, 89)
                else:
                    b_txt = f"{src} ({iw}×{ih})"
                    b_col = (56, 189, 248)
        else:
            if is_wp:
                b_txt = f"✦ {src}"
                b_col = (56, 189, 248)
            else:
                b_txt = f"✦ {src}" if item.get("is_square") else src
                b_col = (52, 199, 89) if item.get("is_square") else (148, 163, 184)

        draw.text((cx, y0 + 178), b_txt, fill=b_col, anchor="mm", font=self._pil_font_badge)

        btn_y0 = y0 + 196
        btn_y1 = y0 + 224
        btn_fill = (0, 122, 255) if is_sel else (31, 37, 51)
        btn_txt = "✓ Seleccionado" if (is_sel and is_wp) else ("✓ Seleccionada" if is_sel else "Ver en Previa")
        btn_tcol = (255, 255, 255) if is_sel else (203, 213, 225)
        draw.rounded_rectangle([x0 + 14, btn_y0, x1 - 14, btn_y1], radius=10, fill=btn_fill)
        draw.text((cx, (btn_y0 + btn_y1) // 2), btn_txt, fill=btn_tcol, anchor="mm", font=self._pil_font_btn)

    def _rebuild_master_grid_image(self):
        """Dibuja todas las tarjetas sobre un único lienzo Pillow en RAM."""
        w = max(300, self.view_w)
        n = len(self.filtered_candidates)
        is_wp = (self.asset_mode == "wallpaper")
        if n == 0:
            self.total_scroll_h = max(1, self.view_h)
            img = Image.new("RGB", (w, self.total_scroll_h), (15, 18, 24))
            draw = ImageDraw.Draw(img)
            if is_wp:
                msg = "Buscando wallpapers apaisados (16:9)..." if self.is_searching else "No hay wallpapers apaisados para mostrar."
            else:
                msg = "Buscando carátulas en Google, Steam y GOG..." if self.is_searching else "No hay carátulas para mostrar."
            draw.text((w // 2, self.view_h // 2), msg, fill=(148, 163, 184), anchor="mm", font=self._pil_font_title)
            self._grid_master_img = img
            return

        rows = (n + self.GRID_COLS - 1) // self.GRID_COLS
        row_h = self.CARD_H + self.CARD_PAD_Y
        self.total_scroll_h = max(self.view_h, self.CARD_PAD_Y + rows * row_h + 12)

        self._grid_master_img = Image.new("RGB", (w, self.total_scroll_h), (15, 18, 24))
        for idx in range(n):
            self._draw_single_card_on_master(idx)

    def _blit_viewport_slice(self):
        """Recorta en <1ms la región visible del buffer maestro y la pinta como imagen única sin ScrollWindowEx."""
        if not hasattr(self, "grid_canvas") or not self.grid_canvas.winfo_exists():
            return
        if self._grid_master_img is None:
            self._rebuild_master_grid_image()

        master = self._grid_master_img
        mw, mh = master.size
        vw = max(1, min(mw, self.view_w))
        vh = max(1, min(mh, self.view_h))
        max_scroll = max(0, mh - vh)
        self.scroll_y = max(0, min(max_scroll, self.scroll_y))

        cropped = master.crop((0, self.scroll_y, vw, self.scroll_y + vh))
        self._grid_slice_tk = ImageTk.PhotoImage(cropped)

        if self._grid_img_item is None:
            self._grid_img_item = self.grid_canvas.create_image(0, 0, image=self._grid_slice_tk, anchor="nw")
        else:
            self.grid_canvas.itemconfig(self._grid_img_item, image=self._grid_slice_tk)

        # Actualizar posición de la barra de desplazamiento
        if mh > vh:
            top_f = self.scroll_y / float(mh)
            bot_f = min(1.0, (self.scroll_y + vh) / float(mh))
            self.scrollbar.set(top_f, bot_f)
        else:
            self.scrollbar.set(0.0, 1.0)

    def _hit_test_card(self, x: int, y: int) -> int:
        """Determina qué tarjeta fue pulsada según las coordenadas (x, y) en el lienzo."""
        if not self.filtered_candidates:
            return -1
        real_y = y + self.scroll_y
        card_w = getattr(self, "_computed_card_w", self.CARD_W)
        row_h = self.CARD_H + self.CARD_PAD_Y

        if real_y < self.CARD_PAD_Y or x < self.CARD_PAD_X:
            return -1

        row = (real_y - self.CARD_PAD_Y) // row_h
        col = (x - self.CARD_PAD_X) // (card_w + self.CARD_PAD_X)
        if col < 0 or col >= self.GRID_COLS:
            return -1

        idx = int(row * self.GRID_COLS + col)
        if 0 <= idx < len(self.filtered_candidates):
            return idx
        return -1

    def _on_grid_canvas_click(self, event):
        idx = self._hit_test_card(event.x, event.y)
        if idx >= 0:
            self._select_card_by_index(idx, auto_confirm=False)

    def _on_grid_canvas_double_click(self, event):
        idx = self._hit_test_card(event.x, event.y)
        if idx >= 0:
            self._select_card_by_index(idx, auto_confirm=True)

    # =================================================================
    # ADAPTACIÓN AL CUADRO Y VISTA PREVIA EN VIVO (PANEL DERECHO)
    # =================================================================
    def _invoke_wallpaper_callback(self, path_str: str, opacity_val: float, blur_val: float):
        if not self.on_wallpaper_selected_callback:
            return
        try:
            self.on_wallpaper_selected_callback(path_str, opacity_val, blur_val)
        except TypeError:
            self.on_wallpaper_selected_callback(path_str, opacity_val)

    def _set_fit_preset(self, preset_idx: int):
        feedback_click()
        if self.asset_mode == "wallpaper":
            if preset_idx < 0 or preset_idx >= len(self._wp_presets):
                return
            self._wp_preset_idx = preset_idx
            _, op_val, blur_val = self._wp_presets[preset_idx]
            if op_val < 0:
                # Opción "🗑 Sin Fondo": quitar wallpaper personalizado del juego
                self.current_wallpaper_path = ""
                self.current_wallpaper_pil = None
                self._invoke_wallpaper_callback("", self.wp_opacity, self.wp_blur)
                self.lbl_status.configure(
                    text="🗑 Se ha quitado el wallpaper de fondo personalizado de este juego.",
                    text_color="#fbbf24"
                )
                return

            self.wp_opacity = op_val
            self.wp_blur = blur_val
            norm_op = self._opacity_to_slider(self.wp_opacity)
            norm_blur = max(0.0, min(1.0, self.wp_blur / 12.0))
            self.offset_slider.set(norm_op)
            self.blur_slider.set(norm_blur)

            pct_op = int(round(self.wp_opacity * 100))
            blur_tag = "Nítido" if self.wp_blur < 0.3 else ("Suave" if self.wp_blur <= 2.5 else "Borroso")
            self.lbl_sl.configure(text=f"Opacidad del fondo (LB / RB): {pct_op}%")
            self.lbl_blur_sl.configure(text=f"Borrosidad / Desenfoque (LT / RT): {self.wp_blur:.1f} ({blur_tag})")

            for i, b in enumerate(self._fit_buttons):
                is_act = (i == preset_idx)
                b.configure(
                    fg_color="#007aff" if is_act else "#1a202c",
                    text_color=COLOR_TEXT_WHITE if is_act else ("#fca5a5" if i == 4 else "#cbd5e1")
                )
            cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx) or self.current_wallpaper_pil
            self._update_live_preview(cur_pil)
            return

        if preset_idx < 0 or preset_idx >= len(self._fit_presets):
            return
        self._fit_preset_idx = preset_idx
        _, self.fit_mode, self.crop_anchor, preset_offset = self._fit_presets[preset_idx]
        self.crop_offset = preset_offset

        # Sincronizar el deslizador con el preset elegido
        if preset_offset is not None:
            self.offset_slider.set(preset_offset)
        elif self.fit_mode == "auto":
            self.offset_slider.set(0.32)
        else:
            self.offset_slider.set(0.5)

        for i, b in enumerate(self._fit_buttons):
            if i == preset_idx:
                b.configure(fg_color="#007aff", text_color=COLOR_TEXT_WHITE)
            else:
                b.configure(fg_color="#1a202c", text_color=COLOR_TEXT_MUTED_LIGHT)

        cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx)
        self._update_live_preview(cur_pil)

    def _schedule_live_preview_debounced(self, cur_pil):
        """Coalesce actualizaciones continuas de sliders/arrastre a un framerate óptimo (35ms / ~30 FPS)."""
        job = getattr(self, "_preview_debounce_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._preview_debounce_job = self.after(35, lambda: self._update_live_preview(cur_pil))

    def _on_offset_slider_changed(self, value: float):
        """Ajusta el encuadre (modo carátula) o la opacidad del fondo (modo wallpaper 16:9)."""
        if self.asset_mode == "wallpaper":
            self.wp_opacity = self._slider_to_opacity(value)
            pct_op = int(round(self.wp_opacity * 100))
            self.lbl_sl.configure(text=f"Opacidad del fondo (LB / RB): {pct_op}%")
            self._refresh_wp_preset_highlight()
            cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx) or self.current_wallpaper_pil
            self._schedule_live_preview_debounced(cur_pil)
            return

        self.crop_offset = float(value)
        if self.fit_mode == "stretch":
            self.fit_mode = "crop"
        cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx)
        self._schedule_live_preview_debounced(cur_pil)

    def _on_blur_slider_changed(self, value: float):
        """Ajusta la borrosidad / desenfoque gaussiano del fondo en modo wallpaper 16:9 (0.0 Nítido ↔ 12.0 Borroso)."""
        self.wp_blur = round(float(value) * 12.0, 1)
        blur_tag = "Nítido" if self.wp_blur < 0.3 else ("Suave" if self.wp_blur <= 2.5 else "Borroso")
        self.lbl_blur_sl.configure(text=f"Borrosidad / Desenfoque (LT / RT): {self.wp_blur:.1f} ({blur_tag})")
        if self.asset_mode == "wallpaper":
            self._refresh_wp_preset_highlight()
            cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx) or self.current_wallpaper_pil
            self._schedule_live_preview_debounced(cur_pil)

    def _refresh_wp_preset_highlight(self):
        """Resalta el preset de wallpaper que coincide con los sliders (ninguno si el ajuste es personalizado)."""
        if self.asset_mode != "wallpaper":
            return
        self._wp_preset_idx = self._match_wp_preset_idx()
        for i, b in enumerate(self._fit_buttons):
            is_act = (i == self._wp_preset_idx)
            b.configure(
                fg_color="#007aff" if is_act else "#1a202c",
                text_color=COLOR_TEXT_WHITE if is_act else ("#fca5a5" if i == 4 else "#cbd5e1")
            )

    def _on_preview_drag_start(self, event):
        self._preview_drag_start_y = event.y
        self._preview_drag_start_offset = self.crop_offset if self.crop_offset is not None else float(self.offset_slider.get())

    def _on_preview_drag_motion(self, event):
        """Arrastrar verticalmente sobre la caja de vista previa desplaza el encuadre en vivo."""
        dy = event.y - self._preview_drag_start_y
        new_off = max(0.0, min(1.0, self._preview_drag_start_offset - (dy / 160.0)))
        if self.asset_mode == "wallpaper":
            self.offset_slider.set(new_off)
            self._on_offset_slider_changed(new_off)
            return
        self.crop_offset = new_off
        if self.fit_mode == "stretch":
            self.fit_mode = "crop"
        self.offset_slider.set(new_off)
        cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx)
        self._schedule_live_preview_debounced(cur_pil)

    def _update_live_preview(self, pil_img: Optional[Image.Image]):
        """Renderiza en el panel lateral derecho cómo se verá la carátula (1:1) o el wallpaper (16:9 Big Picture)."""
        if not hasattr(self, "preview_canvas") or not self.preview_canvas.winfo_exists():
            return

        if self.asset_mode == "wallpaper":
            stage = Image.new("RGBA", (240, 248), (11, 13, 19, 255))
            s_draw = ImageDraw.Draw(stage)
            pct = int(round(self.wp_opacity * 100))
            blur_tag = "Nítido" if self.wp_blur < 0.3 else ("Suave" if self.wp_blur <= 2.5 else "Borroso")
            preview_src = pil_img or self.current_wallpaper_pil

            # 1. Mini-escenario Big Picture superior (232x136) a pantalla completa sin barras grises
            mini_w, mini_h = 232, 136
            mini_floor = 98
            if preview_src is not None:
                orig_sz = None
                if 0 <= self.selected_card_idx < len(self.filtered_candidates):
                    orig_sz = self.filtered_candidates[self.selected_card_idx].get("orig_size")
                w, h = orig_sz if orig_sz else preview_src.size
                self.lbl_prev_info.configure(
                    text=f"Wallpaper 16:9 ({w}×{h} px)\nOpacidad: {pct}%  •  Borrosidad: {self.wp_blur:.1f} ({blur_tag})",
                    text_color=COLOR_CYAN_ACCENT
                )
                mini_bg = compose_big_picture_wallpaper_bg(
                    preview_src,
                    w=mini_w,
                    h=mini_h,
                    floor_y=mini_floor,
                    opacity=self.wp_opacity,
                    blur_radius=max(0.0, self.wp_blur * 0.45)
                ).convert("RGBA")
            else:
                self.lbl_prev_info.configure(
                    text=f"Selecciona un wallpaper 16:9 a la izquierda\nOpacidad: {pct}%  •  Borrosidad: {self.wp_blur:.1f}",
                    text_color=COLOR_TEXT_MUTED
                )
                mini_bg = Image.new("RGBA", (mini_w, mini_h), (15, 18, 24, 255))

            # Superponer la carátula del juego en primer plano (cacheada para 0 latencia al mover sliders)
            fg_flat = getattr(self, "_cached_fg_flat_72", None)
            if fg_flat is None:
                fg_src = self.current_cover_pil or create_procedural_album(self.game_name or "Juego", size=120)
                fg_jewel = create_jewel_case(fg_src, name=self.game_name, size=72)
                fg_flat, _, _ = prepare_flat_cover(fg_jewel, 72, has_reflection=True)
                self._cached_fg_flat_72 = fg_flat
            mini_bg.paste(fg_flat, ((mini_w - 72) // 2, mini_floor - 72), fg_flat)

            stage.paste(mini_bg, (4, 4))
            s_draw.rectangle([3, 3, 4 + mini_w, 4 + mini_h], outline=(0, 122, 255, 180), width=1)
            s_draw.text((120, 13), "Escenario Big Picture Completo", fill=(226, 232, 240, 220), anchor="mm", font=self._pil_font_badge)

            # 2. Vista inferior del arte apaisado 16:9 al 100% de nitidez (232x98, cacheada por imagen)
            raw_w, raw_h = 232, 98
            if preview_src is not None:
                if getattr(self, "_cached_wp_sharp_src_id", None) != id(preview_src):
                    self._cached_wp_sharp_src_id = id(preview_src)
                    self._cached_wp_sharp_im = adapt_wallpaper_to_widescreen(preview_src, width=raw_w, height=raw_h).convert("RGBA")
                wp_sharp = self._cached_wp_sharp_im
                stage.paste(wp_sharp, (4, 146))
                s_draw.rectangle([3, 145, 4 + raw_w, 146 + raw_h], outline=(56, 189, 248, 130), width=1)
            else:
                s_draw.rounded_rectangle([4, 146, 4 + raw_w, 146 + raw_h], radius=8, fill=(16, 20, 28, 255), outline=(36, 44, 61, 255))
                s_draw.text((120, 195), "Arte 16:9 Original", fill=(100, 116, 139, 255), anchor="mm", font=self._pil_font_badge)

            self._preview_tk_ref = ImageTk.PhotoImage(stage)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(0, 0, image=self._preview_tk_ref, anchor="nw")
            return

        box_size = 186
        if pil_img is None:
            base_im = create_procedural_album(self.game_name or "Juego", size=box_size)
            self.lbl_prev_info.configure(
                text="Selecciona cualquier carátula de la izquierda para ver cómo queda en la caja.",
                text_color=COLOR_TEXT_MUTED
            )
        else:
            orig_sz = None
            if 0 <= self.selected_card_idx < len(self.filtered_candidates):
                orig_sz = self.filtered_candidates[self.selected_card_idx].get("orig_size")
            w, h = orig_sz if orig_sz else pil_img.size
            mode_label = self._fit_presets[self._fit_preset_idx][0]
            pct = int(round((self.crop_offset if self.crop_offset is not None else self.offset_slider.get()) * 100))
            self.lbl_prev_info.configure(
                text=f"Original: {w}×{h} px → Caja 1:1\nModo: {mode_label} (Encuadre {pct}%)",
                text_color=COLOR_CYAN_ACCENT
            )
            base_im = pil_img

        jewel = create_jewel_case(
            base_im,
            name=self.game_name,
            size=box_size,
            fit_mode=self.fit_mode,
            crop_anchor=self.crop_anchor,
            crop_offset=self.crop_offset
        )
        flat_with_refl, _, _ = prepare_flat_cover(jewel, box_size, has_reflection=True)

        stage = Image.new("RGBA", (240, 248), (11, 13, 19, 255))
        ox = (240 - box_size) // 2
        oy = 6
        stage.paste(flat_with_refl, (ox, oy), flat_with_refl)

        self._preview_tk_ref = ImageTk.PhotoImage(stage)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, image=self._preview_tk_ref, anchor="nw")

    # =================================================================
    # BÚSQUEDA Y CARGA ASÍNCRONA DE MINIATURAS Y ALTA RESOLUCIÓN
    # =================================================================
    def _start_search(self):
        query = self.entry_search.get().strip()
        if not query:
            return

        is_wp = (self.asset_mode == "wallpaper")
        self.is_searching = True
        self._search_generation += 1
        current_gen = self._search_generation
        self.btn_search.configure(state="disabled")
        if is_wp:
            self.lbl_status.configure(
                text=f"🌐 Buscando wallpapers apaisados (16:9 HD) para '{query}'...",
                text_color=COLOR_CYAN_ACCENT
            )
        else:
            self.lbl_status.configure(
                text=f"🌐 Buscando carátulas en Google, Steam y GOG para '{query}'...",
                text_color=COLOR_CYAN_ACCENT
            )

        if self._thumb_executor:
            try:
                self._thumb_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        self._thumb_executor = ThreadPoolExecutor(max_workers=10)

        self.raw_pil_by_idx.clear()
        self.card_thumb_by_idx.clear()
        self.hd_pil_by_idx.clear()
        self.full_res_loaded.clear()
        self.all_candidates.clear()
        self.filtered_candidates.clear()
        self.selected_card_idx = 0
        self.scroll_y = 0
        self._schedule_grid_redraw(rebuild_master=True)
        self._update_live_preview(None)

        def _worker():
            if is_wp:
                results = search_wallpaper_candidates(query, max_results=24)
            else:
                results = search_cover_candidates(query, max_results=24)

            def _apply_ui():
                if not self.winfo_exists() or current_gen != self._search_generation:
                    return
                self.is_searching = False
                self.btn_search.configure(state="normal")
                self.all_candidates = results
                self.filtered_candidates = list(results)

                if not results:
                    self.lbl_status.configure(
                        text=f"⚠ No se encontraron resultados para '{query}'. Prueba palabras clave más simples.",
                        text_color="#fbbf24"
                    )
                    self._schedule_grid_redraw(rebuild_master=True)
                    return

                if is_wp:
                    self.lbl_status.configure(
                        text=f"¡Se encontraron {len(results)} wallpaper(s) 16:9! Ajusta Opacidad (LB/RB) y Borrosidad (LT/RT) a la derecha.",
                        text_color="#4ade80"
                    )
                else:
                    self.lbl_status.configure(
                        text=f"¡Se encontraron {len(results)} carátula(s)! Haz clic en cualquiera para previsualizarla y adaptarla a la derecha.",
                        text_color="#4ade80"
                    )
                self._schedule_grid_redraw(rebuild_master=True)
                self._highlight_card(0)
                self._load_thumbnails_async(self.filtered_candidates, current_gen, is_wp)

                # Pre-calentar en segundo plano la otra pestaña para que cambiar entre Carátula y Wallpaper sea instantáneo (0ms)
                def _prewarm_other():
                    try:
                        if is_wp:
                            search_cover_candidates(query, max_results=24)
                        else:
                            search_wallpaper_candidates(query, max_results=24)
                    except Exception:
                        pass
                threading.Thread(target=_prewarm_other, daemon=True).start()

            self.after(0, _apply_ui)

        threading.Thread(target=_worker, daemon=True).start()

    def _prepare_card_and_preview_images(self, im: Image.Image, is_wp: bool, card_w: int):
        """Pre-escala la miniatura de tarjeta y la imagen de vista previa en el hilo secundario (0 carga en el hilo UI)."""
        iw, ih = im.size
        orig_size = (iw, ih)

        # 1. Imagen ligera para la vista previa en vivo (máx 600px de lado mayor para respuesta en <2ms)
        max_prev = 600.0
        if max(iw, ih) > max_prev:
            sc_p = max_prev / float(max(iw, ih))
            pw, ph = max(1, int(iw * sc_p)), max(1, int(ih * sc_p))
            preview_im = im.convert("RGBA").resize((pw, ph), Image.Resampling.BILINEAR)
        else:
            preview_im = im.convert("RGBA")

        # 2. Miniatura exacta lista para pegar con .paste() directo sobre la tarjeta
        if is_wp:
            max_tw = max(130, card_w - 22)
            max_th = 114
            th_h = int(max_tw * 9 / 16)
            if th_h > max_th:
                th_h = max_th
                max_tw = int(max_th * 16 / 9)
            card_thumb = adapt_wallpaper_to_widescreen(preview_im, width=max_tw, height=th_h)
        else:
            scale = min(132.0 / max(1, iw), 132.0 / max(1, ih))
            tw, th = max(1, int(iw * scale)), max(1, int(ih * scale))
            card_thumb = preview_im.convert("RGB").resize((tw, th), Image.Resampling.BILINEAR)

        return preview_im, card_thumb, orig_size

    def _load_thumbnails_async(self, candidates: List[Dict[str, Any]], gen: int, is_wp: bool):
        w = max(300, self.view_w)
        avail_w = w - self.CARD_PAD_X * (self.GRID_COLS + 1)
        card_w = max(180, avail_w // self.GRID_COLS)

        def _fetch_one(idx: int, item: Dict[str, Any]):
            if gen != self._search_generation:
                return
            poster_u = item.get("poster_url")
            thumb_u = item.get("thumb_url")
            # Priorizar SIEMPRE thumb_url (CDN ultrarrápido de ~20 KB) para carga instantánea de la cuadrícula
            primary_u = thumb_u or poster_u
            fallback_u = poster_u if primary_u == thumb_u else thumb_u
            if not primary_u:
                return

            im = self._thumb_cache.get(primary_u)
            if not im:
                im = fetch_image_from_url(primary_u, fallback_url=fallback_u, timeout=2.2)
                if im:
                    self._thumb_cache[primary_u] = im

            if im and gen == self._search_generation:
                try:
                    preview_im, card_thumb, orig_sz = self._prepare_card_and_preview_images(im, is_wp, card_w)
                    if primary_u == poster_u:
                        self.hd_pil_by_idx[idx] = im
                        self.full_res_loaded[idx] = True
                    self.after(0, lambda i=idx, p=preview_im, c=card_thumb, s=orig_sz, g=gen: self._apply_thumbnail_to_card(i, p, c, s, g))
                except Exception:
                    pass

        if self._thumb_executor:
            for i, item in enumerate(candidates):
                self._thumb_executor.submit(_fetch_one, i, item)

    def _apply_thumbnail_to_card(self, idx: int, preview_im: Image.Image, card_thumb: Image.Image, orig_size, gen: int):
        if not self.winfo_exists() or gen != self._search_generation or idx >= len(self.filtered_candidates):
            return

        self.filtered_candidates[idx]["orig_size"] = orig_size
        self.raw_pil_by_idx[idx] = preview_im
        self.card_thumb_by_idx[idx] = card_thumb

        # Actualizar únicamente esta tarjeta en el buffer maestro (<0.1ms) y agendar blit a 60 FPS
        self._draw_single_card_on_master(idx)
        self._request_coalesced_blit()

        if idx == self.selected_card_idx:
            self._update_live_preview(preview_im)
            self._prefetch_full_hd_for_card(idx, gen)

    def _prefetch_full_hd_for_card(self, idx: int, gen: int):
        """Descarga silenciosamente en segundo plano la versión Full HD de la tarjeta seleccionada."""
        if idx in self.full_res_loaded or idx < 0 or idx >= len(self.filtered_candidates):
            return
        item = self.filtered_candidates[idx]
        poster_u = item.get("poster_url")
        thumb_u = item.get("thumb_url")
        if not poster_u or poster_u == thumb_u:
            self.full_res_loaded[idx] = True
            return

        self.full_res_loaded[idx] = True

        def _bg_hd():
            if gen != self._search_generation:
                return
            im_hd = self._thumb_cache.get(poster_u)
            if not im_hd:
                im_hd = fetch_image_from_url(poster_u, timeout=2.8)
                if im_hd:
                    self._thumb_cache[poster_u] = im_hd
            if im_hd and gen == self._search_generation:
                self.hd_pil_by_idx[idx] = im_hd
                iw, ih = im_hd.size
                if idx < len(self.filtered_candidates):
                    self.filtered_candidates[idx]["orig_size"] = (iw, ih)

        if self._thumb_executor:
            try:
                self._thumb_executor.submit(_bg_hd)
            except Exception:
                pass

    def _highlight_card(self, idx: int):
        if not self.filtered_candidates or idx < 0 or idx >= len(self.filtered_candidates):
            return

        prev_idx = self.selected_card_idx
        self.selected_card_idx = idx
        self._ensure_card_visible(idx)

        if self._grid_master_img is None:
            self._rebuild_master_grid_image()
        else:
            if 0 <= prev_idx < len(self.filtered_candidates) and prev_idx != idx:
                self._draw_single_card_on_master(prev_idx)
            self._draw_single_card_on_master(idx)
        self._blit_viewport_slice()

        cur_pil = self.raw_pil_by_idx.get(idx)
        self._update_live_preview(cur_pil)
        self._prefetch_full_hd_for_card(idx, self._search_generation)

        chosen = self.filtered_candidates[idx]
        if self.asset_mode == "wallpaper":
            self.btn_confirm.configure(state="normal", text="✓ Aplicar Wallpaper 16:9 ")
            self.lbl_status.configure(
                text=f"Wallpaper seleccionado: '{chosen.get('name')}'. Ajusta Opacidad (LB/RB) y Borrosidad (LT/RT) a la derecha.",
                text_color=COLOR_CYAN_ACCENT
            )
        else:
            self.btn_confirm.configure(state="normal", text="✓ Aplicar Esta Carátula ")
            self.lbl_status.configure(
                text=f"Previsualizando: '{chosen.get('name')}'. Usa los botones 'Auto / Completo / Arriba / Centro / Abajo' a la derecha para encuadrarla.",
                text_color=COLOR_CYAN_ACCENT
            )

    def _select_card_by_index(self, idx: int, auto_confirm: bool = False):
        feedback_click()
        self._highlight_card(idx)
        if auto_confirm:
            self._confirm_selected()

    def _navigate_grid(self, dx: int, dy: int):
        if not self.filtered_candidates:
            return

        total = len(self.filtered_candidates)
        cur = self.selected_card_idx

        new_idx = cur
        if dx != 0:
            new_idx = max(0, min(total - 1, cur + dx))
        elif dy != 0:
            target = cur + (dy * self.GRID_COLS)
            if 0 <= target < total:
                new_idx = target

        if new_idx != cur:
            feedback_click()
            self._highlight_card(new_idx)

    def _open_search_keyboard(self):
        from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
        def _on_confirm(val: str):
            try:
                self.entry_search.delete(0, tk.END)
                self.entry_search.insert(0, val)
                self._on_search_button_clicked()
            except Exception:
                pass
        prompt_on_screen_keyboard(self, title="Buscar Carátula o Wallpaper", initial_text=self.entry_search.get(), on_confirm=_on_confirm)

    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        if inputs.get("b", False) and not prev_inputs.get("b", False):
            self.destroy()
            return True

        # Botón Select / Share: Alternar entre Carátula (Caja 3D) y Wallpaper 16:9 (Fondo Big Picture)
        if inputs.get("select", False) and not prev_inputs.get("select", False):
            next_mode = "wallpaper" if self.asset_mode == "cover" else "cover"
            self._switch_asset_mode(next_mode)
            return True

        if (inputs.get("a", False) and not prev_inputs.get("a", False)) or \
           (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self._confirm_selected()
            return True

        if inputs.get("y", False) and not prev_inputs.get("y", False):
            if self.asset_mode == "wallpaper":
                next_p = (max(-1, self._wp_preset_idx) + 1) % 4  # Cicla entre los 4 presets de Nitidez/Opacidad
                self._set_fit_preset(next_p)
            else:
                next_preset = (self._fit_preset_idx + 1) % len(self._fit_presets)
                self._set_fit_preset(next_preset)
            return True

        if self.asset_mode == "wallpaper":
            # En modo Wallpaper: LB / RB ajusta Opacidad, LT / RT ajusta Borrosidad / Desenfoque
            if inputs.get("lb", False) and not prev_inputs.get("lb", False):
                cur_val = float(self.offset_slider.get())
                new_val = max(0.0, cur_val - 0.08)
                self.offset_slider.set(new_val)
                self._on_offset_slider_changed(new_val)
                return True
            if inputs.get("rb", False) and not prev_inputs.get("rb", False):
                cur_val = float(self.offset_slider.get())
                new_val = min(1.0, cur_val + 0.08)
                self.offset_slider.set(new_val)
                self._on_offset_slider_changed(new_val)
                return True
            if inputs.get("lt", False) and not prev_inputs.get("lt", False):
                cur_b = float(self.blur_slider.get())
                new_b = max(0.0, cur_b - 0.08)
                self.blur_slider.set(new_b)
                self._on_blur_slider_changed(new_b)
                return True
            if inputs.get("rt", False) and not prev_inputs.get("rt", False):
                cur_b = float(self.blur_slider.get())
                new_b = min(1.0, cur_b + 0.08)
                self.blur_slider.set(new_b)
                self._on_blur_slider_changed(new_b)
                return True
        else:
            # En modo Carátula: LB / RB o LT / RT ajusta el deslizador de encuadre
            if (inputs.get("lb", False) and not prev_inputs.get("lb", False)) or \
               (inputs.get("lt", False) and not prev_inputs.get("lt", False)):
                cur_val = float(self.offset_slider.get())
                new_val = max(0.0, cur_val - 0.08)
                self.offset_slider.set(new_val)
                self._on_offset_slider_changed(new_val)
                return True

            if (inputs.get("rb", False) and not prev_inputs.get("rb", False)) or \
               (inputs.get("rt", False) and not prev_inputs.get("rt", False)):
                cur_val = float(self.offset_slider.get())
                new_val = min(1.0, cur_val + 0.08)
                self.offset_slider.set(new_val)
                self._on_offset_slider_changed(new_val)
                return True

        if inputs.get("x", False) and not prev_inputs.get("x", False):
            self._open_search_keyboard()
            return True

        if inputs.get("left", False) and not prev_inputs.get("left", False):
            self._navigate_grid(-1, 0)
            return True
        if inputs.get("right", False) and not prev_inputs.get("right", False):
            self._navigate_grid(1, 0)
            return True
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self._navigate_grid(0, -1)
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self._navigate_grid(0, 1)
            return True

        return False

    def _confirm_selected(self):
        is_wp = (self.asset_mode == "wallpaper")
        if not self.filtered_candidates or self.selected_card_idx >= len(self.filtered_candidates):
            # Si ya había un wallpaper en disco y el usuario solo ajustó Opacidad/Borrosidad, permitir guardar
            if is_wp and self.current_wallpaper_path and os.path.isfile(self.current_wallpaper_path):
                feedback_cover_applied()
                self._invoke_wallpaper_callback(self.current_wallpaper_path, self.wp_opacity, self.wp_blur)
                self.destroy()
            return

        chosen = self.filtered_candidates[self.selected_card_idx]
        poster_url = chosen.get("poster_url")
        if not poster_url:
            return

        chosen_idx = self.selected_card_idx
        chosen_pil = self.hd_pil_by_idx.get(chosen_idx) or self.raw_pil_by_idx.get(chosen_idx)

        if is_wp:
            self.btn_confirm.configure(state="disabled", text="Guardando Wallpaper...")
            self.lbl_status.configure(
                text=f"⬇ Aplicando wallpaper apaisado 16:9 para '{chosen.get('name')}'...",
                text_color="#00f3ff"
            )
            chosen_opacity = self.wp_opacity
            chosen_blur = self.wp_blur

            def _wp_worker():
                os.makedirs(WALLPAPERS_DIR, exist_ok=True)
                safe_name = "".join(c for c in self.game_name if c.isalnum() or c in (' ', '_', '-')).strip() or "game"
                target_file_path = os.path.join(WALLPAPERS_DIR, f"{safe_name}_wallpaper.png")

                src_im = self.hd_pil_by_idx.get(chosen_idx)
                if src_im is None and poster_url != chosen.get("thumb_url"):
                    src_im = fetch_image_from_url(poster_url, timeout=2.0)
                if src_im is None:
                    src_im = chosen_pil

                success = False
                if src_im is not None:
                    try:
                        adapted = adapt_wallpaper_to_widescreen(
                            src_im.convert("RGB"),
                            width=1920,
                            height=1080,
                            crop_offset=0.5
                        )
                        tmp_out = f"{target_file_path}.tmp"
                        adapted.save(tmp_out, "PNG", compress_level=1)
                        os.replace(tmp_out, target_file_path)
                        success = True
                    except Exception:
                        success = False

                if not success:
                    success = download_and_save_wallpaper(
                        poster_url,
                        target_file_path,
                        fallback_url=chosen.get("thumb_url"),
                        crop_offset=0.5
                    )

                def _finish_wp():
                    if not self.winfo_exists():
                        return
                    if success and os.path.isfile(target_file_path):
                        feedback_cover_applied()
                        self._invoke_wallpaper_callback(target_file_path, chosen_opacity, chosen_blur)
                        self.destroy()
                    else:
                        self.btn_confirm.configure(state="normal", text="✓ Aplicar Wallpaper 16:9 ")
                        self.lbl_status.configure(
                            text="❌ Error al descargar o guardar el wallpaper elegido. Inténtalo de nuevo.",
                            text_color="#f43f5e"
                        )

                self.after(0, _finish_wp)

            threading.Thread(target=_wp_worker, daemon=True).start()
            return

        self.btn_confirm.configure(state="disabled", text="Guardando Carátula...")
        self.lbl_status.configure(
            text=f"⬇ Aplicando carátula con el encuadre seleccionado para '{chosen.get('name')}'...",
            text_color="#00f3ff"
        )

        chosen_fit_mode = self.fit_mode
        chosen_crop_anchor = self.crop_anchor
        chosen_crop_offset = self.crop_offset

        def _download_worker():
            os.makedirs(COVERS_DIR, exist_ok=True)
            safe_name = "".join(c for c in self.game_name if c.isalnum() or c in (' ', '_', '-')).strip()
            target_file_path = os.path.join(COVERS_DIR, f"{safe_name}.png")

            src_im = self.hd_pil_by_idx.get(chosen_idx)
            if src_im is None and poster_url != chosen.get("thumb_url"):
                src_im = fetch_image_from_url(poster_url, timeout=2.0)
            if src_im is None:
                src_im = chosen_pil

            success = False
            if src_im is not None:
                try:
                    adapted = adapt_cover_to_square(
                        src_im.convert("RGBA"),
                        size=600,
                        fit_mode=chosen_fit_mode,
                        crop_anchor=chosen_crop_anchor,
                        crop_offset=chosen_crop_offset
                    )
                    tmp_out = f"{target_file_path}.tmp"
                    adapted.save(tmp_out, "PNG", compress_level=1)
                    os.replace(tmp_out, target_file_path)
                    success = True
                except Exception:
                    success = False

            if not success:
                success = download_and_save_cover(
                    poster_url,
                    target_file_path,
                    fallback_url=chosen.get("thumb_url"),
                    fit_mode=chosen_fit_mode,
                    crop_anchor=chosen_crop_anchor,
                    crop_offset=chosen_crop_offset
                )

            def _finish():
                if not self.winfo_exists():
                    return
                if success and os.path.isfile(target_file_path):
                    feedback_cover_applied()
                    if self.on_selected_callback:
                        self.on_selected_callback(target_file_path)
                    self.destroy()
                else:
                    self.btn_confirm.configure(state="normal", text="✓ Aplicar Esta Carátula ")
                    self.lbl_status.configure(
                        text="❌ Error al descargar o guardar la carátula elegida. Inténtalo de nuevo.",
                        text_color="#f43f5e"
                    )

            self.after(0, _finish)

        threading.Thread(target=_download_worker, daemon=True).start()

    def destroy(self):
        unregister_modal_stack(self)
        try:
            self.grab_release()
        except Exception:
            pass
        if self._thumb_executor:
            try:
                self._thumb_executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        super().destroy()
