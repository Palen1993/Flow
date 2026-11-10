"""
GameFlow - Servicio de Copias de Seguridad de Partidas Guardadas (Save Backup)
==============================================================================
Módulo encargado de:
- Detección inteligente de carpetas de guardado de videojuegos en Windows:
  * %USERPROFILE%/Saved Games
  * %LOCALAPPDATA% (incluyendo estructuras Unreal Engine Saved/SaveGames)
  * %APPDATA% (Roaming)
  * %USERPROFILE%/AppData/LocalLow (juegos Unity e indie)
  * %USERPROFILE%/Documents/My Games y %USERPROFILE%/Documents
  * Subcarpetas locales del juego (saves, SaveData, userdata)
- Creación de copias de seguridad automáticas y manuales comprimidas en .zip con manifest de metadatos.
- Política de retención de copias (mantiene las últimas N copias por juego).
- Restauración segura con copia de seguridad previa de protección (pre-restore safety backup).
- Ejecución desacoplada y no bloqueante en segundo plano al terminar partidas.
"""

import os
import sys
import time
import json
import zipfile
import shutil
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

try:
    from core.logger import get_logger
    logger = get_logger("SaveBackupService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.SaveBackupService")

from core.config import BACKUPS_DIR, sanitize_game_filename, update_game_fields_atomic


def format_bytes_size(size_bytes: int) -> str:
    """Formatea bytes a KB, MB o GB legible."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024.0:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024.0 * 1024.0):.1f} MB"
    else:
        return f"{size_bytes / (1024.0 * 1024.0 * 1024.0):.2f} GB"


def get_known_save_roots() -> List[Tuple[str, str]]:
    """Devuelve las ubicaciones raíz de guardado estándar de Windows."""
    roots: List[Tuple[str, str]] = []

    userprofile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    localappdata = os.environ.get("LOCALAPPDATA") or os.path.join(userprofile, "AppData", "Local")
    appdata = os.environ.get("APPDATA") or os.path.join(userprofile, "AppData", "Roaming")
    locallow = os.path.join(userprofile, "AppData", "LocalLow")

    # 1. Saved Games (%USERPROFILE%/Saved Games)
    saved_games = os.path.join(userprofile, "Saved Games")
    if os.path.isdir(saved_games):
        roots.append(("Saved Games", saved_games))

    # 2. LocalAppData (%LOCALAPPDATA%)
    if os.path.isdir(localappdata):
        roots.append(("AppData Local", localappdata))

    # 3. LocalLow (%USERPROFILE%/AppData/LocalLow) - Estándar en Unity / indies
    if os.path.isdir(locallow):
        roots.append(("AppData LocalLow", locallow))

    # 4. Roaming (%APPDATA%)
    if os.path.isdir(appdata):
        roots.append(("AppData Roaming", appdata))

    # 5. Documents / My Games
    my_games = os.path.join(userprofile, "Documents", "My Games")
    if os.path.isdir(my_games):
        roots.append(("Documentos / My Games", my_games))

    # 6. Documents
    docs = os.path.join(userprofile, "Documents")
    if os.path.isdir(docs):
        roots.append(("Documentos", docs))

    # 7. Steam UserData si existe
    steam_roots = [
        r"C:\Program Files (x86)\Steam\userdata",
        r"C:\Program Files\Steam\userdata",
        os.path.join(userprofile, "Steam", "userdata")
    ]
    for sr in steam_roots:
        if os.path.isdir(sr):
            roots.append(("Steam UserData", sr))
            break

    return roots


def _generate_name_variants(name: str) -> List[str]:
    """Genera variaciones de nombre de juego para maximizar el emparejamiento de carpetas."""
    if not name:
        return []
    variants = [name.strip()]

    # Sin puntuación extra
    clean_punc = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip()
    if clean_punc and clean_punc not in variants:
        variants.append(clean_punc)

    # Sin espacios (ej. HollowKnight)
    nospace = "".join(c for c in name if c.isalnum())
    if nospace and nospace not in variants:
        variants.append(nospace)

    # Con guiones bajos (ej. Hollow_Knight)
    underscore = "_".join(clean_punc.split())
    if underscore and underscore not in variants:
        variants.append(underscore)

    return variants


def _get_dir_summary(path: str) -> Tuple[int, int, float]:
    """Calcula la cantidad de archivos, tamaño total en bytes y mtime más reciente de una carpeta."""
    total_files = 0
    total_bytes = 0
    latest_mtime = 0.0

    try:
        for root, _, files in os.walk(path):
            for f in files:
                fp = os.path.join(root, f)
                try:
                    st = os.stat(fp)
                    total_files += 1
                    total_bytes += st.st_size
                    if st.st_mtime > latest_mtime:
                        latest_mtime = st.st_mtime
                except Exception:
                    pass
    except Exception:
        pass

    return total_files, total_bytes, latest_mtime


def detect_game_save_candidates(game: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Escanea las ubicaciones estándar del sistema en busca de posibles carpetas de guardado
    del juego. Devuelve una lista ordenada por relevancia (archivos presentes, fecha de modificación).
    """
    candidates: List[Dict[str, Any]] = []
    seen_paths = set()

    # 1. Si el juego ya tiene una ruta personalizada configurada y existe
    configured_path = game.get("save_path")
    if configured_path and os.path.isdir(configured_path):
        f_count, b_size, mtime = _get_dir_summary(configured_path)
        candidates.append({
            "path": configured_path,
            "label": "Configurada Manualmente",
            "files_count": f_count,
            "size_bytes": b_size,
            "last_modified": mtime,
            "is_configured": True
        })
        seen_paths.add(os.path.normcase(os.path.abspath(configured_path)))

    game_name = game.get("name", "")
    variants = _generate_name_variants(game_name)

    game_path = game.get("path", "")
    exe_dir = os.path.dirname(game_path) if game_path else ""
    exe_base = os.path.splitext(os.path.basename(game_path))[0] if game_path else ""
    if exe_base and exe_base not in variants:
        variants.append(exe_base)

    # 2. Búsqueda en raíces de guardado de Windows
    for root_label, root_dir in get_known_save_roots():
        if not os.path.isdir(root_dir):
            continue

        for var in variants:
            var_l = var.lower()

            # A. Coincidencia directa <root>/<var>
            cand_direct = os.path.join(root_dir, var)
            norm_direct = os.path.normcase(os.path.abspath(cand_direct))
            if norm_direct not in seen_paths and os.path.isdir(cand_direct):
                f_count, b_size, mtime = _get_dir_summary(cand_direct)
                if f_count > 0:
                    candidates.append({
                        "path": cand_direct,
                        "label": f"{root_label} ({var})",
                        "files_count": f_count,
                        "size_bytes": b_size,
                        "last_modified": mtime,
                        "is_configured": False
                    })
                    seen_paths.add(norm_direct)

            # B. Estructura Unreal Engine: <root>/<var>/Saved/SaveGames
            cand_unreal = os.path.join(root_dir, var, "Saved", "SaveGames")
            norm_unreal = os.path.normcase(os.path.abspath(cand_unreal))
            if norm_unreal not in seen_paths and os.path.isdir(cand_unreal):
                f_count, b_size, mtime = _get_dir_summary(cand_unreal)
                if f_count > 0:
                    candidates.append({
                        "path": cand_unreal,
                        "label": f"{root_label} Unreal ({var})",
                        "files_count": f_count,
                        "size_bytes": b_size,
                        "last_modified": mtime,
                        "is_configured": False
                    })
                    seen_paths.add(norm_unreal)

            # C. Subcarpetas de desarrolladores (ej. <root>/TeamCherry/HollowKnight)
            try:
                for dev_entry in os.listdir(root_dir):
                    dev_path = os.path.join(root_dir, dev_entry)
                    if os.path.isdir(dev_path):
                        cand_dev = os.path.join(dev_path, var)
                        norm_dev = os.path.normcase(os.path.abspath(cand_dev))
                        if norm_dev not in seen_paths and os.path.isdir(cand_dev):
                            f_count, b_size, mtime = _get_dir_summary(cand_dev)
                            if f_count > 0:
                                candidates.append({
                                    "path": cand_dev,
                                    "label": f"{root_label} ({dev_entry}/{var})",
                                    "files_count": f_count,
                                    "size_bytes": b_size,
                                    "last_modified": mtime,
                                    "is_configured": False
                                })
                                seen_paths.add(norm_dev)
            except Exception:
                pass

    # 3. Subcarpetas locales de la instalación del juego
    if exe_dir and os.path.isdir(exe_dir):
        local_subfolders = [
            "saves", "save", "SaveData", "savedata", "Save", "Saves",
            "userdata", "profile", "profiles"
        ]
        for sub in local_subfolders:
            cand_loc = os.path.join(exe_dir, sub)
            norm_loc = os.path.normcase(os.path.abspath(cand_loc))
            if norm_loc not in seen_paths and os.path.isdir(cand_loc):
                f_count, b_size, mtime = _get_dir_summary(cand_loc)
                if f_count > 0:
                    candidates.append({
                        "path": cand_loc,
                        "label": f"Instalación del Juego ({sub}/)",
                        "files_count": f_count,
                        "size_bytes": b_size,
                        "last_modified": mtime,
                        "is_configured": False
                    })
                    seen_paths.add(norm_loc)

    # Ordenar candidatos: configurado primero, luego por cantidad de archivos y fecha
    candidates.sort(
        key=lambda c: (
            1 if c.get("is_configured") else 0,
            1 if c.get("files_count", 0) > 0 else 0,
            c.get("last_modified", 0.0),
            c.get("files_count", 0)
        ),
        reverse=True
    )

    return candidates


def get_effective_save_directory(game: Dict[str, Any]) -> Optional[str]:
    """Obtiene la mejor ruta de guardado detectada o configurada para el juego."""
    candidates = detect_game_save_candidates(game)
    if candidates:
        return candidates[0]["path"]
    return None


def get_game_backup_directory(game: Dict[str, Any]) -> str:
    """Devuelve la ruta absoluta del directorio donde se almacenan los .zip de backup del juego."""
    safe_name = sanitize_game_filename(game.get("name", "game"))
    b_dir = os.path.join(BACKUPS_DIR, safe_name)
    os.makedirs(b_dir, exist_ok=True)
    return b_dir


def create_save_backup(
    game: Dict[str, Any],
    save_path: Optional[str] = None,
    comment: str = "Copia manual",
    max_backups: int = 10
) -> Dict[str, Any]:
    """
    Crea un archivo .zip con todos los archivos de guardado y un manifest de metadatos.
    Aplica la política de retención de las últimas max_backups copias.
    """
    source_dir = save_path or get_effective_save_directory(game)
    if not source_dir or not os.path.isdir(source_dir):
        return {
            "success": False,
            "error": "No se detectó la carpeta de guardado del juego."
        }

    b_dir = get_game_backup_directory(game)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = sanitize_game_filename(game.get("name", "game"))
    prefix = "PreRestore" if ("preventivo" in (comment or "").lower() or "safety" in (comment or "").lower()) else "Save"
    zip_name = f"{safe_name}_{prefix}_{timestamp_str}.zip"
    zip_path = os.path.join(b_dir, zip_name)
    counter = 1
    while os.path.exists(zip_path):
        zip_name = f"{safe_name}_{prefix}_{timestamp_str}_{counter}.zip"
        zip_path = os.path.join(b_dir, zip_name)
        counter += 1

    total_files = 0
    total_size = 0

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(source_dir):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, source_dir)
                    try:
                        zf.write(full_p, arcname=rel_p)
                        total_files += 1
                        total_size += os.path.getsize(full_p)
                    except Exception as fe:
                        logger.warning(f"No se pudo empaquetar archivo {full_p}: {fe}")

            # Manifest interno
            manifest = {
                "game_name": game.get("name", "Juego"),
                "source_path": source_dir,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_files": total_files,
                "uncompressed_bytes": total_size,
                "comment": comment
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

        # Enforce retention policy
        _prune_old_backups(b_dir, max_backups)

        # Actualizar metadatos en el juego
        today_formatted = datetime.now().strftime("%Y-%m-%d %H:%M")
        game["last_backup"] = today_formatted
        if not game.get("save_path"):
            game["save_path"] = source_dir

        try:
            update_game_fields_atomic(
                game.get("path") or game.get("name", ""),
                {"last_backup": today_formatted, "save_path": source_dir}
            )
        except Exception:
            pass

        logger.info(f"Copia de seguridad creada para '{game.get('name')}': {zip_name} ({total_files} archivos)")
        return {
            "success": True,
            "zip_path": zip_path,
            "zip_name": zip_name,
            "files_count": total_files,
            "size_bytes": os.path.getsize(zip_path),
            "uncompressed_bytes": total_size,
            "created_at": today_formatted
        }
    except Exception as e:
        logger.error(f"Error creando backup para '{game.get('name')}': {e}", exc_info=True)
        if os.path.isfile(zip_path):
            try:
                os.remove(zip_path)
            except Exception:
                pass
        return {
            "success": False,
            "error": str(e)
        }


def _prune_old_backups(backup_dir: str, max_backups: int):
    """Mantiene como máximo las últimas max_backups copias, eliminando las más antiguas."""
    if max_backups <= 0:
        return
    try:
        zip_files = []
        for f in os.listdir(backup_dir):
            if f.lower().endswith(".zip"):
                fp = os.path.join(backup_dir, f)
                try:
                    zip_files.append((fp, os.path.getmtime(fp)))
                except Exception:
                    pass

        # Ordenar por fecha de más reciente a más antigua
        zip_files.sort(key=lambda x: x[1], reverse=True)
        if len(zip_files) > max_backups:
            for fp, _ in zip_files[max_backups:]:
                try:
                    os.remove(fp)
                    logger.info(f"Backup antiguo eliminado por política de retención: {os.path.basename(fp)}")
                except Exception as ex:
                    logger.warning(f"Error eliminando backup antiguo {fp}: {ex}")
    except Exception as e:
        logger.warning(f"Error aplicando política de retención en {backup_dir}: {e}")


def list_game_backups(game: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Lista todas las copias de seguridad existentes para el juego, ordenadas de más reciente a más antigua."""
    b_dir = get_game_backup_directory(game)
    backups: List[Dict[str, Any]] = []

    if not os.path.isdir(b_dir):
        return backups

    try:
        for f in os.listdir(b_dir):
            if f.lower().endswith(".zip"):
                fp = os.path.join(b_dir, f)
                try:
                    st = os.stat(fp)
                    mtime_dt = datetime.fromtimestamp(st.st_mtime)

                    # Intentar leer manifest
                    comment = "Copia guardada"
                    total_files = 0
                    try:
                        with zipfile.ZipFile(fp, "r") as zf:
                            if "manifest.json" in zf.namelist():
                                m_data = json.loads(zf.read("manifest.json").decode("utf-8"))
                                comment = m_data.get("comment", comment)
                                total_files = int(m_data.get("total_files", 0) or 0)
                            else:
                                total_files = len(zf.namelist())
                    except Exception:
                        pass

                    backups.append({
                        "name": f,
                        "path": fp,
                        "size_bytes": st.st_size,
                        "size_formatted": format_bytes_size(st.st_size),
                        "mtime": st.st_mtime,
                        "date_formatted": mtime_dt.strftime("%d/%m/%Y %H:%M"),
                        "comment": comment,
                        "total_files": total_files
                    })
                except Exception:
                    pass

        backups.sort(key=lambda b: b["mtime"], reverse=True)
    except Exception as e:
        logger.error(f"Error listando backups en {b_dir}: {e}")

    return backups


def restore_save_backup(
    game: Dict[str, Any],
    zip_path: str,
    target_dir: Optional[str] = None,
    create_safety_backup: bool = True
) -> Dict[str, Any]:
    """
    Restaura una copia de seguridad en la carpeta de guardado del juego.
    Por seguridad, crea automáticamente una copia de protección de las partidas actuales antes de sobrescribir.
    """
    if not os.path.isfile(zip_path):
        return {"success": False, "error": f"Archivo de backup no encontrado: {zip_path}"}

    dest_dir = target_dir or get_effective_save_directory(game)
    if not dest_dir:
        return {"success": False, "error": "No se determinó la carpeta de destino para restaurar."}

    # Copia de seguridad preventiva
    safety_info = None
    if create_safety_backup and os.path.isdir(dest_dir):
        try:
            f_count, _, _ = _get_dir_summary(dest_dir)
            if f_count > 0:
                safety_res = create_save_backup(game, save_path=dest_dir, comment="Auto-backup preventivo antes de restaurar")
                if safety_res.get("success"):
                    safety_info = safety_res
        except Exception as se:
            logger.warning(f"Aviso en backup preventivo: {se}")

    os.makedirs(dest_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for item in zf.infolist():
                if item.filename == "manifest.json":
                    continue
                zf.extract(item, dest_dir)

        logger.info(f"Partida restaurada con éxito para '{game.get('name')}' desde {os.path.basename(zip_path)}")
        return {
            "success": True,
            "target_dir": dest_dir,
            "safety_backup": safety_info
        }
    except Exception as e:
        logger.error(f"Error restaurando partida desde {zip_path}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def delete_save_backup(zip_path: str) -> bool:
    """Elimina permanentemente una copia de seguridad específica."""
    try:
        if os.path.isfile(zip_path):
            os.remove(zip_path)
            return True
        return False
    except Exception as e:
        logger.error(f"Error eliminando backup {zip_path}: {e}")
        return False


def run_auto_save_backup_async(game: Dict[str, Any], max_backups: int = 10):
    """Lanza la creación de una copia de seguridad en un hilo secundario sin congelar la interfaz."""
    def _worker():
        try:
            time.sleep(1.0)  # Breve pausa para asegurar que el proceso del juego liberó los archivos
            create_save_backup(game, comment="Copia automática al salir", max_backups=max_backups)
        except Exception as e:
            logger.warning(f"Error en worker de auto backup para '{game.get('name')}': {e}")

    threading.Thread(target=_worker, daemon=True).start()
