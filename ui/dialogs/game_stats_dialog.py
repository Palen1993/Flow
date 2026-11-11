"""
GameFlow - Diálogo de Estadísticas de Juego Avanzadas y Metas Locales
=====================================================================
Diálogo modal Glassmorphism 100% navegable con mando que muestra:
1. Pestaña de Resumen y Gráfica de Actividad (Semanal 7 días / Mensual 30 días estilo Steam/Switch).
2. Pestaña de Metas y Logros Personales (Checklist interactivo para RPGs / Aventuras).
3. Pestaña de Notas y Guía Personal del Juego (Códigos, builds, recordatorios).
"""

import os
import tkinter as tk
from typing import Dict, Any, Optional, Callable, List
import customtkinter as ctk
from PIL import Image

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.dialogs.on_screen_keyboard import prompt_on_screen_keyboard
from core.stats_service import (
    get_game_stats, add_goal_to_game, toggle_game_goal,
    delete_game_goal, set_game_notes
)
from core.config import save_games_data
from core.feedback import feedback_click, trigger_haptic
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
    font_button, font_body, font_title
)


class GameStatsDialog(BaseGlassDialog):
    """
    Diálogo Glassmorphism para estadísticas avanzadas, gráficas de tiempo jugado
    y gestión de metas y notas para el juego seleccionado.
    """

    def __init__(
        self,
        parent,
        game: Dict[str, Any],
        on_game_updated: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        super().__init__(
            parent,
            title=f"Estadísticas - {game.get('name', 'Juego')}",
            width=840,
            height=600,
            corner_radius=22
        )
        self.game = game
        self.on_game_updated = on_game_updated
        self.stats = get_game_stats(self.game)

        # Estado de navegación
        self.current_tab: int = 0  # 0: Actividad/Gráfica, 1: Metas, 2: Notas
        self.chart_mode: str = "weekly"  # "weekly" (7 días) o "monthly" (30 días)
        self.selected_goal_idx: int = 0
        self._goal_widgets: List[ctk.CTkFrame] = []

        self._build_ui()
        self._switch_tab(0)

    _center_window = BaseGlassDialog.center_window

    def _build_ui(self):
        # Tarjeta principal con efecto iOS Liquid Glass
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

        # Miniatura o icono
        self._thumb_img = None
        cover_path = self.game.get("cover")
        if cover_path and os.path.isfile(cover_path):
            try:
                pil_img = Image.open(cover_path).resize((40, 40), Image.Resampling.LANCZOS)
                self._thumb_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(40, 40))
                lbl_icon = ctk.CTkLabel(self.header_bar, image=self._thumb_img, text="")
                lbl_icon.pack(side="left", padx=(0, 10))
            except Exception:
                lbl_icon = ctk.CTkLabel(self.header_bar, text="🎮", font=font_title(20))
                lbl_icon.pack(side="left", padx=(0, 10))
        else:
            lbl_icon = ctk.CTkLabel(self.header_bar, text="🎮", font=font_title(20))
            lbl_icon.pack(side="left", padx=(0, 10))

        # Título y badges
        info_col = ctk.CTkFrame(self.header_bar, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True)

        g_name = self.game.get("name", "Juego")
        lbl_title = ctk.CTkLabel(
            info_col,
            text=g_name,
            font=font_title(18),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        lbl_title.pack(anchor="w")

        meta_parts = []
        if self.game.get("platform"):
            meta_parts.append(f"Plataforma: {self.game.get('platform')}")
        if self.game.get("genre"):
            meta_parts.append(f"Género: {self.game.get('genre')}")
        meta_parts.append(f"Estado: {self.game.get('status', 'Por jugar')}")
        lbl_meta = ctk.CTkLabel(
            info_col,
            text="  •  ".join(meta_parts),
            font=font_body(11),
            text_color=COLOR_TEXT_DIM,
            anchor="w"
        )
        lbl_meta.pack(anchor="w")

        # Botón cerrar
        btn_close = ctk.CTkButton(
            self.header_bar,
            text="✕  Cerrar (B)",
            width=90,
            height=28,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=10,
            command=self.close
        )
        btn_close.pack(side="right")

        # Permitir arrastrar ventana desde la cabecera
        for w in (self.header_bar, lbl_title, info_col, lbl_meta):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # ---------------- Barra de Pestañas (Segmented / Tabs) ----------------
        self.tab_bar = ctk.CTkFrame(self.main_card, fg_color=COLOR_BG_CARD_SECONDARY, height=36, corner_radius=12)
        self.tab_bar.pack(fill="x", padx=20, pady=(4, 10))

        self.tab_buttons: List[ctk.CTkButton] = []
        tabs_def = [
            ("📊 Resumen y Actividad", 0),
            (f"🎯 Metas y Logros ({self.stats['goals_completed_count']}/{self.stats['goals_total_count']})", 1),
            ("📝 Notas del Juego", 2)
        ]

        for text, idx in tabs_def:
            b = ctk.CTkButton(
                self.tab_bar,
                text=text,
                font=font_button(12),
                height=30,
                corner_radius=10,
                fg_color="transparent",
                text_color=COLOR_TEXT_MUTED_LIGHT,
                command=lambda i=idx: self._switch_tab(i)
            )
            b.pack(side="left", padx=4, pady=3, expand=True, fill="x")
            self.tab_buttons.append(b)

        # ---------------- Contenedor de Vistas ----------------
        self.content_frame = ctk.CTkFrame(self.main_card, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # Frames para cada pestaña
        self.frame_tab0 = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.frame_tab1 = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.frame_tab2 = ctk.CTkFrame(self.content_frame, fg_color="transparent")

        self._build_tab0_activity()
        self._build_tab1_goals()
        self._build_tab2_notes()

        # ---------------- Barra Inferior de Atajos ----------------
        self.footer_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=28)
        self.footer_bar.pack(fill="x", padx=20, pady=(0, 8))

        self.lbl_shortcuts = ctk.CTkLabel(
            self.footer_bar,
            text="Cruceta: Navegar  │  (LB / RB): Pestañas  │  (Y): Logros y Trofeos  │  (A): Seleccionar  │  (B): Cerrar",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_shortcuts.pack(side="left")

    # =========================================================================
    # PESTAÑA 0: RESUMEN Y GRÁFICA DE ACTIVIDAD
    # =========================================================================
    def _build_tab0_activity(self):
        # Fila de tarjetas métricas KPI
        kpi_row = ctk.CTkFrame(self.frame_tab0, fg_color="transparent", height=70)
        kpi_row.pack(fill="x", pady=(0, 10))
        kpi_row.grid_columnconfigure((0, 1, 2, 3), weight=1)

        kpis = [
            ("⏱️ Tiempo Total", self.stats["total_playtime_formatted"], COLOR_CYAN_ACCENT),
            ("🎮 Partidas", f"{self.stats['play_count']} sesiones", COLOR_TEXT_WHITE),
            ("📅 Última Sesión", self.stats["last_played_formatted"], COLOR_TEXT_WHITE),
            ("⏳ Promedio / Sesión", self.stats["avg_session_formatted"], COLOR_TEXT_WHITE)
        ]

        for i, (title_kpi, val_kpi, val_color) in enumerate(kpis):
            card = ctk.CTkFrame(
                kpi_row,
                fg_color=COLOR_BG_CARD_SECONDARY,
                border_color=COLOR_BORDER_CARD,
                border_width=1,
                corner_radius=12
            )
            card.grid(row=0, column=i, padx=4, sticky="nsew")

            lbl_t = ctk.CTkLabel(card, text=title_kpi, font=font_body(10), text_color=COLOR_TEXT_DIM)
            lbl_t.pack(anchor="w", padx=10, pady=(6, 0))

            lbl_v = ctk.CTkLabel(card, text=val_kpi, font=font_button(13), text_color=val_color)
            lbl_v.pack(anchor="w", padx=10, pady=(0, 6))

        # Subcabecera de gráfica con selector de rango (Semanal vs Mensual)
        chart_header = ctk.CTkFrame(self.frame_tab0, fg_color="transparent", height=32)
        chart_header.pack(fill="x", pady=(4, 6))

        lbl_chart_title = ctk.CTkLabel(
            chart_header,
            text="📈  Historial de Juego Reciente",
            font=font_button(13),
            text_color=COLOR_TEXT_MAIN
        )
        lbl_chart_title.pack(side="left")

        # Botones para alternar modo semanal / mensual
        selector_box = ctk.CTkFrame(chart_header, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=10)
        selector_box.pack(side="right")

        self.btn_weekly = ctk.CTkButton(
            selector_box,
            text="Últimos 7 Días",
            width=110,
            height=24,
            font=font_button(11),
            corner_radius=8,
            fg_color=COLOR_CYAN_BORDER,
            text_color=COLOR_CYAN_ACCENT,
            command=lambda: self._set_chart_mode("weekly")
        )
        self.btn_weekly.pack(side="left", padx=2, pady=2)

        self.btn_monthly = ctk.CTkButton(
            selector_box,
            text="Últimos 30 Días",
            width=110,
            height=24,
            font=font_button(11),
            corner_radius=8,
            fg_color="transparent",
            text_color=COLOR_TEXT_MUTED,
            command=lambda: self._set_chart_mode("monthly")
        )
        self.btn_monthly.pack(side="left", padx=2, pady=2)

        # Contenedor del Canvas
        self.canvas_card = ctk.CTkFrame(
            self.frame_tab0,
            fg_color=COLOR_BG_DARK,
            border_color=COLOR_BORDER_CARD,
            border_width=1,
            corner_radius=14
        )
        self.canvas_card.pack(fill="both", expand=True, pady=(0, 6))

        # Canvas puro de Tkinter para máxima fluidez y escalado
        self.chart_canvas = tk.Canvas(
            self.canvas_card,
            bg=COLOR_BG_DARK,
            highlightthickness=0,
            bd=0
        )
        self.chart_canvas.pack(fill="both", expand=True, padx=12, pady=10)
        self.chart_canvas.bind("<Configure>", lambda e: self._draw_chart())

        # Pie de resumen del período y botón de copias de seguridad
        tab0_footer = ctk.CTkFrame(self.frame_tab0, fg_color="transparent")
        tab0_footer.pack(fill="x", pady=(0, 2))

        self.lbl_period_summary = ctk.CTkLabel(
            tab0_footer,
            text="",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_period_summary.pack(side="left")

        btn_open_backup = ctk.CTkButton(
            tab0_footer,
            text="💾  Copias de Seguridad...",
            width=165,
            height=26,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=8,
            command=self._open_save_backup_dialog
        )
        btn_open_backup.pack(side="right")

        btn_open_achievements = ctk.CTkButton(
            tab0_footer,
            text="🏆  Logros y Trofeos (Y)...",
            width=165,
            height=26,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            corner_radius=8,
            command=self._open_achievements_dialog
        )
        btn_open_achievements.pack(side="right", padx=(0, 8))

    def _open_save_backup_dialog(self):
        from ui.dialogs.save_backup_dialog import SaveBackupDialog
        SaveBackupDialog(self, self.game, on_game_updated=self.on_game_updated)

    def _open_achievements_dialog(self):
        from ui.dialogs.achievements_dialog import AchievementsDialog
        AchievementsDialog(self, self.game, on_game_updated=self.on_game_updated)

    def _set_chart_mode(self, mode: str):
        if self.chart_mode == mode:
            return
        self.chart_mode = mode
        if mode == "weekly":
            self.btn_weekly.configure(fg_color=COLOR_CYAN_BORDER, text_color=COLOR_CYAN_ACCENT)
            self.btn_monthly.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED)
        else:
            self.btn_weekly.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED)
            self.btn_monthly.configure(fg_color=COLOR_CYAN_BORDER, text_color=COLOR_CYAN_ACCENT)
        self._draw_chart()

    def _draw_chart(self):
        """Renderiza la gráfica de barras estilizada en el Canvas con feedback visual."""
        if not hasattr(self, "chart_canvas") or not self.chart_canvas.winfo_exists():
            return

        canvas = self.chart_canvas
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w < 100 or h < 80:
            return

        is_weekly = (self.chart_mode == "weekly")
        data = self.stats["weekly_activity"] if is_weekly else self.stats["monthly_activity"]
        n_bars = len(data)
        if n_bars == 0:
            return

        total_period = self.stats["weekly_total_formatted"] if is_weekly else self.stats["monthly_total_formatted"]
        summary_text = (
            f"Total jugado en este período: {total_period}  │  "
            f"Día más activo: {self.stats['most_active_day']['day_label']} ({self.stats['most_active_day']['minutes']} min)  │  "
            f"Añadido el: {self.stats['date_added_formatted']}"
        )
        self.lbl_period_summary.configure(text=summary_text)

        # Determinar escala vertical (mínimo 60 min para mostrar rejilla decente)
        max_mins = max(60, max(d["minutes"] for d in data))

        y_bottom = h - 28
        y_top = 26
        usable_h = y_bottom - y_top

        # Líneas guía de rejilla (25%, 50%, 75%, 100%)
        for pct in (0.33, 0.66, 1.0):
            gy = y_bottom - (usable_h * pct)
            canvas.create_line(4, gy, w - 4, gy, fill="#1c2130", dash=(3, 3), width=1)
            ref_mins = int(round(max_mins * pct))
            ref_text = f"{ref_mins // 60}h" if ref_mins >= 60 and ref_mins % 60 == 0 else f"{ref_mins}m"
            canvas.create_text(w - 6, gy - 6, text=ref_text, anchor="e", fill="#4a5568", font=("Segoe UI", 8))

        # Línea base del suelo
        canvas.create_line(4, y_bottom, w - 4, y_bottom, fill="#2b3145", width=1.5)

        # Dibujar barras
        slot_w = w / n_bars
        bar_w = min(42, max(8, int(slot_w * 0.65)))

        for i, item in enumerate(data):
            cx = int((i + 0.5) * slot_w)
            mins = item["minutes"]
            is_today = item.get("is_today", False)

            if mins > 0:
                bar_h = max(6, int((mins / max_mins) * usable_h))
                bx1 = cx - bar_w // 2
                bx2 = cx + bar_w // 2
                by1 = y_bottom - bar_h
                by2 = y_bottom

                fill_col = "#00d2ff" if not is_today else "#38bdf8"
                # Barra con borde redondeado superior
                canvas.create_rectangle(bx1, by1, bx2, by2, fill=fill_col, outline="", width=0)
                # Resplandor suave encima
                canvas.create_line(bx1 + 1, by1, bx2 - 1, by1, fill="#e0f2fe", width=1.5)

                # Etiqueta de valor encima de la barra
                if is_weekly or (mins >= max_mins * 0.4):
                    canvas.create_text(
                        cx, by1 - 8,
                        text=item["hours_str"],
                        fill="#00d2ff" if not is_today else "#7dd3fc",
                        font=("Segoe UI", 8, "bold")
                    )
            else:
                # Marcador tenue en el suelo para días sin juego
                canvas.create_rectangle(
                    cx - bar_w // 3, y_bottom - 2, cx + bar_w // 3, y_bottom,
                    fill="#1f2537", outline=""
                )

            # Etiqueta del día en el eje X
            if is_weekly or (i % 5 == 0 or i == n_bars - 1):
                lbl_color = "#38bdf8" if is_today else "#94a3b8"
                lbl_font = ("Segoe UI", 9, "bold" if is_today else "normal")
                canvas.create_text(cx, y_bottom + 12, text=item["day_label"], fill=lbl_color, font=lbl_font)

    # =========================================================================
    # PESTAÑA 1: METAS Y LOGROS PERSONALES (CHECKLIST)
    # =========================================================================
    def _build_tab1_goals(self):
        # Cabecera de progreso
        prog_card = ctk.CTkFrame(self.frame_tab1, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=12)
        prog_card.pack(fill="x", pady=(0, 8))

        self.lbl_goals_progress = ctk.CTkLabel(
            prog_card,
            text="",
            font=font_button(12),
            text_color=COLOR_TEXT_MAIN
        )
        self.lbl_goals_progress.pack(anchor="w", padx=14, pady=(8, 2))

        self.progress_bar = ctk.CTkProgressBar(
            prog_card,
            progress_color=COLOR_CYAN_ACCENT,
            fg_color=COLOR_BG_DARK,
            height=8,
            corner_radius=4
        )
        self.progress_bar.pack(fill="x", padx=14, pady=(0, 8))

        # Contenedor desplazable de metas
        self.goals_scroll = ctk.CTkScrollableFrame(
            self.frame_tab1,
            fg_color="transparent",
            corner_radius=12
        )
        self.goals_scroll.pack(fill="both", expand=True, pady=(0, 8))

        # Barra de botones de acción
        actions_bar = ctk.CTkFrame(self.frame_tab1, fg_color="transparent", height=32)
        actions_bar.pack(fill="x", pady=(2, 0))

        btn_add = ctk.CTkButton(
            actions_bar,
            text="➕  Añadir Nueva Meta (X)",
            font=font_button(12),
            height=32,
            corner_radius=10,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER,
            border_width=1,
            command=self._prompt_add_goal
        )
        btn_add.pack(side="left", padx=(0, 10))

        lbl_hints = ctk.CTkLabel(
            actions_bar,
            text="(A): Marcar / Desmarcar  │  (Y): Eliminar Meta Seleccionada",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        lbl_hints.pack(side="left")

        self._render_goals_list()

    def _render_goals_list(self):
        # Limpiar widgets previos
        for w in self.goals_scroll.winfo_children():
            w.destroy()
        self._goal_widgets.clear()

        goals = self.stats["goals"]
        total = len(goals)
        completed = sum(1 for g in goals if g.get("completed"))
        pct = (completed / total) if total > 0 else 0.0

        self.progress_bar.set(pct)
        self.lbl_goals_progress.configure(
            text=f"🎯  Progreso de Metas: {completed} de {total} completadas ({int(round(pct * 100))}%)"
        )
        self.tab_buttons[1].configure(text=f"🎯 Metas y Logros ({completed}/{total})")

        if total == 0:
            empty_frame = ctk.CTkFrame(self.goals_scroll, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, pady=40)

            lbl_empty_icon = ctk.CTkLabel(empty_frame, text="🎯", font=font_title(32))
            lbl_empty_icon.pack()

            lbl_empty = ctk.CTkLabel(
                empty_frame,
                text="No hay metas ni tareas creadas para este juego aún.\nPulsa 'Añadir Nueva Meta (X)' para empezar a registrar objetivos.",
                font=font_body(12),
                text_color=COLOR_TEXT_MUTED,
                justify="center"
            )
            lbl_empty.pack(pady=8)
            return

        for idx, g in enumerate(goals):
            g_id = g["id"]
            is_comp = g["completed"]
            text = g["text"]

            card = ctk.CTkFrame(
                self.goals_scroll,
                fg_color=COLOR_BG_CARD_SECONDARY,
                border_color=COLOR_CYAN_ACCENT if idx == self.selected_goal_idx else COLOR_BORDER_CARD,
                border_width=1.5 if idx == self.selected_goal_idx else 1,
                corner_radius=10,
                height=42
            )
            card.pack(fill="x", pady=3, padx=2)

            # Checkbox visual estilizado
            box_text = "✓" if is_comp else ""
            lbl_box = ctk.CTkLabel(
                card,
                text=box_text,
                font=font_button(12),
                width=24,
                height=24,
                corner_radius=6,
                fg_color="#059669" if is_comp else COLOR_BG_DARK,
                text_color=COLOR_TEXT_WHITE
            )
            lbl_box.pack(side="left", padx=10, pady=8)

            # Texto de la meta
            t_color = COLOR_TEXT_MUTED if is_comp else COLOR_TEXT_MAIN
            t_display = f"~~{text}~~" if is_comp else text
            # Tkinter standard label para tachado o texto limpio
            lbl_text = ctk.CTkLabel(
                card,
                text=text,
                font=font_body(12),
                text_color=t_color,
                anchor="w"
            )
            lbl_text.pack(side="left", fill="x", expand=True, padx=4)

            # Badge de completada
            if is_comp:
                lbl_tag = ctk.CTkLabel(
                    card,
                    text="COMPLETADA",
                    font=font_body(9),
                    text_color="#10b981",
                    fg_color="#064e3b",
                    corner_radius=6,
                    width=75,
                    height=20
                )
                lbl_tag.pack(side="right", padx=10)

            # Hacer interactivo por clic de ratón
            for w in (card, lbl_box, lbl_text):
                w.bind("<Button-1>", lambda e, gid=g_id, i=idx: self._on_goal_clicked(gid, i))

            self._goal_widgets.append(card)

    def _on_goal_clicked(self, goal_id: str, idx: int):
        self.selected_goal_idx = idx
        self._toggle_goal(goal_id)

    def _toggle_goal(self, goal_id: str):
        ok = toggle_game_goal(self.game, goal_id)
        if ok:
            try:
                feedback_click()
                trigger_haptic(0.2, 0.2, 60)
            except Exception:
                pass
            self._save_game_changes()
            self.stats = get_game_stats(self.game)
            self._render_goals_list()

    def _prompt_add_goal(self):
        """Abre el teclado virtual OSD para añadir una meta cómodamente desde el mando."""
        family = getattr(self.parent, "_current_controller_family", "xbox")

        def _on_confirm(text: str):
            text = (text or "").strip()
            if not text:
                return
            new_g = add_goal_to_game(self.game, text)
            if new_g:
                self._save_game_changes()
                self.stats = get_game_stats(self.game)
                self.selected_goal_idx = max(0, len(self.stats["goals"]) - 1)
                self._render_goals_list()

        prompt_on_screen_keyboard(
            parent=self,
            title="Añadir Nueva Meta",
            initial_text="",
            on_confirm=_on_confirm,
            family=family
        )

    def _delete_selected_goal(self):
        goals = self.stats["goals"]
        if not goals or self.selected_goal_idx < 0 or self.selected_goal_idx >= len(goals):
            return
        g_id = goals[self.selected_goal_idx]["id"]
        ok = delete_game_goal(self.game, g_id)
        if ok:
            try:
                feedback_click()
            except Exception:
                pass
            self._save_game_changes()
            self.stats = get_game_stats(self.game)
            if self.selected_goal_idx >= len(self.stats["goals"]):
                self.selected_goal_idx = max(0, len(self.stats["goals"]) - 1)
            self._render_goals_list()

    # =========================================================================
    # PESTAÑA 2: NOTAS Y GUÍA PERSONAL DEL JUEGO
    # =========================================================================
    def _build_tab2_notes(self):
        lbl_info = ctk.CTkLabel(
            self.frame_tab2,
            text="Apunta contraseñas, recetas de crafteo, recordatorios de misiones o builds de personajes:",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        lbl_info.pack(anchor="w", pady=(0, 6))

        # Cuadro de texto amplio
        self.txt_notes = ctk.CTkTextbox(
            self.frame_tab2,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1,
            corner_radius=12,
            font=font_body(12),
            text_color=COLOR_TEXT_MAIN,
            wrap="word"
        )
        self.txt_notes.pack(fill="both", expand=True, pady=(0, 8))
        curr_notes = self.game.get("notes", "")
        if curr_notes:
            self.txt_notes.insert("1.0", curr_notes)

        # Acciones de notas
        notes_actions = ctk.CTkFrame(self.frame_tab2, fg_color="transparent", height=32)
        notes_actions.pack(fill="x")

        btn_save = ctk.CTkButton(
            notes_actions,
            text="💾  Guardar Notas (A)",
            font=font_button(12),
            height=32,
            corner_radius=10,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER,
            border_width=1,
            command=self._save_notes
        )
        btn_save.pack(side="left", padx=(0, 10))

        btn_edit_osk = ctk.CTkButton(
            notes_actions,
            text="⌨️  Editar con Teclado en Pantalla (X)",
            font=font_button(12),
            height=32,
            corner_radius=10,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            command=self._prompt_edit_notes_osk
        )
        btn_edit_osk.pack(side="left")

    def _save_notes(self):
        notes_text = self.txt_notes.get("1.0", "end-1c").strip()
        set_game_notes(self.game, notes_text)
        self._save_game_changes()
        self.stats = get_game_stats(self.game)
        try:
            feedback_click()
        except Exception:
            pass

    def _prompt_edit_notes_osk(self):
        family = getattr(self.parent, "_current_controller_family", "xbox")
        current_text = self.txt_notes.get("1.0", "end-1c").strip()

        def _on_confirm(text: str):
            self.txt_notes.delete("1.0", "end")
            self.txt_notes.insert("1.0", text)
            self._save_notes()

        prompt_on_screen_keyboard(
            parent=self,
            title="Editar Notas del Juego",
            initial_text=current_text,
            on_confirm=_on_confirm,
            family=family
        )

    # =========================================================================
    # PERSISTENCIA Y SINCRONIZACIÓN
    # =========================================================================
    def _save_game_changes(self):
        """Persiste atómicamente los cambios en games.json e informa al lanzador."""
        parent = self.parent
        if parent and hasattr(parent, "games") and hasattr(parent, "save_games"):
            try:
                parent.save_games()
            except Exception:
                pass
        elif parent and hasattr(parent, "library_service"):
            try:
                parent.library_service.save()
            except Exception:
                pass
        else:
            # Respaldo atómico directo
            try:
                from core.config import load_games_data
                all_games = load_games_data()
                target_p = self.game.get("path")
                target_n = self.game.get("name")
                for g in all_games:
                    if (target_p and g.get("path") == target_p) or (target_n and g.get("name") == target_n):
                        g["goals"] = self.game.get("goals", [])
                        g["notes"] = self.game.get("notes", "")
                        break
                save_games_data(all_games, merge_existing_playtime=True)
            except Exception:
                pass

        if self.on_game_updated:
            try:
                self.on_game_updated(self.game)
            except Exception:
                pass

    # =========================================================================
    # GESTIÓN DE PESTAÑAS Y NAVEGACIÓN
    # =========================================================================
    def _switch_tab(self, tab_idx: int):
        self.current_tab = tab_idx
        # Actualizar aspecto de los botones
        for i, b in enumerate(self.tab_buttons):
            if i == tab_idx:
                b.configure(fg_color=COLOR_CYAN_BORDER, text_color=COLOR_CYAN_ACCENT)
            else:
                b.configure(fg_color="transparent", text_color=COLOR_TEXT_MUTED_LIGHT)

        # Ocultar todos los frames
        self.frame_tab0.pack_forget()
        self.frame_tab1.pack_forget()
        self.frame_tab2.pack_forget()

        # Mostrar el frame correspondiente
        if tab_idx == 0:
            self.frame_tab0.pack(fill="both", expand=True)
            self._draw_chart()
            self.lbl_shortcuts.configure(
                text="Cruceta (← / →): Alternar 7 Días / 30 Días  │  (LB / RB): Cambiar Pestaña  │  (B): Cerrar"
            )
        elif tab_idx == 1:
            self.frame_tab1.pack(fill="both", expand=True)
            self._render_goals_list()
            self.lbl_shortcuts.configure(
                text="Cruceta (↑ / ↓): Seleccionar  │  (A): Alternar  │  (X): Añadir Meta  │  (Y): Eliminar  │  (LB/RB): Pestañas"
            )
        elif tab_idx == 2:
            self.frame_tab2.pack(fill="both", expand=True)
            self.lbl_shortcuts.configure(
                text="(A): Guardar Notas  │  (X): Teclado Virtual  │  (LB / RB): Cambiar Pestaña  │  (B): Cerrar"
            )

    def next_tab(self):
        self._switch_tab((self.current_tab + 1) % 3)

    def prev_tab(self):
        self._switch_tab((self.current_tab - 1) % 3)

    # =========================================================================
    # MANEJADOR DE MANDO DE CONSOLA (GAMEPAD DISPATCHER)
    # =========================================================================
    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        """
        Navegación 100% por mando:
        - LB / RB: Alternar pestañas
        - B / Back: Salir del diálogo
        - Tab 0: Left / Right cambia entre gráfico semanal y mensual
        - Tab 1: Up / Down navega entre metas, A alterna, X añade, Y elimina
        - Tab 2: A guarda notas, X abre teclado virtual
        """
        # Botones superiores: alternar pestañas
        if inputs.get("lb", False) and not prev_inputs.get("lb", False):
            self.prev_tab()
            return True
        if inputs.get("rb", False) and not prev_inputs.get("rb", False):
            self.next_tab()
            return True

        # Botón B o Back para salir
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.close()
            return True

        # Pestaña 0: Gráfica
        if self.current_tab == 0:
            if inputs.get("left", False) and not prev_inputs.get("left", False):
                self._set_chart_mode("weekly")
                return True
            if inputs.get("right", False) and not prev_inputs.get("right", False):
                self._set_chart_mode("monthly")
                return True
            if inputs.get("y", False) and not prev_inputs.get("y", False):
                self._open_achievements_dialog()
                return True

        # Pestaña 1: Metas
        elif self.current_tab == 1:
            goals = self.stats["goals"]
            if inputs.get("up", False) and not prev_inputs.get("up", False):
                if goals and self.selected_goal_idx > 0:
                    self.selected_goal_idx -= 1
                    self._highlight_selected_goal()
                return True
            if inputs.get("down", False) and not prev_inputs.get("down", False):
                if goals and self.selected_goal_idx < len(goals) - 1:
                    self.selected_goal_idx += 1
                    self._highlight_selected_goal()
                return True
            if inputs.get("a", False) and not prev_inputs.get("a", False):
                if goals and 0 <= self.selected_goal_idx < len(goals):
                    g_id = goals[self.selected_goal_idx]["id"]
                    self._toggle_goal(g_id)
                return True
            if inputs.get("x", False) and not prev_inputs.get("x", False):
                self._prompt_add_goal()
                return True
            if inputs.get("y", False) and not prev_inputs.get("y", False):
                self._delete_selected_goal()
                return True

        # Pestaña 2: Notas
        elif self.current_tab == 2:
            if inputs.get("a", False) and not prev_inputs.get("a", False):
                self._save_notes()
                return True
            if inputs.get("x", False) and not prev_inputs.get("x", False):
                self._prompt_edit_notes_osk()
                return True

        return False

    def _highlight_selected_goal(self):
        """Actualiza el borde de selección de la meta activa para navegación por mando."""
        for i, card in enumerate(self._goal_widgets):
            if i == self.selected_goal_idx:
                card.configure(border_color=COLOR_CYAN_ACCENT, border_width=1.5)
            else:
                card.configure(border_color=COLOR_BORDER_CARD, border_width=1)
