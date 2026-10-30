import os
import re
import sys

# Force utf-8 output
sys.stdout.reconfigure(encoding='utf-8')

files = [
    'ui/dialogs/confirm_exit.py',
    'ui/dialogs/glass_message_box.py',
    'ui/dialogs/controller_info_dialog.py',
    'ui/dialogs/glass_folder_browser.py',
    'ui/dialogs/on_screen_keyboard.py',
    'ui/dialogs/external_import_dialog.py',
    'ui/dialogs/scan_results.py',
    'ui/dialogs/gamepad_config_dialog.py',
    'ui/dialogs/add_edit_game.py',
    'ui/dialogs/select_game_to_edit.py',
    'ui/dialogs/cover_picker_dialog.py',
    'ui/dropdowns.py'
]

for f in files:
    if not os.path.exists(f):
        print(f"NOT FOUND: {f}")
        continue
    with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
        lines = fp.readlines()
    print(f"\n=======================================================")
    print(f"FILE: {f}")
    print(f"=======================================================")
    
    # Check registration
    content = "".join(lines)
    registered = ("push_modal" in content or "register_modal_stack" in content)
    inherits_base = "BaseGlassDialog" in content
    print(f"Direct modal register: {registered} | Inherits BaseGlassDialog: {inherits_base}")
    
    # Buttons
    btn_lines = []
    for i, l in enumerate(lines):
        if "CTkButton" in l or "Button" in l:
            # capture next few lines if text is on next line
            chunk = "".join(lines[i:i+6])
            m = re.search(r'text\s*=\s*(["\'][^"\']+["\']|f["\'][^"\']+["\']|[a-zA-Z0-9_\.\(\)]+)', chunk)
            if m:
                btn_lines.append((i+1, m.group(0).strip()))
    print("Buttons found:")
    for lno, b in btn_lines:
        print(f"  Line {lno:4d}: {b}")
        
    # Gamepad handler
    in_gamepad = False
    gp_lines = []
    for l in lines:
        if "def handle_gamepad_input" in l:
            in_gamepad = True
        elif in_gamepad:
            if re.match(r'^\s{0,4}def\s+', l):
                break
            gp_lines.append(l)
    gp_code = "".join(gp_lines)
    keys = re.findall(r'inputs\.get\([\'"](\w+)[\'"]', gp_code)
    print("Gamepad keys mapped in handle_gamepad_input:")
    print(" ", sorted(list(set(keys))))
    
    # Check if B or back is handled
    b_handled = ("b" in keys or "back" in keys)
    # Check if A or start is handled
    a_handled = ("a" in keys or "start" in keys)
    print(f"Handles Cancel (B/Back): {b_handled} | Handles Confirm (A/Start): {a_handled}")
