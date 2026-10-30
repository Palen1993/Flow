with open('app.py', 'r', encoding='utf-8') as f:
    c = f.read()

target = """        while self._modal_stack:
            top = self._modal_stack[-1]
            try:
                if top.winfo_exists() and (top.state() != "withdrawn") and bool(top.winfo_viewable()):
                    return top
            except Exception:
                pass
            self._modal_stack.pop()

        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            try:
                if bool(self.glass_menu.winfo_viewable()):
                    return self.glass_menu
            except Exception:
                pass"""

replacement = """        while self._modal_stack:
            top = self._modal_stack[-1]
            try:
                if top.winfo_exists():
                    state = getattr(top, "state", lambda: "normal")()
                    if state not in ("withdrawn", "iconic"):
                        return top
            except Exception:
                pass
            self._modal_stack.pop()

        if hasattr(self, "glass_menu") and self.glass_menu and self.glass_menu.winfo_exists():
            try:
                state = getattr(self.glass_menu, "state", lambda: "normal")()
                if state not in ("withdrawn", "iconic"):
                    return self.glass_menu
            except Exception:
                pass"""

if target in c:
    c = c.replace(target, replacement)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print("SUCCESS: app.py patched!")
else:
    # Try normalizing line endings
    c_norm = c.replace('\r\n', '\n')
    target_norm = target.replace('\r\n', '\n')
    replacement_norm = replacement.replace('\r\n', '\n')
    if target_norm in c_norm:
        c_norm = c_norm.replace(target_norm, replacement_norm)
        with open('app.py', 'w', encoding='utf-8') as f:
            f.write(c_norm)
        print("SUCCESS: app.py patched with normalized line endings!")
    else:
        print("ERROR: Target not found in app.py")
