with open('lanzador.py', 'r', encoding='utf-8') as f:
    c = f.read()

target = "from core.system import ensure_admin"
replacement = "from core.system import ensure_admin\nfrom core.logger import get_logger\n\nlogger = get_logger(\"Main\")"

if "logger = get_logger(\"Main\")" not in c:
    c = c.replace(target, replacement)

c = c.replace('print("[Lanzador] Ya existe una instancia activa. Trayendo al frente y cerrando duplicado.")',
              'logger.info("Ya existe una instancia activa. Trayendo al frente y cerrando duplicado.")')

with open('lanzador.py', 'w', encoding='utf-8') as f:
    f.write(c)

print("lanzador.py patched with logger!")
