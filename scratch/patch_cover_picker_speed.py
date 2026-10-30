import os

picker_path = "ui/dialogs/cover_picker_dialog.py"
with open(picker_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add _schedule_live_preview_debounced before _on_offset_slider_changed
target_slider_start = """    def _on_offset_slider_changed(self, value: float):
        \"\"\"Ajusta el encuadre (modo carátula) o la opacidad del fondo (modo wallpaper 16:9).\"\"\"
        if self.asset_mode == "wallpaper":
            self.wp_opacity = self._slider_to_opacity(value)
            pct_op = int(round(self.wp_opacity * 100))
            self.lbl_sl.configure(text=f"Opacidad del fondo (LB / RB): {pct_op}%")
            self._refresh_wp_preset_highlight()
            cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx) or self.current_wallpaper_pil
            self._update_live_preview(cur_pil)
            return

        self.crop_offset = float(value)
        if self.fit_mode == "stretch":
            self.fit_mode = "crop"
        cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx)
        self._update_live_preview(cur_pil)

    def _on_blur_slider_changed(self, value: float):
        \"\"\"Ajusta la borrosidad / desenfoque gaussiano del fondo en modo wallpaper 16:9 (0.0 Nítido ↔ 12.0 Borroso).\"\"\"
        self.wp_blur = round(float(value) * 12.0, 1)
        blur_tag = "Nítido" if self.wp_blur < 0.3 else ("Suave" if self.wp_blur <= 2.5 else "Borroso")
        self.lbl_blur_sl.configure(text=f"Borrosidad / Desenfoque (LT / RT): {self.wp_blur:.1f} ({blur_tag})")
        if self.asset_mode == "wallpaper":
            self._refresh_wp_preset_highlight()
            cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx) or self.current_wallpaper_pil
            self._update_live_preview(cur_pil)"""

repl_slider_start = """    def _schedule_live_preview_debounced(self, cur_pil):
        \"\"\"Coalesce actualizaciones continuas de sliders/arrastre a un framerate óptimo (35ms / ~30 FPS).\"\"\"
        job = getattr(self, "_preview_debounce_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._preview_debounce_job = self.after(35, lambda: self._update_live_preview(cur_pil))

    def _on_offset_slider_changed(self, value: float):
        \"\"\"Ajusta el encuadre (modo carátula) o la opacidad del fondo (modo wallpaper 16:9).\"\"\"
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
        \"\"\"Ajusta la borrosidad / desenfoque gaussiano del fondo en modo wallpaper 16:9 (0.0 Nítido ↔ 12.0 Borroso).\"\"\"
        self.wp_blur = round(float(value) * 12.0, 1)
        blur_tag = "Nítido" if self.wp_blur < 0.3 else ("Suave" if self.wp_blur <= 2.5 else "Borroso")
        self.lbl_blur_sl.configure(text=f"Borrosidad / Desenfoque (LT / RT): {self.wp_blur:.1f} ({blur_tag})")
        if self.asset_mode == "wallpaper":
            self._refresh_wp_preset_highlight()
            cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx) or self.current_wallpaper_pil
            self._schedule_live_preview_debounced(cur_pil)"""

assert target_slider_start in content, "target_slider_start not found"
content = content.replace(target_slider_start, repl_slider_start, 1)

# 2. Update _on_preview_drag_motion to use debouncing as well
target_drag = """        self.offset_slider.set(new_off)
        cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx)
        self._update_live_preview(cur_pil)"""

repl_drag = """        self.offset_slider.set(new_off)
        cur_pil = self.raw_pil_by_idx.get(self.selected_card_idx)
        self._schedule_live_preview_debounced(cur_pil)"""

assert target_drag in content, "target_drag not found"
content = content.replace(target_drag, repl_drag, 1)

with open(picker_path, "w", encoding="utf-8") as f:
    f.write(content)

print("ui/dialogs/cover_picker_dialog.py successfully patched for ultra-smooth responsiveness!")
