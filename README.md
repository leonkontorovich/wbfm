# Whole Brain Freely Moving Tracking and Trace extraction

> **About this fork** ([leonkontorovich/wbfm](https://github.com/leonkontorovich/wbfm), branch `main`): the
> [Zimmer-lab pipeline](https://github.com/Zimmer-lab/wbfm) plus additions for running it from a Windows workstation.
> Anyone is welcome to use them; the lab's own repository is unchanged. Main additions:
> - **Recording dashboard** (`launch_gui.py`, `launch_wbfm_gui.bat`): finds your projects, shows pipeline status and ID
>   counts, and opens the trace explorer.
> - **ID-transfer review in the trace explorer**: a '?' Review panel to accept (Alt+Y), reject (Alt+N) or correct
>   uncertain neuron IDs, compared against an annotated reference recording.
> - **One-command cluster runs** (`go.bat` / `wbsegmentation.bat`): checks raw folders, creates projects, submits the
>   Slurm pipeline, skips recordings that were already analysed, and reports `status` / `verify` / `check-ids`.
>   See [Running the pipeline (Zimmer lab)](docs/running_the_pipeline_zimmer_lab.md), section "Automated runner".
> - **Fixes**: zarr 2/3 compatibility, path translation between Windows and the cluster, Windows launchers, docs.
>
> Machine-specific settings go in a gitignored `launcher_settings.local.bat` (see `launcher_settings.bat`).

Contains code for the pipeline, GUI, and analysis code for the paper:
[An intrinsic neuronal manifold underlies brain-wide hierarchical organization of behavior in C. elegans](https://www.biorxiv.org/content/10.1101/2025.03.09.642241v1)

This repository contains python code for analyzing raw volumetric images in two channels: red (tracking) and green (activity).
Behavior analysis is also included as optional analysis, and is in a separate [repository](https://github.com/Zimmer-lab/centerline_behavior_annotation)

In order to reproduce the paper figures, please see the exported jupyter notebooks [here](wbfm/notebooks/paper/revisions); the [README](wbfm/notebooks/paper/revisions/README.md) in that folder lists the notebook that produces each main and supplementary figure.
Note that the raw data is needed, and thus any code related to loading the data would need to be updated to properly run these scripts.
For a guide to the paper datasets (GCaMP, GFP, mutant, immobilized; naming, pooling, and per-neuron Excel summaries), see [Paper datasets](docs/paper_datasets.md).

# Installation

This project is designed to be installed with Anaconda, but we suggest using [mamba](https://mamba.readthedocs.io/en/latest/).
There are different use cases, some of which have easier installation steps.
Please check all sections below to determine which is best for you.


## Just running the GUI

See [GUI README](wbfm/gui/README.md)


## Running the full pipeline (non-Zimmer)

See: [Running the pipeline](docs/running_the_pipeline.md)


## Dev installation (local, for editing)

This is for developers, or if you want to run the full pipeline on your local machine.
See: [detailed installation instructions](docs/installation_instructions.md)


## Running the full pipeline (Zimmer lab)

If you just want to run the pipeline (most people), then you can use the pre-installed environments installed on the cluster, which can be activated using:
```
conda activate /lisc/data/scratch/neurobiology/zimmer/.conda/envs/wbfm/
```

# Running the pipeline

See: [Running the pipeline](docs/running_the_pipeline.md)

# Summary of GUIs

All guis are in the folder: /folder_of_this_README/wbfm/gui/example.py

1. Initial creation of project. 
```bash
python wbfm/gui/create_project_gui.py
```
See: [Running the pipeline](docs/running_the_pipeline.md) for fields to check after creating a new project

2. Visualization of most intermediate steps in the analysis is also possible, and they can be accessed via the progress gui. This also tells you which steps are completed. Note that the progress checking doesn't work with nwb files, but the gui does:
```bash
python wbfm/gui/progress_gui.py
```
Or, if you know the project already:
```bash
python wbfm/gui/progress_gui.py --project_path PATH-TO-YOUR-PROJECT
```

3. Manual annotation and more detailed visualization. 
Note, this can take minutes to load:

```bash
python wbfm/gui/trace_explorer.py --project_path PATH-TO-YOUR-PROJECT
```


# FAQ, including fixes for common problems

[FAQ](docs/faq.md)

Please also check (via search) the open and closed issues on github.

# More details

[Detailed pipeline steps](docs/detailed_pipeline_steps.md)

[Detailed installation instructions](docs/installation_instructions.md)

[Known issues (FAQ)](docs/faq.md)

[Folder organization](docs/data_folder_organization.md)

[NWB file format (axis order, channel naming)](docs/nwb_format.md)

[Paper datasets (GCaMP, GFP, mutant, immobilized; FAQ and Excel summaries)](docs/paper_datasets.md)

If you would like to contribute, see [how to contribute](docs/how_to_contribute.md)
