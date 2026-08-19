"""
Simple launcher for the trace explorer GUI.
Run: python launch_gui.py [project_config_path]
If no path is provided, a file selection dialog will appear.
"""
import sys
import os
import argparse
import json

# Add wbfm to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wbfm.gui.utils.napari_trace_explorer import napari_trace_explorer_from_config

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".recent_projects.json")

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_history(path):
    history = load_history()
    if path in history:
        history.remove(path)
    history.insert(0, path)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history[:10], f)

def launch_gui_prompt():
    recent = load_history()
    selected_path = None
    
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("tkinter is not available for file dialog.")
        return None

    root = tk.Tk()
    root.title("WBFM Launcher")
    
    def on_select_recent(path):
        nonlocal selected_path
        selected_path = path
        root.destroy()
        
    def on_browse():
        nonlocal selected_path
        initial_dir = os.path.dirname(recent[0]) if recent else None
        path = filedialog.askopenfilename(
            title="Select project_config.yaml",
            initialdir=initial_dir,
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")]
        )
        if path:
            selected_path = path
            root.destroy()
            
    tk.Label(root, text="Launch WBFM Trace Explorer", font=("Arial", 14, "bold")).pack(pady=10)
    
    if recent:
        tk.Label(root, text="Recent Projects:", font=("Arial", 10)).pack(anchor="w", padx=10)
        for path in recent:
            # truncate path if too long
            display_path = path if len(path) < 70 else "..." + path[-67:]
            btn = tk.Button(root, text=display_path, command=lambda p=path: on_select_recent(p), anchor="w")
            btn.pack(fill="x", padx=10, pady=2)
            
    tk.Button(root, text="Browse for new project...", command=on_browse, bg="lightblue").pack(pady=15, padx=10, fill="x")
    
    # Center window
    root.geometry("500x350")
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')
    
    root.mainloop()
    return selected_path

def main():
    parser = argparse.ArgumentParser(description="Launch trace explorer")
    parser.add_argument("project_path", nargs="?", default=None, help="Path to project_config.yaml")
    args = parser.parse_args()

    project_path = args.project_path

    if not project_path:
        project_path = launch_gui_prompt()
            
    if not project_path:
        # Fallback to default
        project_path = r"Z:\neurobiology\zimmer\LeonK\25_degrees_npr-1_vs_rde4\AX10059worm1-2026-04-10\project_config.yaml"
        print(f"No project path provided. Using default: {project_path}")

    if project_path and os.path.isdir(project_path):
        candidate = os.path.join(project_path, "project_config.yaml")
        if os.path.exists(candidate):
            project_path = candidate

    # Save to history if valid
    if project_path and os.path.exists(project_path):
        save_history(project_path)
    else:
        print(f"Error: Project path does not exist: {project_path}")
        sys.exit(1)

    print(f"Loading project: {project_path}")
    print("This may take several minutes...")

    napari_trace_explorer_from_config(
        project_path,
        load_tracklets=True,
        force_tracklets_to_be_sparse=True,
        DEBUG=True,
    )

if __name__ == "__main__":
    main()
