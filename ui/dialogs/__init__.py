"""
Dialogs package for GameFlow Launcher.
Contains modal and floating management dialogs with PEP 562 lazy loading for fast cold startup.
"""
import importlib
from typing import Any

_LAZY_EXPORTS = {
    "BaseGlassDialog": ("ui.dialogs.base_dialog", "BaseGlassDialog"),
    "register_modal_stack": ("ui.dialogs.base_dialog", "register_modal_stack"),
    "unregister_modal_stack": ("ui.dialogs.base_dialog", "unregister_modal_stack"),
    "AddEditGameDialog": ("ui.dialogs.add_edit_game", "AddEditGameDialog"),
    "ScanResultsDialog": ("ui.dialogs.scan_results", "ScanResultsDialog"),
    "SelectGameToEditDialog": ("ui.dialogs.select_game_to_edit", "SelectGameToEditDialog"),
    "invalidate_thumb_cache": ("ui.dialogs.select_game_to_edit", "invalidate_thumb_cache"),
    "GamepadConfigDialog": ("ui.dialogs.gamepad_config_dialog", "GamepadConfigDialog"),
    "ConfirmExitDialog": ("ui.dialogs.confirm_exit", "ConfirmExitDialog"),
    "CoverPickerDialog": ("ui.dialogs.cover_picker_dialog", "CoverPickerDialog"),
    "ControllerInfoDialog": ("ui.dialogs.controller_info_dialog", "ControllerInfoDialog"),
    "GlassMessageBox": ("ui.dialogs.glass_message_box", "GlassMessageBox"),
    "show_info": ("ui.dialogs.glass_message_box", "show_info"),
    "show_warning": ("ui.dialogs.glass_message_box", "show_warning"),
    "show_error": ("ui.dialogs.glass_message_box", "show_error"),
    "ask_yes_no": ("ui.dialogs.glass_message_box", "ask_yes_no"),
    "GlassFolderBrowserDialog": ("ui.dialogs.glass_folder_browser", "GlassFolderBrowserDialog"),
    "browse_folder": ("ui.dialogs.glass_folder_browser", "browse_folder"),
    "browse_file": ("ui.dialogs.glass_folder_browser", "browse_file"),
    "OnScreenKeyboardDialog": ("ui.dialogs.on_screen_keyboard", "OnScreenKeyboardDialog"),
    "prompt_on_screen_keyboard": ("ui.dialogs.on_screen_keyboard", "prompt_on_screen_keyboard"),
    "ExternalImportDialog": ("ui.dialogs.external_import_dialog", "ExternalImportDialog"),
    "BatchSteamGridDBDialog": ("ui.dialogs.batch_steamgriddb_dialog", "BatchSteamGridDBDialog"),
    "CollectionsFilterDialog": ("ui.dialogs.collections_dialog", "CollectionsFilterDialog"),
    "InGameOverlayDialog": ("ui.dialogs.in_game_overlay", "InGameOverlayDialog"),
    "GameStatsDialog": ("ui.dialogs.game_stats_dialog", "GameStatsDialog"),
    "SaveBackupDialog": ("ui.dialogs.save_backup_dialog", "SaveBackupDialog"),
    "PerformanceProfileDialog": ("ui.dialogs.performance_dialog", "PerformanceProfileDialog"),
    "PerformanceDialog": ("ui.dialogs.performance_dialog", "PerformanceProfileDialog"),
    "CloudSyncDialog": ("ui.dialogs.cloud_sync_dialog", "CloudSyncDialog"),
    "AchievementsDialog": ("ui.dialogs.achievements_dialog", "AchievementsDialog"),
    "KioskDialog": ("ui.dialogs.kiosk_dialog", "KioskDialog"),
}

__all__ = list(_LAZY_EXPORTS.keys())


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is not None:
        mod_name, attr_name = target
        mod = importlib.import_module(mod_name)
        val = getattr(mod, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

