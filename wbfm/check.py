"""
WBFM System Health Check ('wbfm doctor')
Run: python -m wbfm.check [optional_project_path]
"""
import sys
import os
import platform
from pathlib import Path

def run_check(project_path=None):
    print("=" * 60)
    print("           WBFM ENVIRONMENT & SYSTEM HEALTH CHECK           ")
    print("=" * 60)

    all_passed = True

    # 1. Python and OS
    print(f"\n[1] Platform & Runtime:")
    print(f"    OS: {platform.system()} {platform.release()} ({platform.version()})")
    print(f"    Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"    Default Encoding: {sys.getdefaultencoding()}")
    if sys.flags.utf8_mode:
        print("    UTF-8 Mode (-X utf8): ENABLED [OK]")
    else:
        print("    UTF-8 Mode (-X utf8): NOT EXPLICIT (Consider using python -X utf8 on Windows)")

    # 2. Windows Long Paths
    if platform.system() == "Windows":
        print(f"\n[2] Windows Filesystem:")
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem")
            val, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            if val == 1:
                print("    LongPathsEnabled: 1 (Enabled) [OK]")
            else:
                print("    LongPathsEnabled: 0 (Disabled) [WARNING: deeply nested Zarr directories may exceed MAX_PATH]")
        except Exception as e:
            print(f"    Could not read LongPathsEnabled registry: {e}")

    # 3. Core Package Imports
    print(f"\n[3] Package Imports:")
    packages = [
        ("wbfm", "wbfm"),
        ("zarr", "zarr"),
        ("tables", "PyTables (HDF5)"),
        ("sacred", "sacred"),
        ("ruamel.yaml", "ruamel.yaml"),
    ]
    for mod, label in packages:
        try:
            __import__(mod)
            print(f"    {label}: OK")
        except ImportError as e:
            print(f"    {label}: FAILED ({e})")
            all_passed = False

    # 4. Snakemake
    try:
        import snakemake
        smk_ver = getattr(snakemake, '__version__', 'unknown')
        if smk_ver.startswith("7.32"):
            print(f"    Snakemake: {smk_ver} [OK]")
        else:
            print(f"    Snakemake: {smk_ver} [NOTE: Pipeline is designed for 7.32.x]")
    except ImportError:
        print("    Snakemake: NOT INSTALLED (Required for pipeline execution)")

    # 5. Qt & Napari GUI
    print(f"\n[4] GUI & Rendering Stack:")
    try:
        from qtpy.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        print("    Qt / PyQt: OK")
    except Exception as e:
        print(f"    Qt / PyQt: FAILED ({e})")
        all_passed = False

    try:
        import napari
        viewer = napari.Viewer(show=False)
        viewer.close()
        print(f"    Napari: {napari.__version__} (Headless viewer test passed) [OK]")
    except Exception as e:
        print(f"    Napari: FAILED ({e})")
        all_passed = False

    # 6. ~/.wbfm/config.yaml
    print(f"\n[5] Machine Configuration (~/.wbfm/config.yaml):")
    try:
        from wbfm.utils.general.utils_hardcoded import load_hardcoded_neural_network_paths, is_zimmer_lab
        print(f"    is_zimmer_lab(): {is_zimmer_lab()}")
        paths = load_hardcoded_neural_network_paths()
        print(f"    Loaded config sections: {list(paths.keys())} [OK]")
    except Exception as e:
        print(f"    Config loading: FAILED ({e})")
        all_passed = False

    # 7. Optional Project Validation
    if project_path:
        print(f"\n[6] Project Configuration Check: {project_path}")
        p_path = Path(project_path)
        if not p_path.exists():
            print(f"    ERROR: Path {p_path} does not exist.")
            all_passed = False
        else:
            try:
                from wbfm.utils.projects.finished_project_data import ProjectData
                print("    Loading ProjectData metadata...")
                p_data = ProjectData.load_final_project_data(
                    str(p_path),
                    to_load_tracklets=False,
                    to_load_interactivity=False,
                )
                print(f"    Volumes: {p_data.num_frames}")
                try:
                    print(f"    Finished neurons: {len(p_data.finished_neuron_names())}")
                except Exception as e:
                    print(f"    Finished neurons: N/A ({e})")
                print("    Project data check: OK")
            except Exception as e:
                print(f"    Project data check: FAILED ({e})")
                all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("          ALL CHECKS PASSED - READY FOR USE          ")
    else:
        print("          SOME CHECKS REPORTED WARNINGS/FAILURES     ")
    print("=" * 60 + "\n")
    return all_passed

if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(0 if run_check(proj) else 1)  # non-zero so scripts/launchers can use it as a preflight
