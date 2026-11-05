"""
Script de sincronizacion de juegos desde GameFlow (jugador) hacia Lanzador (desarrollo).
Copia games.json, covers/ y wallpapers/ para que el entorno de desarrollo tenga
la misma biblioteca real de juegos para probar las nuevas funciones.
"""
import os
import sys
import shutil

BASE_DEV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYER_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(BASE_DEV_DIR), "GameFlow"))

def sync_from_player():
    print("=" * 60)
    print(">> SINCRONIZANDO JUEGOS DESDE TU APP HACIA DESARROLLO")
    print("=" * 60)
    print(f"  Desde (App de juego): {PLAYER_APP_DIR}")
    print(f"  Hacia (Desarrollo):   {BASE_DEV_DIR}")

    player_games = os.path.join(PLAYER_APP_DIR, "games.json")
    if not os.path.isfile(player_games):
        print(f"[ERROR] No se encontro {player_games}. Inicia primero tu app de juego.")
        return False

    dev_games = os.path.join(BASE_DEV_DIR, "games.json")
    shutil.copy2(player_games, dev_games)
    print("  [OK] games.json copiado al entorno de desarrollo.")

    player_covers = os.path.join(PLAYER_APP_DIR, "covers")
    dev_covers = os.path.join(BASE_DEV_DIR, "covers")
    os.makedirs(dev_covers, exist_ok=True)
    cov_count = 0
    if os.path.isdir(player_covers):
        for f in os.listdir(player_covers):
            src_f = os.path.join(player_covers, f)
            dst_f = os.path.join(dev_covers, f)
            if os.path.isfile(src_f) and not os.path.exists(dst_f):
                shutil.copy2(src_f, dst_f)
                cov_count += 1
    print(f"  [OK] {cov_count} caratula(s) nueva(s) sincronizada(s).")

    player_wallpapers = os.path.join(PLAYER_APP_DIR, "wallpapers")
    dev_wallpapers = os.path.join(BASE_DEV_DIR, "wallpapers")
    os.makedirs(dev_wallpapers, exist_ok=True)
    wp_count = 0
    if os.path.isdir(player_wallpapers):
        for f in os.listdir(player_wallpapers):
            src_f = os.path.join(player_wallpapers, f)
            dst_f = os.path.join(dev_wallpapers, f)
            if os.path.isfile(src_f) and not os.path.exists(dst_f):
                shutil.copy2(src_f, dst_f)
                wp_count += 1
    print(f"  [OK] {wp_count} wallpaper(s) nuevo(s) sincronizado(s).")

    player_gp = os.path.join(PLAYER_APP_DIR, "gamepad_config.json")
    dev_gp = os.path.join(BASE_DEV_DIR, "gamepad_config.json")
    if os.path.isfile(player_gp):
        shutil.copy2(player_gp, dev_gp)
        print("  [OK] gamepad_config.json sincronizado.")

    print("\n" + "=" * 60)
    print("[OK] SINCRONIZACION COMPLETADA CON EXITO!")
    print("  Tu entorno de desarrollo tiene ahora la misma biblioteca que tu app.")
    print("=" * 60)
    return True

if __name__ == "__main__":
    sync_from_player()
