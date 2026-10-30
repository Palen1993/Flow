"""
Script de compilación automatizado para GameFlow Launcher.
Genera la suite de ejecutables en dist/GameFlow Launcher y crea un archivo .zip portátil listo para enviar.
"""
import os
import sys
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

    print("[2/4] Copiando carpetas de datos y configuraciones iniciales...")
    # Asegurar que covers, wallpapers y assets existan en dist
    for folder in ["covers", "wallpapers", "assets"]:
        src = os.path.join(base_dir, folder)
        dst = os.path.join(dist_app, folder)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # Copiar games.json y gamepad_config.json si existen
    for f_name in ["games.json", "gamepad_config.json"]:
        src_file = os.path.join(base_dir, f_name)
        dst_file = os.path.join(dist_app, f_name)
        if os.path.isfile(src_file):
            shutil.copy2(src_file, dst_file)
            print(f"  -> Copiado {f_name}")

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
    print(f"  Archivo para tu amigo: {zip_path} ({size_mb:.1f} MB)")

if __name__ == "__main__":
    main()
