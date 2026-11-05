"""
Script de sincronizacion e instalacion/actualizacion de GameFlow Launcher Personal.
Transfiere los binarios compilados y assets a la carpeta fija de juego diario:
C:\\Users\\jorge\\Documents\\Programas\\GameFlow

Garantia de seguridad:
- NUNCA sobrescribe games.json, covers/ ni wallpapers/ si ya existen en la app de juego.
- Crea el acceso directo en el Escritorio con icono oficial.
"""
import os
import sys
import shutil
import subprocess

BASE_DEV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYER_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(BASE_DEV_DIR), "GameFlow"))

def create_desktop_shortcut(target_exe: str, working_dir: str, icon_path: str):
    """Crea o actualiza el acceso directo en el Escritorio de Windows."""
    desktop_dir = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
    shortcut_path = os.path.join(desktop_dir, "GameFlow.lnk")
    try:
        ps_script = f'''
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
        $Shortcut.TargetPath = "{target_exe}"
        $Shortcut.WorkingDirectory = "{working_dir}"
        $Shortcut.IconLocation = "{icon_path}"
        $Shortcut.Description = "GameFlow Launcher - Tu centro de juegos de alto rendimiento"
        $Shortcut.Save()
        '''
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True, capture_output=True)
        print(f"  [OK] Acceso directo creado en el Escritorio: {shortcut_path}")
        return True
    except Exception as e:
        print(f"  [AVISO] No se pudo crear el acceso directo automaticamente: {e}")
        return False

def sync_to_player(build_first: bool = True):
    print("=" * 60)
    print(">> SINCRONIZANDO CON TU APLICACION PERSONAL (GameFlow)")
    print("=" * 60)
    print(f"  Carpeta de Desarrollo: {BASE_DEV_DIR}")
    print(f"  Carpeta de Juego:      {PLAYER_APP_DIR}")

    # 1. Compilar si se solicita
    if build_first:
        print("\n[1/4] Compilando la ultima version del codigo fuente...")
        python_exe = os.path.join(BASE_DEV_DIR, "venv", "Scripts", "python.exe")
        if not os.path.isfile(python_exe):
            python_exe = sys.executable
        ret = subprocess.call([python_exe, os.path.join(BASE_DEV_DIR, "build.py")])
        if ret != 0:
            print("[ERROR] Error en la compilacion. Se cancela la actualizacion.")
            return False

    dist_app = os.path.join(BASE_DEV_DIR, "dist", "GameFlow Launcher")
    if not os.path.isdir(dist_app):
        print(f"[ERROR] No se encontro la carpeta compilada: {dist_app}")
        return False

    os.makedirs(PLAYER_APP_DIR, exist_ok=True)

    # 2. Copiar binarios y dependencias del motor
    print("\n[2/4] Actualizando ejecutables y dependencias del motor...")
    for item in ["GameFlow Launcher.exe", "sentinel_process.exe", "gamepad_watcher.exe"]:
        src = os.path.join(dist_app, item)
        dst = os.path.join(PLAYER_APP_DIR, item)
        if os.path.isfile(src):
            try:
                shutil.copy2(src, dst)
            except PermissionError:
                print(f"[AVISO] No se pudo sobrescribir {item}. Cierra la app e intentalo de nuevo.")
                return False

    for folder in ["_internal", "assets"]:
        src_f = os.path.join(dist_app, folder)
        dst_f = os.path.join(PLAYER_APP_DIR, folder)
        if os.path.isdir(src_f):
            if os.path.exists(dst_f):
                shutil.rmtree(dst_f)
            shutil.copytree(src_f, dst_f)
            print(f"  -> Actualizada carpeta {folder}/")

    # Asegurar marcador portable
    with open(os.path.join(PLAYER_APP_DIR, ".portable"), "w", encoding="utf-8") as f:
        f.write("")

    # 3. Inicializar o preservar datos de juego del usuario
    print("\n[3/4] Comprobando biblioteca personal de juegos...")
    player_games = os.path.join(PLAYER_APP_DIR, "games.json")
    player_covers = os.path.join(PLAYER_APP_DIR, "covers")
    player_wallpapers = os.path.join(PLAYER_APP_DIR, "wallpapers")
    player_gamepad = os.path.join(PLAYER_APP_DIR, "gamepad_config.json")

    os.makedirs(player_covers, exist_ok=True)
    os.makedirs(player_wallpapers, exist_ok=True)

    dev_games = os.path.join(BASE_DEV_DIR, "games.json")
    dev_covers = os.path.join(BASE_DEV_DIR, "covers")
    dev_wallpapers = os.path.join(BASE_DEV_DIR, "wallpapers")
    dev_gamepad = os.path.join(BASE_DEV_DIR, "gamepad_config.json")

    if not os.path.isfile(player_games) and os.path.isfile(dev_games):
        shutil.copy2(dev_games, player_games)
        print("  -> Importada tu biblioteca inicial de juegos a GameFlow/")
    else:
        print("  [OK] Tu archivo games.json se mantiene 100% INTACTO (tus juegos no se tocan)")

    if os.path.isfile(dev_gamepad) and not os.path.isfile(player_gamepad):
        shutil.copy2(dev_gamepad, player_gamepad)

    cov_count = 0
    if os.path.isdir(dev_covers):
        for f in os.listdir(dev_covers):
            src_cov = os.path.join(dev_covers, f)
            dst_cov = os.path.join(player_covers, f)
            if os.path.isfile(src_cov) and not os.path.exists(dst_cov):
                shutil.copy2(src_cov, dst_cov)
                cov_count += 1
    if cov_count > 0:
        print(f"  -> Copiadas {cov_count} caratulas nuevas a GameFlow/covers/")

    wp_count = 0
    if os.path.isdir(dev_wallpapers):
        for f in os.listdir(dev_wallpapers):
            src_wp = os.path.join(dev_wallpapers, f)
            dst_wp = os.path.join(player_wallpapers, f)
            if os.path.isfile(src_wp) and not os.path.exists(dst_wp):
                shutil.copy2(src_wp, dst_wp)
                wp_count += 1
    if wp_count > 0:
        print(f"  -> Copiados {wp_count} wallpapers nuevos a GameFlow/wallpapers/")

    # 4. Crear acceso directo en el Escritorio
    print("\n[4/4] Verificando acceso directo en el Escritorio...")
    target_exe = os.path.join(PLAYER_APP_DIR, "GameFlow Launcher.exe")
    icon_file = os.path.join(PLAYER_APP_DIR, "assets", "icon.ico")
    create_desktop_shortcut(target_exe, PLAYER_APP_DIR, icon_file)

    print("\n" + "=" * 60)
    print("[OK] ACTUALIZACION COMPLETADA CON EXITO!")
    print(f"  Tu aplicacion para jugar: {PLAYER_APP_DIR}")
    print("  Puedes iniciarla desde el acceso directo 'GameFlow' en tu Escritorio.")
    print("=" * 60)
    return True

if __name__ == "__main__":
    build_flag = "--no-build" not in sys.argv
    sync_to_player(build_first=build_flag)
