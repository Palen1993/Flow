with open('core/launcher.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Add import
import_block = """try:
    from core.logger import get_logger
    logger = get_logger("Launcher")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.Launcher")
"""

if "logger = get_logger(\"Launcher\")" not in c:
    c = c.replace("import win32con\n", "import win32con\n" + import_block)

replacements = [
    ('print(f"[Launcher] Configuración de Unreal Engine ({game_name}) sincronizada: Pos=({t_left}, {t_top}), Res={w}x{h}, Mode=Borderless")',
     'logger.info(f"Configuración de Unreal Engine ({game_name}) sincronizada: Pos=({t_left}, {t_top}), Res={w}x{h}, Mode=Borderless")'),
    ('print(f"[Launcher] Error al sincronizar config de Unreal Engine: {e}")',
     'logger.error(f"Error al sincronizar config de Unreal Engine: {e}")'),
    ('print(f"[Launcher] Configuración de AC Black Flag sincronizada con Monitor {target_monitor_index}")',
     'logger.info(f"Configuración de AC Black Flag sincronizada con Monitor {target_monitor_index}")'),
    ('print(f"[Launcher] Error al sincronizar config gráfica: {e}")',
     'logger.error(f"Error al sincronizar config gráfica: {e}")'),
    ('print(f"[Centinela] Guardia activa iniciada para {target_monitor_name} {target_monitor_rect}")',
     'logger.info(f"Guardia activa iniciada para {target_monitor_name} {target_monitor_rect}")'),
    ('print(f"[Centinela] El proceso del juego ({exe_base}) ha concluido. Centinela apagado.")',
     'logger.info(f"El proceso del juego ({exe_base}) ha concluido. Centinela apagado.")'),
    ('print(f"[Centinela] ¡Re-anclaje detectado en caliente! \'{w_title}\' se desvió a Rect={rect}. Devolviendo a {target_monitor_name}...")',
     'logger.warning(f"¡Re-anclaje detectado en caliente! \'{w_title}\' se desvió a Rect={rect}. Devolviendo a {target_monitor_name}...")'),
    ('print(f"[Launcher] Guardián desacoplado iniciado (PID {proc.pid}) para {target_monitor_name} {target_monitor_rect}")',
     'logger.info(f"Guardián desacoplado iniciado (PID {proc.pid}) para {target_monitor_name} {target_monitor_rect}")'),
    ('print(f"[Launcher] Error iniciando guardián desacoplado: {e}")',
     'logger.error(f"Error iniciando guardián desacoplado: {e}")'),
    ('print(f"[Launcher] {fallback_msg}")',
     'logger.info(fallback_msg)'),
    ('print(f"[Launcher] Iniciando {game_path}...")',
     'logger.info(f"Iniciando {game_path}...")'),
    ('print(f"[Launcher] Blindaje Unreal Engine inyectado: {\' \'.join(ue_params)}")',
     'logger.info(f"Blindaje Unreal Engine inyectado: {\' \'.join(ue_params)}")'),
    ('print(f"[Launcher] Blindaje Unity Engine inyectado: {\' \'.join(unity_params)}")',
     'logger.info(f"Blindaje Unity Engine inyectado: {\' \'.join(unity_params)}")'),
    ('print(f"[Launcher] Blindaje Godot Engine inyectado: {\' \'.join(godot_params)}")',
     'logger.info(f"Blindaje Godot Engine inyectado: {\' \'.join(godot_params)}")'),
    ('print(f"[Launcher] Blindaje Source Engine inyectado: {\' \'.join(source_params)}")',
     'logger.info(f"Blindaje Source Engine inyectado: {\' \'.join(source_params)}")'),
    ('print(f"[Launcher] {game_path} requiere elevación. Solicitando permisos de Administrador...")',
     'logger.info(f"{game_path} requiere elevación. Solicitando permisos de Administrador...")'),
    ('print(f"[Launcher] Monitorizando ventanas del juego para {t_name} {t_rect}...")',
     'logger.info(f"Monitorizando ventanas del juego para {t_name} {t_rect}...")'),
    ('print(f"[Launcher] Ventana detectada \'{w_title}\' ({best_window[\'width\']}x{best_window[\'height\']}). Posicionando en {t_name}...")',
     'logger.info(f"Ventana detectada \'{w_title}\' ({best_window[\'width\']}x{best_window[\'height\']}). Posicionando en {t_name}...")'),
    ('print(f"[Launcher] La ventana no responde a SetWindowPos. Disparando bypass DWM por hardware (Win + Shift + Flecha)...")',
     'logger.warning("La ventana no responde a SetWindowPos. Disparando bypass DWM por hardware (Win + Shift + Flecha)...")'),
    ('print(f"[Launcher] Ventana principal estabilizada correctamente en {t_name}.")',
     'logger.info(f"Ventana principal estabilizada correctamente en {t_name}.")'),
    ('print("[Launcher] Tiempo de espera finalizado (juego ejecutándose).")',
     'logger.info("Tiempo de espera finalizado (juego ejecutándose).")'),
    ('print(f"Error ejecutando el juego: {e}")',
     'logger.error(f"Error ejecutando el juego: {e}", exc_info=True)'),
]

for src, rep in replacements:
    if src in c:
        c = c.replace(src, rep)
    else:
        # Check normalized line endings
        src_n = src.replace("\r\n", "\n")
        c_n = c.replace("\r\n", "\n")
        if src_n in c_n:
            c = c_n.replace(src_n, rep)
            print("Replaced normalized:", src[:30])
        else:
            print("Warning: not found:", src[:40])

with open('core/launcher.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("Launcher patched successfully!")
