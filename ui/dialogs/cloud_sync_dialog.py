"""
GameFlow - Diálogo de Configuración de Sincronización en la Nube (Cloud Save Sync Dialog)
========================================================================================
Diálogo modal Glassmorphism 100% navegable con mando y teclado para:
- Elegir proveedor de nube (OneDrive, Google Drive, Dropbox, Carpeta Local/NAS o Nextcloud/WebDAV).
- Configurar credenciales y rutas de sincronización con autodetección inteligente.
- Probar la conexión en tiempo real con validación de permisos de escritura.
- Sincronizar toda la biblioteca de copias de seguridad de forma asíncrona.
- Activar o desactivar la subida automática al terminar partidas.
"""

import os
import threading
import time
from datetime import datetime
import tkinter as tk
from typing import Dict, Any, Optional, Callable, List
import customtkinter as ctk

from ui.dialogs.base_dialog import BaseGlassDialog
from ui.dialogs.glass_message_box import show_info, show_error
from ui.dialogs.glass_folder_browser import browse_folder
from core.cloud_sync_service import (
    load_cloud_config,
    save_cloud_config,
    detect_local_cloud_providers,
    test_cloud_connection,
    sync_all_games,
    PROVIDER_ONEDRIVE,
    PROVIDER_GDRIVE,
    PROVIDER_DROPBOX,
    PROVIDER_LOCAL_FOLDER,
    PROVIDER_WEBDAV,
    PROVIDER_NAMES,
    PROVIDER_ICONS
)
from core.feedback import feedback_click, trigger_haptic
from ui.theme import (
    COLOR_BG_CARD, COLOR_BG_CARD_SECONDARY, COLOR_BG_DARK,
    COLOR_GLASS_BORDER, COLOR_GLASS_HOVER, COLOR_BORDER_CARD,
    COLOR_CYAN_ACCENT, COLOR_CYAN_BORDER,
    COLOR_IOS_BLUE, COLOR_IOS_BLUE_HOVER, COLOR_IOS_BLUE_BORDER,
    COLOR_BTN_SECONDARY_BG, COLOR_BTN_SECONDARY_HOVER, COLOR_BTN_SECONDARY_BORDER,
    COLOR_STATUS_SUCCESS, COLOR_STATUS_DANGER,
    COLOR_TEXT_MAIN, COLOR_TEXT_WHITE, COLOR_TEXT_BRIGHT, COLOR_TEXT_MUTED,
    COLOR_TEXT_MUTED_LIGHT, COLOR_TEXT_DIM,
    font_button, font_body, font_title
)


class CloudSyncDialog(BaseGlassDialog):
    """
    Diálogo modal Glassmorphism para configurar Cloud Save Sync y gestionar la sincronización.
    """

    def __init__(
        self,
        parent,
        games: Optional[List[Dict[str, Any]]] = None,
        on_sync_completed: Optional[Callable[[], None]] = None
    ):
        super().__init__(
            parent,
            title="Sincronización de Partidas en la Nube",
            width=860,
            height=640,
            corner_radius=22
        )
        self.games = games or getattr(parent, "games", []) or []
        self.on_sync_completed = on_sync_completed

        self.config = load_cloud_config()
        self.detected_providers = detect_local_cloud_providers()

        self.selected_provider = self.config.get("provider", PROVIDER_LOCAL_FOLDER)
        self.sync_in_progress = False

        self._nav_elements: List[ctk.CTkBaseClass] = []
        self._current_nav_idx: int = 0
        self._provider_buttons: Dict[str, ctk.CTkButton] = {}

        self._build_ui()
        self._update_provider_ui()
        self._bind_events()

    _center_window = BaseGlassDialog.center_window

    def _build_ui(self):
        # Tarjeta principal con efecto iOS Liquid Glass
        self.main_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_BG_CARD,
            border_color=COLOR_GLASS_BORDER,
            border_width=1.5,
            corner_radius=22
        )
        self.main_card.pack(fill="both", expand=True, padx=4, pady=4)

        # ---------------- Cabecera ----------------
        self.header_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=50)
        self.header_bar.pack(fill="x", padx=20, pady=(12, 6))

        lbl_icon = ctk.CTkLabel(self.header_bar, text="☁️", font=font_title(24))
        lbl_icon.pack(side="left", padx=(0, 10))

        info_col = ctk.CTkFrame(self.header_bar, fg_color="transparent")
        info_col.pack(side="left", fill="both", expand=True)

        lbl_title = ctk.CTkLabel(
            info_col,
            text="Sincronización de Partidas en la Nube (Cloud Save Sync)",
            font=font_title(16),
            text_color=COLOR_TEXT_MAIN,
            anchor="w"
        )
        lbl_title.pack(anchor="w")

        lbl_sub = ctk.CTkLabel(
            info_col,
            text="Sincroniza automáticamente tus partidas con OneDrive, Google Drive, Dropbox o WebDAV / Nextcloud.",
            font=font_body(11),
            text_color=COLOR_TEXT_MUTED,
            anchor="w"
        )
        lbl_sub.pack(anchor="w")

        # ---------------- Contenedor con Scroll ----------------
        self.scroll_content = ctk.CTkScrollableFrame(
            self.main_card,
            fg_color="transparent",
            corner_radius=12
        )
        self.scroll_content.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # 1. Selector de Proveedor
        lbl_prov_header = ctk.CTkLabel(
            self.scroll_content,
            text="PROVEEDOR DE ALMACENAMIENTO EN LA NUBE",
            font=font_button(11),
            text_color=COLOR_CYAN_ACCENT,
            anchor="w"
        )
        lbl_prov_header.pack(fill="x", pady=(4, 6))

        prov_row = ctk.CTkFrame(self.scroll_content, fg_color="transparent")
        prov_row.pack(fill="x", pady=(0, 12))

        prov_keys = [PROVIDER_ONEDRIVE, PROVIDER_GDRIVE, PROVIDER_DROPBOX, PROVIDER_LOCAL_FOLDER, PROVIDER_WEBDAV]
        for p_key in prov_keys:
            p_name = PROVIDER_NAMES[p_key]
            p_icon = PROVIDER_ICONS[p_key]
            short_name = p_name.replace("Microsoft ", "").replace(" / WebDAV", "")
            btn = ctk.CTkButton(
                prov_row,
                text=f"{p_icon} {short_name}",
                font=font_button(11),
                height=34,
                corner_radius=10,
                fg_color=COLOR_BTN_SECONDARY_BG,
                hover_color=COLOR_BTN_SECONDARY_HOVER,
                border_color=COLOR_BORDER_CARD,
                border_width=1,
                command=lambda k=p_key: self._on_select_provider(k)
            )
            btn.pack(side="left", padx=3, fill="x", expand=True)
            self._provider_buttons[p_key] = btn
            self._nav_elements.append(btn)

        # 2. Tarjeta de Configuración Específica del Proveedor
        self.provider_settings_card = ctk.CTkFrame(
            self.scroll_content,
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1
        )
        self.provider_settings_card.pack(fill="x", pady=(0, 12), ipady=8)

        # Contenedores dinámicos para Carpeta vs WebDAV
        self.folder_settings_frame = ctk.CTkFrame(self.provider_settings_card, fg_color="transparent")
        self.webdav_settings_frame = ctk.CTkFrame(self.provider_settings_card, fg_color="transparent")

        # --- A. Campos para Carpeta Local / Cloud Drive ---
        lbl_folder_tag = ctk.CTkLabel(
            self.folder_settings_frame,
            text="Ruta de la Carpeta Sincronizada:",
            font=font_button(12),
            text_color=COLOR_TEXT_BRIGHT,
            anchor="w"
        )
        lbl_folder_tag.pack(fill="x", padx=16, pady=(8, 2))

        folder_input_row = ctk.CTkFrame(self.folder_settings_frame, fg_color="transparent")
        folder_input_row.pack(fill="x", padx=16, pady=(0, 6))

        self.entry_folder_path = ctk.CTkEntry(
            folder_input_row,
            height=34,
            corner_radius=8,
            font=font_body(11),
            fg_color=COLOR_BG_DARK,
            border_color=COLOR_BORDER_CARD
        )
        self.entry_folder_path.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_folder_path.insert(0, self.config.get("local_cloud_path", ""))
        self._nav_elements.append(self.entry_folder_path)

        self.btn_browse = ctk.CTkButton(
            folder_input_row,
            text="📂 Explorar...",
            width=110,
            height=34,
            corner_radius=8,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            command=self._on_browse_folder
        )
        self.btn_browse.pack(side="left", padx=(0, 6))
        self._nav_elements.append(self.btn_browse)

        self.btn_autodetect = ctk.CTkButton(
            folder_input_row,
            text="⚡ Autodetectar",
            width=110,
            height=34,
            corner_radius=8,
            font=font_button(11),
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            command=self._on_autodetect_provider_folder
        )
        self.btn_autodetect.pack(side="left")
        self._nav_elements.append(self.btn_autodetect)

        # --- B. Campos para WebDAV (Nextcloud / ownCloud) ---
        lbl_dav_url = ctk.CTkLabel(
            self.webdav_settings_frame,
            text="URL del Servidor WebDAV / Nextcloud:",
            font=font_button(12),
            text_color=COLOR_TEXT_BRIGHT,
            anchor="w"
        )
        lbl_dav_url.pack(fill="x", padx=16, pady=(8, 2))

        self.entry_webdav_url = ctk.CTkEntry(
            self.webdav_settings_frame,
            height=34,
            corner_radius=8,
            font=font_body(11),
            placeholder_text="https://mi-servidor.com/remote.php/dav/files/usuario/GameFlow_Saves",
            fg_color=COLOR_BG_DARK,
            border_color=COLOR_BORDER_CARD
        )
        self.entry_webdav_url.pack(fill="x", padx=16, pady=(0, 8))
        self.entry_webdav_url.insert(0, self.config.get("webdav_url", ""))
        self._nav_elements.append(self.entry_webdav_url)

        dav_cred_row = ctk.CTkFrame(self.webdav_settings_frame, fg_color="transparent")
        dav_cred_row.pack(fill="x", padx=16, pady=(0, 6))

        user_col = ctk.CTkFrame(dav_cred_row, fg_color="transparent")
        user_col.pack(side="left", fill="x", expand=True, padx=(0, 6))
        lbl_user = ctk.CTkLabel(user_col, text="Usuario:", font=font_button(11), text_color=COLOR_TEXT_MUTED, anchor="w")
        lbl_user.pack(fill="x", pady=(0, 2))
        self.entry_webdav_user = ctk.CTkEntry(
            user_col,
            height=34,
            corner_radius=8,
            font=font_body(11),
            fg_color=COLOR_BG_DARK,
            border_color=COLOR_BORDER_CARD
        )
        self.entry_webdav_user.pack(fill="x")
        self.entry_webdav_user.insert(0, self.config.get("webdav_user", ""))
        self._nav_elements.append(self.entry_webdav_user)

        pwd_col = ctk.CTkFrame(dav_cred_row, fg_color="transparent")
        pwd_col.pack(side="left", fill="x", expand=True, padx=(6, 0))
        lbl_pwd = ctk.CTkLabel(pwd_col, text="Contraseña o Token de Aplicación:", font=font_button(11), text_color=COLOR_TEXT_MUTED, anchor="w")
        lbl_pwd.pack(fill="x", pady=(0, 2))
        self.entry_webdav_pwd = ctk.CTkEntry(
            pwd_col,
            height=34,
            corner_radius=8,
            font=font_body(11),
            show="*",
            fg_color=COLOR_BG_DARK,
            border_color=COLOR_BORDER_CARD
        )
        self.entry_webdav_pwd.pack(fill="x")
        self.entry_webdav_pwd.insert(0, self.config.get("webdav_password", ""))
        self._nav_elements.append(self.entry_webdav_pwd)

        # 3. Opciones de Activación y Sincronización Automática
        options_card = ctk.CTkFrame(
            self.scroll_content,
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1
        )
        options_card.pack(fill="x", pady=(0, 12), ipady=6)

        opt_row1 = ctk.CTkFrame(options_card, fg_color="transparent")
        opt_row1.pack(fill="x", padx=16, pady=6)

        self.switch_enabled = ctk.CTkSwitch(
            opt_row1,
            text="Activar Sincronización en la Nube (Cloud Save Sync)",
            font=font_button(12),
            text_color=COLOR_TEXT_WHITE,
            progress_color=COLOR_IOS_BLUE
        )
        self.switch_enabled.pack(side="left")
        if self.config.get("enabled", False):
            self.switch_enabled.select()
        else:
            self.switch_enabled.deselect()
        self._nav_elements.append(self.switch_enabled)

        opt_row2 = ctk.CTkFrame(options_card, fg_color="transparent")
        opt_row2.pack(fill="x", padx=16, pady=6)

        self.switch_auto = ctk.CTkSwitch(
            opt_row2,
            text="Subir automáticamente copias de seguridad al salir de cada juego",
            font=font_body(12),
            text_color=COLOR_TEXT_MUTED_LIGHT,
            progress_color=COLOR_CYAN_ACCENT
        )
        self.switch_auto.pack(side="left")
        if self.config.get("auto_sync_on_backup", True):
            self.switch_auto.select()
        else:
            self.switch_auto.deselect()
        self._nav_elements.append(self.switch_auto)

        # 4. Estado de Conexión y Acciones Principales
        status_card = ctk.CTkFrame(
            self.scroll_content,
            corner_radius=16,
            fg_color=COLOR_BG_CARD_SECONDARY,
            border_color=COLOR_BORDER_CARD,
            border_width=1
        )
        status_card.pack(fill="x", pady=(0, 10), ipady=6)

        stat_header = ctk.CTkFrame(status_card, fg_color="transparent")
        stat_header.pack(fill="x", padx=16, pady=(6, 4))

        self.lbl_conn_status = ctk.CTkLabel(
            stat_header,
            text="⚪ Estado de conexión: Sin verificar",
            font=font_button(12),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_conn_status.pack(side="left")

        last_time = self.config.get("last_sync_time") or "Ninguna todavía"
        self.lbl_last_sync = ctk.CTkLabel(
            stat_header,
            text=f"Última sincr.: {last_time}",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        self.lbl_last_sync.pack(side="right")

        actions_btn_row = ctk.CTkFrame(status_card, fg_color="transparent")
        actions_btn_row.pack(fill="x", padx=16, pady=(4, 6))

        self.btn_test_conn = ctk.CTkButton(
            actions_btn_row,
            text="⚡ Probar Conexión (A)",
            font=font_button(12),
            height=36,
            corner_radius=10,
            fg_color=COLOR_BTN_SECONDARY_BG,
            hover_color=COLOR_BTN_SECONDARY_HOVER,
            border_color=COLOR_BTN_SECONDARY_BORDER,
            border_width=1,
            command=self._on_test_connection
        )
        self.btn_test_conn.pack(side="left", padx=(0, 10))
        self._nav_elements.append(self.btn_test_conn)

        self.btn_sync_now = ctk.CTkButton(
            actions_btn_row,
            text="☁️ Sincronizar Toda la Biblioteca Ahora",
            font=font_button(12),
            height=36,
            corner_radius=10,
            fg_color=COLOR_IOS_BLUE,
            hover_color=COLOR_IOS_BLUE_HOVER,
            border_color=COLOR_IOS_BLUE_BORDER,
            border_width=1.2,
            command=self._on_sync_now
        )
        self.btn_sync_now.pack(side="left", padx=(0, 10))
        self._nav_elements.append(self.btn_sync_now)

        self.lbl_sync_progress = ctk.CTkLabel(
            actions_btn_row,
            text="",
            font=font_body(11),
            text_color=COLOR_CYAN_ACCENT
        )
        self.lbl_sync_progress.pack(side="left", padx=4)

        # ---------------- Pie con Atajos de Mando ----------------
        self.footer_bar = ctk.CTkFrame(self.main_card, fg_color="transparent", height=28)
        self.footer_bar.pack(fill="x", padx=20, pady=(0, 8))

        lbl_footer_shortcuts = ctk.CTkLabel(
            self.footer_bar,
            text="Cruceta (↑ / ↓): Navegar  │  (A): Activar / Probar  │  (X): Explorar Carpeta  │  (Start): Sincronizar  │  (B): Guardar y Salir",
            font=font_body(11),
            text_color=COLOR_TEXT_DIM
        )
        lbl_footer_shortcuts.pack(anchor="center")

    def _update_provider_ui(self):
        """Actualiza la visualización según el proveedor seleccionado."""
        for p_key, btn in self._provider_buttons.items():
            is_sel = (p_key == self.selected_provider)
            btn.configure(
                fg_color=COLOR_IOS_BLUE if is_sel else COLOR_BTN_SECONDARY_BG,
                hover_color=COLOR_IOS_BLUE_HOVER if is_sel else COLOR_BTN_SECONDARY_HOVER,
                border_color=COLOR_IOS_BLUE_BORDER if is_sel else COLOR_BORDER_CARD,
                text_color=COLOR_TEXT_WHITE if is_sel else COLOR_TEXT_MUTED_LIGHT
            )

        if self.selected_provider == PROVIDER_WEBDAV:
            self.folder_settings_frame.pack_forget()
            self.webdav_settings_frame.pack(fill="x")
        else:
            self.webdav_settings_frame.pack_forget()
            self.folder_settings_frame.pack(fill="x")

            # Si el campo de carpeta está vacío, intentar autodetectar la del proveedor
            if not self.entry_folder_path.get().strip():
                self._on_autodetect_provider_folder(silent=True)

    def _on_select_provider(self, provider_key: str):
        feedback_click()
        self.selected_provider = provider_key
        self._update_provider_ui()

    def _on_autodetect_provider_folder(self, silent: bool = False):
        """Autodetecta la carpeta local correspondiente al proveedor actual."""
        detected = detect_local_cloud_providers()
        found_path = None
        for d in detected:
            if d["provider"] == self.selected_provider:
                found_path = d["path"]
                break

        if found_path:
            self.entry_folder_path.delete(0, "end")
            self.entry_folder_path.insert(0, found_path)
            if not silent:
                feedback_click()
                self.lbl_conn_status.configure(
                    text=f"🟢 {PROVIDER_NAMES.get(self.selected_provider)} detectado correctamente",
                    text_color=COLOR_STATUS_SUCCESS
                )
        elif not silent:
            self.lbl_conn_status.configure(
                text=f"⚠️ No se detectó instalación local de {PROVIDER_NAMES.get(self.selected_provider)}. Indica la ruta manualmente.",
                text_color=COLOR_TEXT_MUTED
            )

    def _on_browse_folder(self):
        feedback_click()
        init_dir = self.entry_folder_path.get().strip() or None
        chosen = browse_folder(parent=self, title="Seleccionar Carpeta para Sincronización", initial_dir=init_dir)
        if chosen:
            self.entry_folder_path.delete(0, "end")
            self.entry_folder_path.insert(0, chosen)

    def _get_current_dialog_config(self) -> Dict[str, Any]:
        """Obtiene el diccionario de configuración con los valores actuales de la UI."""
        return {
            "enabled": bool(self.switch_enabled.get()),
            "provider": self.selected_provider,
            "local_cloud_path": self.entry_folder_path.get().strip(),
            "subfolder_name": self.config.get("subfolder_name", "GameFlow_Saves"),
            "webdav_url": self.entry_webdav_url.get().strip(),
            "webdav_user": self.entry_webdav_user.get().strip(),
            "webdav_password": self.entry_webdav_pwd.get().strip(),
            "auto_sync_on_backup": bool(self.switch_auto.get()),
            "last_sync_time": self.config.get("last_sync_time", ""),
            "last_sync_status": self.config.get("last_sync_status", "none"),
            "last_sync_error": self.config.get("last_sync_error", ""),
            "synced_files": self.config.get("synced_files", {})
        }

    def _on_test_connection(self):
        feedback_click()
        cfg = self._get_current_dialog_config()
        self.lbl_conn_status.configure(text="⏳ Probando conexión...", text_color=COLOR_CYAN_ACCENT)
        self.update_idletasks()

        def _worker():
            success, msg = test_cloud_connection(cfg)

            def _update_ui():
                if not self.winfo_exists():
                    return
                if success:
                    self.lbl_conn_status.configure(text=f"🟢 {msg}", text_color=COLOR_STATUS_SUCCESS)
                    try:
                        trigger_haptic(1000, 1000, 15)
                    except Exception:
                        pass
                else:
                    self.lbl_conn_status.configure(text=f"🔴 Error: {msg}", text_color=COLOR_STATUS_DANGER)

            if self.winfo_exists():
                self.after(0, _update_ui)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_sync_now(self):
        if self.sync_in_progress:
            return

        feedback_click()
        self._save_changes()

        if not self.games:
            self.lbl_sync_progress.configure(text="No hay juegos en la biblioteca.")
            return

        self.sync_in_progress = True
        self.btn_sync_now.configure(state="disabled")
        self.lbl_sync_progress.configure(text="Iniciando sincronización...")

        def _progress(idx, total, g_name):
            if self.winfo_exists():
                self.after(0, lambda: self.lbl_sync_progress.configure(
                    text=f"Sincronizando [{idx}/{total}]: {g_name}..."
                ) if self.winfo_exists() else None)

        def _worker():
            res = sync_all_games(self.games, progress_cb=_progress)

            def _done():
                if not self.winfo_exists():
                    return
                self.sync_in_progress = False
                self.btn_sync_now.configure(state="normal")
                up = res.get("total_uploaded", 0)
                if res.get("success"):
                    self.lbl_sync_progress.configure(
                        text=f"✓ Sincronización completada ({up} nuevos backups subidos).",
                        text_color=COLOR_STATUS_SUCCESS
                    )
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                    self.lbl_last_sync.configure(text=f"Última sincr.: {now_str}")
                else:
                    err_txt = "; ".join(res.get("errors", []))[:60]
                    self.lbl_sync_progress.configure(
                        text=f"Completado con avisos: {err_txt}",
                        text_color="#FBBF24"
                    )
                if self.on_sync_completed:
                    self.on_sync_completed()

            if self.winfo_exists():
                self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _save_changes(self):
        current_cfg = self._get_current_dialog_config()
        save_cloud_config(current_cfg)

    def close(self):
        self._save_changes()
        feedback_click()
        super().close()

    def _bind_events(self):
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<Return>", lambda e: self._on_test_connection())

    # -------------------------------------------------------------------------
    # Soporte 100% de Mando
    # -------------------------------------------------------------------------
    def handle_gamepad_input(self, inputs: Dict[str, Any], prev_inputs: Dict[str, Any]) -> bool:
        """Navegación nativa con mando para CloudSyncDialog."""
        if (inputs.get("b", False) and not prev_inputs.get("b", False)) or \
           (inputs.get("back", False) and not prev_inputs.get("back", False)):
            self.close()
            return True

        if inputs.get("start", False) and not prev_inputs.get("start", False):
            self._on_sync_now()
            return True

        if inputs.get("x", False) and not prev_inputs.get("x", False):
            if self.selected_provider != PROVIDER_WEBDAV:
                self._on_browse_folder()
                return True

        # Cruceta Arriba / Abajo para alternar entre proveedores o probar conexión
        if inputs.get("left", False) and not prev_inputs.get("left", False):
            prov_keys = [PROVIDER_ONEDRIVE, PROVIDER_GDRIVE, PROVIDER_DROPBOX, PROVIDER_LOCAL_FOLDER, PROVIDER_WEBDAV]
            curr_idx = prov_keys.index(self.selected_provider) if self.selected_provider in prov_keys else 0
            new_idx = (curr_idx - 1) % len(prov_keys)
            self._on_select_provider(prov_keys[new_idx])
            return True

        if inputs.get("right", False) and not prev_inputs.get("right", False):
            prov_keys = [PROVIDER_ONEDRIVE, PROVIDER_GDRIVE, PROVIDER_DROPBOX, PROVIDER_LOCAL_FOLDER, PROVIDER_WEBDAV]
            curr_idx = prov_keys.index(self.selected_provider) if self.selected_provider in prov_keys else 0
            new_idx = (curr_idx + 1) % len(prov_keys)
            self._on_select_provider(prov_keys[new_idx])
            return True

        # Botón A: Probar conexión o guardar
        if inputs.get("a", False) and not prev_inputs.get("a", False):
            self._on_test_connection()
            return True

        return False
