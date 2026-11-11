"""
Dialogs package for GameFlow Launcher.
Contains modal and floating management dialogs.
"""
from ui.dialogs.base_dialog import BaseGlassDialog, register_modal_stack, unregister_modal_stack
from ui.dialogs.add_edit_game import AddEditGameDialog
from ui.dialogs.scan_results import ScanResultsDialog
from ui.dialogs.select_game_to_edit import SelectGameToEditDialog, invalidate_thumb_cache
from ui.dialogs.gamepad_config_dialog import GamepadConfigDialog
from ui.dialogs.confirm_exit import ConfirmExitDialog
from ui.dialogs.cover_picker_dialog import CoverPickerDialog
from ui.dialogs.controller_info_dialog import ControllerInfoDialog
from ui.dialogs.glass_message_box import GlassMessageBox, show_info, show_warning, show_error, ask_yes_no
from ui.dialogs.glass_folder_browser import GlassFolderBrowserDialog, browse_folder, browse_file
from ui.dialogs.on_screen_keyboard import OnScreenKeyboardDialog, prompt_on_screen_keyboard
from ui.dialogs.external_import_dialog import ExternalImportDialog
from ui.dialogs.batch_steamgriddb_dialog import BatchSteamGridDBDialog
from ui.dialogs.collections_dialog import CollectionsFilterDialog
from ui.dialogs.in_game_overlay import InGameOverlayDialog
from ui.dialogs.game_stats_dialog import GameStatsDialog
from ui.dialogs.save_backup_dialog import SaveBackupDialog
from ui.dialogs.performance_dialog import PerformanceProfileDialog
PerformanceDialog = PerformanceProfileDialog
from ui.dialogs.cloud_sync_dialog import CloudSyncDialog
from ui.dialogs.achievements_dialog import AchievementsDialog

__all__ = [
    "AchievementsDialog",
    "CloudSyncDialog",
    "PerformanceProfileDialog",
    "PerformanceDialog",
    "SaveBackupDialog",
    "GameStatsDialog",
    "InGameOverlayDialog",
    "CollectionsFilterDialog",
    "BatchSteamGridDBDialog",
    "ExternalImportDialog",
    "BaseGlassDialog",
    "register_modal_stack",
    "unregister_modal_stack",
    "AddEditGameDialog",
    "ScanResultsDialog",
    "SelectGameToEditDialog",
    "invalidate_thumb_cache",
    "GamepadConfigDialog",
    "ConfirmExitDialog",
    "CoverPickerDialog",
    "ControllerInfoDialog",
    "GlassMessageBox",
    "show_info",
    "show_warning",
    "show_error",
    "ask_yes_no",
    "GlassFolderBrowserDialog",
    "browse_folder",
    "browse_file",
    "OnScreenKeyboardDialog",
    "prompt_on_screen_keyboard"
]
