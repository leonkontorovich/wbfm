import sys
sys.path.append(r"C:\GithubRepositories\wbfm")
from wbfm.utils.projects.finished_project_data import ProjectData
from wbfm.utils.visualization.utils_napari import napari_labels_from_traces_dataframe

import argparse
import sys
import os

# Add wbfm to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from launch_gui import launch_gui_prompt, save_history

def get_project_path():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_path", nargs="?", default=None)
    args = parser.parse_args()
    
    if args.project_path:
        return args.project_path
        
    path = launch_gui_prompt()
    if path:
        return path
        
    return r"Z:\neurobiology\zimmer\LeonK\25_degrees_npr-1_vs_rde4\AX10059worm1-2026-04-10\project_config.yaml"

project_path = get_project_path()
if os.path.exists(project_path):
    save_history(project_path)
project_data = ProjectData.load_final_project_data(project_path,
                                                   to_load_tracklets=False,
                                                   to_load_interactivity=False,
                                                   to_load_segmentation_metadata=True,
                                                   to_load_frames=False,
                                                   allow_hybrid_loading=True)

df = project_data.red_traces
print("Dataframe columns:", df.columns)

try:
    options = napari_labels_from_traces_dataframe(df, z_to_xy_ratio=project_data.physical_unit_conversion.z_to_xy_ratio)
    print("Success! Keys in options:", options.keys())
except Exception as e:
    import traceback
    traceback.print_exc()

