from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FALLOUTNV_DIR = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam" / "steamapps" / "common" / "Fallout New Vegas"


@dataclass(frozen=True)
class GeckConfig:
    game_dir: Path
    geck_exe: Path
    nvse_loader: Path
    data_dir: Path
    backup_dir: Path
    screenshot_dir: Path
    load_order_file: Path | None


def default_load_order_file() -> Path | None:
    override = os.environ.get("GECK_MCP_LOAD_ORDER_FILE")
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / "FalloutNV" / "plugins.txt"


def get_config(game_dir: str | None = None) -> GeckConfig:
    resolved_game_dir = Path(
        game_dir
        or os.environ.get("GECK_MCP_FNV_DIR")
        or os.environ.get("FALLOUTNV_DIR")
        or DEFAULT_FALLOUTNV_DIR
    ).expanduser()

    geck_exe = Path(os.environ.get("GECK_MCP_GECK_EXE", resolved_game_dir / "GECK.exe"))
    data_dir = Path(os.environ.get("GECK_MCP_DATA_DIR", resolved_game_dir / "Data"))

    return GeckConfig(
        game_dir=resolved_game_dir,
        geck_exe=geck_exe,
        nvse_loader=resolved_game_dir / "nvse_loader.exe",
        data_dir=data_dir,
        backup_dir=Path(os.environ.get("GECK_MCP_BACKUP_DIR", Path.cwd() / "backups")),
        screenshot_dir=Path(os.environ.get("GECK_MCP_SCREENSHOT_DIR", Path.cwd() / "screenshots")),
        load_order_file=default_load_order_file(),
    )
