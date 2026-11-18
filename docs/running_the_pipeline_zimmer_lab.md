# Running the pipeline within the zimmer lab

Most of this information is only relevant to the Zimmer lab, and uses internal formatting and paths.

## Legacy data preparation

See expected folder structure [here](data_folder_organization.md).

1. Red channel (tracking) as an ndtiff folder
2. Green channel (signal) as an ndtiff folder
3. 1 conda environment (see above for installation instructions, or use pre-installed versions on the cluster)

An alternatives to ndtiff for raw data:
1. bigtiff for the raw data, but is deprecated.


### Legacy creating a single project (single recording)

Most people will create multiple projects at once (next section), but for a single recording, see: [detailed pipeline steps](detailed_pipeline_steps.md).

### Creating multiple projects

Each recording will generate one project, and you can use the create_projects_from_folder.sh script.

Important: the data folders must be organized in a specific way, see [here](data_folder_organization.md).

```commandline
bash /PATH_TO_THIS_CODE/wbfm/scripts/cluster/create_multiple_projects_from_data_parent_folder.sh -t /path/to/parent/data/folder -p /path/to/projects/folder
```

Where "/path/to/parent/data/folder" contains subfolders with red, green, and (optionally) behavioral data, and "/path/to/projects/folder" is a folder where the new projects will be generated. 
In principle "/path/to/projects/folder" should be empty, but this is not necessary.

As of September 2023, this is the proper path to this code on the cluster:
```commandline
ls /lisc/data/scratch/neurobiology/zimmer/wbfm/code/wbfm/wbfm/scripts/cluster
```

For running projects, you will most likely want to run them all simultaneously instead of one-by-one.
See this [section](#running-the-rest-of-the-workflow-for-multiple-projects).

#### *IMPORTANT*

Creating and running the project on different operating systems will cause problems.
See [Summary of common problems](#summary-of-common-problems) for more details.

### Checklist of most important parameters to change or validate

You should check that the correct files were found, and that the z-metadata is correct.

1. project_config.yaml
   1. red_fname
   2. green_fname
   3. behavior_fname (optional)
2. dat/preprocessing_config.yaml
   1. raw_number_of_planes (before any removal)
   2. starting_plane (set 1 to remove a single plane)
3. segment_config.yaml
   1. max_number_of_objects (increase for immobilized projects)

For all other settings, the defaults should work well.


## Running the rest of the workflow via snakemake

### Running the rest of the workflow for single project

Most people will run multiple projects at once (next section), but for a single recording, see: [detailed pipeline steps](detailed_pipeline_steps.md).

### Running the rest of the workflow for multiple projects

If you have many projects to run, you can use the run_all_projects_in_parent_folder.sh script.
This is especially useful if you created the projects using the create_multiple_projects_from_data_parent_folder.sh script.

```commandline
bash /PATH_TO_THIS_CODE/wbfm/scripts/cluster/run_all_projects_in_parent_folder.sh -t /path/to/projects/folder
```

Note that you should run this script from a directory where you have permission to create files.
Otherwise the log files will be created in the directory where you ran the script, which will crash silently due to permission errors.

For more details on each step, see: [detailed pipeline steps](detailed_pipeline_steps.md).


## Automated runner from Windows (`wbsegmentation.py`)

`wbsegmentation.py` (code in `automation/auto_pipeline.py`) does project creation and Slurm submission in one step
from a Windows machine with the `Z:` share mounted and `ssh lisc` configured. It only orchestrates; all compute runs on the cluster.

### Raw data layout

One folder per worm inside a dated batch folder. The worm folder name becomes the project name
(`<worm folder>-<acquisition date>`), so name it as you want the project to be called:

```
Lit_raw\24092026\
  ZIM2165_Litworm1\
    2026-09-24_10-37_ZIM2165_Litworm1_Ch0\   (NDTiff store: *.tif + NDTiff.index)
    2026-09-24_10-37_ZIM2165_Litworm1_Ch1\
    config.yaml                              (acquisition metadata, see below)
```

Microscope output lands as flat `_Ch0`/`_Ch1` sibling folders; move each pair into its worm folder before launching.
Moves within the share are instant renames. To rename a worm, rename the worm folder and the `_Ch0`/`_Ch1` folders,
but **never the `.tif` files**, because `NDTiff.index` refers to them by filename.

`config.yaml` supplies the physical units forwarded to the project. If it is missing, the runner stops: copy the
acquisition's `config.yaml` into the worm folder, or pass `--default-config` to write a template with *assumed* values
(22 planes, 1.5 um z-step, 20 ms exposure, 1 flyback plane discarded). Set `strain:` per condition (e.g. `ZIM2165_Lit` / `ZIM2165_Ctrl`); it feeds NWB export metadata.

### Launch

```commandline
wbsegmentation.bat "Z:\...\Lit_raw\24092026" --output-parent "Z:\...\Lit_immob" --immobilized
```

`--immobilized` sets `max_number_of_objects: 220`. Status and deliverables: `wbsegmentation.bat status|verify "<project_dir>"`.
`status` lists only that project's Slurm jobs (master job and Snakemake rule jobs); `verify` also reports whether the master
job finished without writing `PIPELINE_FAILED.flag`.

Recordings that already have a project (same `parent_data_folder`, in `--output-parent` or `LeonK\Analysis*`) are skipped;
pass `--force` to analyse them again. `wbsegmentation.bat sanitize "<raw folder>" --dry-run` shows the folder renames
the runner would make without changing anything.
`wbsegmentation.bat` runs `wbsegmentation.py` with the `gui_only` env Python. `launcher_settings.bat` sets where that env
lives. To override it on one machine, use a gitignored `launcher_settings.local.bat`.

`0a-create_new_project.py` runs from the **cluster's** repo clone, so edits to the local `new_project_defaults/` do not
reach new projects. Anything that must differ from the cluster template is patched per project by `initialize_project()`
before submission: `snakemake_config.yaml` (tracker, Barlow model), `segment_config.yaml` (immobilized) and `RUNME.sh` (see below).

After launch, check the [parameter checklist](#checklist-of-most-important-parameters-to-change-or-validate) for every project.
In `project_config.yaml` the path values are written on the line *after* the key, so `grep -A1 red_fname`.

### What the master job runs, and how long it takes

Each worm gets one master job (`wbfm_<name>`, 2 CPU) that runs `RUNME.sh` (SuperGlue tracking up to traces) and then
`RUNME.sh -s barlow_embedding` (embedding for ID transfer). It writes `PIPELINE_COMPLETE.flag` at the end.
Observed per-worm timings (ZIM2165 immobilized, 18 min recordings, 2026-09):

| Stage | Time |
|---|---|
| preprocessing | ~20 min |
| segmentation | ~5.5 h |
| build_frame_objects + match/tracking + tracklets | ~1-1.5 h |
| combine_tracking_and_tracklets | 1-5 h (largest variance) |
| extract_full_traces | ~10 min, so **traces are ready after ~9-13 h** |
| barlow_embedding | ~50 min, so **fully complete after ~10-14 h** |

> [!IMPORTANT]
> **Resource Sizing for Segmentation**: In the Oct 2026 LiSC cluster audit, segmentation jobs requested `256G` RAM and `40` CPUs for `36h`, but only consumed peak **13.2 GB RAM** (95% memory wasted) and **8.3 cores** (79% CPU wasted) across ~12 hours. Do not allocate 256G / 40 cores in `cluster_config.yaml`. Right-size requests to `--mem=32G` (max 48G), `--cpus-per-task=10` to `12`, and `--time=16:00:00` to avoid FairShare penalties and queue delays.

#### *IMPORTANT*: the Barlow step must not re-run segmentation

Once masks exist, `pipeline.smk` switches its `ruleorder` from `segmentation` to `alt_segmentation`. That rule has a
different input set, which trips Snakemake's default `input` rerun trigger. The `barlow_embedding` call then
re-segments the whole recording (about 6 h wasted) and **overwrites `masks.zarr` after the traces were extracted from it**.
This happened in all projects launched before 2026-09-24.

`initialize_project()` now adds `--rerun-triggers mtime` to `RUNME.sh` for the `barlow_embedding` target, and logs a warning if it cannot.
To confirm on a running project: the master log's `[3/3]` section, or `snakemake/.snakemake/log/`, must **not** show `rule alt_segmentation`.
If you create projects some other way and run `RUNME.sh -s barlow_embedding` yourself, add the same flag.
