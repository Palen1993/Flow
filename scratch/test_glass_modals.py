"""Prueba integral de los nuevos modales GlassMessageBox y GlassFolderBrowserDialog."""
import customtkinter as ctk
from ui.dialogs.glass_message_box import GlassMessageBox, show_info, show_warning, show_error, ask_yes_no
from ui.dialogs.glass_folder_browser import GlassFolderBrowserDialog, browse_folder, browse_file

app = ctk.CTk()
app.geometry("400x300")
app.withdraw()

# 1. Probar GlassMessageBox tipo info
dlg_info = GlassMessageBox(app, "Prueba Info", "Este es un mensaje de prueba informativo.", kind="info")
app.update()
assert dlg_info.winfo_exists()
# Simular pulsación de botón A en gamepad
dlg_info.handle_gamepad_input({"a": True}, {"a": False})
app.update()
assert not dlg_info.winfo_exists(), "GlassMessageBox info debió cerrarse con A"

# 2. Probar GlassMessageBox tipo confirm
dlg_conf = GlassMessageBox(app, "Confirmar Acción", "¿Deseas continuar?", kind="confirm", is_destructive=True)
app.update()
assert dlg_conf._focused_btn == 0  # Comienza en cancelar por ser destructivo
# Simular D-Pad derecha
dlg_conf.handle_gamepad_input({"right": True}, {"right": False})
assert dlg_conf._focused_btn == 1  # Foco en confirmar
# Simular A
dlg_conf.handle_gamepad_input({"a": True}, {"a": False})
app.update()
assert dlg_conf.result is True, "GlassMessageBox debió confirmar"

# 3. Probar GlassFolderBrowserDialog
dlg_fb = GlassFolderBrowserDialog(app, title="Escanear", select_mode="folder")
app.update()
assert dlg_fb.winfo_exists()
# Navegar abajo
dlg_fb.handle_gamepad_input({"down": True}, {"down": False})
# Confirmar carpeta con X
dlg_fb.handle_gamepad_input({"x": True}, {"x": False})
app.update()
assert dlg_fb.selected_path is not None, "GlassFolderBrowserDialog debió seleccionar la ruta actual con X"

print("✅ Todos los nuevos diálogos modales funcionan y responden a inputs de mando al 100%")
app.destroy()
