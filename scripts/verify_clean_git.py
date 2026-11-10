"""
Verificador de seguridad para Git.
Garantiza que ningún archivo de datos personales (games.json con juegos, carátulas o wallpapers personales)
pueda ser introducido en un commit.
"""
import sys
import subprocess

def main():
    res = subprocess.run(
        ["git", "diff", "--cached", "--diff-filter=ACMR", "--name-only"],
        capture_output=True, text=True, check=True
    )
    staged_files = res.stdout.strip().splitlines()

    blocked = []
    for f in staged_files:
        f_norm = f.strip().replace("\\", "/").lower()
        if f_norm in ("games.json", "games.json.bak", "gamepad_config.json", ".portable"):
            blocked.append(f)
        elif f_norm.startswith("covers/") and not f_norm.endswith(".gitkeep"):
            blocked.append(f)
        elif f_norm.startswith("wallpapers/") and not f_norm.endswith(".gitkeep"):
            blocked.append(f)
        elif f_norm.endswith((".log", ".bak", ".lnk", ".tmp")):
            blocked.append(f)

    if blocked:
        print("\n" + "=" * 70)
        print("❌ ERROR DE SEGURIDAD GIT: Intento de subir datos personales bloqueado")
        print("=" * 70)
        print("Se ha detectado que intentas commitear archivos de tu biblioteca personal:")
        for b in blocked:
            print(f"  - {b}")
        print("\nTu coleccion de juegos debe mantenerse privada en tu equipo.")
        print("Usa 'git reset HEAD <archivo>' para desmarcarlo antes de commitear.")
        print("=" * 70 + "\n")
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()
