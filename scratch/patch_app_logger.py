with open('app.py', 'r', encoding='utf-8') as f:
    c = f.read()

target = "from core.system import get_monitors"
replacement = "from core.system import get_monitors\nfrom core.logger import get_logger\n\nlogger = get_logger(\"App\")"

if "logger = get_logger(\"App\")" not in c:
    c = c.replace(target, replacement)

c = c.replace('print(f"[App] Error al refrescar juegos desde disco: {e}")',
              'logger.error(f"Error al refrescar juegos desde disco: {e}", exc_info=True)')
c = c.replace('print("[App] Lanzamiento ignorado: ya hay un juego iniciando.")',
              'logger.warning("Lanzamiento ignorado: ya hay un juego iniciando.")')
c = c.replace('print(msg)', 'logger.info(msg)')

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("app.py patched with logger!")
