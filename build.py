"""
Script de compilación automatizado para GameFlow Launcher.
Genera la suite de ejecutables en dist/GameFlow Launcher y crea un archivo .zip portátil listo para enviar.
Limpia estrictamente cualquier dato personal (juegos, carátulas y fondos del desarrollador)
para que la versión distribuida comience como una instalación limpia lista para cualquier usuario.
"""
import os
import sys
import json
import shutil
import subprocess
import zipfile

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    python_exe = os.path.join(base_dir, "venv", "Scripts", "python.exe")
    if not os.path.isfile(python_exe):
        python_exe = sys.executable

    print("[1/4] Compilando con PyInstaller usando gameflow.spec...")
    cmd = [python_exe, "-m", "PyInstaller", "--clean", "-y", "gameflow.spec"]
    ret = subprocess.call(cmd)
    if ret != 0:
        print(f"Error en la compilación de PyInstaller (código {ret})")
        sys.exit(ret)

    dist_app = os.path.join(base_dir, "dist", "GameFlow Launcher")
    if not os.path.isdir(dist_app):
        print(f"Error: No se encontró el directorio generado: {dist_app}")
        sys.exit(1)

    print("[2/4] Preparando carpetas de distribución limpias (sin datos personales)...")
    # 1. Copiar assets de la aplicación (iconos, mandos, fuentes, audio)
    assets_src = os.path.join(base_dir, "assets")
    assets_dst = os.path.join(dist_app, "assets")
    if os.path.isdir(assets_src):
        if os.path.exists(assets_dst):
            shutil.rmtree(assets_dst)
        shutil.copytree(assets_src, assets_dst)
        print("  -> Copiada carpeta assets/")

    # 2. Asegurar que covers y wallpapers se creen totalmente vacías
    for folder in ["covers", "wallpapers"]:
        dst = os.path.join(dist_app, folder)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        os.makedirs(dst, exist_ok=True)
        print(f"  -> Creada carpeta limpia y vacía: {folder}/")

    # 3. Generar un games.json inicial limpio (biblioteca vacía)
    dst_games = os.path.join(dist_app, "games.json")
    with open(dst_games, "w", encoding="utf-8") as f:
        f.write("[]\n")
    print("  -> Generado games.json limpio (sin juegos personales)")

    # 4. Generar configuración de gamepad limpia con valores predeterminados
    default_gamepad_config = {
        "selected_controller_id": "xinput_all",
        "selected_controller_name": "🎮 Mandos Xbox / XInput (Inalámbrico o USB)",
        "auto_launch_on_connect": True,
        "close_on_game_launch": True,
        "launch_on_xbox_button": True,
        "start_in_mini_mode": True,
        "auto_fullscreen": False,
        "enable_controller_nav": True,
        "enable_haptics": True,
        "enable_sound_fx": True,
        "start_with_windows": False
    }
    dst_gamepad = os.path.join(dist_app, "gamepad_config.json")
    with open(dst_gamepad, "w", encoding="utf-8") as f:
        json.dump(default_gamepad_config, f, indent=4)
    print("  -> Generado gamepad_config.json con valores estándar")

    # 5. Limpieza de archivos de log, temporales o cachés residuales en dist_app
    for root, dirs, files in os.walk(dist_app):
        for f in files:
            if f.endswith((".log", ".tmp", ".bak")) or f.startswith(".perm_test"):
                try:
                    os.remove(os.path.join(root, f))
                except Exception:
                    pass

    print("[3/4] Creando paquete comprimido portable (.zip)...")
    zip_path = os.path.join(base_dir, "dist", "GameFlow_Launcher_Portable.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(dist_app):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, os.path.join(base_dir, "dist"))
                zf.write(abs_path, rel_path)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"[4/4] ¡COMPILACIÓN COMPLETADA CON ÉXITO!")
    print(f"  Carpeta ejecutable: {dist_app}")
    print(f"  Archivo para distribución/amigos: {zip_path} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    main()
