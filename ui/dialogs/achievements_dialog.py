"""
GameFlow - Diálogo de Logros y Trofeos (Steam & RetroAchievements)
==================================================================
Diálogo modal Glassmorphism 100% operable con mando que ofrece:
1. Vista unificada de logros oficiales de Steam y RetroAchievements.
2. Medidor visual de progreso, puntos y porcentaje de desbloqueo.
3. Filtros rápidos (Todos, Desbloqueados, Bloqueados, Secretos) con LB/RB.
4. Consulta y refresco asíncrono sin bloquear la interfaz.
5. Diálogo integrado de configuración de API Keys y autodetección de SteamID en Windows.
6. Vinculación de juegos a Steam AppID o RetroAchievements GameID.
"""

import os
import threading
import tkinter as tk
from typing import Dict, Any, Optional, Callable, List
import customtkinter as ctk
from PIL import Image

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
from core.achievements_service import (
    load_achievements_config, save_achievements_config,
    detect_local_steam_profile, detect_game_steam_appid,
    detect_game_retroachievements_id, set_game_retroachievements_id,
    get_game_achievements, fetch_steam_achievements, fetch_retroachievements
)
from core.feedback import feedback_click, trigger_haptic
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_DANGER, COLOR_STATUS_WARNING,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, font_title, scroll_to_widget
)


class AchievementsDialog(BaseGlassDialog):
    """
    Diálogo modal Glassmorphism para inspeccionar logros de Steam y RetroAchievements.
    """

    def __init__(
        self,
        parent,
        game: Dict[str, Any],
        on_game_updated: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        super().__init__(
            parent,
            title=f"Logros y Trofeos - {game.get('name', 'Juego')}",
            width=860,
            height=620,
            corner_radius=22
        )
        self.game = game
        self.on_game_updated = on_game_updated

        # Estado interno
        self.is_loading: bool = False
        self.achievements_data: Dict[str, Any] = {}
        self.active_filter: str = "all"  # "all", "unlocked", "locked", "secret"
        self.filter_options = [
            ("all", "Todos"),
            ("unlocked", "Desbloqueados 🟢"),
            ("locked", "Bloqueados 🔒"),
            ("secret", "Secretos ❓")
        ]
        self.active_filter_idx: int = 0
        self.selected_item_idx: int = 0
        self._item_frames: List[ctk.CTkFrame] = []
        self._filtered_items: List[Dict[str, Any]] = []

        self._build_ui()
        self._load_data(force_refresh=False)

    _center_window = BaseGlassDialog.center_window

    def _build_ui(self):
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)

        # ---------------- Cabecera ----------------
        self.header_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=50)
        self.header_bar.pack(fill="x", padx=20, pady=(12, 6))

        # Icono / Carátula
        self._thumb_img = None
        cover_path = self.game.get("cover")
        if cover_path and os.path.isfile(cover_path):
            try:
                with Image.open(cover_path) as raw_im:
                    pil_img = raw_im.resize((44, 44), Image.Resampling.LANCZOS)
                self._thumb_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(44, 44))
                lbl_icon = ctk.CTkLabel(self.header_bar, image=self._thumb_img, text="")
                lbl_icon.pack(side="left", padx=(0, 12))
            except Exception:
                lbl_icon = ctk.CTkLabel(self.header_bar, text="🏆", font=font_title(24))
                lbl_icon.pack(side="left", padx=(0, 12))
        else:
            lbl_icon = ctk.CTkLabel(self.header_bar, text="🏆", font=font_title(24))
            lbl_icon.pack(side="left", padx=(0, 12))

        # Título y Metadata
        info_col = ctk.CTkFrame(self.header_bar, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True)

        g_name = self.game.get("name", "Juego")
        self.lbl_title = ctk.CTkLabel(
            info_col,
            text=f"🏆 Logros de {g_name}",
            font=font_title(18),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        self.lbl_title.pack(anchor="w")

        self.lbl_platform_badge = ctk.CTkLabel(
            info_col,
            text="Cargando plataforma...",
            font=font_body(11),
            text_color=COLOR_CYAN_ACCENT,
            anchor="w"
        )
        self.lbl_platform_badge.pack(anchor="w")

        # Botones de Acción en Cabecera
        btn_box = ctk.CTkFrame(self.header_bar, fg_color="transparent")
        btn_box.pack(side="right")

        self.btn_refresh = ctk.CTkButton(
            btn_box,
            text="🔄 Refrescar (X)",
            width=110,
            height=30,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=10,
            command=self._refresh_online
        )
        self.btn_refresh.pack(side="left", padx=4)

        self.btn_settings = ctk.CTkButton(
            btn_box,
            text="⚙ Cuentas (Y)",
            width=105,
            height=30,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=10,
            command=self._open_settings
        )
        self.btn_settings.pack(side="left", padx=4)

        self.btn_close = ctk.CTkButton(
            btn_box,
            text="✕ Cerrar (B)",
            width=90,
            height=30,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=10,
            command=self.close
        )
        self.btn_close.pack(side="left", padx=4)

        for w in (self.header_bar, self.lbl_title, info_col, self.lbl_platform_badge):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # ---------------- Barra de Progreso y Estadísticas ----------------
        self.progress_card = ctk.CTkFrame(
            self.main_card,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_GLASS_BORDER,
            border_width=1,
            corner_radius=14
        )
        self.progress_card.pack(fill="x", padx=20, pady=(4, 8))

        stats_row = ctk.CTkFrame(self.progress_card, fg_color="transparent")
        stats_row.pack(fill="x", padx=16, pady=(10, 4))

        self.lbl_progress_text = ctk.CTkLabel(
            stats_row,
            text="🏆 0 / 0 Desbloqueados (0%)",
            font=font_title(13),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_progress_text.pack(side="left")

        self.lbl_points_text = ctk.CTkLabel(
            stats_row,
            text="",
            font=font_body(12),
            text_color=COLOR_STATUS_WARNING
        )
        self.lbl_points_text.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            self.progress_card,
            height=10,
            corner_radius=5,
            progress_color=COLOR_STATUS_SUCCESS,
            fg_color=COLOR_BG_DARK
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x", padx=16, pady=(0, 10))

        # ---------------- Filtros (Segmented Control / LB / RB) ----------------
        self.filter_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=34)
        self.filter_bar.pack(fill="x", padx=20, pady=(2, 6))

        self.filter_buttons: List[ctk.CTkButton] = []
        for idx, (f_id, f_label) in enumerate(self.filter_options):
            b = ctk.CTkButton(
                self.filter_bar,
                text=f_label,
                font=font_button(11),
                height=28,
                corner_radius=9,
                fg_color=COLOR_IOS_BLUE if idx == 0 else COLOR_BG_CARD_SECONDARY,
                text_color=COLOR_TEXT_WHITE if idx == 0 else COLOR_TEXT_MUTED_LIGHT,
                command=lambda i=idx: self._select_filter(i)
            )
            b.pack(side="left", padx=(0, 6))
            self.filter_buttons.append(b)

        lbl_hint = ctk.CTkLabel(
            self.filter_bar,
            text="LB / RB para cambiar filtro  •  D-Pad para navegar",
            font=font_body(10),
            text_color=COLOR_TEXT_DIM
        )
        lbl_hint.pack(side="right", padx=4)

        # ---------------- Lista Scrolleable de Logros ----------------
        self.scroll_container = ctk.CTkScrollableFrame(
            self.main_card,
            fg_color="transparent",
            corner_radius=12
        )
        self.scroll_container.pack(fill="both", expand=True, padx=16, pady=(2, 8))

        # Mensaje de carga inicial
        self.lbl_empty = ctk.CTkLabel(
            self.scroll_container,
            text="⏳ Cargando logros y progreso...",
            font=font_body(14),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_empty.pack(pady=60)

    # ---------------- Carga de Datos Asíncrona ----------------
    def _load_data(self, force_refresh: bool = False):
        if self.is_loading:
            return
        self.is_loading = True
        self.btn_refresh.configure(text="⏳ Cargando...")

        def _worker():
            data = get_game_achievements(self.game, force_refresh=force_refresh)
            if self.winfo_exists():
                self.after(0, lambda: self._on_data_loaded(data))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_data_loaded(self, data: Dict[str, Any]):
        if not self.winfo_exists():
            return
        self.is_loading = False
        self.achievements_data = data
        self.btn_refresh.configure(text="🔄 Refrescar (X)")

        plat = data.get("platform", "Local")
        tot = data.get("total_count", 0)
        unlocked = data.get("unlocked_count", 0)
        pct = data.get("progress_percent", 0.0)
        tot_pts = data.get("total_points", 0)
        unlocked_pts = data.get("unlocked_points", 0)

        # Actualizar badge de plataforma
        if plat == "Steam":
            appid = data.get("game_id", "")
            self.lbl_platform_badge.configure(
                text=f"🎮 Plataforma: Steam (AppID: {appid})",
                text_color=COLOR_CYAN_ACCENT
            )
        elif plat == "RetroAchievements":
            gid = data.get("game_id", "")
            self.lbl_platform_badge.configure(
                text=f"🏆 Plataforma: RetroAchievements (Game #{gid})",
                text_color=COLOR_STATUS_WARNING
            )
        else:
            self.lbl_platform_badge.configure(
                text="⭐ Plataforma: Metas y Logros Locales de GameFlow",
                text_color=COLOR_TEXT_DIM
            )

        # Actualizar barra de progreso
        self.lbl_progress_text.configure(
            text=f"🏆 {unlocked} / {tot} Desbloqueados ({pct}%)"
        )
        if tot_pts > 0:
            self.lbl_points_text.configure(
                text=f"💎 Puntos: {unlocked_pts} / {tot_pts} pts"
            )
        else:
            self.lbl_points_text.configure(text="")

        self.progress_bar.set(min(1.0, max(0.0, pct / 100.0)))

        # Actualizar contadores de botones de filtro
        achs = data.get("achievements", [])
        c_unlocked = sum(1 for a in achs if a.get("unlocked"))
        c_locked = sum(1 for a in achs if not a.get("unlocked"))
        c_secret = sum(1 for a in achs if a.get("hidden"))

        self.filter_buttons[0].configure(text=f"Todos ({tot})")
        self.filter_buttons[1].configure(text=f"Desbloqueados 🟢 ({c_unlocked})")
        self.filter_buttons[2].configure(text=f"Bloqueados 🔒 ({c_locked})")
        self.filter_buttons[3].configure(text=f"Secretos ❓ ({c_secret})")

        self._render_achievements_list()

    def _select_filter(self, idx: int):
        self.active_filter_idx = idx % len(self.filter_options)
        self.active_filter = self.filter_options[self.active_filter_idx][0]
        for i, b in enumerate(self.filter_buttons):
            if i == self.active_filter_idx:
                b.configure(fg_color=COLOR_IOS_BLUE, text_color=COLOR_TEXT_WHITE)
            else:
                b.configure(fg_color=COLOR_BG_CARD_SECONDARY, text_color=COLOR_TEXT_MUTED_LIGHT)
        feedback_click()
        self._render_achievements_list()

    def _render_achievements_list(self):
        # Limpiar lista anterior
        for w in self.scroll_container.winfo_children():
            w.destroy()
        self._item_frames.clear()
        self._filtered_items.clear()
        self.selected_item_idx = 0

        achs = self.achievements_data.get("achievements", [])
        if not achs:
            plat = self.achievements_data.get("platform", "Local")
            empty_frame = ctk.CTkFrame(self.scroll_container, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=40)

            if plat == "RetroAchievements" and "error" in self.achievements_data:
                msg = "No se pudieron obtener logros de RetroAchievements.\nConfigura tu Usuario y Web API Key en '⚙ Cuentas (Y)'."
            elif plat == "Local":
                msg = (
                    "Este juego no está vinculado a Steam ni a RetroAchievements.\n\n"
                    "Puedes definir metas personales en 'Estadísticas (S)' para que aparezcan aquí como logros,\n"
                    "o vincularlo manualmente con un AppID de Steam o ID de RetroAchievements."
                )
            else:
                msg = "No se encontraron logros disponibles para este título."

            lbl_msg = ctk.CTkLabel(
                empty_frame,
                text=msg,
                font=font_body(13),
                text_color=COLOR_TEXT_MUTED,
                justify="center"
            )
            lbl_msg.pack(pady=(0, 16))

            btn_link = ctk.CTkButton(
                empty_frame,
                text="🔗 Vincular AppID / RetroAchievements (Start)",
                font=font_button(12),
                height=34,
                corner_radius=12,
                fg_color=COLOR_IOS_BLUE,
                hover_color=COLOR_IOS_BLUE_HOVER,
                command=self._open_link_dialog
            )
            btn_link.pack()
            return

        # Filtrar lista
        for a in achs:
            u = bool(a.get("unlocked"))
            h = bool(a.get("hidden"))
            if self.active_filter == "unlocked" and not u:
                continue
            if self.active_filter == "locked" and u:
                continue
            if self.active_filter == "secret" and not h:
                continue
            self._filtered_items.append(a)

        if not self._filtered_items:
            lbl_empty = ctk.CTkLabel(
                self.scroll_container,
                text="No hay logros que coincidan con este filtro.",
                font=font_body(13),
                text_color=COLOR_TEXT_DIM
            )
            lbl_empty.pack(pady=40)
            return

        for idx, item in enumerate(self._filtered_items):
            card = self._build_achievement_card(idx, item)
            card.pack(fill="x", pady=4)
            self._item_frames.append(card)

        self._highlight_selected_item()

    def _build_achievement_card(self, idx: int, item: Dict[str, Any]) -> ctk.CTkFrame:
        is_unlocked = bool(item.get("unlocked"))
        is_hidden = bool(item.get("hidden")) and not is_unlocked

        bg_col = COLOR_BG_CARD_SECONDARY if is_unlocked else COLOR_BG_DARK
        border_col = COLOR_STATUS_SUCCESS if is_unlocked else COLOR_GLASS_BORDER

        card = ctk.CTkFrame(
            self.scroll_container,
            fg_color=bg_col,
            border_color=border_col,
            border_width=1.2 if is_unlocked else 1.0,
            corner_radius=14
        )

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        # Icono / Badge
        icon_box = ctk.CTkFrame(inner, fg_color="transparent", width=44, height=44)
        icon_box.pack(side="left", padx=(0, 12))
        icon_box.pack_propagate(False)

        badge_txt = "🏆" if is_unlocked else ("❓" if is_hidden else "🔒")
        lbl_badge = ctk.CTkLabel(
            icon_box,
            text=badge_txt,
            font=font_title(20 if not is_unlocked else 22),
            text_color=COLOR_STATUS_SUCCESS if is_unlocked else COLOR_TEXT_DIM
        )
        lbl_badge.pack(expand=True)

        # Información central
        info_frame = ctk.CTkFrame(inner, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True)

        title_txt = "Logro Oculto" if is_hidden else item.get("title", "Logro")
        lbl_card_title = ctk.CTkLabel(
            info_frame,
            text=title_txt,
            font=font_title(13),
            text_color=COLOR_TEXT_MAIN if is_unlocked else COLOR_TEXT_MUTED_LIGHT,
            anchor="w"
        )
        lbl_card_title.pack(anchor="w")

        if is_hidden:
            desc_txt = "Continúa jugando para descubrir este logro secreto."
        else:
            desc_txt = item.get("description") or "Sin descripción disponible."

        lbl_desc = ctk.CTkLabel(
            info_frame,
            text=desc_txt,
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED if is_unlocked else COLOR_TEXT_DIM,
            anchor="w",
            wraplength=480,
            justify="left"
        )
        lbl_desc.pack(anchor="w", pady=(1, 0))

        # Metadata derecha (puntos, rareza, fecha)
        right_frame = ctk.CTkFrame(inner, fg_color="transparent")
        right_frame.pack(side="right", padx=(8, 0))

        pts = item.get("points", 0)
        if pts > 0:
            lbl_pts = ctk.CTkLabel(
                right_frame,
                text=f"+{pts} pts",
                font=font_title(11),
                text_color=COLOR_STATUS_WARNING if is_unlocked else COLOR_TEXT_DIM,
                anchor="e"
            )
            lbl_pts.pack(anchor="e")

        rarity = item.get("rarity_percent")
        if rarity is not None:
            lbl_rarity = ctk.CTkLabel(
                right_frame,
                text=f"💎 {rarity}%",
                font=font_body(10),
                text_color=COLOR_CYAN_ACCENT if rarity < 10 else COLOR_TEXT_DIM,
                anchor="e"
            )
            lbl_rarity.pack(anchor="e")

        unlock_time = item.get("unlock_time")
        if is_unlocked and unlock_time:
            lbl_time = ctk.CTkLabel(
                right_frame,
                text=f"✓ {unlock_time}",
                font=font_body(10),
                text_color=COLOR_STATUS_SUCCESS,
                anchor="e"
            )
            lbl_time.pack(anchor="e")
        elif not is_unlocked:
            lbl_status = ctk.CTkLabel(
                right_frame,
                text="Bloqueado",
                font=font_body(10),
                text_color=COLOR_TEXT_DIM,
                anchor="e"
            )
            lbl_status.pack(anchor="e")

        card.bind("<Button-1>", lambda e, i=idx: self._on_card_click(i))
        for w in (inner, icon_box, lbl_badge, info_frame, lbl_card_title, lbl_desc, right_frame):
            w.bind("<Button-1>", lambda e, i=idx: self._on_card_click(i))

        return card

    def _on_card_click(self, idx: int):
        self.selected_item_idx = idx
        self._highlight_selected_item()
        feedback_click()

    def _highlight_selected_item(self):
        for idx, card in enumerate(self._item_frames):
            is_sel = (idx == self.selected_item_idx)
            item = self._filtered_items[idx] if idx < len(self._filtered_items) else {}
            is_unlocked = bool(item.get("unlocked"))
            if is_sel:
                card.configure(
                    border_color=COLOR_CYAN_ACCENT,
                    border_width=2.0,
                    fg_color=COLOR_GLASS_HOVER
                )
                scroll_to_widget(card, self.scroll_container)
            else:
                card.configure(
                    border_color=COLOR_STATUS_SUCCESS if is_unlocked else COLOR_GLASS_BORDER,
                    border_width=1.2 if is_unlocked else 1.0,
                    fg_color=COLOR_BG_CARD_SECONDARY if is_unlocked else COLOR_BG_DARK
                )

    # ---------------- Acciones Online y Diálogos ----------------
    def _refresh_online(self):
        feedback_click()
        trigger_haptic()
        self._load_data(force_refresh=True)

    def _open_settings(self):
        feedback_click()
        AchievementsSettingsDialog(
            self,
            on_saved=lambda: self._load_data(force_refresh=True)
        )

    def _open_link_dialog(self):
        feedback_click()
        LinkGameIdDialog(
            self,
            game=self.game,
            on_linked=lambda: self._load_data(force_refresh=True)
        )

    # ---------------- Soporte para Mando de Consola ----------------
    def handle_gamepad_input(self, action: str) -> bool:
        if action in ("up", "dpad_up"):
            if self._item_frames and self.selected_item_idx > 0:
                self.selected_item_idx -= 1
                self._highlight_selected_item()
                feedback_click()
            return True

        if action in ("down", "dpad_down"):
            if self._item_frames and self.selected_item_idx < len(self._item_frames) - 1:
                self.selected_item_idx += 1
                self._highlight_selected_item()
                feedback_click()
            return True

        if action in ("lb", "prev_tab"):
            new_idx = (self.active_filter_idx - 1) % len(self.filter_options)
            self._select_filter(new_idx)
            return True

        if action in ("rb", "next_tab"):
            new_idx = (self.active_filter_idx + 1) % len(self.filter_options)
            self._select_filter(new_idx)
            return True

        if action in ("x_button", "refresh"):
            self._refresh_online()
            return True

        if action in ("y_button", "settings"):
            self._open_settings()
            return True

        if action in ("start", "menu"):
            self._open_link_dialog()
            return True

        if action in ("a_button", "select"):
            # Si es meta local, permitir alternarla
            plat = self.achievements_data.get("platform")
            if plat == "Local" and 0 <= self.selected_item_idx < len(self._filtered_items):
                item = self._filtered_items[self.selected_item_idx]
                from core.stats_service import toggle_game_goal
                toggle_game_goal(self.game, item.get("id", ""))
                if self.on_game_updated:
                    self.on_game_updated(self.game)
                self._load_data(force_refresh=True)
            feedback_click()
            return True

        if action in ("b_button", "back", "cancel"):
            self.close()
            return True

        return False


# ==============================================================================
# DIÁLOGO DE CONFIGURACIÓN DE APIS (STEAM & RETROACHIEVEMENTS)
# ==============================================================================

class AchievementsSettingsDialog(BaseGlassDialog):
    """
    Diálogo para configurar API Keys de Steam y credenciales de RetroAchievements.
    """

    def __init__(self, parent, on_saved: Optional[Callable[[], None]] = None):
        super().__init__(
            parent,
            title="Ajustes de Logros y APIs",
            width=620,
            height=540,
            corner_radius=20
        )
        self.on_saved = on_saved
        self.config = load_achievements_config()
        self._build_ui()

    _center_window = BaseGlassDialog.center_window

    def _build_ui(self):
        card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=20
        )
        card.pack(fill="both", expand=True, padx=4, pady=4)

        # Cabecera
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 8))

        lbl_t = ctk.CTkLabel(
            head,
            text="⚙ Configuración de Steam y RetroAchievements",
            font=font_title(15),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_t.pack(side="left")

        # Contenedor scrolleable
        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=4)

        # --- SECCIÓN STEAM ---
        lbl_steam = ctk.CTkLabel(
            scroll,
            text="🎮 STEAM (PC)",
            font=font_title(13),
            text_color=COLOR_CYAN_ACCENT,
            anchor="w"
        )
        lbl_steam.pack(fill="x", pady=(4, 2))

        # Botón Autodetección SteamID
        btn_autodetect = ctk.CTkButton(
            scroll,
            text="🔍 Autodetectar SteamID desde Windows",
            height=30,
            corner_radius=9,
            font=font_button(11),
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            command=self._autodetect_steam
        )
        btn_autodetect.pack(fill="x", pady=(2, 8))

        # SteamID64
        lbl_id = ctk.CTkLabel(scroll, text="SteamID64 (ej: 76561198...):", font=font_body(11), text_color=COLOR_TEXT_MUTED, anchor="w")
        lbl_id.pack(fill="x")
        self.ent_steamid = ctk.CTkEntry(scroll, height=32, corner_radius=8, font=font_body(12))
        self.ent_steamid.insert(0, self.config.get("steam_id64", ""))
        self.ent_steamid.pack(fill="x", pady=(2, 8))

        # Steam API Key
        lbl_key = ctk.CTkLabel(scroll, text="Steam Web API Key (opcional para perfiles privados):", font=font_body(11), text_color=COLOR_TEXT_MUTED, anchor="w")
        lbl_key.pack(fill="x")
        self.ent_steamkey = ctk.CTkEntry(scroll, height=32, corner_radius=8, font=font_body(12), show="*")
        self.ent_steamkey.insert(0, self.config.get("steam_api_key", ""))
        self.ent_steamkey.pack(fill="x", pady=(2, 12))

        # --- SECCIÓN RETROACHIEVEMENTS ---
        lbl_ra = ctk.CTkLabel(
            scroll,
            text="🏆 RETROACHIEVEMENTS (Emuladores / Retro)",
            font=font_title(13),
            text_color=COLOR_STATUS_WARNING,
            anchor="w"
        )
        lbl_ra.pack(fill="x", pady=(8, 2))

        # Usuario RA
        lbl_ra_u = ctk.CTkLabel(scroll, text="Nombre de Usuario de RetroAchievements:", font=font_body(11), text_color=COLOR_TEXT_MUTED, anchor="w")
        lbl_ra_u.pack(fill="x")
        self.ent_ra_user = ctk.CTkEntry(scroll, height=32, corner_radius=8, font=font_body(12))
        self.ent_ra_user.insert(0, self.config.get("retroachievements_username", ""))
        self.ent_ra_user.pack(fill="x", pady=(2, 8))

        # Web API Key RA
        lbl_ra_k = ctk.CTkLabel(
            scroll,
            text="Web API Key (obtenla en retroachievements.org/controlpanel.php):",
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        lbl_ra_k.pack(fill="x")
        self.ent_ra_key = ctk.CTkEntry(scroll, height=32, corner_radius=8, font=font_body(12), show="*")
        self.ent_ra_key.insert(0, self.config.get("retroachievements_api_key", ""))
        self.ent_ra_key.pack(fill="x", pady=(2, 12))

        # Botón Teclado en Pantalla
        btn_osk = ctk.CTkButton(
            scroll,
            text="⌨ Abrir Teclado Virtual (OSK)",
            height=28,
            corner_radius=8,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            command=self._prompt_keyboard
        )
        btn_osk.pack(fill="x", pady=(2, 8))

        # Barra inferior de botones
        bottom_bar = ctk.CTkFrame(card, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=16, pady=(8, 12))

        btn_cancel = ctk.CTkButton(
            bottom_bar,
            text="✕ Cancelar (B)",
            width=110,
            height=34,
            corner_radius=10,
            font=font_button(12),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            command=self.close
        )
        btn_cancel.pack(side="left")

        btn_save = ctk.CTkButton(
            bottom_bar,
            text="💾 Guardar Cambios (A)",
            width=160,
            height=34,
            corner_radius=10,
            font=font_button(12),
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            command=self._save
        )
        btn_save.pack(side="right")

    def _autodetect_steam(self):
        prof = detect_local_steam_profile()
        sid = prof.get("steam_id64", "")
        pers = prof.get("persona_name", "")
        if sid:
            self.ent_steamid.delete(0, "end")
            self.ent_steamid.insert(0, sid)
            msg = f"Detectado: {pers} ({sid})" if pers else f"Detectado: {sid}"
            from ui.dialogs.glass_message_box import show_info
            show_info("Steam Autodetectado", f"Se localizó la cuenta:\n{msg}", parent=self)
        else:
            from ui.dialogs.glass_message_box import show_warning
            show_warning("Steam", "No se encontró ninguna sesión reciente de Steam en este equipo.", parent=self)

    def _prompt_keyboard(self):
        val = prompt_on_screen_keyboard(self, "Entrada de Texto", self.ent_steamkey.get())
        if val is not None:
            self.ent_steamkey.delete(0, "end")
            self.ent_steamkey.insert(0, val)

    def _save(self):
        self.config["steam_id64"] = self.ent_steamid.get().strip()
        self.config["steam_api_key"] = self.ent_steamkey.get().strip()
        self.config["retroachievements_username"] = self.ent_ra_user.get().strip()
        self.config["retroachievements_api_key"] = self.ent_ra_key.get().strip()

        save_achievements_config(self.config)
        feedback_click()
        trigger_haptic()
        if self.on_saved:
            self.on_saved()
        self.close()

    def handle_gamepad_input(self, action: str) -> bool:
        if action in ("a_button", "select"):
            self._save()
            return True
        if action in ("b_button", "back", "cancel"):
            self.close()
            return True
        if action in ("x_button", "osk"):
            self._prompt_keyboard()
            return True
        return False


# ==============================================================================
# DIÁLOGO DE VINCULACIÓN DE APPID / RETROACHIEVEMENTS ID
# ==============================================================================

class LinkGameIdDialog(BaseGlassDialog):
    """
    Diálogo para asociar manualmente un Steam AppID o RetroAchievements ID a un juego.
    """

    def __init__(self, parent, game: Dict[str, Any], on_linked: Optional[Callable[[], None]] = None):
        super().__init__(
            parent,
            title="Vincular IDs de Logros",
            width=540,
            height=380,
            corner_radius=20
        )
        self.game = game
        self.on_linked = on_linked
        self._build_ui()

    _center_window = BaseGlassDialog.center_window

    def _build_ui(self):
        card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=20
        )
        card.pack(fill="both", expand=True, padx=4, pady=4)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 8))

        lbl_t = ctk.CTkLabel(
            head,
            text=f"🔗 Vincular IDs para '{self.game.get('name', 'Juego')}'",
            font=font_title(14),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_t.pack(anchor="w")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=4)

        # Steam AppID
        lbl_steam = ctk.CTkLabel(body, text="Steam AppID (ej: 105600 para Terraria):", font=font_body(11), text_color=COLOR_TEXT_MUTED, anchor="w")
        lbl_steam.pack(fill="x", pady=(4, 2))

        cur_appid = detect_game_steam_appid(self.game) or ""
        self.ent_steam = ctk.CTkEntry(body, height=32, corner_radius=8, font=font_body(12))
        self.ent_steam.insert(0, cur_appid)
        self.ent_steam.pack(fill="x", pady=(0, 10))

        # RetroAchievements GameID
        lbl_ra = ctk.CTkLabel(body, text="RetroAchievements Game ID (ej: 1440 para Super Mario World):", font=font_body(11), text_color=COLOR_TEXT_MUTED, anchor="w")
        lbl_ra.pack(fill="x", pady=(4, 2))

        cur_ra = detect_game_retroachievements_id(self.game) or ""
        self.ent_ra = ctk.CTkEntry(body, height=32, corner_radius=8, font=font_body(12))
        self.ent_ra.insert(0, cur_ra)
        self.ent_ra.pack(fill="x", pady=(0, 12))

        # Botones
        btn_bar = ctk.CTkFrame(card, fg_color="transparent")
        btn_bar.pack(fill="x", padx=16, pady=(8, 14))

        btn_cancel = ctk.CTkButton(
            btn_bar,
            text="✕ Cancelar (B)",
            width=100,
            height=32,
            corner_radius=9,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            command=self.close
        )
        btn_cancel.pack(side="left")

        btn_save = ctk.CTkButton(
            btn_bar,
            text="✓ Guardar Asociación (A)",
            width=160,
            height=32,
            corner_radius=9,
            font=font_button(11),
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            command=self._save
        )
        btn_save.pack(side="right")

    def _save(self):
        s_val = self.ent_steam.get().strip()
        ra_val = self.ent_ra.get().strip()

        if s_val.isdigit():
            self.game["steam_appid"] = s_val
            self.game["platform"] = "Steam"
            self.game["platform_id"] = s_val
        elif not s_val:
            self.game.pop("steam_appid", None)

        set_game_retroachievements_id(self.game, ra_val)

        from core.config import save_games_data
        save_games_data()

        feedback_click()
        trigger_haptic()
        if self.on_linked:
            self.on_linked()
        self.close()

    def handle_gamepad_input(self, action: str) -> bool:
        if action in ("a_button", "select"):
            self._save()
            return True
        if action in ("b_button", "back", "cancel"):
            self.close()
            return True
        return False
