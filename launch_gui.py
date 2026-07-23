"""
Simple launcher for the trace explorer GUI.
No command-line arguments needed - just run: python launch_gui.py
"""
import sys
import os

# Add wbfm to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wbfm.gui.utils.napari_trace_explorer import napari_trace_explorer_from_config

project_path = r"Z:\neurobiology\zimmer\LeonK\25_degrees_npr-1_vs_rde4\AX10059worm1-2026-04-10\project_config.yaml"

print(f"Loading project: {project_path}")
print("This may take several minutes...")

napari_trace_explorer_from_config(
    project_path,
    load_tracklets=True,
    force_tracklets_to_be_sparse=True,
    DEBUG=True,
)
