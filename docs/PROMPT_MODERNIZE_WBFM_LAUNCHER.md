# Prompt: Modernize WBFM GUI Launcher & Recording Dashboard

> **Target Workspace**: `C:\GithubRepositories\wbfm`  
> **Environment**: `C:\Users\Zim_Admin\Miniforge3\envs\gui_only\python.exe` (`qtpy 2.4.3`, `PyQt5`, `napari 0.8.0`)  
> **Launcher Scripts**: `launch_wbfm_gui.bat` $\to$ `launch_gui.py` $\to$ `wbfm.gui.utils.napari_trace_explorer`

---

## Task Objective

You are tasking an agent to overhaul and modernize the **WBFM Trace Explorer Launcher** (`launch_gui.py`). The current implementation is an old, primitive Tkinter file dialog that only lists recent paths from `.recent_projects.json`. 

Replace it with a **fast, intuitive, modern Qt-based Recording Dashboard & Launcher** (`qtpy.QtWidgets`) that provides a live overview of whole-brain recordings, displays annotation and pipeline status at a glance, and launches datasets with one click.

---

## Copy & Paste Prompt for the New Session

```markdown
You are tasked with overhauling and modernizing the WBFM Trace Explorer GUI launcher (`C:\GithubRepositories\wbfm\launch_gui.py` and `launch_wbfm_gui.bat`).

### Context & Current State
* The launcher runs under Windows in Conda environment `gui_only` (`C:\Users\Zim_Admin\Miniforge3\envs\gui_only\python.exe`), which has `qtpy 2.4.3`, `PyQt5`, and `napari 0.8.0` installed.
* Currently, `launch_gui.py` displays a bare, legacy Tkinter prompt that only shows a raw list of strings from `.recent_projects.json`.
* When a project is selected, it calls:
  ```python
  from wbfm.gui.utils.napari_trace_explorer import napari_trace_explorer_from_config
  napari_trace_explorer_from_config(project_path, load_tracklets=False, force_tracklets_to_be_sparse=True)
  ```
  *(Note: Newer Barlow-only datasets lack `all_tracklets.pickle`, so tracklet loading must gracefully default to False/Fast mode).*

---

### Key Requirements for the Modernized Launcher

#### 1. Modern, Intuitive Qt UI (`qtpy.QtWidgets`)
* Replace the legacy Tkinter dialog with a clean, modern Qt application (`QApplication`, `QMainWindow` or `QDialog`).
* Use a clean, polished stylesheet (dark or modern flat light theme matching Napari).
* Fast startup: The launcher window must appear in under 1 second.

#### 2. Live Recording Overview Dashboard
Implement a searchable, sortable table (`QTableWidget` or `QTreeView`) displaying available recordings across key project directories:
* **Default Directory Search Roots**:
  - `Z:\neurobiology\zimmer\LeonK\Analysis04092026`
  - `Z:\neurobiology\zimmer\LeonK\Analysis_Final_Worms_Strict_Chirality_No_Overlap`
  - `Z:\neurobiology\zimmer\LeonK\25_degrees_npr-1_vs_rde4`
  - Plus any custom directories or recent history in `.recent_projects.json`.
* **Asynchronous / Non-Blocking Metadata Scanner**:
  - Scanning network directories on `Z:\` must run in a background worker thread (`QThread`), populating rows asynchronously with a progress indicator so the UI NEVER freezes.
* **Streamlined 8 Dashboard Columns**:
  1. **Recording Name**: Stretched main column (e.g. `AX10059worm1-2026-04-10`).
  2. **Date**: Acquisition date parsed from recording name or file metadata.
  3. **Pipeline Status Badges**:
     - StarDist Masks (`masks.zarr` / `metadata.pickle`) [✓ / ✗]
     - 3D SuperGlue Tracks (`combined_3d_tracks.h5`) [✓ / ✗]
     - Calcium Traces (`green_traces.h5`) [✓ / ✗]
     - Barlow Tracker (`worm_tracker_barlow.pickle`) [✓ / ✗]
  4. **Total Tracked Neurons**: Count of tracked neurons extracted from `combined_3d_tracks.h5` or traces headers.
  5. **Annotated Neurons Count**: Fast inspection of `manual_annotation.h5` or `manual_annotation.xlsx` (e.g. `28 / 180`). Double-clicking opens `QuickGlanceAnnotationDialog`.

* **Spacious, Scrollable Inspector Sidebar**:
  - Resilient `QScrollArea` wrapping to prevent vertical or horizontal squishing across displays and scaling levels.
  - Dedicated full-width `🔍 View Annotated Neurons (N)` action button and bilateral pair stats summary (`10 pairs, 8 unpaired`).
  - Searchable chip badge flow and real-time badge filter.

#### 3. Search, Filter & Quick-Actions
* **Search / Filter Bar**: Real-time filtering by recording name, strain (`AX10059`, `ZIM2554`, `N2`), date, or condition.
* **Filter Preset Checkboxes**:
  - `Show only fully processed recordings`
  - `Show recordings with missing annotations`
  - `Recent only`
* **Browse Button**: For opening any arbitrary folder or `project_config.yaml` not in the preset roots.

#### 4. Launch Optimization & Speed
* **One-Click Launch**: Double-clicking any row or clicking a prominent `🚀 Open in Trace Explorer` button launches the selected recording.
* **Launch Options Toggles**:
  - Checkbox: `Fast Mode: Traces & IDs Only` (sets `load_tracklets=False`, loads Napari 5x faster, recommended).
  - Checkbox: `Load Full 3D Tracklets` (for deep tracking inspection, catches missing tracklet pickles gracefully).
* **Smooth Handoff**: Hide/minimize or cleanly close the launcher window while Napari initializes, preventing clutter and memory bloat.

#### 5. Backward Compatibility & CLI Support
* Preserve command-line argument support: `python launch_gui.py [path_to_project_or_yaml]` must still bypass the launcher window and open directly if a path is passed.
* Preserve and update `.recent_projects.json` with timestamps.
* Ensure `launch_wbfm_gui.bat` continues to work seamlessly without modification.

---

### Expected Deliverables
1. Updated `C:\GithubRepositories\wbfm\launch_gui.py` implementing the Qt launcher and dashboard.
2. Verified launch under `gui_only` environment via `launch_wbfm_gui.bat`.
3. Standalone test ensuring background scanning handles missing network paths or disconnected drives gracefully without crashing.
```
