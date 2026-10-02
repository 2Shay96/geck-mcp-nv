from __future__ import annotations

import os
import math
import tempfile
import re
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .config import GeckConfig
from .esp import walk, fields, validate


class GeckAutomationError(RuntimeError):
    """Raised when GECK automation cannot complete safely."""


PLUGIN_SUFFIXES = {".esm", ".esp"}
DATA_FILE_SUFFIXES = PLUGIN_SUFFIXES | {".bsa"}
ALLOWED_LOG_NAMES = {
    "EditorWarnings.txt",
    "nvse.log",
    "nvse_loader.log",
    "nvse_editor.log",
}
PLACED_SIGNATURES = {b"REFR", b"ACHR", b"ACRE"}
PATCHABLE_PLACED_SIGNATURES = PLACED_SIGNATURES


@dataclass(frozen=True)
class WindowSelector:
    handle: int | None = None
    title_regex: str | None = None
    backend: str = "win32"


def dependency_status() -> dict[str, bool]:
    modules = ["mcp", "psutil", "pywinauto", "PIL"]
    status: dict[str, bool] = {}
    for module in modules:
        try:
            __import__(module)
        except Exception:
            status[module] = False
        else:
            status[module] = True
    return status


def doctor(config: GeckConfig) -> dict[str, Any]:
    return {
        "game_dir": str(config.game_dir),
        "game_dir_exists": config.game_dir.exists(),
        "geck_exe": str(config.geck_exe),
        "geck_exe_exists": config.geck_exe.exists(),
        "nvse_loader": str(config.nvse_loader),
        "nvse_loader_exists": config.nvse_loader.exists(),
        "data_dir": str(config.data_dir),
        "data_dir_exists": config.data_dir.exists(),
        "load_order_file": str(config.load_order_file) if config.load_order_file else None,
        "load_order_file_exists": bool(config.load_order_file and config.load_order_file.exists()),
        "dependencies": dependency_status(),
        "os_name": os.name,
    }


def _require_windows() -> None:
    if os.name != "nt":
        raise GeckAutomationError("GECK UI automation only works on Windows.")


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise GeckAutomationError(f"{label} not found: {path}")


def _require_dir(path: Path, label: str) -> None:
    if not path.is_dir():
        raise GeckAutomationError(f"{label} not found: {path}")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _sanitize_label(label: str | None) -> str | None:
    if not label:
        return None
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", label.strip())
    return clean.strip("._-") or None


def _unique_backup_path(
    config: GeckConfig,
    source: Path,
    label: str | None = None,
    transaction: bool = False,
) -> Path:
    suffix_parts = [_timestamp()]
    if transaction:
        suffix_parts.append("tx")
    clean_label = _sanitize_label(label)
    if clean_label:
        suffix_parts.append(clean_label)

    base_name = f"{source.stem}.{'.'.join(suffix_parts)}"
    target = config.backup_dir / f"{base_name}{source.suffix}"
    counter = 1
    while target.exists():
        target = config.backup_dir / f"{base_name}.{counter}{source.suffix}"
        counter += 1
    return target


def _safe_backup_file(config: GeckConfig, backup_name_or_path: str) -> Path:
    if not backup_name_or_path:
        raise GeckAutomationError("Backup path or transaction id is required.")

    raw = Path(backup_name_or_path)
    path = raw if raw.is_absolute() else config.backup_dir / raw.name
    if path.suffix.lower() not in PLUGIN_SUFFIXES:
        allowed = ", ".join(sorted(PLUGIN_SUFFIXES))
        raise GeckAutomationError(f"Unsupported backup suffix. Allowed: {allowed}")

    resolved_backup_dir = config.backup_dir.resolve()
    resolved_path = path.resolve()
    if resolved_backup_dir not in resolved_path.parents and resolved_path != resolved_backup_dir:
        raise GeckAutomationError("Resolved backup path escaped the MCP backup directory.")
    _require_file(resolved_path, "Backup")
    return resolved_path


def _safe_data_file(config: GeckConfig, file_name: str, suffixes: set[str]) -> Path:
    if not file_name or Path(file_name).name != file_name:
        raise GeckAutomationError("Use a bare file name inside Data, not a path.")

    path = config.data_dir / file_name
    if path.suffix.lower() not in suffixes:
        allowed = ", ".join(sorted(suffixes))
        raise GeckAutomationError(f"Unsupported file suffix. Allowed: {allowed}")

    resolved_data = config.data_dir.resolve()
    resolved_path = path.resolve()
    if resolved_data not in resolved_path.parents and resolved_path != resolved_data:
        raise GeckAutomationError("Resolved file path escaped the Data directory.")
    return resolved_path


def list_data_files(config: GeckConfig, include_bsa: bool = False) -> list[dict[str, Any]]:
    _require_dir(config.data_dir, "Data directory")
    suffixes = DATA_FILE_SUFFIXES if include_bsa else PLUGIN_SUFFIXES
    files: list[dict[str, Any]] = []

    for path in sorted(config.data_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "suffix": path.suffix.lower(),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    return files


def plugin_status(config: GeckConfig, plugin_name: str, backup: bool = False) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    exists = plugin.exists()
    result: dict[str, Any] = {
        "name": plugin.name,
        "path": str(plugin),
        "exists": exists,
    }
    if exists:
        stat = plugin.stat()
        result.update(
            {
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
    if backup and exists:
        result["backup"] = backup_plugin(config, plugin.name)["backup"]
    return result


def _parse_form_id(form_id: str | int) -> int:
    if isinstance(form_id, int):
        return form_id
    clean = form_id.strip().lower().removeprefix("0x")
    return int(clean, 16)


def _format_form_id(form_id: int) -> str:
    return f"{form_id:08X}"


def _iter_records(data, signature=None):
    for off, sig, size, form, _, _ in walk(data):
        if sig != b"GRUP" and (signature is None or sig == signature or
                                isinstance(signature, set) and sig in signature):
            yield off, sig, size, form


def _iter_groups(data):
    for off, sig, size, _, _, _ in walk(data):
        if sig == b"GRUP":
            yield off, size, off + size


def _parse_placed_record(data, off, signature, size, form_id):
    base_id = position = rotation = None
    names = []
    for sig, value, length in fields(data, off, size):
        if sig in (b"NAME", b"DATA") and sig.decode("ascii") in names:
            raise GeckAutomationError("Duplicate NAME or DATA in placed record.")
        names.append(sig.decode("ascii", errors="replace"))
        if sig == b"NAME" and length == 4:
            base_id = struct.unpack_from("<I", data, value)[0]
        elif sig == b"DATA":
            if length != 24:
                raise GeckAutomationError("Placed DATA must contain exactly six floats.")
            values = struct.unpack_from("<6f", data, value)
            if not all(math.isfinite(v) for v in values):
                raise GeckAutomationError("Non-finite placed coordinates or rotation.")
            position, rotation = values[:3], values[3:]
    return {
        "record_type": signature.decode("ascii"), "record_offset": off,
        "record_size": size, "form_id": _format_form_id(form_id),
        "base_form_id": _format_form_id(base_id) if base_id is not None else None,
        "position": dict(zip(("x", "y", "z"), position)) if position else None,
        "rotation": dict(zip(("x", "y", "z"), rotation)) if rotation else None,
        "rotation_units": "radians", "fields": names,
    }


def _require_editor_closed(config):
    # GECK may load a plugin as a dependency, so checking only its title is insufficient.
    if list_geck_processes(config):
        raise GeckAutomationError("Close GECK/NVSE and Fallout: New Vegas before direct plugin edits or rollback; loaded files may differ from disk. Capture coordinates with placement_plan_from_status_bar first, then use esp_patch_ref_position after closing.")


def _atomic_plugin_write(config, plugin, original, updated):
    validate(updated)
    _require_editor_closed(config)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=plugin.parent, prefix=plugin.name + ".", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        if temp.read_bytes() != updated:
            raise GeckAutomationError("Temporary plugin verification failed.")
        _require_editor_closed(config)
        if plugin.read_bytes() != original:
            raise GeckAutomationError("Plugin changed during editing; refusing to overwrite it.")
        os.replace(temp, plugin)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def _find_placed_record(data: bytes | bytearray, target_form_id: int) -> dict[str, Any] | None:
    raw = bytes(data)
    for off, sig, size, form_id in _iter_records(raw, PATCHABLE_PLACED_SIGNATURES):
        if form_id == target_form_id:
            return _parse_placed_record(raw, off, sig, size, form_id)
    return None


def _dict_position(position: dict[str, float], offsets: tuple[float, float, float]) -> dict[str, float]:
    return {
        "x": float(position["x"]) + offsets[0],
        "y": float(position["y"]) + offsets[1],
        "z": float(position["z"]) + offsets[2],
    }


def _choose_rotation(
    status: dict[str, Any],
    existing_ref: dict[str, Any] | None = None,
    use_status_rotation: bool = False,
    preserve_existing_rotation: bool = True,
    explicit_rotation: tuple[float | None, float | None, float | None] = (None, None, None),
) -> tuple[dict[str, float], str, list[str]]:
    warnings: list[str] = []
    if any(value is not None for value in explicit_rotation) and not all(value is not None for value in explicit_rotation):
        raise GeckAutomationError("For a placement plan, supply all three rotation axes or omit them. Direct position patching supports individual axes.")
    if all(value is not None for value in explicit_rotation):
        rx, ry, rz = explicit_rotation
        return {"x": float(rx), "y": float(ry), "z": float(rz)}, "explicit", warnings

    status_rotation = status.get("rotation")
    if use_status_rotation and status_rotation:
        return {
            "x": float(status_rotation["x"]),
            "y": float(status_rotation["y"]),
            "z": float(status_rotation["z"]),
        }, "status_bar", warnings

    existing_rotation = existing_ref.get("rotation") if existing_ref else None
    if preserve_existing_rotation and existing_rotation:
        if use_status_rotation:
            warnings.append("Status bar has no rotation; preserving the target record's current rotation.")
        return {
            "x": float(existing_rotation["x"]),
            "y": float(existing_rotation["y"]),
            "z": float(existing_rotation["z"]),
        }, "existing_record", warnings

    warnings.append("No status-bar or existing rotation was available; using 0,0,0.")
    return {"x": 0.0, "y": 0.0, "z": 0.0}, "fallback_zero", warnings


def _parse_refr(data: bytes, off: int, size: int, form_id: int) -> dict[str, Any]:
    return _parse_placed_record(data, off, b"REFR", size, form_id)


def esp_list_placed_refs(config: GeckConfig, plugin_name: str) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    data = plugin.read_bytes()
    refs = []
    for off, sig, size, form, cell, world in walk(data):
        if sig in PLACED_SIGNATURES:
            ref = _parse_placed_record(data, off, sig, size, form)
            ref["cell_form_id"] = _format_form_id(cell) if cell is not None else None
            ref["world_form_id"] = _format_form_id(world) if world is not None else None
            refs.append(ref)
    return {"plugin": str(plugin), "refs": refs, "ref_count": len(refs)}


def esp_find_nearby_refs(
    config: GeckConfig,
    plugin_name: str,
    x: float,
    y: float,
    z: float,
    radius: float = 256.0,
    cell_form_id: str | None = None,
) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Plugin")
    data = plugin.read_bytes()
    radius = max(0.0, radius)
    matches: list[dict[str, Any]] = []
    for ref in esp_list_placed_refs(config, plugin_name)["refs"]:
        if cell_form_id is not None and ref["cell_form_id"] != _format_form_id(_parse_form_id(cell_form_id)):
            continue
        position = ref.get("position")
        if not position:
            continue
        dx = position["x"] - x
        dy = position["y"] - y
        dz = position["z"] - z
        distance = (dx * dx + dy * dy + dz * dz) ** 0.5
        if distance <= radius:
            ref["distance"] = distance
            ref["delta"] = {"x": dx, "y": dy, "z": dz}
            matches.append(ref)
    matches.sort(key=lambda item: item["distance"])
    return {"plugin": str(plugin), "anchor": {"x": x, "y": y, "z": z}, "radius": radius, "matches": matches, "cell_form_id": cell_form_id, "warning": None if cell_form_id else "Unscoped coordinates can match unrelated cells; supply cell_form_id."}


def placement_report(
    config: GeckConfig,
    plugin_name: str,
    backend: str = "win32",
    suspicious_distance: float = 1024.0,
    suspicious_z_delta: float = 512.0,
    cell_form_id: str | None = None,
) -> dict[str, Any]:
    if cell_form_id is None:
        raise GeckAutomationError("Supply the anchor cell_form_id to avoid comparing unrelated cells.")
    status = status_bar(backend)
    anchor = status.get("position")
    refs = esp_list_placed_refs(config, plugin_name)["refs"]
    if not anchor:
        raise GeckAutomationError("GECK status bar does not currently contain parseable coordinates.")

    assessed: list[dict[str, Any]] = []
    for ref in refs:
        if ref.get("cell_form_id") != _format_form_id(_parse_form_id(cell_form_id)):
            continue
        position = ref.get("position")
        if not position:
            continue
        dx = position["x"] - anchor["x"]
        dy = position["y"] - anchor["y"]
        dz = position["z"] - anchor["z"]
        distance = (dx * dx + dy * dy + dz * dz) ** 0.5
        suspicious_reasons = []
        if distance > suspicious_distance:
            suspicious_reasons.append(f"distance>{suspicious_distance:g}")
        if abs(dz) > suspicious_z_delta:
            suspicious_reasons.append(f"abs(z_delta)>{suspicious_z_delta:g}")
        item = dict(ref)
        item["distance_from_status_bar"] = distance
        item["delta_from_status_bar"] = {"x": dx, "y": dy, "z": dz}
        item["suspicious"] = bool(suspicious_reasons)
        item["suspicious_reasons"] = suspicious_reasons
        assessed.append(item)

    assessed.sort(key=lambda item: item["distance_from_status_bar"])
    return {
        "plugin": str(_safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)),
        "status_bar": status,
        "refs": assessed,
        "warning": "This is a coordinate sanity check, not a physics/collision solver. For perfect floor contact, use GECK/Havok or a native raycast bridge.",
    }


def esp_patch_ref_position(
    config: GeckConfig,
    plugin_name: str,
    ref_form_id: str | int,
    x: float,
    y: float,
    z: float,
    rot_x: float | None = None,
    rot_y: float | None = None,
    rot_z: float | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Plugin")
    target = _parse_form_id(ref_form_id)
    _require_editor_closed(config)
    original = plugin.read_bytes()
    validate(original)
    data = bytearray(original)
    backup_path: str | None = None
    if backup:
        backup_path = backup_plugin(config, plugin.name)["backup"]

    patched = False
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    for off, sig, size, form_id in _iter_records(data, PATCHABLE_PLACED_SIGNATURES):
        if form_id != target:
            continue
        before = _parse_placed_record(data, off, sig, size, form_id)
        if before["rotation"] is None:
            raise GeckAutomationError("Target has no position/rotation DATA.")
        angles = [before["rotation"][axis] if value is None else value
                  for axis, value in zip(("x", "y", "z"), (rot_x, rot_y, rot_z))]
        values = (x, y, z, *angles)
        if not all(math.isfinite(v) for v in values):
            raise GeckAutomationError("Coordinates and rotations must be finite.")
        for sig, value, length in fields(data, off, size):
            if sig == b"DATA" and length == 24:
                struct.pack_into("<6f", data, value, *values)
                patched = True
                break
        after = _parse_placed_record(data, off, sig, size, form_id)
        break

    if not patched:
        raise GeckAutomationError(f"Placed form ID was not found or had no DATA field: {_format_form_id(target)}")

    _atomic_plugin_write(config, plugin, original, data)
    return {
        "plugin": str(plugin),
        "backup": backup_path,
        "patched": _format_form_id(target),
        "before": before,
        "after": after,
        "warning": "If this plugin is open in GECK, reload it before saving or GECK may overwrite this file patch.",
    }


def esp_delete_refs(
    config: GeckConfig,
    plugin_name: str,
    ref_form_ids: list[str],
    backup: bool = True,
) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Plugin")
    targets = {_parse_form_id(form_id) for form_id in ref_form_ids}
    _require_editor_closed(config)
    original = plugin.read_bytes()
    validate(original)
    data = bytearray(original)
    backup_path: str | None = None
    if backup:
        backup_path = backup_plugin(config, plugin.name)["backup"]

    deletions: list[tuple[int, int, int]] = []
    deleted: list[str] = []
    for off, _sig, size, form_id in _iter_records(data, PLACED_SIGNATURES):
        if form_id in targets:
            deletions.append((off, off + 24 + size, form_id))
            deleted.append(_format_form_id(form_id))

    if not deletions:
        raise GeckAutomationError("No matching placed records found to delete.")

    total_removed_by_group: dict[int, int] = {}
    groups = list(_iter_groups(data))
    for start, end, _form_id in deletions:
        length = end - start
        for group_off, _group_size, group_end in groups:
            if group_off < start and end <= group_end:
                total_removed_by_group[group_off] = total_removed_by_group.get(group_off, 0) + length

    for group_off, removed_length in total_removed_by_group.items():
        old_size = struct.unpack_from("<I", data, group_off + 4)[0]
        struct.pack_into("<I", data, group_off + 4, old_size - removed_length)

    if set(deleted) != {_format_form_id(t) for t in targets}:
        raise GeckAutomationError("Some requested references are missing; no records deleted.")
    header_size = struct.unpack_from("<I", data, 4)[0]
    headers = [(value, length) for sig, value, length in fields(data, 0, header_size) if sig == b"HEDR"]
    if len(headers) != 1 or headers[0][1] != 12:
        raise GeckAutomationError("Expected exactly one 12-byte TES4 HEDR.")
    count_off = headers[0][0] + 4
    old_count = struct.unpack_from("<I", data, count_off)[0]
    if old_count < len(deletions):
        raise GeckAutomationError("Invalid HEDR record count.")
    struct.pack_into("<I", data, count_off, old_count - len(deletions))

    for start, end, _form_id in sorted(deletions, reverse=True):
        del data[start:end]

    _atomic_plugin_write(config, plugin, original, data)
    return {
        "plugin": str(plugin),
        "backup": backup_path,
        "deleted": deleted,
        "size": len(data),
        "warning": "If this plugin is open in GECK, reload it before saving or GECK may overwrite this file patch.",
    }


def esp_delete_refs_by_base(
    config: GeckConfig,
    plugin_name: str,
    base_form_ids: list[str],
    backup: bool = True,
) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Plugin")
    targets = {_parse_form_id(form_id) for form_id in base_form_ids}
    refs = esp_list_placed_refs(config, plugin.name)["refs"]
    ref_form_ids = [
        ref["form_id"]
        for ref in refs
        if ref.get("base_form_id") and _parse_form_id(ref["base_form_id"]) in targets
    ]
    if not ref_form_ids:
        target_text = ", ".join(_format_form_id(target) for target in sorted(targets))
        raise GeckAutomationError(f"No placed records found with base FormID(s): {target_text}")

    result = esp_delete_refs(config, plugin.name, ref_form_ids, backup)
    result["base_form_ids"] = [_format_form_id(target) for target in sorted(targets)]
    return result


def backup_plugin(
    config: GeckConfig,
    plugin_name: str,
    label: str | None = None,
    transaction: bool = False,
) -> dict[str, str]:
    source = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(source, "Plugin")

    config.backup_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_backup_path(config, source, label=label, transaction=transaction)
    shutil.copy2(source, target)
    stat = target.stat()
    return {
        "source": str(source),
        "backup": str(target),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(timespec="seconds"),
        "source_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def transaction_begin(
    config: GeckConfig,
    plugin_name: str,
    label: str | None = None,
) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Plugin")
    backup = backup_plugin(config, plugin.name, label=label, transaction=True)
    return {
        "plugin": str(plugin),
        "transaction_id": Path(backup["backup"]).name,
        "backup": backup["backup"],
        "status": plugin_status(config, plugin.name),
        "warning": "This protects the file on disk. If the plugin is open in GECK, reload it after external patches before saving.",
    }


def transaction_list(
    config: GeckConfig,
    plugin_name: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    source: Path | None = None
    if plugin_name:
        source = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)

    entries: list[dict[str, Any]] = []
    for path in config.backup_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in PLUGIN_SUFFIXES:
            continue
        if source and not path.name.lower().startswith(f"{source.stem.lower()}."):
            continue
        stat = path.stat()
        entries.append(
            {
                "transaction_id": path.name,
                "path": str(path.resolve()),
                "plugin_hint": f"{path.name.split('.')[0]}{path.suffix}",
                "is_transaction": ".tx" in path.name.lower(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(timespec="seconds"),
                "size": stat.st_size,
                "source_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "_created_timestamp": stat.st_ctime,
            }
        )

    entries.sort(key=lambda item: item["_created_timestamp"], reverse=True)
    for entry in entries:
        entry.pop("_created_timestamp", None)
    capped = max(1, min(limit, 500))
    return {"backup_dir": str(config.backup_dir.resolve()), "transactions": entries[:capped]}


def transaction_rollback(
    config: GeckConfig,
    plugin_name: str,
    transaction_id_or_path: str,
    create_pre_rollback_backup: bool = True,
) -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    source_backup = _safe_backup_file(config, transaction_id_or_path)
    if source_backup.suffix.lower() != plugin.suffix.lower():
        raise GeckAutomationError("Backup suffix does not match the target plugin suffix.")

    pre_rollback_backup: str | None = None
    if plugin.exists() and create_pre_rollback_backup:
        pre_rollback_backup = backup_plugin(config, plugin.name, label="pre_rollback")["backup"]

    _atomic_plugin_write(config, plugin, plugin.read_bytes(), source_backup.read_bytes())
    return {
        "plugin": str(plugin),
        "rolled_back_from": str(source_backup),
        "pre_rollback_backup": pre_rollback_backup,
        "status": plugin_status(config, plugin.name),
        "refs": esp_list_placed_refs(config, plugin.name)["refs"],
        "warning": "Rollback changed the file on disk. If this plugin is open in GECK, close/reload it before saving.",
    }


def transaction_verify(config: GeckConfig, plugin_name: str, backend: str = "win32") -> dict[str, Any]:
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Plugin")
    active: dict[str, Any]
    try:
        active = active_plugin(backend)
    except Exception as exc:
        active = {"ok": False, "error": str(exc), "error_type": type(exc).__name__}

    refs_result = esp_list_placed_refs(config, plugin.name)
    return {
        "plugin": str(plugin),
        "status": plugin_status(config, plugin.name),
        "active_plugin": active,
        "ref_count": len(refs_result["refs"]),
        "refs": refs_result["refs"],
        "recent_transactions": transaction_list(config, plugin.name, limit=10)["transactions"],
        "warning": "Verification reads disk state. If GECK is already open, its in-memory state can still differ until reload.",
    }


def read_load_order(config: GeckConfig) -> dict[str, Any]:
    path = config.load_order_file
    if not path:
        return {"path": None, "exists": False, "plugins": []}
    if not path.exists():
        return {"path": str(path), "exists": False, "plugins": []}

    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    plugins = [
        line.strip().lstrip("*")
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    return {"path": str(path), "exists": True, "plugins": plugins, "raw_lines": lines}


def write_load_order(config: GeckConfig, plugins: list[str], backup: bool = True) -> dict[str, Any]:
    if not config.load_order_file:
        raise GeckAutomationError("LOCALAPPDATA is not set, so plugins.txt cannot be found.")

    known_plugins = {item["name"].lower(): item["name"] for item in list_data_files(config, include_bsa=False)}
    normalized: list[str] = []
    for plugin in plugins:
        clean = plugin.strip().lstrip("*")
        if clean.lower() not in known_plugins:
            raise GeckAutomationError(f"Plugin is not present in Data: {plugin}")
        normalized.append(known_plugins[clean.lower()])

    config.load_order_file.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if backup and config.load_order_file.exists():
        backup_path = config.load_order_file.with_suffix(f".{_timestamp()}.bak")
        shutil.copy2(config.load_order_file, backup_path)

    config.load_order_file.write_text("\n".join(normalized) + "\n", encoding="utf-8")
    return {
        "path": str(config.load_order_file),
        "plugins": normalized,
        "backup": str(backup_path) if backup_path else None,
    }


def tail_log(config: GeckConfig, log_name: str = "EditorWarnings.txt", lines: int = 80) -> dict[str, Any]:
    if log_name not in ALLOWED_LOG_NAMES:
        raise GeckAutomationError(f"Unsupported log name. Allowed: {', '.join(sorted(ALLOWED_LOG_NAMES))}")
    path = config.game_dir / log_name
    if not path.exists():
        return {"path": str(path), "exists": False, "text": ""}

    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "path": str(path),
        "exists": True,
        "line_count": len(content),
        "text": "\n".join(content[-max(1, min(lines, 1000)) :]),
    }


def active_plugin(backend: str = "win32") -> dict[str, Any]:
    main = _resolve_window(WindowSelector(title_regex=r".*Garden of Eden Creation Kit.*", backend=backend))
    title = main.window_text()
    match = re.search(r"\[([^\]]+\.(?:esp|esm))\]", title, re.IGNORECASE)
    return {
        "plugin": match.group(1) if match else None,
        "title": title,
        "window": _window_info(main),
    }


def status_bar(backend: str = "win32") -> dict[str, Any]:
    main = _resolve_window(WindowSelector(title_regex=r".*Garden of Eden Creation Kit.*", backend=backend))
    bars = _try(lambda: main.descendants(class_name="msctls_statusbar32"), [])
    if not bars:
        raise GeckAutomationError("GECK status bar was not found.")
    bar = bars[0]
    part_count = _try(lambda: bar.part_count(), 0)
    parts = [_try(lambda index=i: bar.get_part_text(index), "") for i in range(part_count)]
    result: dict[str, Any] = {
        "window": _window_info(main),
        "parts": parts,
        "selected_editor_id": parts[0] if len(parts) > 0 else "",
        "selected_type": parts[1] if len(parts) > 1 else "",
        "coordinate_text": parts[2] if len(parts) > 2 else "",
        "render_stats": parts[3] if len(parts) > 3 else "",
    }

    coordinate_text = result["coordinate_text"]
    match = re.search(
        r"(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\s*"
        r"\[\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\s*\]"
        r"\s*\(([^)]+)\)",
        coordinate_text,
    )
    if match:
        x, y, z, rx, ry, rz, cell = match.groups()
        result["position"] = {"x": float(x), "y": float(y), "z": float(z)}
        result["rotation"] = {"x": float(rx), "y": float(ry), "z": float(rz)}
        result["cell"] = cell
    else:
        match = re.search(
            r"(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\s*"
            r"\(([^)]+)\)",
            coordinate_text,
        )
        if match:
            x, y, z, cell = match.groups()
            result["position"] = {"x": float(x), "y": float(y), "z": float(z)}
            result["cell"] = cell
    return result


def placement_plan_from_status_bar(
    backend: str = "win32",
    object_kind: str = "generic",
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    use_status_rotation: bool = False,
    rot_x: float | None = None,
    rot_y: float | None = None,
    rot_z: float | None = None,
) -> dict[str, Any]:
    status = status_bar(backend)
    position = status.get("position")
    if not position:
        raise GeckAutomationError("GECK status bar does not currently contain parseable coordinates.")

    rotation, rotation_source, warnings = _choose_rotation(
        status=status,
        existing_ref=None,
        use_status_rotation=use_status_rotation,
        preserve_existing_rotation=False,
        explicit_rotation=(rot_x, rot_y, rot_z),
    )
    target = _dict_position(position, (offset_x, offset_y, offset_z))

    kind = object_kind.strip().lower()
    if status.get("selected_editor_id") == "Camera":
        warnings.append("Status bar is showing the camera coordinate, not a selected floor/object reference.")
    if kind in {"weapon", "item", "misc", "misc item"}:
        warnings.append("Weapon/item origins are often above or inside the mesh; verify final contact in Render Window.")
    elif kind in {"npc", "actor", "achr"}:
        warnings.append("Actor placement also needs navmesh, package, ownership/faction, and collision checks.")
    elif kind in {"creature", "acre"}:
        warnings.append("Creature placement also needs navmesh, AI package, and collision checks.")
    elif kind in {"light", "ligh"}:
        warnings.append("Light placement needs radius/color/flicker verification; coordinates only place the emitter.")
    elif kind in {"navmesh", "navm"}:
        warnings.append("NAVM data must not be edited with generic placed-ref patch tools.")

    if offset_z == 0.0:
        warnings.append("No Z offset was applied; object origin may still float or clip.")

    return {
        "source_status_bar": status,
        "target_position": target,
        "target_rotation": rotation,
        "rotation_source": rotation_source,
        "offset": {"x": offset_x, "y": offset_y, "z": offset_z},
        "object_kind": object_kind,
        "warnings": warnings,
        "write_tool": "geck_esp_patch_ref_to_status_bar_offset",
    }


def esp_patch_ref_to_status_bar_offset(
    config: GeckConfig,
    plugin_name: str,
    ref_form_id: str | int,
    backend: str = "win32",
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    use_status_rotation: bool = False,
    preserve_existing_rotation: bool = True,
    rot_x: float | None = None,
    rot_y: float | None = None,
    rot_z: float | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    status = status_bar(backend)
    position = status.get("position")
    if not position:
        raise GeckAutomationError("GECK status bar does not currently contain parseable coordinates.")

    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Plugin")
    target = _parse_form_id(ref_form_id)
    existing_ref = _find_placed_record(plugin.read_bytes(), target)
    if not existing_ref:
        raise GeckAutomationError(f"Placed form ID was not found: {_format_form_id(target)}")

    target_position = _dict_position(position, (offset_x, offset_y, offset_z))
    target_rotation, rotation_source, warnings = _choose_rotation(
        status=status,
        existing_ref=existing_ref,
        use_status_rotation=use_status_rotation,
        preserve_existing_rotation=preserve_existing_rotation,
        explicit_rotation=(rot_x, rot_y, rot_z),
    )

    # Legacy entry point now produces an explicit deferred command. Capturing a
    # live status bar and writing to the same loaded plugin cannot be safe.
    return {
        "ok": False, "applied": False,
        "error": "Live status-bar patching is disabled. Save authorized UI changes, close GECK, then apply the captured arguments with geck_esp_patch_ref_position.",
        "next_tool": "geck_esp_patch_ref_position",
        "arguments": {"plugin_name": plugin.name, "ref_form_id": _format_form_id(target),
                      "game_dir": str(config.game_dir), **target_position,
                      "rot_x": target_rotation["x"], "rot_y": target_rotation["y"],
                      "rot_z": target_rotation["z"], "backup": backup},
        "source_status_bar": status, "rotation_source": rotation_source,
        "placement_warnings": warnings,
    }


def esp_patch_ref_to_status_bar(
    config: GeckConfig,
    plugin_name: str,
    ref_form_id: str | int,
    backend: str = "win32",
    backup: bool = True,
) -> dict[str, Any]:
    return esp_patch_ref_to_status_bar_offset(
        config=config,
        plugin_name=plugin_name,
        ref_form_id=ref_form_id,
        backend=backend,
        backup=backup,
    )


def launch_geck(config: GeckConfig, via_nvse: bool = False, extra_args: list[str] | None = None) -> dict[str, Any]:
    _require_windows()
    _require_dir(config.game_dir, "Fallout: New Vegas directory")

    if via_nvse:
        executable = config.nvse_loader
        args = [str(executable), "-editor"]
        _require_file(executable, "NVSE loader")
    else:
        executable = config.geck_exe
        args = [str(executable)]
        _require_file(executable, "GECK executable")

    if extra_args:
        args.extend(extra_args)

    process = subprocess.Popen(args, cwd=config.game_dir)
    return {
        "pid": process.pid,
        "args": args,
        "cwd": str(config.game_dir),
        "via_nvse": via_nvse,
    }


def list_geck_processes(config: GeckConfig) -> list[dict[str, Any]]:
    try:
        import psutil
    except Exception as exc:
        raise GeckAutomationError("psutil is required for process listing.") from exc

    names = {"geck.exe", "nvse_loader.exe"}
    processes: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cwd", "create_time"]):
        try:
            info = proc.info
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        name = (info.get("name") or "").lower()
        exe = info.get("exe") or ""
        if name not in names and str(config.game_dir).lower() not in exe.lower():
            continue
        processes.append(
            {
                "pid": info.get("pid"),
                "name": info.get("name"),
                "exe": exe,
                "cwd": info.get("cwd"),
                "create_time": info.get("create_time"),
            }
        )
    return processes


def _serialize_rect(rect: Any) -> dict[str, int]:
    return {
        "left": int(rect.left),
        "top": int(rect.top),
        "right": int(rect.right),
        "bottom": int(rect.bottom),
        "width": int(rect.width()),
        "height": int(rect.height()),
    }


def _desktop(backend: str):
    _require_windows()
    try:
        from pywinauto import Desktop
    except Exception as exc:
        raise GeckAutomationError("pywinauto is required for window automation.") from exc
    return Desktop(backend=backend)


def _window_info(window: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "handle": int(window.handle),
        "title": _try(lambda: window.window_text(), ""),
        "class_name": _try(lambda: window.class_name(), ""),
        "process_id": _try(lambda: window.process_id(), None),
        "visible": _try(lambda: window.is_visible(), None),
        "enabled": _try(lambda: window.is_enabled(), None),
    }
    rect = _try(lambda: window.rectangle(), None)
    if rect is not None:
        info["rectangle"] = _serialize_rect(rect)
    return info


def _normalize_editor_id(value: str) -> str:
    return value.strip().removesuffix("*").strip()


def _list_views(window: Any) -> list[Any]:
    return sorted(
        _try(lambda: window.descendants(class_name="SysListView32"), []),
        key=lambda control: (control.rectangle().left, control.rectangle().top),
    )


def _edits(window: Any) -> list[Any]:
    return sorted(
        _try(lambda: window.descendants(class_name="Edit"), []),
        key=lambda control: (control.rectangle().top, control.rectangle().left),
    )


def _combos(window: Any) -> list[Any]:
    return sorted(
        _try(lambda: window.descendants(class_name="ComboBox"), []),
        key=lambda control: (control.rectangle().top, control.rectangle().left),
    )


def _buttons(window: Any) -> list[Any]:
    return sorted(
        _try(lambda: window.descendants(class_name="Button"), []),
        key=lambda control: (control.rectangle().top, control.rectangle().left),
    )


def _row_values(list_view: Any, row_index: int, max_columns: int | None = None) -> list[str]:
    column_count = _try(lambda: list_view.column_count(), 0)
    if max_columns is not None:
        column_count = min(column_count, max_columns)
    values: list[str] = []
    for column_index in range(column_count):
        values.append(_try(lambda c=column_index: list_view.get_item(row_index, c).text(), ""))
    return values


def _list_view_rows(
    list_view: Any,
    start_row: int = 0,
    max_rows: int = 50,
    max_columns: int | None = None,
) -> dict[str, Any]:
    item_count = _try(lambda: list_view.item_count(), 0)
    rows = []
    start = max(0, min(start_row, item_count))
    stop = min(item_count, start + max(1, min(max_rows, 500)))
    for row_index in range(start, stop):
        rows.append({"row_index": row_index, "values": _row_values(list_view, row_index, max_columns)})
    return {
        "handle": int(list_view.handle),
        "item_count": item_count,
        "column_count": _try(lambda: list_view.column_count(), None),
        "start_row": start,
        "rows": rows,
    }


def _find_rows(
    list_view: Any,
    query: str,
    column: int = 0,
    exact: bool = True,
    max_matches: int = 25,
) -> list[dict[str, Any]]:
    needle = _normalize_editor_id(query).lower()
    matches: list[dict[str, Any]] = []
    item_count = _try(lambda: list_view.item_count(), 0)
    column_count = _try(lambda: list_view.column_count(), 0)

    for row_index in range(item_count):
        values = _row_values(list_view, row_index)
        haystacks = [values[column]] if 0 <= column < len(values) else values
        for value in haystacks:
            normalized = _normalize_editor_id(value).lower()
            matched = normalized == needle if exact else needle in normalized
            if matched:
                matches.append({"row_index": row_index, "values": values[:column_count]})
                break
        if len(matches) >= max_matches:
            break
    return matches


def _select_list_row(list_view: Any, row_index: int, double: bool = False) -> None:
    item = list_view.select(row_index)
    if double:
        item.click_input(double=True)


def list_view_rows(
    selector: WindowSelector,
    list_index: int = 0,
    start_row: int = 0,
    max_rows: int = 50,
    max_columns: int | None = None,
) -> dict[str, Any]:
    window = _resolve_window(selector)
    lists = _list_views(window)
    if list_index < 0 or list_index >= len(lists):
        raise GeckAutomationError(f"List index {list_index} is out of range. Found {len(lists)} lists.")
    return {"window": _window_info(window), "list": _list_view_rows(lists[list_index], start_row, max_rows, max_columns)}


def find_list_rows(
    selector: WindowSelector,
    query: str,
    list_index: int = 0,
    column: int = 0,
    exact: bool = True,
    max_matches: int = 25,
) -> dict[str, Any]:
    window = _resolve_window(selector)
    lists = _list_views(window)
    if list_index < 0 or list_index >= len(lists):
        raise GeckAutomationError(f"List index {list_index} is out of range. Found {len(lists)} lists.")
    return {
        "window": _window_info(window),
        "list_index": list_index,
        "query": query,
        "matches": _find_rows(lists[list_index], query, column, exact, max_matches),
    }


def _try(func, default):
    try:
        return func()
    except Exception:
        return default


def list_windows(backend: str = "win32", title_filter: str | None = None) -> list[dict[str, Any]]:
    desktop = _desktop(backend)
    pattern = re.compile(title_filter, re.IGNORECASE) if title_filter else None
    windows: list[dict[str, Any]] = []

    for window in desktop.windows():
        info = _window_info(window)
        searchable = f"{info.get('title', '')} {info.get('class_name', '')}"
        if pattern and not pattern.search(searchable):
            continue
        windows.append(info)
    return windows


def _resolve_window(selector: WindowSelector):
    desktop = _desktop(selector.backend)
    if selector.handle is not None:
        return desktop.window(handle=int(selector.handle))

    title_regex = selector.title_regex or r".*(GECK|G\.E\.C\.K\.|Garden of Eden).*"
    candidates = desktop.windows(title_re=title_regex)
    if not candidates:
        raise GeckAutomationError(f"No window matched title regex: {title_regex}")
    return candidates[0]


def focus_window(selector: WindowSelector) -> dict[str, Any]:
    window = _resolve_window(selector)
    if _try(lambda: window.is_minimized(), False):
        window.restore()
    window.set_focus()
    return _window_info(window)


def send_keys(selector: WindowSelector, keys: str, pause: float = 0.05, focus: bool = True) -> dict[str, Any]:
    if focus:
        focus_window(selector)
    try:
        from pywinauto.keyboard import send_keys as pywinauto_send_keys
    except Exception as exc:
        raise GeckAutomationError("pywinauto is required for keyboard automation.") from exc
    pywinauto_send_keys(keys, pause=pause)
    return {"sent": keys, "pause": pause}


def menu_select(selector: WindowSelector, menu_path: str) -> dict[str, Any]:
    window = _resolve_window(selector)
    window.set_focus()
    window.menu_select(menu_path)
    return {"menu_path": menu_path, "window": _window_info(window)}


def save_active_plugin(config: GeckConfig, backend: str = "win32", wait_seconds: float = 4.0) -> dict[str, Any]:
    before = active_plugin(backend)
    plugin_name = before.get("plugin")
    if not plugin_name:
        raise GeckAutomationError("No named active plugin. Use GECK Save As and inspect the dialog first.")
    plugin = _safe_data_file(config, plugin_name, PLUGIN_SUFFIXES)
    _require_file(plugin, "Active plugin")
    old_stat = plugin.stat()
    old_stamp = (old_stat.st_mtime_ns, old_stat.st_size)
    backup = backup_plugin(config, plugin_name)["backup"]
    main = _resolve_window(WindowSelector(title_regex=r".*Garden of Eden Creation Kit.*", backend=backend))
    main.set_focus()
    main.menu_select("File->Save")
    deadline = time.monotonic() + max(0.0, min(wait_seconds, 30.0))
    previous = None
    stable_since = time.monotonic()
    after = before
    while time.monotonic() < deadline:
        time.sleep(0.25)
        after = active_plugin(backend)
        try:
            stat = plugin.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp != previous:
                previous, stable_since = stamp, time.monotonic()
                continue
            if (stamp != old_stamp and time.monotonic() - stable_since >= 0.5
                    and after.get("plugin") == plugin_name
                    and "*" not in str(after.get("title", ""))
                    and main.is_enabled()):
                list(walk(plugin.read_bytes()))
                return {"before": before, "after": after, "saved": True,
                        "backup": backup, "plugin_status": plugin_status(config, plugin_name)}
        except (OSError, ValueError):
            # GECK may still be writing. Do not retry the Save command.
            continue
    return {"before": before, "after": after, "saved": False, "backup": backup,
            "reason": "Save not verified before timeout; inspect GECK dialogs and file state before retrying."}


def _control_info(control: Any) -> dict[str, Any]:
    info: dict[str, Any] = {
        "handle": _try(lambda: int(control.handle), None),
        "title": _try(lambda: control.window_text(), ""),
        "class_name": _try(lambda: control.class_name(), ""),
        "friendly_class_name": _try(lambda: control.friendly_class_name(), ""),
        "control_type": _try(lambda: control.element_info.control_type, ""),
        "automation_id": _try(lambda: control.element_info.automation_id, ""),
        "enabled": _try(lambda: control.is_enabled(), None),
        "visible": _try(lambda: control.is_visible(), None),
    }
    rect = _try(lambda: control.rectangle(), None)
    if rect is not None:
        info["rectangle"] = _serialize_rect(rect)
    return info


def control_tree(selector: WindowSelector, max_depth: int = 2) -> dict[str, Any]:
    window = _resolve_window(selector)
    max_depth = max(0, min(max_depth, 8))

    def walk(control: Any, depth: int) -> dict[str, Any]:
        node = _control_info(control)
        if depth >= max_depth:
            return node
        children = _try(lambda: control.children(), [])
        node["children"] = [walk(child, depth + 1) for child in children]
        return node

    return walk(window, 0)


def click_control(
    selector: WindowSelector,
    title: str | None = None,
    class_name: str | None = None,
    control_type: str | None = None,
    automation_id: str | None = None,
    found_index: int = 0,
    double: bool = False,
) -> dict[str, Any]:
    window = _resolve_window(selector)
    criteria: dict[str, Any] = {}
    if title:
        criteria["title"] = title
    if class_name:
        criteria["class_name"] = class_name
    if control_type:
        criteria["control_type"] = control_type
    if automation_id:
        criteria["auto_id"] = automation_id
    if not criteria:
        raise GeckAutomationError("Provide at least one control selector.")

    controls = window.descendants(**criteria)
    if found_index < 0 or found_index >= len(controls):
        raise GeckAutomationError(f"Control index {found_index} is out of range. Found {len(controls)} controls.")

    control = controls[found_index]
    window.set_focus()
    if double:
        control.double_click_input()
    else:
        control.click_input()
    return {"clicked": _control_info(control), "double": double}


def click_at(
    selector: WindowSelector,
    x: int,
    y: int,
    button: str = "left",
    relative_to_window: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    window = _resolve_window(selector)
    coords = (int(x), int(y))
    if relative_to_window:
        rect = window.rectangle()
        coords = (rect.left + int(x), rect.top + int(y))

    try:
        from pywinauto.mouse import click, double_click
    except Exception as exc:
        raise GeckAutomationError("pywinauto is required for mouse automation.") from exc

    window.set_focus()
    if double:
        double_click(button=button, coords=coords)
    else:
        click(button=button, coords=coords)

    return {"coords": {"x": coords[0], "y": coords[1]}, "button": button, "double": double}


def screenshot(selector: WindowSelector, config: GeckConfig, file_name: str | None = None) -> dict[str, Any]:
    window = _resolve_window(selector)
    config.screenshot_dir.mkdir(parents=True, exist_ok=True)
    target = config.screenshot_dir / (file_name or f"geck_{_timestamp()}.png")
    if Path(target.name).name != target.name or target.suffix.lower() != ".png":
        raise GeckAutomationError("Screenshot file name must be a bare .png name.")

    image = window.capture_as_image()
    image.save(target)
    return {"path": str(target), "window": _window_info(window)}


def open_data_dialog(selector: WindowSelector) -> dict[str, Any]:
    return menu_select(selector, "File->Data...")


def cell_view_snapshot(
    backend: str = "win32",
    max_cells: int = 30,
    max_refs: int = 50,
) -> dict[str, Any]:
    window = _resolve_window(WindowSelector(title_regex=r"^Cell View$", backend=backend))
    lists = _list_views(window)
    if len(lists) < 2:
        raise GeckAutomationError(f"Cell View should contain two list views. Found {len(lists)}.")

    combos = _combos(window)
    world_space = _try(lambda: combos[0].window_text().strip(), "") if combos else ""
    cell_list, ref_list = lists[0], lists[1]

    selected_cell: dict[str, Any] | None = None
    for row_index in range(_try(lambda: cell_list.item_count(), 0)):
        if _try(lambda r=row_index: cell_list.is_selected(r), False):
            selected_cell = _cell_row(cell_list, row_index)
            break

    return {
        "window": _window_info(window),
        "world_space": world_space,
        "selected_cell": selected_cell,
        "cells": [_cell_row(cell_list, row["row_index"]) for row in _list_view_rows(cell_list, 0, max_cells).get("rows", [])],
        "references": [_reference_row(ref_list, row["row_index"]) for row in _list_view_rows(ref_list, 0, max_refs).get("rows", [])],
        "cell_count": _try(lambda: cell_list.item_count(), 0),
        "reference_count": _try(lambda: ref_list.item_count(), 0),
    }


def _cell_row(cell_list: Any, row_index: int) -> dict[str, Any]:
    values = _row_values(cell_list, row_index, 6)
    values += [""] * (6 - len(values))
    editor_id = _normalize_editor_id(values[0])
    return {
        "row_index": row_index,
        "editor_id": editor_id,
        "modified": values[0].strip().endswith("*"),
        "form_id": values[1],
        "name": values[2],
        "location": values[3],
        "path": values[4],
        "owner": values[5],
        "values": values,
    }


def _reference_row(ref_list: Any, row_index: int) -> dict[str, Any]:
    values = _row_values(ref_list, row_index, 5)
    values += [""] * (5 - len(values))
    return {
        "row_index": row_index,
        "editor_id": _normalize_editor_id(values[0]),
        "form_id": values[1],
        "type": values[2],
        "owner": values[3],
        "lock_level": values[4],
        "values": values,
    }


def set_cell_view_world_space(world_space: str, backend: str = "win32") -> dict[str, Any]:
    window = _resolve_window(WindowSelector(title_regex=r"^Cell View$", backend=backend))
    combos = _combos(window)
    if not combos:
        raise GeckAutomationError("Cell View world-space combo box was not found.")
    combo = combos[0]
    window.set_focus()
    combo.select(world_space)
    time.sleep(0.2)
    return {"world_space": combo.window_text().strip(), "window": _window_info(window)}


def select_cell(
    editor_id: str,
    world_space: str | None = None,
    backend: str = "win32",
    exact: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    if world_space:
        set_cell_view_world_space(world_space, backend)

    window = _resolve_window(WindowSelector(title_regex=r"^Cell View$", backend=backend))
    lists = _list_views(window)
    if len(lists) < 2:
        raise GeckAutomationError(f"Cell View should contain two list views. Found {len(lists)}.")

    cell_list = lists[0]
    matches = _find_rows(cell_list, editor_id, column=0, exact=exact, max_matches=10)
    if not matches:
        raise GeckAutomationError(f"Cell Editor ID not found in current Cell View list: {editor_id}")
    if exact and len(matches) > 1:
        raise GeckAutomationError(f"Cell Editor ID matched multiple rows: {editor_id}")

    row_index = matches[0]["row_index"]
    window.set_focus()
    _select_list_row(cell_list, row_index, double=double)
    time.sleep(0.2)
    return {
        "selected_cell": _cell_row(cell_list, row_index),
        "matches": matches,
        "window": _window_info(window),
    }


def go_to_exterior_cell(
    world_space: str,
    x: int,
    y: int,
    backend: str = "win32",
) -> dict[str, Any]:
    set_cell_view_world_space(world_space, backend)
    window = _resolve_window(WindowSelector(title_regex=r"^Cell View$", backend=backend))
    edits = _edits(window)
    buttons = _buttons(window)
    if len(edits) < 2:
        raise GeckAutomationError("Cell View X/Y edit fields were not found.")
    go_buttons = [button for button in buttons if button.window_text() == "Go"]
    if not go_buttons:
        raise GeckAutomationError("Cell View Go button was not found.")

    window.set_focus()
    edits[0].set_edit_text(str(x))
    edits[1].set_edit_text(str(y))
    go_buttons[0].click_input()
    time.sleep(0.5)
    return {"world_space": world_space, "x": x, "y": y, "window": _window_info(window)}


def find_cell_references(
    query: str,
    backend: str = "win32",
    column: int = 0,
    exact: bool = False,
    max_matches: int = 25,
) -> dict[str, Any]:
    window = _resolve_window(WindowSelector(title_regex=r"^Cell View$", backend=backend))
    lists = _list_views(window)
    if len(lists) < 2:
        raise GeckAutomationError(f"Cell View should contain two list views. Found {len(lists)}.")
    ref_list = lists[1]
    matches = _find_rows(ref_list, query, column=column, exact=exact, max_matches=max_matches)
    return {
        "query": query,
        "matches": [_reference_row(ref_list, match["row_index"]) for match in matches],
        "window": _window_info(window),
    }


def select_cell_reference(
    query: str,
    backend: str = "win32",
    column: int = 0,
    exact: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    window = _resolve_window(WindowSelector(title_regex=r"^Cell View$", backend=backend))
    lists = _list_views(window)
    if len(lists) < 2:
        raise GeckAutomationError(f"Cell View should contain two list views. Found {len(lists)}.")
    ref_list = lists[1]
    matches = _find_rows(ref_list, query, column=column, exact=exact, max_matches=10)
    if not matches:
        raise GeckAutomationError(f"Cell reference not found: {query}")

    row_index = matches[0]["row_index"]
    window.set_focus()
    _select_list_row(ref_list, row_index, double=double)
    return {
        "selected_reference": _reference_row(ref_list, row_index),
        "matches": [_reference_row(ref_list, match["row_index"]) for match in matches],
        "window": _window_info(window),
    }


def object_window_snapshot(
    backend: str = "win32",
    max_rows: int = 50,
) -> dict[str, Any]:
    window = _resolve_window(WindowSelector(title_regex=r"^Object Window$", backend=backend))
    lists = _list_views(window)
    if not lists:
        raise GeckAutomationError("Object Window list view was not found.")
    list_view = lists[0]
    rows = []
    for row in _list_view_rows(list_view, 0, max_rows).get("rows", []):
        values = row["values"]
        rows.append(
            {
                "row_index": row["row_index"],
                "editor_id": _normalize_editor_id(values[0]) if values else "",
                "form_id": values[1] if len(values) > 1 else "",
                "count": values[2] if len(values) > 2 else "",
                "users": values[3] if len(values) > 3 else "",
                "type": values[4] if len(values) > 4 else "",
                "name": values[5] if len(values) > 5 else "",
                "values": values,
            }
        )
    return {"window": _window_info(window), "row_count": _try(lambda: list_view.item_count(), 0), "rows": rows}


def object_window_filter(text: str, backend: str = "win32") -> dict[str, Any]:
    window = _resolve_window(WindowSelector(title_regex=r"^Object Window$", backend=backend))
    edits = _edits(window)
    if not edits:
        raise GeckAutomationError("Object Window filter edit was not found.")
    window.set_focus()
    edits[0].set_edit_text(text)
    time.sleep(0.3)
    return object_window_snapshot(backend=backend, max_rows=50)


def select_object_record(
    editor_id: str,
    backend: str = "win32",
    exact: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    window = _resolve_window(WindowSelector(title_regex=r"^Object Window$", backend=backend))
    lists = _list_views(window)
    if not lists:
        raise GeckAutomationError("Object Window list view was not found.")
    list_view = lists[0]
    matches = _find_rows(list_view, editor_id, column=0, exact=exact, max_matches=10)
    if not matches:
        raise GeckAutomationError(f"Object Editor ID not found in current Object Window list: {editor_id}")
    row_index = matches[0]["row_index"]
    window.set_focus()
    _select_list_row(list_view, row_index, double=double)
    values = _row_values(list_view, row_index)
    return {
        "selected_record": {
            "row_index": row_index,
            "editor_id": _normalize_editor_id(values[0]) if values else "",
            "form_id": values[1] if len(values) > 1 else "",
            "values": values,
        },
        "matches": matches,
        "window": _window_info(window),
    }


def place_object_in_render(
    editor_id: str,
    render_title_regex: str | None = None,
    backend: str = "win32",
    drop_x_ratio: float = 0.82,
    drop_y_ratio: float = 0.42,
    dry_run: bool = False,
) -> dict[str, Any]:
    try:
        from pywinauto.mouse import move, press, release
    except Exception as exc:
        raise GeckAutomationError("pywinauto is required for mouse drag automation.") from exc

    object_window_filter(editor_id, backend=backend)
    selected = select_object_record(editor_id, backend=backend, exact=True, double=False)
    object_window = _resolve_window(WindowSelector(title_regex=r"^Object Window$", backend=backend))
    object_lists = _list_views(object_window)
    if not object_lists:
        raise GeckAutomationError("Object Window list view was not found.")

    object_list = object_lists[0]
    matches = _find_rows(object_list, editor_id, column=0, exact=True, max_matches=1)
    if not matches:
        raise GeckAutomationError(f"Object Editor ID not found after selecting: {editor_id}")

    row_index = matches[0]["row_index"]
    item = object_list.get_item(row_index, 0)
    item_rect = item.rectangle()
    list_rect = object_list.rectangle()
    start = (
        list_rect.left + item_rect.left + min(30, max(5, item_rect.width() // 2)),
        list_rect.top + item_rect.top + max(5, item_rect.height() // 2),
    )

    render_regex = render_title_regex or r".*\[Free camera, perspective\].*"
    render_window = _resolve_window(WindowSelector(title_regex=render_regex, backend=backend))
    render_rect = render_window.rectangle()
    drop_x_ratio = max(0.05, min(drop_x_ratio, 0.95))
    drop_y_ratio = max(0.05, min(drop_y_ratio, 0.95))
    end = (
        render_rect.left + int(render_rect.width() * drop_x_ratio),
        render_rect.top + int(render_rect.height() * drop_y_ratio),
    )

    result: dict[str, Any] = {
        "selected": selected.get("selected_record", selected),
        "object_filter": editor_id,
        "object_window": _window_info(object_window),
        "render_window": _window_info(render_window),
        "start": {"x": start[0], "y": start[1]},
        "end": {"x": end[0], "y": end[1]},
        "dry_run": dry_run,
    }
    if dry_run:
        return result

    press(button="left", coords=start)
    time.sleep(0.25)
    for step in range(1, 16):
        x = start[0] + (end[0] - start[0]) * step // 15
        y = start[1] + (end[1] - start[1]) * step // 15
        move(coords=(x, y))
        time.sleep(0.04)
    time.sleep(0.2)
    release(button="left", coords=end)
    time.sleep(1.0)
    result["placed"] = True
    return result


def normalize_menu_path(menu_path: str | Iterable[str]) -> str:
    if isinstance(menu_path, str):
        return menu_path
    return "->".join(str(part) for part in menu_path)
