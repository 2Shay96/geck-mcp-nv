# Tool reference

The server exposes these 46 tools. Parameter schemas are available through MCP `tools/list`.

Always supply an explicit plugin name for file operations. Historical defaults are test names, not a selected mod.

| Tool | Purpose |
| --- | --- |
| `geck_doctor` | Check paths and optional dependencies for this GECK MCP server. |
| `geck_list_plugins` | List plugin files in the Fallout: New Vegas Data folder. |
| `geck_backup_plugin` | Copy an .esm or .esp from Data into the MCP backup directory. |
| `geck_plugin_status` | Check whether an .esp/.esm exists in Data, optionally creating a backup. |
| `geck_transaction_begin` | Create a named rollback point before direct ESP/ESM file edits. |
| `geck_transaction_list` | List recent MCP backup/transaction files, newest first. |
| `geck_transaction_rollback` | Restore a plugin from a transaction id or backup path inside the MCP backup directory. |
| `geck_transaction_verify` | Verify on-disk plugin state, active GECK plugin, placed records, and recent rollback points. |
| `geck_esp_list_refs` | Read placed REFR/ACHR/ACRE records from an .esp/.esm file. |
| `geck_esp_patch_ref_position` | Patch a placed record with GECK closed. Rotation is in radians; omitted axes are preserved. |
| `geck_esp_nearby_refs` | Find placed records in a plugin near a coordinate. |
| `geck_placement_report` | Assess saved placed records against the status bar, restricted to the required anchor cell_form_id. |
| `geck_status_bar` | Read GECK's bottom status bar, including selected object coordinates when available. |
| `geck_placement_plan_from_status_bar` | Dry-run a target position/rotation from GECK's status-bar coordinate plus offsets. |
| `geck_esp_patch_ref_to_status_bar` | Legacy planning only: capture deferred patch arguments; never writes while GECK is open. Returns applied=false. |
| `geck_esp_patch_ref_to_status_bar_offset` | Legacy planning only: capture deferred patch arguments plus offsets; returns applied=false without writing. |
| `geck_esp_delete_refs` | Delete placed records directly from an .esp/.esm file and update group sizes. |
| `geck_esp_delete_refs_by_base` | Delete placed records whose NAME/base FormID matches one of the given base IDs. |
| `geck_active_plugin` | Read the active plugin name from the GECK main window title. |
| `geck_save_active_plugin` | Save the active GECK plugin through File > Save and return plugin status. |
| `geck_read_load_order` | Read the Fallout: New Vegas plugins.txt load order. |
| `geck_write_load_order` | Rewrite the Fallout: New Vegas plugins.txt load order after validating plugin names. |
| `geck_tail_log` | Read the tail of a known GECK or NVSE log file. |
| `geck_launch` | Launch GECK normally, or with NVSE via nvse_loader.exe -editor. |
| `geck_list_processes` | List GECK and NVSE-related processes. |
| `geck_list_windows` | List top-level desktop windows visible to pywinauto. |
| `geck_focus_window` | Focus the GECK main window or a matching dialog. |
| `geck_control_tree` | Dump a GECK window/control tree for planning UI automation. |
| `geck_list_view_rows` | Read rows from a Win32 ListView in a GECK window or dialog. |
| `geck_find_list_rows` | Find rows in a GECK ListView by text, usually Editor ID or Form ID. |
| `geck_send_keys` | Send a pywinauto key sequence to GECK, such as ^s, %{F4}, or {ENTER}. |
| `geck_menu_select` | Select a GECK menu path, for example File->Data... or ['File', 'Save']. |
| `geck_open_data_dialog` | Open GECK's File > Data dialog. |
| `geck_click_control` | Click a child control found by title, class, UIA type, or automation id. |
| `geck_click_at` | Click coordinates, window-relative by default. |
| `geck_screenshot` | Capture a screenshot of a GECK window or dialog as a PNG file. |
| `geck_cell_view_snapshot` | Read Cell View state: world space, selected cell, visible cells, and current cell references. |
| `geck_cell_set_world_space` | Set Cell View's world-space combo box, e.g. Interiors or Wasteland. |
| `geck_cell_select` | Select an interior/exterior cell in Cell View by Editor ID. |
| `geck_cell_go_to_exterior` | Use Cell View's world-space/X/Y/Go controls to jump to an exterior cell. |
| `geck_cell_find_refs` | Find references in the currently selected Cell View object list by Editor ID/Form ID/type. |
| `geck_cell_select_ref` | Select a reference in the currently selected Cell View object list. |
| `geck_object_snapshot` | Read the current Object Window list rows. |
| `geck_object_filter` | Set Object Window's Filter field and return the filtered rows. |
| `geck_object_select` | Select or optionally open a current Object Window record by Editor ID. |
| `geck_place_object_in_render` | Drag an Object Window record into the active Render Window to create a placed reference. |

Direct file editing and rollback require the editor/game to be closed. Legacy status-bar patch tools only return deferred arguments. A successful file operation is not a gameplay or collision guarantee.

[Back to setup](../README.md#quick-setup)
