with open('ui/dialogs/add_edit_game.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_CYAN_ACCENT,
    COLOR_CYAN_BORDER, COLOR_CYAN_GLOW, font_button, font_body, apply_rounded_window_region
)"""

import_rep = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_BTN_DANGER_BG, COLOR_BTN_DANGER_HOVER, COLOR_BTN_DANGER_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED_LIGHT,
    font_button, font_body, apply_rounded_window_region
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('self.configure(fg_color="#141722")', 'self.configure(fg_color=COLOR_BG_CARD)'),
    ('fg_color="#141722",\n            border_color="#2b3345"', 'fg_color=COLOR_BG_CARD,\n            border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f8fafc"', 'text_color=COLOR_TEXT_MAIN'),
    ('left_frame = ctk.CTkFrame(content_frame, fg_color="#181d28", border_color="#242c3d"',
     'left_frame = ctk.CTkFrame(content_frame, fg_color=COLOR_BG_CARD_SECONDARY, border_color=COLOR_BORDER_CARD'),
    ('right_frame = ctk.CTkFrame(content_frame, fg_color="#181d28", border_color="#242c3d"',
     'right_frame = ctk.CTkFrame(content_frame, fg_color=COLOR_BG_CARD_SECONDARY, border_color=COLOR_BORDER_CARD'),
    ('text_color="#f1f5f9"', 'text_color=COLOR_TEXT_BRIGHT'),
    ('fg_color="#0f1218", border_color="#242a3a"', 'fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_HOVER'),
    ('fg_color="#ff2d55", hover_color="#e02245", border_color="#ff6384", border_width=1.2,\n                corner_radius=19, text_color="#ffffff"',
     'fg_color=COLOR_BTN_DANGER_BG, hover_color=COLOR_BTN_DANGER_HOVER, border_color=COLOR_BTN_DANGER_BORDER, border_width=1.2,\n                corner_radius=19, text_color=COLOR_TEXT_WHITE'),
    ('fg_color="#1c212d", hover_color="#283040", border_color="#333c50", border_width=1.0,\n            corner_radius=19, text_color="#cbd5e1"',
     'fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER, border_color=COLOR_BTN_SECONDARY_BORDER, border_width=1.0,\n            corner_radius=19, text_color=COLOR_TEXT_MUTED_LIGHT'),
    ('fg_color="#007aff", hover_color="#0062cc", border_color="#3894ff", border_width=1.2,\n            corner_radius=19, text_color="#ffffff"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER, border_color=COLOR_IOS_BLUE_BORDER, border_width=1.2,\n            corner_radius=19, text_color=COLOR_TEXT_WHITE'),
    ('fg_color="#007aff", hover_color="#0062cc", border_color="#3894ff", border_width=1.0,\n            corner_radius=15, text_color="#ffffff"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER, border_color=COLOR_IOS_BLUE_BORDER, border_width=1.0,\n            corner_radius=15, text_color=COLOR_TEXT_WHITE'),
    ('text_color="#cbd5e1"', 'text_color=COLOR_TEXT_MUTED_LIGHT'),
    ('widget.configure(text_color="#38bdf8" if is_foc else "#f8fafc")',
     'widget.configure(text_color=COLOR_CYAN_ACCENT if is_foc else COLOR_TEXT_MAIN)'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('ui/dialogs/add_edit_game.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("add_edit_game.py patched successfully!")
