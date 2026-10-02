from __future__ import annotations

from typing import Any

try:  # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # SDK 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

from .config import get_config
from .geck import (
    GeckAutomationError,
    WindowSelector,
    active_plugin,
    backup_plugin,
    cell_view_snapshot,
    click_at,
    click_control,
    control_tree,
    doctor,
    esp_delete_refs,
    esp_delete_refs_by_base,
    esp_find_nearby_refs,
    esp_list_placed_refs,
    esp_patch_ref_position,
    esp_patch_ref_to_status_bar,
    esp_patch_ref_to_status_bar_offset,
    find_cell_references,
    find_list_rows,
    focus_window,
    go_to_exterior_cell,
    launch_geck,
    list_data_files,
    list_geck_processes,
    list_view_rows,
    list_windows,
    menu_select,
    normalize_menu_path,
    open_data_dialog,
    object_window_filter,
    object_window_snapshot,
    place_object_in_render,
    placement_plan_from_status_bar,
    placement_report,
    plugin_status,
    read_load_order,
    save_active_plugin,
    screenshot,
    select_cell,
    select_cell_reference,
    select_object_record,
    send_keys,
    set_cell_view_world_space,
    status_bar,
    tail_log,
    transaction_begin,
    transaction_list,
    transaction_rollback,
    transaction_verify,
    write_load_order,
)


mcp = FastMCP("geck-mcp-nv")


def _config(game_dir: str | None = None):
    return get_config(game_dir)


def _selector(
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
) -> WindowSelector:
    return WindowSelector(handle=handle, title_regex=title_regex, backend=backend)


def _run(func, *args, **kwargs) -> Any:
    try:
        return func(*args, **kwargs)
    except GeckAutomationError as exc:
        return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "error_type": type(exc).__name__}


def _as_ok_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        if result.get("ok") is False:
            return result
        return {"ok": True, **result}
    return {"ok": True, "result": result}


def _as_ok_list(key: str, result: Any) -> dict[str, Any]:
    if isinstance(result, dict) and result.get("ok") is False:
        return result
    return {"ok": True, key: result}


@mcp.tool()
def geck_doctor(game_dir: str | None = None) -> dict[str, Any]:
    """Check paths and optional dependencies for this GECK MCP server."""
    return doctor(_config(game_dir))


@mcp.tool()
def geck_list_plugins(game_dir: str | None = None, include_bsa: bool = False) -> dict[str, Any]:
    """List plugin files in the Fallout: New Vegas Data folder."""
    result = _run(list_data_files, _config(game_dir), include_bsa)
    return _as_ok_list("files", result)


@mcp.tool()
def geck_backup_plugin(
    plugin_name: str,
    game_dir: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Copy an .esm or .esp from Data into the MCP backup directory."""
    result = _run(backup_plugin, _config(game_dir), plugin_name, label)
    return _as_ok_dict(result)


@mcp.tool()
def geck_plugin_status(
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    backup: bool = False,
) -> dict[str, Any]:
    """Check whether an .esp/.esm exists in Data, optionally creating a backup."""
    result = _run(plugin_status, _config(game_dir), plugin_name, backup)
    return _as_ok_dict(result)


@mcp.tool()
def geck_transaction_begin(
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Create a named rollback point before direct ESP/ESM file edits."""
    result = _run(transaction_begin, _config(game_dir), plugin_name, label)
    return _as_ok_dict(result)


@mcp.tool()
def geck_transaction_list(
    plugin_name: str | None = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """List recent MCP backup/transaction files, newest first."""
    result = _run(transaction_list, _config(game_dir), plugin_name, limit)
    return _as_ok_dict(result)


@mcp.tool()
def geck_transaction_rollback(
    transaction_id_or_path: str,
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    create_pre_rollback_backup: bool = True,
) -> dict[str, Any]:
    """Restore a plugin from a transaction id or backup path inside the MCP backup directory."""
    result = _run(transaction_rollback, _config(game_dir), plugin_name, transaction_id_or_path, create_pre_rollback_backup)
    return _as_ok_dict(result)


@mcp.tool()
def geck_transaction_verify(
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    backend: str = "win32",
) -> dict[str, Any]:
    """Verify on-disk plugin state, active GECK plugin, placed records, and recent rollback points."""
    result = _run(transaction_verify, _config(game_dir), plugin_name, backend)
    return _as_ok_dict(result)


@mcp.tool()
def geck_esp_list_refs(plugin_name: str = "AI_Test_DoNotUse.esp", game_dir: str | None = None) -> dict[str, Any]:
    """Read placed REFR/ACHR/ACRE records from an .esp/.esm file."""
    result = _run(esp_list_placed_refs, _config(game_dir), plugin_name)
    return _as_ok_dict(result)


@mcp.tool()
def geck_esp_patch_ref_position(
    ref_form_id: str,
    x: float,
    y: float,
    z: float,
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    rot_x: float | None = None,
    rot_y: float | None = None,
    rot_z: float | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Patch a placed record with GECK closed. Rotation is in radians; omitted axes are preserved."""
    result = _run(esp_patch_ref_position, _config(game_dir), plugin_name, ref_form_id, x, y, z, rot_x, rot_y, rot_z, backup)
    return _as_ok_dict(result)


@mcp.tool()
def geck_esp_nearby_refs(
    x: float,
    y: float,
    z: float,
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    radius: float = 256.0,
    cell_form_id: str | None = None,
) -> dict[str, Any]:
    """Find placed records in a plugin near a coordinate."""
    result = _run(esp_find_nearby_refs, _config(game_dir), plugin_name, x, y, z, radius, cell_form_id)
    return _as_ok_dict(result)


@mcp.tool()
def geck_placement_report(
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    backend: str = "win32",
    suspicious_distance: float = 1024.0,
    suspicious_z_delta: float = 512.0,
    cell_form_id: str | None = None,
) -> dict[str, Any]:
    """Assess saved placed records against the status bar, restricted to the required anchor cell_form_id."""
    result = _run(placement_report, _config(game_dir), plugin_name, backend, suspicious_distance, suspicious_z_delta, cell_form_id)
    return _as_ok_dict(result)


@mcp.tool()
def geck_status_bar(backend: str = "win32") -> dict[str, Any]:
    """Read GECK's bottom status bar, including selected object coordinates when available."""
    result = _run(status_bar, backend)
    return _as_ok_dict(result)


@mcp.tool()
def geck_placement_plan_from_status_bar(
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
    """Dry-run a target position/rotation from GECK's status-bar coordinate plus offsets."""
    result = _run(
        placement_plan_from_status_bar,
        backend,
        object_kind,
        offset_x,
        offset_y,
        offset_z,
        use_status_rotation,
        rot_x,
        rot_y,
        rot_z,
    )
    return _as_ok_dict(result)


@mcp.tool()
def geck_esp_patch_ref_to_status_bar(
    ref_form_id: str,
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    backend: str = "win32",
    backup: bool = True,
) -> dict[str, Any]:
    """Legacy planning only: capture deferred patch arguments; never writes while GECK is open. Returns applied=false."""
    result = _run(esp_patch_ref_to_status_bar, _config(game_dir), plugin_name, ref_form_id, backend, backup)
    return _as_ok_dict(result)


@mcp.tool()
def geck_esp_patch_ref_to_status_bar_offset(
    ref_form_id: str,
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
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
    """Legacy planning only: capture deferred patch arguments plus offsets; returns applied=false without writing."""
    result = _run(
        esp_patch_ref_to_status_bar_offset,
        _config(game_dir),
        plugin_name,
        ref_form_id,
        backend,
        offset_x,
        offset_y,
        offset_z,
        use_status_rotation,
        preserve_existing_rotation,
        rot_x,
        rot_y,
        rot_z,
        backup,
    )
    return _as_ok_dict(result)


@mcp.tool()
def geck_esp_delete_refs(
    ref_form_ids: list[str],
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Delete placed records directly from an .esp/.esm file and update group sizes."""
    result = _run(esp_delete_refs, _config(game_dir), plugin_name, ref_form_ids, backup)
    return _as_ok_dict(result)


@mcp.tool()
def geck_esp_delete_refs_by_base(
    base_form_ids: list[str],
    plugin_name: str = "AI_Test_DoNotUse.esp",
    game_dir: str | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Delete placed records whose NAME/base FormID matches one of the given base IDs."""
    result = _run(esp_delete_refs_by_base, _config(game_dir), plugin_name, base_form_ids, backup)
    return _as_ok_dict(result)


@mcp.tool()
def geck_active_plugin(backend: str = "win32") -> dict[str, Any]:
    """Read the active plugin name from the GECK main window title."""
    result = _run(active_plugin, backend)
    return _as_ok_dict(result)


@mcp.tool()
def geck_save_active_plugin(
    game_dir: str | None = None,
    backend: str = "win32",
    wait_seconds: float = 4.0,
) -> dict[str, Any]:
    """Save the active GECK plugin through File > Save and return plugin status."""
    result = _run(save_active_plugin, _config(game_dir), backend, wait_seconds)
    return _as_ok_dict(result)


@mcp.tool()
def geck_read_load_order(game_dir: str | None = None) -> dict[str, Any]:
    """Read the Fallout: New Vegas plugins.txt load order."""
    result = _run(read_load_order, _config(game_dir))
    return _as_ok_dict(result)


@mcp.tool()
def geck_write_load_order(
    plugins: list[str],
    game_dir: str | None = None,
    backup: bool = True,
) -> dict[str, Any]:
    """Rewrite the Fallout: New Vegas plugins.txt load order after validating plugin names."""
    result = _run(write_load_order, _config(game_dir), plugins, backup)
    return _as_ok_dict(result)


@mcp.tool()
def geck_tail_log(
    log_name: str = "EditorWarnings.txt",
    lines: int = 80,
    game_dir: str | None = None,
) -> dict[str, Any]:
    """Read the tail of a known GECK or NVSE log file."""
    result = _run(tail_log, _config(game_dir), log_name, lines)
    return _as_ok_dict(result)


@mcp.tool()
def geck_launch(
    game_dir: str | None = None,
    via_nvse: bool = False,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Launch GECK normally, or with NVSE via nvse_loader.exe -editor."""
    result = _run(launch_geck, _config(game_dir), via_nvse, extra_args)
    return _as_ok_dict(result)


@mcp.tool()
def geck_list_processes(game_dir: str | None = None) -> dict[str, Any]:
    """List GECK and NVSE-related processes."""
    result = _run(list_geck_processes, _config(game_dir))
    return _as_ok_list("processes", result)


@mcp.tool()
def geck_list_windows(
    backend: str = "win32",
    title_filter: str | None = None,
) -> dict[str, Any]:
    """List top-level desktop windows visible to pywinauto."""
    result = _run(list_windows, backend, title_filter)
    return _as_ok_list("windows", result)


@mcp.tool()
def geck_focus_window(
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
) -> dict[str, Any]:
    """Focus the GECK main window or a matching dialog."""
    result = _run(focus_window, _selector(handle, title_regex, backend))
    return _as_ok_dict(result)


@mcp.tool()
def geck_control_tree(
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
    max_depth: int = 2,
) -> dict[str, Any]:
    """Dump a GECK window/control tree for planning UI automation."""
    result = _run(control_tree, _selector(handle, title_regex, backend), max_depth)
    return _as_ok_dict(result)


@mcp.tool()
def geck_list_view_rows(
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
    list_index: int = 0,
    start_row: int = 0,
    max_rows: int = 50,
    max_columns: int | None = None,
) -> dict[str, Any]:
    """Read rows from a Win32 ListView in a GECK window or dialog."""
    result = _run(list_view_rows, _selector(handle, title_regex, backend), list_index, start_row, max_rows, max_columns)
    return _as_ok_dict(result)


@mcp.tool()
def geck_find_list_rows(
    query: str,
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
    list_index: int = 0,
    column: int = 0,
    exact: bool = True,
    max_matches: int = 25,
) -> dict[str, Any]:
    """Find rows in a GECK ListView by text, usually Editor ID or Form ID."""
    result = _run(
        find_list_rows,
        _selector(handle, title_regex, backend),
        query,
        list_index,
        column,
        exact,
        max_matches,
    )
    return _as_ok_dict(result)


@mcp.tool()
def geck_send_keys(
    keys: str,
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
    pause: float = 0.05,
    focus: bool = True,
) -> dict[str, Any]:
    """Send a pywinauto key sequence to GECK, such as ^s, %{F4}, or {ENTER}."""
    result = _run(send_keys, _selector(handle, title_regex, backend), keys, pause, focus)
    return _as_ok_dict(result)


@mcp.tool()
def geck_menu_select(
    menu_path: str | list[str],
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
) -> dict[str, Any]:
    """Select a GECK menu path, for example File->Data... or ['File', 'Save']."""
    result = _run(menu_select, _selector(handle, title_regex, backend), normalize_menu_path(menu_path))
    return _as_ok_dict(result)


@mcp.tool()
def geck_open_data_dialog(
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
) -> dict[str, Any]:
    """Open GECK's File > Data dialog."""
    result = _run(open_data_dialog, _selector(handle, title_regex, backend))
    return _as_ok_dict(result)


@mcp.tool()
def geck_click_control(
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
    title: str | None = None,
    class_name: str | None = None,
    control_type: str | None = None,
    automation_id: str | None = None,
    found_index: int = 0,
    double: bool = False,
) -> dict[str, Any]:
    """Click a child control found by title, class, UIA type, or automation id."""
    result = _run(
        click_control,
        _selector(handle, title_regex, backend),
        title,
        class_name,
        control_type,
        automation_id,
        found_index,
        double,
    )
    return _as_ok_dict(result)


@mcp.tool()
def geck_click_at(
    x: int,
    y: int,
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
    button: str = "left",
    relative_to_window: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    """Click coordinates, window-relative by default."""
    result = _run(
        click_at,
        _selector(handle, title_regex, backend),
        x,
        y,
        button,
        relative_to_window,
        double,
    )
    return _as_ok_dict(result)


@mcp.tool()
def geck_screenshot(
    handle: int | None = None,
    title_regex: str | None = None,
    backend: str = "win32",
    file_name: str | None = None,
    game_dir: str | None = None,
) -> dict[str, Any]:
    """Capture a screenshot of a GECK window or dialog as a PNG file."""
    result = _run(screenshot, _selector(handle, title_regex, backend), _config(game_dir), file_name)
    return _as_ok_dict(result)


@mcp.tool()
def geck_cell_view_snapshot(
    backend: str = "win32",
    max_cells: int = 30,
    max_refs: int = 50,
) -> dict[str, Any]:
    """Read Cell View state: world space, selected cell, visible cells, and current cell references."""
    result = _run(cell_view_snapshot, backend, max_cells, max_refs)
    return _as_ok_dict(result)


@mcp.tool()
def geck_cell_set_world_space(world_space: str, backend: str = "win32") -> dict[str, Any]:
    """Set Cell View's world-space combo box, e.g. Interiors or Wasteland."""
    result = _run(set_cell_view_world_space, world_space, backend)
    return _as_ok_dict(result)


@mcp.tool()
def geck_cell_select(
    editor_id: str,
    world_space: str | None = None,
    backend: str = "win32",
    exact: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    """Select an interior/exterior cell in Cell View by Editor ID."""
    result = _run(select_cell, editor_id, world_space, backend, exact, double)
    return _as_ok_dict(result)


@mcp.tool()
def geck_cell_go_to_exterior(
    world_space: str,
    x: int,
    y: int,
    backend: str = "win32",
) -> dict[str, Any]:
    """Use Cell View's world-space/X/Y/Go controls to jump to an exterior cell."""
    result = _run(go_to_exterior_cell, world_space, x, y, backend)
    return _as_ok_dict(result)


@mcp.tool()
def geck_cell_find_refs(
    query: str,
    backend: str = "win32",
    column: int = 0,
    exact: bool = False,
    max_matches: int = 25,
) -> dict[str, Any]:
    """Find references in the currently selected Cell View object list by Editor ID/Form ID/type."""
    result = _run(find_cell_references, query, backend, column, exact, max_matches)
    return _as_ok_dict(result)


@mcp.tool()
def geck_cell_select_ref(
    query: str,
    backend: str = "win32",
    column: int = 0,
    exact: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    """Select a reference in the currently selected Cell View object list."""
    result = _run(select_cell_reference, query, backend, column, exact, double)
    return _as_ok_dict(result)


@mcp.tool()
def geck_object_snapshot(backend: str = "win32", max_rows: int = 50) -> dict[str, Any]:
    """Read the current Object Window list rows."""
    result = _run(object_window_snapshot, backend, max_rows)
    return _as_ok_dict(result)


@mcp.tool()
def geck_object_filter(text: str, backend: str = "win32") -> dict[str, Any]:
    """Set Object Window's Filter field and return the filtered rows."""
    result = _run(object_window_filter, text, backend)
    return _as_ok_dict(result)


@mcp.tool()
def geck_object_select(
    editor_id: str,
    backend: str = "win32",
    exact: bool = True,
    double: bool = False,
) -> dict[str, Any]:
    """Select or optionally open a current Object Window record by Editor ID."""
    result = _run(select_object_record, editor_id, backend, exact, double)
    return _as_ok_dict(result)


@mcp.tool()
def geck_place_object_in_render(
    editor_id: str,
    render_title_regex: str | None = None,
    backend: str = "win32",
    drop_x_ratio: float = 0.82,
    drop_y_ratio: float = 0.42,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Drag an Object Window record into the active Render Window to create a placed reference."""
    result = _run(place_object_in_render, editor_id, render_title_regex, backend, drop_x_ratio, drop_y_ratio, dry_run)
    return _as_ok_dict(result)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
