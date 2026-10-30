with open('ui/dialogs/cover_picker_dialog.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_src = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_BG_DARK, COLOR_TEXT_MAIN, COLOR_TEXT_MUTED, font_button, font_title
)"""

import_rep = """from ui.theme import (
    COLOR_TRANS_KEY, COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_BG_DARK, COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY,
    COLOR_GLASS_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_title, font_body
)"""

c = c.replace(import_src, import_rep)

replacements = [
    ('fg_color="#141722", border_color="#2b3345"', 'fg_color=COLOR_BG_CARD, border_color=COLOR_GLASS_BORDER'),
    ('fg_color="#141722"', 'fg_color=COLOR_BG_CARD'),
    ('border_color="#2b3345"', 'border_color=COLOR_GLASS_BORDER'),
    ('text_color="#f8fafc"', 'text_color=COLOR_TEXT_MAIN'),
    ('text_color="#ffffff"', 'text_color=COLOR_TEXT_WHITE'),
    ('text_color="#cbd5e1"', 'text_color=COLOR_TEXT_MUTED_LIGHT'),
    ('text_color="#94a3b8"', 'text_color=COLOR_TEXT_MUTED'),
    ('text_color="#38bdf8"', 'text_color=COLOR_CYAN_ACCENT'),
    ('border_color="#38bdf8"', 'border_color=COLOR_CYAN_ACCENT'),
    ('fg_color="#007aff", hover_color="#0062cc", border_color="#3894ff"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER, border_color=COLOR_IOS_BLUE_BORDER'),
    ('fg_color="#007aff", hover_color="#0062cc"',
     'fg_color=COLOR_IOS_BLUE, hover_color=COLOR_IOS_BLUE_HOVER'),
    ('fg_color="#1c212d", hover_color="#283040", border_color="#333c50"',
     'fg_color=COLOR_BTN_SECONDARY_BG, hover_color=COLOR_BTN_SECONDARY_HOVER, border_color=COLOR_BTN_SECONDARY_BORDER'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)

with open('ui/dialogs/cover_picker_dialog.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("cover_picker_dialog.py patched with theme tokens successfully!")
