with open('core/system.py', 'r', encoding='utf-8') as f:
    c = f.read()

import_block = """try:
    from core.logger import get_logger
    logger = get_logger("System")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.System")
"""

if "logger = get_logger(\"System\")" not in c:
    c = c.replace("import win32process\n", "import win32process\n" + import_block)

replacements = [
    ('print(f"Prioridad alta establecida para PID {pid}")',
     'logger.info(f"Prioridad alta establecida para PID {pid}")'),
    ('print(f"Error al establecer prioridad: {e}")',
     'logger.error(f"Error al establecer prioridad: {e}")'),
    ('print(f"[System] Cursor situado preventivamente en el centro del monitor: ({cx}, {cy})")',
     'logger.info(f"Cursor situado preventivamente en el centro del monitor: ({cx}, {cy})")'),
    ('print(f"[System] No se pudo situar el cursor: {e}")',
     'logger.warning(f"No se pudo situar el cursor: {e}")'),
    ('print(f"[System] Inyección DWM ejecutada: Win + Shift + {direction.upper()}")',
     'logger.info(f"Inyección DWM ejecutada: Win + Shift + {direction.upper()}")'),
    ('print(f"[System] Error inyectando combinación Win+Shift+Flecha: {e}")',
     'logger.error(f"Error inyectando combinación Win+Shift+Flecha: {e}")'),
    ('print(f"[System] Ventana {hwnd} posicionada con éxito en ({left}, {top}) [{target_width}x{target_height}]")',
     'logger.info(f"Ventana {hwnd} posicionada con éxito en ({left}, {top}) [{target_width}x{target_height}]")'),
    ('print(f"[System] Aviso UIPI: No se puede mover la ventana {hwnd} (el juego requiere permisos de Administrador)")',
     'logger.warning(f"Aviso UIPI: No se puede mover la ventana {hwnd} (el juego requiere permisos de Administrador)")'),
    ('print(f"[System] Error al mover ventana {hwnd}: {e}")',
     'logger.error(f"Error al mover ventana {hwnd}: {e}")'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)
            print("Replaced normalized:", src[:30])
        else:
            print("Warning: not found:", src[:40])

with open('core/system.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("System patched successfully!")
