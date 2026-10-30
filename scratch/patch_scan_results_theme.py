with open('ui/dialogs/scan_results.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_CYAN_ACCENT,
    COLOR_CYAN_GLOW, font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

import_rep = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_GLOW,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER,
    COLOR_BTN_SECONDARY_BG,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_WARNING,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_MUTED, COLOR_TEXT_DIM,
    font_button, font_body, scroll_to_widget, apply_rounded_window_region
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('self.configure(fg_color="#141722")', 'self.configure(fg_color=COLOR_BG_CARD)'),
    ('fg_color="#141722",\n            border_color="#2b3345"', 'fg_color=COLOR_BG_CARD,\n            border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f8fafc"', 'text_color=COLOR_TEXT_MAIN'),
    ('fg_color="#007aff", hover_color="#0062cc",\n            corner_radius=15, text_color="#ffffff"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,\n            corner_radius=15, text_color=COLOR_TEXT_WHITE'),
    ('fg_color="#1c212d", hover_color="#262d3d", border_color="#2b3345", border_width=1.2,\n            corner_radius=15, text_color="#94a3b8"',
     'fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d", border_color=COLOR_GLASS_BORDER, border_width=1.2,\n            corner_radius=15, text_color=COLOR_TEXT_MUTED'),
    ('font=font_body(12), text_color="#64748b"', 'font=font_body(12), text_color=COLOR_TEXT_DIM'),
    ('font=font_body(11), text_color="#64748b"', 'font=font_body(11), text_color=COLOR_TEXT_DIM'),
    ('row_frame = ctk.CTkFrame(scroll_frame, fg_color="#181d28", corner_radius=14, border_color="#242c3d"',
     'row_frame = ctk.CTkFrame(scroll_frame, fg_color=COLOR_BG_CARD_SECONDARY, corner_radius=14, border_color=COLOR_BORDER_CARD'),
    ('bg="#181d28"', 'bg=COLOR_BG_CARD_SECONDARY'),
    ('fg_color="#0f1218", border_color="#2b3345"', 'fg_color=COLOR_BG_DARK, border_color=COLOR_GLASS_BORDER'),
    ('text_color="#34c759"', 'text_color=COLOR_STATUS_SUCCESS'),
    ('text_color="#f59e0b"', 'text_color=COLOR_STATUS_WARNING'),
    ('font=font_button(12), text_color="#94a3b8"', 'font=font_button(12), text_color=COLOR_TEXT_MUTED'),
    ('fg_color="#007aff", hover_color="#0062cc",\n            corner_radius=19, text_color="#ffffff"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER,\n            corner_radius=19, text_color=COLOR_TEXT_WHITE'),
    ('fg_color="#1c212d", hover_color="#262d3d", border_color="#2b3345", border_width=1.2,\n            corner_radius=19, text_color="#94a3b8"',
     'fg_color=COLOR_BTN_SECONDARY_BG, hover_color="#262d3d", border_color=COLOR_GLASS_BORDER, border_width=1.2,\n            corner_radius=19, text_color=COLOR_TEXT_MUTED'),
    ('rf.configure(border_color="#007aff", border_width=2.0, fg_color="#1d2536")',
     'rf.configure(border_color=COLOR_IOS_BLUE, border_width=2.0, fg_color="#1d2536")'),
    ('rf.configure(border_color="#242c3d", border_width=1.0, fg_color="#181d28")',
     'rf.configure(border_color=COLOR_BORDER_CARD, border_width=1.0, fg_color=COLOR_BG_CARD_SECONDARY)'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('ui/dialogs/scan_results.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("scan_results.py patched successfully!")
