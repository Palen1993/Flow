"""
GameFlow - Servicio de Sincronización de Partidas en la Nube (Cloud Save Sync)
==============================================================================
Módulo encargado de la sincronización automática y manual de copias de seguridad (.zip)
con proveedores de almacenamiento en la nube:
1. Carpetas locales sincronizadas:
   * Microsoft OneDrive (%USERPROFILE%/OneDrive)
   * Google Drive (Unidades virtuales G:, H: o %USERPROFILE%/Google Drive)
   * Dropbox (%USERPROFILE%/Dropbox)
   * Carpetas personalizadas / Recursos compartidos en red (NAS, Samba, Synology)
2. Servidores WebDAV estándar (Nextcloud, ownCloud, Box, servidores auto-alojados):
   * Protocolo WebDAV nativo vía urllib (PROPFIND, MKCOL, PUT, GET, DELETE)
   * Cero dependencias externas adicionales (100% biblioteca estándar de Python)
3. Sincronización desacoplada y asíncrona:
   * Subida automática en segundo plano tras crear copias de seguridad locales
   * Listado y descarga de partidas guardadas en la nube hacia la consola/PC
   * Historial y registro de archivos sincronizados
"""

import os
import sys
import json
import time
import shutil
import base64
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Callable

try:
    from core.logger import get_logger
    logger = get_logger("CloudSyncService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.CloudSyncService")

from core.config import get_storage_dir, sanitize_game_filename
from core.save_backup_service import get_game_backup_directory, format_bytes_size


CLOUD_SYNC_CONFIG_FILE = os.path.join(get_storage_dir(), "cloud_sync.json")

# Proveedores compatibles
PROVIDER_ONEDRIVE = "onedrive"
PROVIDER_GDRIVE = "gdrive"
PROVIDER_DROPBOX = "dropbox"
PROVIDER_LOCAL_FOLDER = "local_folder"
PROVIDER_WEBDAV = "webdav"

PROVIDER_NAMES: Dict[str, str] = {
    PROVIDER_ONEDRIVE: "Microsoft OneDrive",
    PROVIDER_GDRIVE: "Google Drive",
    PROVIDER_DROPBOX: "Dropbox",
    PROVIDER_LOCAL_FOLDER: "Carpeta en la Nube / NAS",
    PROVIDER_WEBDAV: "Nextcloud / WebDAV"
}

PROVIDER_ICONS: Dict[str, str] = {
    PROVIDER_ONEDRIVE: "🏢",
    PROVIDER_GDRIVE: "📁",
    PROVIDER_DROPBOX: "📦",
    PROVIDER_LOCAL_FOLDER: "💾",
    PROVIDER_WEBDAV: "🌐"
}

_CONFIG_LOCK = threading.Lock()


# -----------------------------------------------------------------------------
# Detección Automática de Proveedores Locales en el Sistema
# -----------------------------------------------------------------------------
def detect_local_cloud_providers() -> List[Dict[str, Any]]:
    """
    Detecta automáticamente las carpetas de sincronización locales presentes en el equipo:
    OneDrive, Google Drive, Dropbox y carpetas de usuario estándar.
    """
    detected: List[Dict[str, Any]] = []
    userprofile = os.environ.get("USERPROFILE") or os.path.expanduser("~")

    # 1. Microsoft OneDrive
    onedrive_candidates = [
        os.environ.get("OneDrive"),
        os.environ.get("OneDriveConsumer"),
        os.environ.get("OneDriveCommercial"),
        os.path.join(userprofile, "OneDrive"),
    ]
    for cand in onedrive_candidates:
        if cand and os.path.isdir(cand):
            detected.append({
                "provider": PROVIDER_ONEDRIVE,
                "name": "Microsoft OneDrive",
                "icon": "🏢",
                "path": os.path.normpath(cand),
                "is_detected": True
            })
            break

    # 2. Google Drive
    gdrive_candidates = [
        r"G:\My Drive",
        r"G:\Mi unidad",
        r"H:\My Drive",
        r"H:\Mi unidad",
        os.path.join(userprofile, "Google Drive"),
        os.path.join(userprofile, "GoogleDrive"),
    ]
    for cand in gdrive_candidates:
        if cand and os.path.isdir(cand):
            detected.append({
                "provider": PROVIDER_GDRIVE,
                "name": "Google Drive",
                "icon": "📁",
                "path": os.path.normpath(cand),
                "is_detected": True
            })
            break

    # 3. Dropbox
    dropbox_candidates = [
        os.path.join(userprofile, "Dropbox"),
    ]
    for cand in dropbox_candidates:
        if cand and os.path.isdir(cand):
            detected.append({
                "provider": PROVIDER_DROPBOX,
                "name": "Dropbox",
                "icon": "📦",
                "path": os.path.normpath(cand),
                "is_detected": True
            })
            break

    return detected


# -----------------------------------------------------------------------------
# Persistencia de Configuración
# -----------------------------------------------------------------------------
def get_default_cloud_config() -> Dict[str, Any]:
    """Genera la estructura por defecto de configuración de Cloud Sync."""
    local_providers = detect_local_cloud_providers()
    default_provider = local_providers[0]["provider"] if local_providers else PROVIDER_LOCAL_FOLDER
    default_path = local_providers[0]["path"] if local_providers else ""

    return {
        "enabled": False,
        "provider": default_provider,
        "local_cloud_path": default_path,
        "subfolder_name": "GameFlow_Saves",
        "webdav_url": "",
        "webdav_user": "",
        "webdav_password": "",
        "auto_sync_on_backup": True,
        "last_sync_time": "",
        "last_sync_status": "none",
        "last_sync_error": "",
        "synced_files": {}  # Dict[zip_name, Dict[str, Any]]
    }


def load_cloud_config() -> Dict[str, Any]:
    """Carga la configuración de Cloud Sync desde el disco de forma atómica."""
    with _CONFIG_LOCK:
        defaults = get_default_cloud_config()
        if not os.path.isfile(CLOUD_SYNC_CONFIG_FILE):
            return defaults

        try:
            with open(CLOUD_SYNC_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    defaults.update(saved)
            return defaults
        except Exception as e:
            logger.warning(f"Error cargando {CLOUD_SYNC_CONFIG_FILE}: {e}")
            return defaults


def save_cloud_config(config_data: Dict[str, Any]) -> bool:
    """Guarda la configuración de Cloud Sync atómicamente."""
    with _CONFIG_LOCK:
        try:
            tmp_path = CLOUD_SYNC_CONFIG_FILE + f".tmp_{os.getpid()}_{int(time.time()*1000)}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp_path, CLOUD_SYNC_CONFIG_FILE)
            logger.info("Configuración de Cloud Save Sync guardada correctamente.")
            return True
        except Exception as e:
            logger.error(f"Error guardando configuración de Cloud Sync: {e}", exc_info=True)
            return False


def is_cloud_sync_enabled() -> bool:
    """Indica si la sincronización en la nube está activa y configurada."""
    cfg = load_cloud_config()
    if not cfg.get("enabled", False):
        return False
    prov = cfg.get("provider")
    if prov in (PROVIDER_ONEDRIVE, PROVIDER_GDRIVE, PROVIDER_DROPBOX, PROVIDER_LOCAL_FOLDER):
        p = cfg.get("local_cloud_path")
        return bool(p and os.path.isdir(p))
    elif prov == PROVIDER_WEBDAV:
        return bool(cfg.get("webdav_url"))
    return False


# -----------------------------------------------------------------------------
# Cliente WebDAV Nativo (Nextcloud / ownCloud / Genérico)
# -----------------------------------------------------------------------------
class WebDAVClient:
    """
    Cliente WebDAV ligero y determinista utilizando únicamente la biblioteca estándar.
    Implementa PROPFIND, MKCOL, PUT, GET y DELETE compatible con Nextcloud.
    """

    def __init__(self, base_url: str, username: str = "", password: str = "", timeout: int = 15):
        self.base_url = (base_url or "").rstrip("/")
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout

    def _get_auth_header(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "GameFlow-Launcher-CloudSync/1.0"
        }
        if self.username or self.password:
            raw_cred = f"{self.username}:{self.password}".encode("utf-8")
            b64_cred = base64.b64encode(raw_cred).decode("ascii")
            headers["Authorization"] = f"Basic {b64_cred}"
        return headers

    def _build_url(self, relative_path: str) -> str:
        rel = relative_path.lstrip("/")
        if not rel:
            return self.base_url
        return f"{self.base_url}/{urllib.parse.quote(rel)}"

    def test_connection(self) -> Tuple[bool, str]:
        """Verifica la conectividad y autenticación con el servidor WebDAV."""
        if not self.base_url:
            return False, "La URL del servidor WebDAV está vacía."

        headers = self._get_auth_header()
        headers["Depth"] = "0"
        url = self.base_url

        try:
            req = urllib.request.Request(url, headers=headers, method="PROPFIND")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                code = resp.getcode()
                if code in (200, 207):
                    return True, "Conexión WebDAV exitosa y credenciales validadas."
                return False, f"Respuesta inesperada del servidor: HTTP {code}"
        except urllib.error.HTTPError as he:
            if he.code in (401, 403):
                return False, f"Error de autenticación WebDAV (HTTP {he.code}): Usuario o contraseña incorrectos."
            elif he.code in (404, 405):
                # Intentar método OPTIONS si PROPFIND devolvió 405
                try:
                    req_opt = urllib.request.Request(url, headers=self._get_auth_header(), method="OPTIONS")
                    with urllib.request.urlopen(req_opt, timeout=self.timeout) as resp_opt:
                        if resp_opt.getcode() in (200, 204):
                            return True, "Servidor WebDAV alcanzado correctamente (OPTIONS)."
                except Exception:
                    pass
                return False, f"Servidor WebDAV devolvió código HTTP {he.code}."
            return False, f"Error HTTP {he.code}: {he.reason}"
        except Exception as e:
            return False, f"Error de red WebDAV: {str(e)}"

    def ensure_directory_tree(self, relative_dir_path: str) -> bool:
        """Crea la estructura de carpetas remota en WebDAV mediante peticiones MKCOL sucesivas."""
        parts = [p for p in relative_dir_path.strip("/").split("/") if p]
        curr = ""
        headers = self._get_auth_header()

        for p in parts:
            curr = f"{curr}/{p}" if curr else p
            url = self._build_url(curr)
            try:
                req = urllib.request.Request(url, headers=headers, method="MKCOL")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    pass
            except urllib.error.HTTPError as he:
                # 405 o 301 o 409 indican que el recurso ya existe
                if he.code in (405, 301, 409):
                    continue
                elif he.code not in (201, 200):
                    logger.debug(f"MKCOL para {url} devolvió HTTP {he.code}")
            except Exception as e:
                logger.debug(f"Aviso creando carpeta WebDAV '{curr}': {e}")
        return True

    def upload_file(self, local_file_path: str, remote_relative_path: str) -> Tuple[bool, str]:
        """Sube un archivo local al servidor WebDAV usando HTTP PUT."""
        if not os.path.isfile(local_file_path):
            return False, f"Archivo local no encontrado: {local_file_path}"

        parent_dir = os.path.dirname(remote_relative_path).replace("\\", "/")
        if parent_dir:
            self.ensure_directory_tree(parent_dir)

        url = self._build_url(remote_relative_path)
        headers = self._get_auth_header()
        headers["Content-Type"] = "application/zip"
        headers["Content-Length"] = str(os.path.getsize(local_file_path))

        try:
            with open(local_file_path, "rb") as f:
                data = f.read()

            req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
            with urllib.request.urlopen(req, timeout=self.timeout + 30) as resp:
                code = resp.getcode()
                if code in (200, 201, 204):
                    return True, "Subida completada con éxito."
                return False, f"Respuesta inesperada al subir: HTTP {code}"
        except Exception as e:
            logger.error(f"Error subiendo archivo WebDAV a {url}: {e}")
            return False, str(e)

    def download_file(self, remote_relative_path: str, local_dest_path: str) -> Tuple[bool, str]:
        """Descarga un archivo desde WebDAV mediante HTTP GET a un destino local."""
        url = self._build_url(remote_relative_path)
        headers = self._get_auth_header()

        os.makedirs(os.path.dirname(local_dest_path), exist_ok=True)
        tmp_dest = local_dest_path + f".tmp_{int(time.time()*1000)}"

        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout + 30) as resp, open(tmp_dest, "wb") as out_f:
                shutil.copyfileobj(resp, out_f)

            shutil.move(tmp_dest, local_dest_path)
            return True, "Descarga completada con éxito."
        except Exception as e:
            if os.path.isfile(tmp_dest):
                try:
                    os.remove(tmp_dest)
                except Exception:
                    pass
            logger.error(f"Error descargando archivo WebDAV desde {url}: {e}")
            return False, str(e)

    def list_files(self, remote_relative_dir: str) -> List[Dict[str, Any]]:
        """Lista archivos .zip en una carpeta remota de WebDAV utilizando PROPFIND."""
        url = self._build_url(remote_relative_dir)
        headers = self._get_auth_header()
        headers["Depth"] = "1"
        headers["Content-Type"] = "application/xml"

        # XML de consulta estándar PROPFIND
        propfind_xml = (
            '<?xml version="1.0" encoding="utf-8" ?>\n'
            '<d:propfind xmlns:d="DAV:">\n'
            '  <d:prop>\n'
            '    <d:displayname/>\n'
            '    <d:getcontentlength/>\n'
            '    <d:getlastmodified/>\n'
            '    <d:resourcetype/>\n'
            '  </d:prop>\n'
            '</d:propfind>'
        ).encode("utf-8")

        files: List[Dict[str, Any]] = []

        try:
            req = urllib.request.Request(url, data=propfind_xml, headers=headers, method="PROPFIND")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                xml_content = resp.read()

            root = ET.fromstring(xml_content)
            # Manejar namespaces XML DAV:
            ns = {"d": "DAV:"}

            for resp_node in root.findall("d:response", ns):
                href_node = resp_node.find("d:href", ns)
                if href_node is None or not href_node.text:
                    continue

                href_str = urllib.parse.unquote(href_node.text.rstrip("/"))
                fname = os.path.basename(href_str)

                # Ignorar la propia carpeta consultada y archivos que no sean .zip
                if not fname or not fname.lower().endswith(".zip"):
                    continue

                propstat = resp_node.find("d:propstat/d:prop", ns)
                size_bytes = 0
                mtime_str = ""

                if propstat is not None:
                    len_node = propstat.find("d:getcontentlength", ns)
                    if len_node is not None and len_node.text:
                        try:
                            size_bytes = int(len_node.text)
                        except ValueError:
                            pass
                    mod_node = propstat.find("d:getlastmodified", ns)
                    if mod_node is not None and mod_node.text:
                        mtime_str = mod_node.text

                files.append({
                    "name": fname,
                    "remote_path": f"{remote_relative_dir.strip('/')}/{fname}",
                    "size_bytes": size_bytes,
                    "size_formatted": format_bytes_size(size_bytes),
                    "mtime_str": mtime_str
                })
        except Exception as e:
            logger.debug(f"Aviso listando archivos WebDAV en {url}: {e}")

        return files


# -----------------------------------------------------------------------------
# Lógica Unificada de Almacenamiento en la Nube (Local Folder y WebDAV)
# -----------------------------------------------------------------------------
def get_effective_cloud_target_for_game(game: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Calcula las rutas de destino para el juego en el proveedor activo."""
    cfg = config or load_cloud_config()
    provider = cfg.get("provider", PROVIDER_LOCAL_FOLDER)
    safe_name = sanitize_game_filename(game.get("name", "game"))
    subfolder = cfg.get("subfolder_name", "GameFlow_Saves")

    if provider in (PROVIDER_ONEDRIVE, PROVIDER_GDRIVE, PROVIDER_DROPBOX, PROVIDER_LOCAL_FOLDER):
        base_dir = cfg.get("local_cloud_path") or ""
        game_cloud_dir = os.path.join(base_dir, subfolder, safe_name) if base_dir else ""
        return {
            "provider": provider,
            "type": "local_folder",
            "base_dir": base_dir,
            "game_cloud_dir": game_cloud_dir,
            "subfolder": subfolder,
            "safe_name": safe_name
        }
    elif provider == PROVIDER_WEBDAV:
        relative_dir = f"{subfolder}/{safe_name}"
        return {
            "provider": provider,
            "type": "webdav",
            "webdav_url": cfg.get("webdav_url", ""),
            "webdav_user": cfg.get("webdav_user", ""),
            "webdav_password": cfg.get("webdav_password", ""),
            "relative_dir": relative_dir,
            "safe_name": safe_name
        }

    return {"provider": "none", "type": "none"}


def test_cloud_connection(config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """Prueba la disponibilidad y validez del proveedor configurado."""
    cfg = config or load_cloud_config()
    provider = cfg.get("provider", PROVIDER_LOCAL_FOLDER)

    if provider in (PROVIDER_ONEDRIVE, PROVIDER_GDRIVE, PROVIDER_DROPBOX, PROVIDER_LOCAL_FOLDER):
        path = cfg.get("local_cloud_path", "")
        if not path:
            return False, "No se ha seleccionado ninguna carpeta de sincronización local."
        if not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                return False, f"La carpeta no existe y no pudo ser creada: {e}"

        # Probar permiso de escritura creando un archivo temporal de prueba
        test_file = os.path.join(path, f".gameflow_test_{os.getpid()}.tmp")
        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("gameflow_sync_test")
            os.remove(test_file)
            p_name = PROVIDER_NAMES.get(provider, "Carpeta Local")
            return True, f"Acceso correcto y permisos de escritura verificados en {p_name}."
        except Exception as e:
            return False, f"Error de permisos de escritura en la carpeta: {e}"

    elif provider == PROVIDER_WEBDAV:
        url = cfg.get("webdav_url", "")
        user = cfg.get("webdav_user", "")
        pwd = cfg.get("webdav_password", "")
        client = WebDAVClient(url, user, pwd)
        return client.test_connection()

    return False, "Proveedor de nube no reconocido o desactivado."


def upload_backup_to_cloud(game: Dict[str, Any], zip_path: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Sube un archivo de copia de seguridad local al destino en la nube configurado.
    Actualiza el registro de archivos sincronizados en la configuración.
    """
    if not os.path.isfile(zip_path):
        return {"success": False, "error": f"Archivo de backup no existe: {zip_path}"}

    cfg = config or load_cloud_config()
    if not cfg.get("enabled", False):
        return {"success": False, "error": "La sincronización en la nube está desactivada."}

    target_info = get_effective_cloud_target_for_game(game, cfg)
    target_type = target_info.get("type")
    zip_name = os.path.basename(zip_path)
    file_size = os.path.getsize(zip_path)

    try:
        if target_type == "local_folder":
            game_dir = target_info.get("game_cloud_dir")
            if not game_dir:
                return {"success": False, "error": "Ruta de carpeta en la nube no configurada."}

            os.makedirs(game_dir, exist_ok=True)
            dest_file = os.path.join(game_dir, zip_name)
            shutil.copy2(zip_path, dest_file)
            remote_ref = dest_file
            success = True
            msg = "Copiado a carpeta en la nube."

        elif target_type == "webdav":
            client = WebDAVClient(
                target_info["webdav_url"],
                target_info["webdav_user"],
                target_info["webdav_password"]
            )
            rel_path = f"{target_info['relative_dir']}/{zip_name}"
            success, msg = client.upload_file(zip_path, rel_path)
            remote_ref = rel_path
        else:
            return {"success": False, "error": "Tipo de proveedor no compatible."}

        if success:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            synced_map = cfg.setdefault("synced_files", {})
            synced_map[zip_name] = {
                "game": game.get("name", "Juego"),
                "synced_at": now_str,
                "size_bytes": file_size,
                "remote_ref": remote_ref,
                "provider": target_info.get("provider")
            }
            cfg["last_sync_time"] = now_str
            cfg["last_sync_status"] = "success"
            cfg["last_sync_error"] = ""
            save_cloud_config(cfg)
            logger.info(f"Backup '{zip_name}' sincronizado con éxito en la nube ({target_info.get('provider')}).")

            return {
                "success": True,
                "zip_name": zip_name,
                "remote_ref": remote_ref,
                "synced_at": now_str
            }
        else:
            cfg["last_sync_status"] = "error"
            cfg["last_sync_error"] = msg
            save_cloud_config(cfg)
            return {"success": False, "error": msg}

    except Exception as e:
        logger.error(f"Excepción subiendo backup a la nube: {e}", exc_info=True)
        cfg["last_sync_status"] = "error"
        cfg["last_sync_error"] = str(e)
        save_cloud_config(cfg)
        return {"success": False, "error": str(e)}


def list_cloud_backups(game: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Lista las copias de seguridad de este juego que existen actualmente en el almacenamiento en la nube."""
    cfg = config or load_cloud_config()
    if not cfg.get("enabled", False):
        return []

    target_info = get_effective_cloud_target_for_game(game, cfg)
    target_type = target_info.get("type")
    results: List[Dict[str, Any]] = []

    try:
        if target_type == "local_folder":
            g_dir = target_info.get("game_cloud_dir")
            if g_dir and os.path.isdir(g_dir):
                for f in os.listdir(g_dir):
                    if f.lower().endswith(".zip"):
                        fp = os.path.join(g_dir, f)
                        try:
                            st = os.stat(fp)
                            results.append({
                                "name": f,
                                "path": fp,
                                "size_bytes": st.st_size,
                                "size_formatted": format_bytes_size(st.st_size),
                                "mtime": st.st_mtime,
                                "date_formatted": datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M"),
                                "is_remote": False
                            })
                        except Exception:
                            pass

        elif target_type == "webdav":
            client = WebDAVClient(
                target_info["webdav_url"],
                target_info["webdav_user"],
                target_info["webdav_password"]
            )
            files = client.list_files(target_info["relative_dir"])
            for item in files:
                results.append({
                    "name": item["name"],
                    "path": item["remote_path"],
                    "size_bytes": item["size_bytes"],
                    "size_formatted": item["size_formatted"],
                    "mtime": 0,
                    "date_formatted": item.get("mtime_str", "En la nube"),
                    "is_remote": True
                })

        results.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    except Exception as e:
        logger.warning(f"Error listando backups en la nube para '{game.get('name')}': {e}")

    return results


def download_cloud_backup(
    game: Dict[str, Any],
    cloud_item: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None
) -> Tuple[bool, str]:
    """
    Descarga una copia de seguridad desde la nube hacia la carpeta local de copias de seguridad de GameFlow.
    """
    cfg = config or load_cloud_config()
    target_info = get_effective_cloud_target_for_game(game, cfg)
    local_backup_dir = get_game_backup_directory(game)
    os.makedirs(local_backup_dir, exist_ok=True)

    zip_name = cloud_item.get("name")
    if not zip_name:
        return False, "Nombre de archivo no especificado."

    dest_local_path = os.path.join(local_backup_dir, zip_name)

    try:
        if target_info.get("type") == "local_folder":
            src_path = cloud_item.get("path")
            if not src_path or not os.path.isfile(src_path):
                return False, f"Archivo de origen en la nube no encontrado: {src_path}"
            shutil.copy2(src_path, dest_local_path)
            return True, dest_local_path

        elif target_info.get("type") == "webdav":
            client = WebDAVClient(
                target_info["webdav_url"],
                target_info["webdav_user"],
                target_info["webdav_password"]
            )
            remote_path = cloud_item.get("path") or f"{target_info['relative_dir']}/{zip_name}"
            success, msg = client.download_file(remote_path, dest_local_path)
            if success:
                return True, dest_local_path
            return False, msg

        return False, "Proveedor no configurado."
    except Exception as e:
        logger.error(f"Error descargando backup de la nube: {e}", exc_info=True)
        return False, str(e)


def sync_game_backups(game: Dict[str, Any], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Sincroniza todos los backups locales del juego que aún no hayan sido subidos a la nube.
    """
    cfg = config or load_cloud_config()
    if not cfg.get("enabled", False):
        return {"success": False, "uploaded": 0, "error": "Cloud Sync desactivado"}

    from core.save_backup_service import list_game_backups
    local_backups = list_game_backups(game)
    synced_map = cfg.get("synced_files", {})

    uploaded_count = 0
    errors: List[str] = []

    for b in local_backups:
        z_name = b["name"]
        # Si aún no está marcado como sincronizado, subirlo
        if z_name not in synced_map:
            res = upload_backup_to_cloud(game, b["path"], cfg)
            if res.get("success"):
                uploaded_count += 1
            else:
                errors.append(f"{z_name}: {res.get('error')}")

    return {
        "success": len(errors) == 0,
        "uploaded": uploaded_count,
        "total_local": len(local_backups),
        "errors": errors
    }


def sync_all_games(games: List[Dict[str, Any]], progress_cb: Optional[Callable[[int, int, str], None]] = None) -> Dict[str, Any]:
    """
    Sincroniza todos los backups de todos los juegos de la biblioteca con el almacenamiento en la nube.
    """
    cfg = load_cloud_config()
    if not cfg.get("enabled", False):
        return {"success": False, "error": "Cloud Sync no está activado."}

    total = len(games)
    total_uploaded = 0
    all_errors = []

    for idx, g in enumerate(games):
        if progress_cb:
            progress_cb(idx + 1, total, g.get("name", "Juego"))
        res = sync_game_backups(g, cfg)
        total_uploaded += res.get("uploaded", 0)
        if res.get("errors"):
            all_errors.extend(res["errors"])

    return {
        "success": len(all_errors) == 0,
        "total_games": total,
        "total_uploaded": total_uploaded,
        "errors": all_errors
    }


def maybe_auto_sync_backup(game: Dict[str, Any], zip_path: str) -> None:
    """
    Función gancho (hook) invocada al crear un backup local. Si la auto-sincronización está activa,
    despacha la subida a un hilo en segundo plano de forma no bloqueante.
    """
    try:
        cfg = load_cloud_config()
        if cfg.get("enabled", False) and cfg.get("auto_sync_on_backup", True):
            def _async_worker():
                try:
                    upload_backup_to_cloud(game, zip_path, cfg)
                except Exception as e:
                    logger.warning(f"Error en worker asíncrono de auto-sync a la nube: {e}")

            threading.Thread(target=_async_worker, daemon=True).start()
    except Exception as e:
        logger.debug(f"Aviso en verificación de auto-sync en la nube: {e}")
