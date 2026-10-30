with open('ui/dialogs/gamepad_config_dialog.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_CYAN_ACCENT,
    COLOR_CYAN_GLOW, font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

import_rep = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_DANGER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('self.configure(fg_color="#141722")', 'self.configure(fg_color=COLOR_BG_CARD)'),
    ('fg_color="#141722",\n            border_color="#2b3345"', 'fg_color=COLOR_BG_CARD,\n            border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f8fafc"', 'text_color=COLOR_TEXT_MAIN'),
    ('font=font_body(12), text_color="#64748b"', 'font=font_body(12), text_color=COLOR_TEXT_DIM'),
    ('card_dev = ctk.CTkFrame(scroll, fg_color="#181d28", corner_radius=16, border_color="#242c3d"',
     'card_dev = ctk.CTkFrame(scroll, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=16, border_color=COLOR_BORDER_CARD'),
    ('card_switches = ctk.CTkFrame(scroll, fg_color="#181d28", corner_radius=16, border_color="#242c3d"',
     'card_switches = ctk.CTkFrame(scroll, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=16, border_color=COLOR_BORDER_CARD'),
    ('card_guide = ctk.CTkFrame(scroll, fg_color="#181d28", corner_radius=16, border_color="#242c3d"',
     'card_guide = ctk.CTkFrame(scroll, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=16, border_color=COLOR_BORDER_CARD'),
    ('text_color="#f1f5f9"', 'text_color=COLOR_TEXT_BRIGHT'),
    ('text_color="#94a3b8"', 'text_color=COLOR_TEXT_MUTED'),
    ('progress_color="#34c759"', 'progress_color=COLOR_STATUS_SUCCESS'),
    ('fg_color="#007aff", hover_color="#0062cc", border_color="#3894ff", border_width=1.2,\n            corner_radius=19, text_color="#ffffff"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER, border_color=COLOR_IOS_BLUE_BORDER, border_width=1.2,\n            corner_radius=19, text_color=COLOR_TEXT_WHITE'),
    ('fg_color="#1c212d", hover_color="#283040", border_color="#333c50", border_width=1.0,\n            corner_radius=19, text_color="#cbd5e1"',
     'fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER, border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0,\n            corner_radius=19, text_color=COLOR_TEXT_MUTED_LIGHT'),
    ('text_color="#38bdf8" if is_foc else "#f8fafc"', 'text_color=COLOR_CYAN_ACCENT if is_foc else COLOR_TEXT_MAIN'),
    ('border_color="#38bdf8" if is_foc else "#3894ff"', 'border_color=COLOR_CYAN_ACCENT if is_foc else COLOR_IOS_BLUE_BORDER'),
    ('border_color="#007aff" if is_foc else "#333c50"', 'border_color=COLOR_IOS_BLUE if is_foc else COLOR_BTN_SECONDARY_BORDER'),
    ('text_color="#4ade80"', 'text_color=COLOR_STATUS_SUCCESS'),
    ('text_color="#f87171"', 'text_color=COLOR_STATUS_DANGER'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('ui/dialogs/gamepad_config_dialog.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("gamepad_config_dialog.py patched successfully!")
