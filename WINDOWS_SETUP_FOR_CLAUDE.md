# wbfm on Windows — setup, pipeline, and GUI guide

**Written from the macOS clone at `~/Documents/GitHubRepositories/wbfm` (branch `main`, package version 1.4.0).**

This document has three parts:

- **Part 1 — Context.** How this repo is organized, how configuration is layered, how the pipeline is orchestrated, and how the GUIs work. Read this once; everything in Part 2 makes more sense afterwards.
- **Part 2 — The Windows walkthrough.** Numbered steps for a human, each with a matching **`▸ Claude:`** block containing the exact commands and verification checks to hand to Claude Code on the Windows machine.
- **Part 3 — Improvements worth making.** Real defects and rough edges found while reading the code, with enough detail to act on them in a later session.

A ready-to-paste bootstrap prompt for the Windows Claude Code session is at the very end (§2.0).

---

## Part 1 — Context: how this thing is put together

### 1.1 What the repo actually is

`wbfm` is a normal Python package (`setup.py`, version 1.4.0) that does two different jobs at once:

1. **Library + scripts** — `wbfm/utils/`, `wbfm/pipeline/`, and the numbered entry points in `wbfm/scripts/`.
2. **A directory of project templates** — `wbfm/new_project_defaults/`. This is *data*, shipped inside the package via `package_data={"wbfm": ["**/*.yaml"]}`. When you create a project, this tree is copied to your new project folder.

That second point is the single most important structural fact. **A "project" is not a database row or a config file — it is a folder on disk** that contains its own copies of every config file *and its own copy of the snakemake workflow*. Two projects can therefore run different pipeline versions side by side, and editing a project's config never touches the code.

```
wbfm/
├── setup.py                      # version 1.4.0, packages found via find_namespace_packages
├── conda-environments/
│   ├── wbfm.yaml                 # full pipeline env (Linux/CUDA-oriented — see §2.3)
│   ├── gui_only.yaml             # lightweight env, GUIs only, no torch/tensorflow
│   ├── wbfm_dev.yaml
│   └── wbfm_export.yaml          # frozen `conda env export` of a working Linux env
├── docs/                         # the docs you'd otherwise be reading
└── wbfm/
    ├── scripts/                  # numbered pipeline entry points (see §1.4)
    ├── pipeline/                 # project creation + step implementations
    ├── utils/                    # the actual library
    │   ├── projects/wbfm_config.yaml     # TEMPLATE for machine-level paths (§1.2)
    │   └── general/hardcoded_paths.py    # the config-resolution logic (§1.2)
    ├── gui/                      # PyQt5 + napari + dash GUIs (§1.5)
    ├── nn_checkpoints/           # ⚠ contains only a warp matrix — NOT the networks
    ├── new_project_defaults/     # ← the project template tree
    └── alternative_project_defaults/     # drop-in config overrides per project type
```

### 1.2 Configuration is layered in three tiers

Understanding this layering is what makes the Windows port tractable, because each tier fails differently.

**Tier 1 — Machine-level: `~/.wbfm/config.yaml`**

Holds paths to pretrained neural networks; these are properties of *your machine*, not of any project. The template lives at `wbfm/utils/projects/wbfm_config.yaml`. The resolution logic is `load_hardcoded_neural_network_paths()` in `wbfm/utils/general/hardcoded_paths.py`, and it tries, in order:

1. `~/.wbfm/config.yaml`
2. the file pointed at by the `WBFM_CONFIG_PATH` environment variable
3. the package defaults — **but only if `is_zimmer_lab()` returns true**, which it does by literally checking `Path('/lisc/data/scratch/neurobiology/zimmer').exists()`
4. otherwise: it *writes* a stub to `~/.wbfm/config.yaml` and raises `IncompleteConfigFileError`

On a Windows PC outside the Zimmer lab, step 3 is always false, so **you will hit step 4 on first run**. That is expected and by design — the error is the instruction. You then fill in the stub. This is the first thing to do on the new machine.

The keys that matter:

```yaml
segmentation_paths:
    model_parent_folder: <folder containing your StarDist model folders>
    model_name: students_and_lukas_3d_zarr
tracking_paths:
    model_parent_folder: <folder containing the SuperGlue .ckpt files>
    global_tracking_model_name: superglue_neurons_5_datasets_07_08_uint16.ckpt
    tracklet_model_name: superglue_neurons_5_datasets_adjacent_07_11_uint16.ckpt
behavior_paths:
    ...  # only needed if you run the behavior pipeline (separate repo)
```

> **⚠ Blocker to plan around.** The pretrained weights are **not in the repo and not published anywhere I can find** — I grepped the whole tree for zenodo/osf/figshare/download links and found nothing. `wbfm/nn_checkpoints/` contains a single 152-byte `.npy` warp matrix, not the networks. The paths in the template all point at `/lisc/data/scratch/neurobiology/zimmer/...`. So before segmentation or classic tracking can run on Windows you must **obtain the StarDist folder and the two SuperGlue `.ckpt` files from the lab** (cluster copy, shared drive, or ask Charles Fieseler). Everything else in this guide can be set up and verified without them, so don't let this block the rest.

**Tier 2 — Project-level: the project folder**

Copied from `new_project_defaults/` at creation time:

| Path in project | What it controls |
|---|---|
| `project_config.yaml` | raw-data paths (`red_fname`, `green_fname`, `behavior_fname`, `parent_data_folder`), physical units, index of the sub-configs |
| `dat/preprocessing_config.yaml` | `raw_number_of_planes`, `starting_plane`, alignment, background subtraction, dtypes |
| `1-segmentation/segment_config.yaml` | `stardist_model_name`, `max_number_of_objects`, postprocessing |
| `2-training_data/training_data_config.yaml` | frame/match building |
| `3-tracking/tracking_config.yaml` | global tracking + tracklet matching, `only_use_previous_matches`, Barlow/HDBSCAN options |
| `4-traces/traces_config.yaml` | trace extraction thresholds |
| `visualization/`, `nwb/`, `behavior/` | outputs and behavior pipeline |
| `snakemake/snakemake_config.yaml` | `use_barlow_tracker`, `barlow_model_path`, plus all behavior-pipeline parameters |
| `snakemake/pipeline.smk` | **the workflow itself, copied per project** |
| `snakemake/cluster_config.yaml` | SLURM resources per rule (irrelevant when running locally) |
| `snakemake/RUNME.sh` | the bash launcher |
| `log/print_project_status.py` | prints which steps are done |

The docs name a short checklist of fields that actually need attention per project (from `docs/running_the_pipeline_zimmer_lab.md`):

1. `project_config.yaml` → `red_fname`, `green_fname`, `behavior_fname`
2. `dat/preprocessing_config.yaml` → `raw_number_of_planes`, `starting_plane`
3. `1-segmentation/segment_config.yaml` → `max_number_of_objects` (raise for immobilized recordings that include the tail)

`wbfm/alternative_project_defaults/` holds drop-in replacements for specific situations — `barlow/snakemake_config.yaml`, `immobilized/segment_config.yaml`, `long_video/cluster_config.yaml`, `short_video/cluster_config.yaml`, etc. You copy these over the project's file.

**Tier 3 — Invocation-level: sacred**

Every numbered script is a [sacred](https://sacred.readthedocs.io/) experiment, which is why the CLI uses the unusual `with key=value` syntax:

```bash
python scripts/4-make_final_traces.py with project_path=/path/to/project/project_config.yaml
```

Any config key can be overridden on the command line this way. `ex.automain` means the script body only runs under `__main__`, which incidentally is what makes it safe under Windows' spawn-based multiprocessing.

### 1.3 How the pipeline is orchestrated

`snakemake` drives everything, but in an unusual way that's worth knowing before you debug it:

- `pipeline.smk` starts with `configfile: "snakemake_config.yaml"` — **a relative path**, so snakemake must be invoked from inside the project's `snakemake/` folder.
- It then locates the project by walking *up* from the workflow file: `project_dir = os.path.dirname(snakemake.workflow.workflow.basedir)`. The comment in the file admits this is "an undocumented feature, and may not work for other versions (this is 7.32)".
- It warns if `snakemake.__version__` isn't `7.32.x`. **Pin snakemake to 7.32.** This is not cosmetic — the `workflow.basedir` trick and the `--cluster`/`--cluster-status` CLI flags used by `RUNME.sh` were all removed or reworked in snakemake 8.
- Rules don't shell out to Python. Each rule calls `_run_helper(script_name, project_path)`, which does `importlib.import_module(f"wbfm.scripts.{script_name}")` and then `_module.ex.run(...)` **in the same process**. (The indirection exists because module names starting with a digit can't be imported normally.) Practical consequence: a rule failure gives you a Python traceback, and the whole pipeline shares one interpreter's memory.
- Only two `shell()` calls exist in the entire workflow — both `shell("ml p7zip")`, both wrapped in `try/except` as of commit `0b6dbd9d` ("Catch linux error; #992"). So **the workflow itself does not need a POSIX shell.** Only `RUNME.sh` does.

`RUNME.sh` flags (from its own `usage()`):

| Flag | Meaning |
|---|---|
| `-n` | dry run — always do this first |
| `-c` | **do NOT use the cluster**, i.e. run locally ← what you want on Windows |
| `-s RULE` | target rule: `traces` (default), `traces_and_behavior`, `behavior` |
| `-R RULE` | force restart from this rule |
| `-f` | run only one rule (`--allowed-rules RULE --force`) |
| `-h` | help |

With no flags it submits to SLURM via `sbatch`, which does not exist on Windows. **Always pass `-c`.**

Note also the hardcoded `SNAKEMAKE_OPT="-s pipeline.smk --latency-wait 60 --cores 56 --retries 2"`. `--cores 56` is a cluster number. See §2.6.

### 1.4 The pipeline steps

Target rule `traces` produces `4-traces/green_traces.h5`. The chain, with the durations quoted in `docs/detailed_pipeline_steps.md` (these are cluster timings for full-size data):

| Rule | Script | Output | Rough cost |
|---|---|---|---|
| — | `0a-create_new_project.py` or `0-create_new_project_from_nwb.py` | project folder | ~1 min |
| `preprocessing` | `0b-preprocess_working_copy_of_data.py` | `dat/bounding_boxes.pickle`, preprocessed zarr | slow, I/O bound |
| `segmentation` | `1-segment_video.py` | `1-segmentation/masks.zarr`, `metadata.pickle` | **slowest, 3–12 h**; StarDist3D → needs TensorFlow |
| `build_frame_objects` | `2a-build_frame_objects.py` | frame objects | GPU-ish |
| `match_frame_pairs` | `2b-match_adjacent_volumes.py` | matches | GPU-ish |
| `postprocess_matches_to_tracklets` | `2c-postprocess_matches_to_tracklets.py` | tracklets | fast |
| `tracking` *or* `barlow_embedding`+`barlow_tracking` | `3a-track_time_independent.py` | per-neuron positions | 1–3 h |
| `combine_tracking_and_tracklets` | `3b-match_tracklets_and_tracks_using_neuron_initialization.py` | `3-tracking/postprocessing/combined_3d_tracks.h5` | **~6 h** |
| `extract_full_traces` | `4-make_final_traces.py` | `4-traces/red_traces.h5`, `green_traces.h5`, `.png` summaries | ~30 min |

> **Re-running a later target on a finished project** (e.g. `RUNME.sh -s barlow_embedding` after `traces`): once masks exist, the `ruleorder` switches `segmentation` to `alt_segmentation`. Its different input set trips Snakemake's default rerun trigger, so segmentation runs again (hours) and overwrites `masks.zarr`. Pass `--rerun-triggers mtime`. The automated runner does this for you; see `docs/running_the_pipeline_zimmer_lab.md` § "Automated runner".

Two tracker families exist. The default (`use_barlow_tracker: False` in `snakemake_config.yaml`) is the SuperGlue-based tracklet tracker used in the paper. Setting it true switches to [BarlowTrack](https://github.com/Zimmer-lab/barlow_track/) and requires `barlow_model_path` to point at a `resnet50.pth`. **The `trace_explorer` manual-correction GUI only works with tracklet-based tracking**, i.e. not with the Barlow default — `docs/running_the_pipeline.md` says this explicitly.

End-to-end scale reference from the docs: a 3-minute video with ~5 neurons ≈ 10 minutes; an 8-minute video with ~150 neurons at TXYZ ≈ (1600×600×900×22) ≈ 8 hours *on the cluster*.

### 1.5 How the GUIs work

Two independent technology stacks live in `wbfm/gui/`:

**PyQt5 + napari (desktop):**

- **`create_project_gui.py`** — a `QDialog` built by hand (originally generated by `pyuic5` from `raw/create_project_raw.ui`). Buttons open file dialogs to set project folder / red file / green file / data folder, plus text fields for experimenter and task. `create_project()` then *builds a command string* and runs `subprocess.run(full_command, shell=True)`. Two gotchas that matter on Windows, both covered in §2.7: the command is `python scripts/0a-create_new_project.py ...` — a **relative path**, so the GUI only works if launched with cwd = `<repo>/wbfm` — and the arguments are **not quoted**, so any path containing a space breaks it.
- **`progress_gui.py`** — the intended entry point. `--project_path/-p` takes a `project_config.yaml`. It reports which pipeline steps have completed and exposes buttons that open pre-configured napari viewers (`napari_for_masks_tracking`, `napari_for_masks_training`, `open_traces_gui`), each calling `project_data.add_layers_to_viewer(viewer, which_layers=[...])`. Progress detection does not work for `.nwb`-backed projects, though the viewers do.
- **`trace_explorer.py`** — a thin `argparse` wrapper (`--project_path`, `--force_tracklets_to_be_sparse`, `--load_tracklets`, `--DEBUG`) around `napari_trace_explorer_from_config()` in `gui/utils/napari_trace_explorer.py`. This is the real workhorse: manual neuron ID assignment, tracklet correction, segmentation correction. Takes ~1 minute or more to load; `wbfm/gui/README.md` notes that if it takes over 5 minutes it has hung and you should retry.

The trace_explorer layout is four regions — napari layer list (left), 3D data (center), menus/buttons (right), matplotlib graph (bottom) — organized around a deliberate two-level split: **whole-worm layers** (`Red data`, `Green data`, `Neuron IDs`, `Colored segmentation`, `Raw segmentation`) versus **single-neuron layers** (`track_of_point`, `final_track`). Interactivity is **off by default** and must be enabled with a checkbox top-right; the `Raw segmentation` layer must be the highlighted layer for clicks to register. Middle-click selects a neuron into the spreadsheet-style table for naming; ctrl-click attempts automatic re-segmentation; alt-click applies a manual split. Closing the GUI saves by default. The full workflow narrative — the three categories of tracklet problem and their fixes, conflict resolution, the segmentation loop — is in `wbfm/gui/README.md` §"Trace_explorer GUI: two workflows", and there's a [YouTube playlist](https://youtube.com/playlist?list=PL0LLlJzm-VqQhX4Kw2KqoeccJVk4jhPS3) (first two videos general, later ones specific to tracklet/segmentation correction).

One important consequence of the design: **manual corrections do not regenerate the traces.** After a correction session you must rerun step `3b` (with `only_use_previous_matches=True` in `tracking_config.yaml` — much faster), optionally step `1-alt` if segmentation changed, then step `4`.

**Dash / plotly (browser):**

- `wbfm_dashboard.py -p <parent_folder>` — monitor many projects at once.
- `interactive_two_dataframe_gui.py`, `interactive_scatterplot.py`, `interactive_summary_heatmap.py`, `interactive_behavior_video.py`, `interactive_folder_grid_plot_explorer.py` — analysis explorers, served over HTTP with `--port` and optional `--allow_public_access`.

`wbfm/gui/examples/*.sh` shows real invocations. Note that several are stale (`gui/traces_gui.py`, `gui/gui.py`, `gui/utils/manual_annotation.py` no longer exist) — but `gui_gfp.sh` and `gui_example.sh` are historically interesting because they were written *for Windows*, using `Y:/shared_projects/...` drive-letter paths and a Git Bash shebang.

### 1.6 Cross-OS path handling (read before touching any config)

`wbfm/utils/general/utils_filenames.py::resolve_mounted_path_in_current_os()` tries to translate paths between Windows drive letters and cluster mounts. Its mapping table is **hardcoded to the Zimmer lab** (`Y: → /groups/zimmer`, `Z:`/`S: → /lisc/data/scratch...`, plus a Mac samba entry) and is commented "Last updated: Oct 2025". If a path already resolves on the current OS it is returned unchanged, so for a self-contained Windows project with local data this function is a no-op — fine. But it means you get **no automatic help** translating your own paths, and this is why both `README.md` and `docs/running_the_pipeline_zimmer_lab.md` warn that creating a project on one OS and running it on another requires manually fixing `red_fname` / `green_fname` / `parent_data_folder` / `behavior_fname`.

Rule of thumb: **create and run each project on the same machine.**

---

## Part 2 — The Windows walkthrough

### 2.0 Bootstrap prompt for Claude Code on the Windows PC

Open a terminal in the Windows clone of this repo, start Claude Code, and paste:

> Read `WINDOWS_SETUP_FOR_CLAUDE.md` in the repo root. It is a setup guide written from my macOS clone of the same repo, and it contains `▸ Claude:` blocks with the exact commands and verification checks for each step.
>
> Work through Part 2 in order. For each step: run the verification first, tell me whether it passed, and only then make changes. Stop and ask me before (a) creating or deleting a conda environment, (b) editing anything under `wbfm/new_project_defaults/`, (c) any step the guide marks as needing lab-supplied network weights.
>
> Adapt to what you actually find on this machine rather than assuming the guide is right — it was written without access to this PC. Report every place reality differs from the document, and note them so I can fold the corrections back in.

Everything below is written so it can be followed by a human or executed by Claude with that prompt.

---

### 2.1 Decide which of the three install profiles you need

| Profile | Environment | Can do | Cannot do |
|---|---|---|---|
| **A — GUI only** | `conda-environments/gui_only.yaml` | open and inspect finished projects, manual annotation in `trace_explorer` | run any pipeline step |
| **B — full pipeline, CPU** | Windows-adapted `wbfm.yaml` (§2.3) | everything, slowly | GPU acceleration |
| **C — full pipeline, GPU** | as B, plus a CUDA torch build | everything | TensorFlow GPU (Windows-native TF is CPU-only since 2.11; StarDist would need WSL2) |

**Strong recommendation: set up A first and confirm a GUI opens, then move to B.** Profile A has no torch, no TensorFlow, and no CUDA pins, so it isolates the pure Windows/Qt/napari problems from the much messier dependency problems. If you skip straight to B and something fails, you won't know which layer broke.

Because the pipeline is genuinely heavy (segmentation alone is 3–12 h *on a cluster with GPUs*), the realistic long-term arrangement is: **pipeline on a cluster or Linux box, GUIs and analysis on the Windows PC with the data mounted.** Profile A is not a lesser option — for most day-to-day work it is the right one. Note that GUIs *must* run locally (per `wbfm/gui/README.md`); only the data may be remote.

> **▸ Claude:** Report which profile is being set up, then check what's already present:
> ```powershell
> conda env list
> python -c "import sys; print(sys.version)"
> git -C . rev-parse --abbrev-ref HEAD; git -C . log --oneline -3
> nvidia-smi          # non-zero exit / not found ⇒ no NVIDIA GPU ⇒ profile B, not C
> ```

---

### 2.2 Fix line endings **before** cloning — this one bites silently

The repo has **no `.gitattributes`**. If git on Windows is configured with `core.autocrlf=true` (a common default, and what Git for Windows offers in its installer), every `.sh` file gets CRLF endings on checkout. `RUNME.sh` is then copied verbatim into each new project, and running it under Git Bash fails with cryptic errors like `$'\r': command not found` or `usage:` printed for no reason.

```powershell
git config --global core.autocrlf input
```

Then clone (or, if already cloned, re-normalize):

```powershell
git clone https://github.com/Zimmer-lab/wbfm.git
# or, in an existing clone:
git rm --cached -r .
git reset --hard
```

Skip the submodule. `.gitmodules` points `wbfm/utils/external/ts_spatial_filter` at `git@github.com:Charles-Fieseler-Vienna/ts_spatial_filter.git` — an **SSH** URL to a private-looking repo. `git submodule update --init` will fail without a key on that account. It is not needed for the pipeline.

> **▸ Claude:** Verify, don't assume:
> ```powershell
> git config --get core.autocrlf
> # Should print "input" (or nothing). If it prints "true", fix it and re-checkout.
> ```
> Confirm the launcher script is LF-only:
> ```powershell
> python -c "d=open(r'wbfm/new_project_defaults/snakemake/RUNME.sh','rb').read(); print('CRLF found:', b'\r\n' in d)"
> ```
> Must print `CRLF found: False`. If True, convert it (`dos2unix`, or rewrite with `newline='\n'`) **and** report it, because it means the whole checkout is affected, not just this file.

---

### 2.3 Install a package manager, then the environment

Install **Miniforge** (conda-forge by default, no Anaconda ToS concerns — the repo's own docs flag this: "please be wary of the terms of service"). `mamba` comes with it and is dramatically faster at solving these environments. You get a "Miniforge Prompt" in the Start menu; use that for conda work, and **Git Bash** for `bash RUNME.sh`.

**Profile A:**

```powershell
cd <repo>\conda-environments
mamba env create -f gui_only.yaml --name gui_only
conda activate gui_only
```

**Profile B — do not use `wbfm.yaml` unmodified.** Read the file first and you'll see why. It contains, simultaneously:

```yaml
- cudatoolkit=10.0.130     # CUDA 10.0
- cudnn=7.6.5
- pytorch=1.13.0
- pytorch-cuda=11.6        # CUDA 11.6 — contradicts the above
```

Those two CUDA pins cannot both be satisfied; the environment is also built around `python=3.8` and the `nvidia` channel, and pulls three packages straight from GitHub `main`/`master` (`wbfm`, `imutils`, `centerline_behavior_annotation`), so it is not reproducible in time either. On Windows the solve will most likely fail outright or resolve to something broken.

Make a Windows variant instead. Copy `wbfm.yaml` to `conda-environments/wbfm_windows.yaml` and:

- **delete** `cudatoolkit=10.0.130` and `cudnn=7.6.5`
- **delete** `pytorch-cuda=11.6` for CPU (profile B), or replace both CUDA pins with a single `pytorch-cuda=<version your driver supports>` for profile C
- **pin** `snakemake=7.32.*` — `pipeline.smk` warns on anything else and `RUNME.sh` uses snakemake-7-only CLI flags
- keep `python=3.8` for now (see §3.11 — it is EOL, but the code isn't ready to move)
- replace the three `git+https://...` lines with editable local installs (next step), so you control the versions

Then install the three repos from source, which is what `docs/installation_instructions.md` calls "4 things: 1 conda environment and 3 custom packages":

```powershell
git clone https://github.com/Zimmer-lab/imutils.git
git clone https://github.com/Zimmer-lab/centerline_behavior_annotation.git
# then, in each of the three repos (wbfm, imutils, centerline_behavior_annotation):
pip install -e .
```

> **▸ Claude:** After creating the environment, verify imports individually rather than trusting the solve — a conda solve can "succeed" and still produce an unimportable torch on Windows:
> ```powershell
> python -c "import wbfm; print('wbfm', wbfm.__file__)"
> python -c "import napari, qtpy; print('napari', napari.__version__)"
> python -c "import zarr, tables, sacred, ruamel.yaml; print('io ok')"
> python -c "import snakemake; print('snakemake', snakemake.__version__)"   # expect 7.32.x
> ```
> Profile B/C only:
> ```powershell
> python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
> python -c "import tensorflow as tf; print('tf', tf.__version__)"
> python -c "from stardist.models import StarDist3D; print('stardist ok')"
> ```
> Report the actual versions. If `snakemake.__version__` is 8.x, stop and flag it — `RUNME.sh` will fail on `--cluster`/`--cluster-status`, and `pipeline.smk`'s `workflow.basedir` project detection is undocumented behavior that may have changed.

---

### 2.4 Create `~/.wbfm/config.yaml`

Expected to fail-then-teach on first run: `load_hardcoded_neural_network_paths()` writes a stub to `%USERPROFILE%\.wbfm\config.yaml` and raises `IncompleteConfigFileError`. Trigger it deliberately, then fill in the stub.

Use **forward slashes** in the YAML (`C:/Users/you/models/...`). Backslashes in unquoted YAML are escape characters and will corrupt paths.

If you'd rather keep the config alongside your data, set `WBFM_CONFIG_PATH` to point at it — that's checked second, before the Zimmer-lab fallback.

> **▸ Claude:** Trigger and inspect:
> ```powershell
> python -c "from wbfm.utils.general.hardcoded_paths import load_hardcoded_neural_network_paths as f, is_zimmer_lab; print('zimmer:', is_zimmer_lab()); print(f())"
> ```
> `is_zimmer_lab()` must print `False` on this machine. Expect `IncompleteConfigFileError` on the first call and a new stub at `%USERPROFILE%\.wbfm\config.yaml`.
>
> Then fill in `segmentation_paths` and `tracking_paths` **only with paths that exist on this machine** — verify each with `Test-Path` before writing it, and leave the `behavior_paths` block alone unless the behavior pipeline is actually in scope. If the network weights aren't on this machine yet, say so plainly and leave those keys pointing nowhere; don't invent plausible paths. Re-run the command above and confirm it returns a dict without raising.

---

### 2.5 Create a project

Two entry points, depending on your input data.

**From an NWB file (the documented, recommended route):**

```powershell
cd <repo>\wbfm\scripts
python 0-create_new_project_from_nwb.py with project_dir=D:/wbfm_projects/my_project nwb_file=D:/data/my_recording.nwb copy_nwb_file=True unpack_nwb=True
```

Success looks like `Successfully created new project at: {project_fname}`. The NWB is copied into the project and any raw data found is unpacked to zarr — `docs/running_the_pipeline.md` recommends leaving `unpack_nwb=True` because parallel access to NWB files caused "strange bugs".

Note: the docs write these arguments with a stray comma (`copy_nwb_file=True, unpack_nwb=True`). Drop the comma.

**From raw red/green data (Zimmer-internal ndtiff/btf layout):**

```powershell
cd <repo>\wbfm
python scripts/0a-create_new_project.py with project_dir=D:/wbfm_projects/my_project parent_data_folder=D:/data/ZIM_worm2 task_name=gfp experimenter=LK
```

This expects the folder layout from `docs/data_folder_organization.md`: one folder per recording with `*CH0` (green), `*CH1` (red), and optionally `*CH0-BH` (behavior) subfolders containing `.btf` files, and **no other `.btf` files** in them.

`docs/detailed_pipeline_steps.md` links to `wbfm/scripts/examples/0-create_new_project-windows-EXAMPLE.sh` for a worked Windows example — **that file does not exist** in the current tree (see §3.6).

Then walk the Tier-2 checklist from §1.2 and fix the paths.

> **▸ Claude:** After creation, verify the project structure and the paths inside it:
> ```powershell
> Get-ChildItem -Recurse -Depth 1 D:/wbfm_projects/my_project | Select-Object FullName
> python D:/wbfm_projects/my_project/log/print_project_status.py
> ```
> Then read `project_config.yaml` and check every non-null path field (`red_fname`, `green_fname`, `behavior_fname`, `parent_data_folder`) with `Test-Path`. Report any that don't resolve — this is the single most common failure mode when a project moves between operating systems, and `resolve_mounted_path_in_current_os()` will not fix paths it doesn't recognize.
> Also confirm the project got its own `snakemake/` folder containing `pipeline.smk`, `snakemake_config.yaml`, `cluster_config.yaml`, and an **LF-ending** `RUNME.sh`.

---

### 2.6 Run the pipeline locally

The two Windows-specific adjustments, both in the project's own `snakemake/` folder:

1. **`RUNME.sh` hardcodes `--cores 56`.** Edit the project's copy to your real core count, or `--cores all`:
   ```bash
   SNAKEMAKE_OPT="-s pipeline.smk --latency-wait 60 --cores all --retries 2"
   ```
   Individual rules also declare `threads: 56`; snakemake clamps those down to the available cores, so they need no edit.
2. **Always pass `-c`.** Without it, `RUNME.sh` calls `sbatch`, which doesn't exist. `cluster_config.yaml` is then entirely inert — ignore it.

From **Git Bash** (not PowerShell — `RUNME.sh` is bash):

```bash
conda activate wbfm            # or however conda is exposed to your Git Bash
cd /d/wbfm_projects/my_project/snakemake
bash RUNME.sh -h               # confirm the script parses at all
bash RUNME.sh -n               # DRY RUN — always first
bash RUNME.sh -c               # actually run, locally
```

The dry run prints a table of the steps it intends to execute, computed from which output files already exist. If it errors, the likely causes per `docs/detailed_pipeline_steps.md` are: the project was renamed, a permissions problem, or you're re-running a project where snakemake's file-timestamp bookkeeping is already confused.

If you prefer to bypass bash entirely — reasonable on Windows, and it sidesteps the CRLF issue permanently — run snakemake directly with the same arguments the script would have used:

```powershell
cd D:\wbfm_projects\my_project\snakemake
snakemake traces -s pipeline.smk --latency-wait 60 --cores all --retries 2 -n
```

You can also skip snakemake and run steps one at a time — see the table in §1.4 and use `python scripts/<N>-<name>.py with project_path=<project_config.yaml>`. This is the documented approach for re-running steps in an existing project, because snakemake "only reliably works for the first run."

> **▸ Claude:** Do the dry run before anything else and paste its output. Then, before any long run:
> - Confirm `--cores` in the project's `RUNME.sh` is not still 56.
> - Confirm `-c` is in the command. If a run is launched without it, kill it — it will try to `sbatch`.
> - Check free disk space. Preprocessing writes a full zarr copy of the raw video; this is easily hundreds of GB for real data.
> - Enable Win32 long paths if not already on (`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`, needs admin + reboot). Zarr stores create deeply nested chunk directories and will hit `MAX_PATH` otherwise. Report the current value rather than changing it yourself.
>
> If a rule fails, remember the traceback is a real Python traceback from `_run_helper()` — read it directly, don't treat it as an opaque snakemake error. Also note the documented recovery: delete the partial outputs of the failed step, then re-run from the dry run.

---

### 2.7 Run the GUIs

```powershell
conda activate gui_only
cd <repo>

python -X utf8 wbfm\gui\progress_gui.py --project_path D:/wbfm_projects/my_project/project_config.yaml
python -X utf8 wbfm\gui\trace_explorer.py --project_path D:/wbfm_projects/my_project/project_config.yaml
```

**Always use `-X utf8` on Windows.** `README.md` documents a `UnicodeDecodeError` from some napari/Python combinations on Windows that this flag fixes. It is harmless otherwise, so make it a habit.

`trace_explorer` takes a minute or more to load and occasionally just doesn't open — per `wbfm/gui/README.md`, if it exceeds 5 minutes, quit and retry.

**The project-creation GUI needs a specific working directory.** `create_project_gui.py` builds the string `python scripts/0a-create_new_project.py ...` with a *relative* path, so despite what the READMEs say (`python wbfm/gui/create_project_gui.py` from the top level), the **Create** button only works when cwd is `<repo>\wbfm`:

```powershell
cd <repo>\wbfm
python -X utf8 gui\create_project_gui.py
```

And because those arguments are interpolated into a shell string **without quoting**, any project or data path containing a space will break it. Avoid spaces in paths, or use the command line from §2.5 instead. (See §3.10.)

> **▸ Claude:** Verify the Qt stack can actually create a window before blaming the project data — these are two very different failures:
> ```powershell
> python -X utf8 -c "from qtpy.QtWidgets import QApplication; a=QApplication([]); print('Qt ok')"
> python -X utf8 -c "import napari; v=napari.Viewer(show=False); print('napari ok'); v.close()"
> ```
> If Qt fails, it's an environment problem (§2.3). If Qt works but `trace_explorer` fails, it's the project or the data.
>
> When launching a GUI, run it in the background and report the console output — these scripts print progress and warnings to stdout, and `trace_explorer` prints its options and a "may take a couple minutes to load" line at startup. Do **not** conclude the GUI works because the process didn't exit; confirm a window appeared, or ask me to confirm.

---

### 2.8 What "working" looks like

Checkpoints, in order — don't move on until each holds:

1. `import wbfm` succeeds and points into the Windows clone.
2. `is_zimmer_lab()` is `False`, and `load_hardcoded_neural_network_paths()` returns a dict without raising.
3. A napari window opens from `progress_gui.py`.
4. `bash RUNME.sh -n` prints a plan without errors.
5. `bash RUNME.sh -c` completes at least the `preprocessing` rule.
6. `4-traces/` contains `red_traces.h5`, `green_traces.h5`, and the summary `.png` files. Per `docs/running_the_pipeline.md`, those PNGs are the first thing to look at on a finished project.

---

## Part 3 — Improvements worth working on with the next Claude

Ordered roughly by (impact ÷ effort). Items 1–6 are small, self-contained, and each removes a real Windows failure. Items 7–12 are larger.

**1. Add a `.gitattributes`.** The repo has none, so `core.autocrlf=true` silently CRLF-ifies `RUNME.sh` and every other `.sh`, which then get copied into projects and fail under bash. One file fixes it for every Windows user forever:
```
*.sh text eol=lf
*.smk text eol=lf
```
→ *Highest value-per-line change in this list.*

**2. Make `--cores` a flag in `RUNME.sh`.** `SNAKEMAKE_OPT` hardcodes `--cores 56`, a cluster-specific number that is wrong on every workstation. Add a `-j N` option defaulting to `all`, alongside the existing `-s/-R/-n/-f/-c`.

**3. Pin `snakemake=7.32.*` in the environment files.** `pipeline.smk` already warns at runtime that it's "only tested on snakemake version 7.32.X", relies on the undocumented `snakemake.workflow.workflow.basedir`, and `RUNME.sh` uses `--cluster` / `--cluster-config` / `--cluster-status`, all removed in snakemake 8. Right now `wbfm.yaml` lists `snakemake` unpinned, so a fresh install gets 8.x and breaks. Turn the warning into a hard version check, or pin it.

**4. Fix the contradictory CUDA pins in `conda-environments/wbfm.yaml`.** It requests `cudatoolkit=10.0.130` + `cudnn=7.6.5` *and* `pytorch-cuda=11.6` in the same dependency list. These are mutually exclusive; the file cannot be describing a working environment. `wbfm_export.yaml` (a real `conda env export`) is the ground truth to reconcile against. While there: the three `git+https://.../@main` pip lines make the environment non-reproducible, since the same yaml resolves differently over time.

**5. Add `conda-environments/wbfm_windows.yaml`.** Same as (4)'s cleaned-up version, minus CUDA, with snakemake pinned. Turns §2.3 from a manual editing exercise into one command.

**6. Fix the broken documentation links.** Concretely:
   - `README.md` links `docs/known_issues.md` — **the file doesn't exist** (its content appears to have been merged into `docs/faq.md`).
   - `docs/detailed_pipeline_steps.md` links `wbfm/scripts/examples/0-create_new_project-linux-EXAMPLE.sh` and `...-windows-EXAMPLE.sh` — **`wbfm/scripts/examples/` doesn't exist.** These would be exactly the right thing for a new Windows user, so consider writing them rather than deleting the links.
   - Files inside `docs/` link to their siblings as `docs/foo.md` instead of `foo.md`, so they 404 on GitHub. There are **10 such links** — 5 in `running_the_pipeline.md` and 5 in `running_the_pipeline_zimmer_lab.md`, pointing at `data_folder_organization.md`, `detailed_pipeline_steps.md`, `faq.md`, and `running_the_pipeline_zimmer_lab.md`. Separately, `installation_instructions.md` links `wbfm/gui/README.md`, which needs `../` from inside `docs/`. Find them all with `grep -rn '](docs/' docs/*.md`.
   - `docs/running_the_pipeline.md` has `copy_nwb_file=True, unpack_nwb=True` — the comma is a copy-paste error in a command users will paste.
   - `wbfm/gui/examples/` references three scripts that no longer exist (`gui/traces_gui.py`, `gui/gui.py`, `gui/utils/manual_annotation.py`).

**7. Publish the pretrained networks, or document how to get them.** This is the hardest wall a new user hits, and it's not mentioned in any of the install docs. Neither the StarDist model (`Students_and_Lukas_3d_zarr`) nor the SuperGlue checkpoints ship with the repo — `wbfm/nn_checkpoints/` holds only a 152-byte warp matrix — and there is no download link anywhere in the tree. A Zenodo deposit plus a `wbfm_config.yaml` template that references it would make the pipeline genuinely installable off-cluster. Failing that, `IncompleteConfigFileError` should say *where to obtain* the weights, not just that the config is incomplete.

**8. Add a `wbfm doctor` / `python -m wbfm.check` command.** One command that verifies: imports, `snakemake.__version__`, `~/.wbfm/config.yaml` presence and that each referenced network path exists, torch/TF availability, and for a given project that every path in `project_config.yaml` resolves. Essentially §2.8 as code. This would collapse most of Part 2 into a single run and would pay for itself the first time someone moves a project between machines.

**9. Make `resolve_mounted_path_in_current_os()` data-driven.** It hardcodes Zimmer drive mappings (`Y: → /groups/zimmer`, `Z:`/`S: → /lisc/data/scratch...`) in source, with a comment that they need updating regularly — they were last touched Oct 2025. Move the table into `~/.wbfm/config.yaml` as a `mounted_drives:` block so each site configures its own. Related: the same function's `machine_is_linux = "ix" in os.name.lower()` is true on macOS too (`os.name == 'posix'` on both), which happens to be harmless here but is a trap for anyone editing it.

**10. Fix `create_project_gui.py`'s subprocess call.** Two independent bugs in `create_project()`:
   - It runs `python scripts/0a-create_new_project.py ...` with a **relative path**, so the GUI only works when cwd is `<repo>/wbfm` — while both `README.md` and `wbfm/gui/README.md` tell users to launch it from the repo root, where the button silently does nothing useful. Resolve the script path relative to the `wbfm` package instead (`importlib.resources` or `Path(__file__).parents[1]`).
   - It builds one unquoted shell string and calls `subprocess.run(full_command, shell=True)`, so any path containing a space is split into multiple arguments. Pass a list and drop `shell=True`. This is near-guaranteed to hit Windows users (`C:\Users\First Last\...`, `My Documents`).

**11. Add a Windows CI job.** Even a `windows-latest` job that only creates the `gui_only` environment, imports `wbfm`, and instantiates a headless `napari.Viewer` would catch the CRLF, Qt, and path-handling regressions this document exists to work around.

**12. Plan the move off Python 3.8.** Both environment files pin `python=3.8`, which reached end of life in October 2024 — no security patches, and an ever-shrinking set of installable wheels on Windows in particular. Two known blockers to sequence: `cgitb` (used by the numbered scripts via `cgitb.enable(format='text')`) was deprecated in 3.11 and **removed in 3.13**; and snakemake 8 requires 3.11+, which collides with item (3). So this is really "modernize snakemake and the scripts together" — worth scoping deliberately rather than attempting incrementally.

---

### Provenance

Everything above was derived by reading this repo at commit `a3881cfc`. Primary sources, if you want to check any claim: `README.md`, `docs/installation_instructions.md`, `docs/running_the_pipeline.md`, `docs/running_the_pipeline_zimmer_lab.md`, `docs/detailed_pipeline_steps.md`, `docs/faq.md`, `docs/data_folder_organization.md`, `wbfm/gui/README.md`, `wbfm/new_project_defaults/snakemake/{RUNME.sh,pipeline.smk,snakemake_config.yaml,cluster_config.yaml}`, `wbfm/utils/general/hardcoded_paths.py`, `wbfm/utils/general/utils_filenames.py`, `wbfm/utils/projects/wbfm_config.yaml`, `wbfm/gui/{create_project_gui.py,progress_gui.py,trace_explorer.py}`, `conda-environments/{wbfm.yaml,gui_only.yaml}`.

**It was written without access to the Windows PC.** Nothing in Part 2 has been executed on Windows — the steps are inferred from the code and the existing docs. Treat each `▸ Claude:` verification as the actual source of truth and correct this document as you go.
