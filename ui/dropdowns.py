import time
from typing import List, Optional
import tkinter as tk
import customtkinter as ctk

from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_DROPDOWN, COLOR_CYAN_ACCENT,
    COLOR_CYAN_BORDER, font_button, font_body, scroll_to_widget, apply_rounded_window_region
)
from ui.modal_manager import register_modal_stack, unregister_modal_stack

class FloatingGlassDropdown(ctk.CTkToplevel):
    """Menú desplegable flotante translúcido con bordes redondeados y soporte para scroll."""
    def __init__(self, parent, anchor_widget, values: List[str], current_value: str = "", on_select=None, min_width: int = 280, item_icon: str = ""):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.transient(parent)
        self.anchor_widget = anchor_widget
        self.values = values
        self.current_value = current_value
        self.on_select = on_select
        self.item_icon = item_icon
        
        # Fondo transparente para esquinas redondeadas en Windows
        try:
            self.configure(fg_color=COLOR_TRANS_KEY)
            self.wm_attributes("-transparentcolor", COLOR_TRANS_KEY)
        except Exception:
            self.configure(fg_color=COLOR_BG_DROPDOWN)
            
        parent.update_idletasks()
        anchor_widget.update_idletasks()
        
        bx = anchor_widget.winfo_rootx()
        by = anchor_widget.winfo_rooty()
        bw = anchor_widget.winfo_width()
        bh = anchor_widget.winfo_height()
        
        dw = max(bw, min_width)
        item_h = 36
        max_visible = 6
        num_items = len(values)
        
        if num_items <= max_visible:
            dh = num_items * item_h + 18
            use_scroll = False
        else:
            dh = max_visible * item_h + 18
            use_scroll = True
            
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        
        # Alinear preferentemente borde derecho del botón con el dropdown si desborda
        x = bx + bw - dw
        if x < 10:
            x = max(10, bx)
        if x + dw > screen_w - 10:
            x = screen_w - dw - 10
            
        y = by + bh + 4
        if y + dh > screen_h - 10:
            y = max(10, by - dh - 4)
            
        self.geometry(f"{dw}x{dh}+{x}+{y}")
        
        card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_DROPDOWN,
            border_color=COLOR_CYAN_ACCENT,
            border_width=1.8,
            corner_radius=14
        )
        card.pack(fill="both", expand=True, padx=4, pady=4)
        
        if use_scroll:
            container = ctk.CTkScrollableFrame(card, fg_color="transparent")
            container.pack(fill="both", expand=True, padx=4, pady=4)
            self._scroll_container = container
        else:
            container = ctk.CTkFrame(card, fg_color="transparent")
            container.pack(fill="both", expand=True, padx=4, pady=4)
            self._scroll_container = None

        self.item_buttons: List[ctk.CTkButton] = []
        self.selected_index = 0
        for i, val in enumerate(values):
            if val == current_value:
                self.selected_index = i
                break

        for i, val in enumerate(values):
            if i > 0 and not use_scroll:
                sep = ctk.CTkFrame(container, height=1, fg_color="#182c47")
                sep.pack(fill="x", padx=6, pady=1)
                
            is_active = (val == current_value)
            prefix = "✓  " if is_active else "     "
            icon = self.item_icon if (self.item_icon and not val.startswith(self.item_icon.strip())) else ""
            
            btn_kwargs = {
                "master": container,
                "text": f"{prefix}{icon}{val}",
                "anchor": "w",
                "height": 30,
                "corner_radius": 8,
                "fg_color": "#102b4c" if is_active else "transparent",
                "hover_color": "#1a3d66",
                "border_width": 1.2 if is_active else 0,
                "text_color": "#38bdf8" if is_active else "#f0f9ff",
                "font": font_body(12, weight="bold" if is_active else "normal"),
                "command": lambda v=val: self._select_val(v)
            }
            if is_active:
                btn_kwargs["border_color"] = COLOR_CYAN_BORDER
                
            btn = ctk.CTkButton(**btn_kwargs)
            btn.pack(fill="x", padx=2, pady=1)
            btn.bind("<Enter>", lambda e, idx=i: self._on_hover(idx))
            self.item_buttons.append(btn)

        self._update_highlight()
        register_modal_stack(self)
        self.bind("<FocusOut>", lambda e: self.after(120, self._check_focus_out))
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Up>", lambda e: self.select_prev())
        self.bind("<Down>", lambda e: self.select_next())
        self.bind("<Return>", lambda e: self.trigger_selected())
        self.bind("<space>", lambda e: self.trigger_selected())
        self.after(20, self._safe_focus)

    def _on_hover(self, idx: int):
        self.selected_index = idx
        self._update_highlight(auto_scroll=False)

    def _update_highlight(self, auto_scroll: bool = True):
        for i, btn in enumerate(self.item_buttons):
            if not btn.winfo_exists():
                continue
            is_sel = (i == self.selected_index)
            if is_sel:
                btn.configure(
                    fg_color="#1a3d66",
                    border_color=COLOR_CYAN_BORDER,
                    border_width=1.4,
                    text_color="#ffffff"
                )
                if auto_scroll and self._scroll_container:
                    edge = "top" if i == 0 else ("bottom" if i == len(self.item_buttons) - 1 else None)
                    scroll_to_widget(self._scroll_container, btn, force_edge=edge)
            else:
                is_cur = (i < len(self.values) and self.values[i] == self.current_value)
                btn.configure(
                    fg_color="#102b4c" if is_cur else "transparent",
                    border_width=1.0 if is_cur else 0,
                    text_color="#38bdf8" if is_cur else "#f0f9ff"
                )

    def select_prev(self):
        if not self.item_buttons:
            return
        self.selected_index = (self.selected_index - 1) % len(self.item_buttons)
        self._update_highlight(auto_scroll=True)
        try:
            from core.feedback import feedback_menu
            feedback_menu()
        except Exception:
            pass

    def select_next(self):
        if not self.item_buttons:
            return
        self.selected_index = (self.selected_index + 1) % len(self.item_buttons)
        self._update_highlight(auto_scroll=True)
        try:
            from core.feedback import feedback_menu
            feedback_menu()
        except Exception:
            pass

    def trigger_selected(self):
        if 0 <= self.selected_index < len(self.values):
            self._select_val(self.values[self.selected_index])

    def _safe_focus(self):
        try:
            if self.winfo_exists():
                self.focus_force()
        except Exception:
            pass

    def _check_focus_out(self):
        try:
            if self.winfo_exists() and not self.focus_displayof():
                self.destroy()
        except Exception:
            pass

    def destroy(self):
        unregister_modal_stack(self)
        super().destroy()

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self.select_prev()
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self.select_next()
            return True
        if (inputs.get("a", False) and not prev_inputs.get("a", False)) or \
           (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self.trigger_selected()
            return True
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("x", False) and not prev_inputs.get("x", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.destroy()
            return True
        return True

    def _select_val(self, val: str):
        if self.on_select:
            self.on_select(val)
        self.destroy()

    def destroy(self):
        unregister_modal_stack(self)
        try:
            if self.anchor_widget and hasattr(self.anchor_widget, "_active_dropdown"):
                self.anchor_widget._active_dropdown = None
                self.anchor_widget._last_closed_time = time.time()
        except Exception:
            pass
        super().destroy()

class GlassDropdownButton(ctk.CTkButton):
    """Botón con estilo cristal que despliega una lista flotante Glassmorphism."""
    def __init__(self, master, values: List[str] = None, variable: ctk.StringVar = None, command=None, 
                 placeholder: str = "Seleccionar...", width: int = 240, height: int = 32, 
                 item_icon: str = "", font=None, **kwargs):
        self.values = values or []
        self.variable = variable
        self.user_command = command
        self.placeholder = placeholder
        self.item_icon = item_icon
        self._active_dropdown = None
        self._last_closed_time = 0.0
        
        initial_text = ""
        if self.variable and self.variable.get():
            initial_text = self.variable.get()
        elif self.values:
            initial_text = self.values[0]
        else:
            initial_text = placeholder
            
        btn_font = font or font_button(12)
        
        default_opts = {
            "height": height,
            "corner_radius": 14,
            "fg_color": "#132338",
            "hover_color": "#1a3556",
            "border_color": COLOR_CYAN_BORDER,
            "border_width": 1.4,
            "text_color": "#f0f9ff",
            "font": btn_font
        }
        default_opts.update(kwargs)
        if "width" in kwargs:
            default_opts["width"] = kwargs["width"]
        else:
            default_opts["width"] = width
            
        super().__init__(master, text=f"{initial_text}  ▾" if initial_text else f"{placeholder}  ▾", 
                         command=self._toggle_dropdown, **default_opts)
        
        self.current_value = initial_text
        if self.variable and not self.variable.get() and initial_text != placeholder:
            self.variable.set(initial_text)

    def _toggle_dropdown(self):
        now = time.time()
        if now - self._last_closed_time < 0.25:
            return
            
        if self._active_dropdown and self._active_dropdown.winfo_exists():
            try:
                self._active_dropdown.destroy()
            except Exception:
                pass
            self._active_dropdown = None
            self._last_closed_time = now
            return
            
        cur = self.get()
        self._active_dropdown = FloatingGlassDropdown(
            parent=self.winfo_toplevel(),
            anchor_widget=self,
            values=self.values,
            current_value=cur,
            on_select=self._on_select_item,
            min_width=max(self.winfo_width(), 260),
            item_icon=self.item_icon
        )

    def _on_select_item(self, val: str):
        self.set(val)
        if self.user_command:
            self.user_command(val)

    def set(self, val: str):
        self.current_value = val
        if self.variable:
            self.variable.set(val)
        display_text = f"{val}  ▾" if val else f"{self.placeholder}  ▾"
        self.configure(text=display_text)

    def get(self) -> str:
        if self.variable:
            return self.variable.get()
        return self.current_value

    def configure_values(self, values: List[str]):
        self.values = values

class FloatingGlassMenu(ctk.CTkToplevel):
    """Menú contextual o de cabecera flotante estilo Glassmorphism con navegación completa por mando y teclado."""
    def __init__(self, parent, anchor_widget, items):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.items = items
        self.item_buttons = []
        self.selected_index = 0
        
        try:
            self.configure(fg_color=COLOR_TRANS_KEY)
            self.wm_attributes("-transparentcolor", COLOR_TRANS_KEY)
        except Exception:
            self.configure(fg_color="#0b0f17")
        
        parent.update_idletasks()
        mw = 355
        mh = len(items) * 44 + 28
        try:
            if anchor_widget is not None and anchor_widget != parent and anchor_widget.winfo_viewable() and anchor_widget.winfo_height() < 120:
                bx = anchor_widget.winfo_rootx()
                by = anchor_widget.winfo_rooty()
                bw = anchor_widget.winfo_width()
                bh = anchor_widget.winfo_height()
                x = max(10, bx + bw - mw)
                y = by + bh + 8
            else:
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                x = max(10, px + pw - mw - 22)
                y = py + 56
                # Si el lienzo CoverFlow tiene un botón "menu" ("⚙ Opciones"), alinear bajo él
                stage = getattr(parent, "cover_stage", None)
                if stage is not None and getattr(stage, "hud_hitboxes", None):
                    for (hx1, hy1, hx2, hy2, hact) in stage.hud_hitboxes:
                        if hact == "menu":
                            sx = stage.winfo_rootx()
                            sy = stage.winfo_rooty()
                            x = max(10, min(px + pw - mw - 18, sx + hx1))
                            y = sy + hy2 + 8
                            break
        except Exception:
            x, y = 100, 60
        self.geometry(f"{mw}x{mh}+{x}+{y}")
        
        card = ctk.CTkFrame(
            self,
            fg_color="#141722",
            border_color="#2b3345",
            border_width=1.5,
            corner_radius=20
        )
        card.pack(fill="both", expand=True, padx=4, pady=4)
        
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=8, pady=8)
        
        def on_item(cmd):
            self.destroy()
            if cmd:
                cmd()
                
        for i, (icon, label, action) in enumerate(items):
            if i > 0:
                sep = ctk.CTkFrame(content, height=1, fg_color="#1e2434")
                sep.pack(fill="x", padx=10, pady=2)

            # Eliminar selector de variación U+FE0F que en Tcl/Tk introduce un hueco ancho extra tras el icono
            clean_icon = str(icon or "").replace("\ufe0f", "").strip()
            btn_text = f"  {clean_icon} {label}" if clean_icon else f"  {label}"
            btn = ctk.CTkButton(
                content,
                text=btn_text,
                anchor="w",
                height=38,
                corner_radius=12,
                fg_color="transparent",
                hover_color="#222838",
                text_color="#f1f5f9",
                font=font_button(13),
                command=lambda a=action: on_item(a)
            )
            btn.pack(fill="x", padx=4, pady=2)
            btn.bind("<Enter>", lambda e, idx=i: self._on_hover(idx))
            self.item_buttons.append(btn)

        self._update_highlight()
            
        self.bind("<FocusOut>", lambda e: self.after(120, self._check_focus_out))
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<b>", lambda e: self.destroy())
        self.bind("<B>", lambda e: self.destroy())
        self.bind("<x>", lambda e: self.destroy())
        self.bind("<X>", lambda e: self.destroy())
        self.bind("<Up>", lambda e: self.select_prev())
        self.bind("<Down>", lambda e: self.select_next())
        self.bind("<Return>", lambda e: self.trigger_selected())
        self.bind("<space>", lambda e: self.trigger_selected())
        register_modal_stack(self)
        self.focus_set()

    def _update_highlight(self):
        for idx, btn in enumerate(self.item_buttons):
            if idx == self.selected_index:
                btn.configure(
                    fg_color="#222838",
                    border_color="#364057",
                    border_width=1.0,
                    text_color="#ffffff"
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    border_width=0,
                    text_color="#f1f5f9"
                )

    def _on_hover(self, idx: int):
        self.selected_index = idx
        self._update_highlight()

    def select_next(self):
        if not self.item_buttons:
            return
        self.selected_index = (self.selected_index + 1) % len(self.item_buttons)
        self._update_highlight()
        try:
            from core.feedback import feedback_menu
            feedback_menu()
        except Exception:
            pass

    def select_prev(self):
        if not self.item_buttons:
            return
        self.selected_index = (self.selected_index - 1) % len(self.item_buttons)
        self._update_highlight()
        try:
            from core.feedback import feedback_menu
            feedback_menu()
        except Exception:
            pass

    def trigger_selected(self):
        if 0 <= self.selected_index < len(self.items):
            action = self.items[self.selected_index][2]
            self.destroy()
            if action:
                action()

    def _check_focus_out(self):
        try:
            if self.winfo_exists() and not self.focus_displayof():
                self.destroy()
        except Exception:
            pass

    def handle_gamepad_input(self, inputs: dict, prev_inputs: dict) -> bool:
        if inputs.get("up", False) and not prev_inputs.get("up", False):
            self.select_prev()
            return True
        if inputs.get("down", False) and not prev_inputs.get("down", False):
            self.select_next()
            return True
        if (inputs.get("a", False) and not prev_inputs.get("a", False)) or \
           (inputs.get("start", False) and not prev_inputs.get("start", False)):
            self.trigger_selected()
            return True
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("x", False) and not prev_inputs.get("x", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.destroy()
            return True
        return True
