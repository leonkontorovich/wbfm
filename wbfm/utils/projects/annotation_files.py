"""
Which manual-annotation file of a project is the current one.

Shared by the recording dashboard (launch_gui.py) and `go check-ids` (automation/auto_pipeline.py), so the ID counts,
the '?' list and "Open in Excel" all refer to the same file. Standard library only (cheap to import, Python 3.8).
"""
import os
from typing import List, Optional, Union

# In priority order (used when no modification time decides); paths relative to the project folder
ANNOTATION_CANDIDATES = (
    "3-tracking/manual_annotation/manual_annotation.xlsx",
    "3-tracking/manual_annotation/manual_annotation.h5",
    "3-tracking/manual_annotation/manual_annotation_iterative.xlsx",
    "3-tracking/manual_annotation/manual_annotation_hungarian.xlsx",
    "3-tracking/id_transfer_output/hungarian/manual_annotation.xlsx",
    "3-tracking/hungarian/manual_annotation.xlsx",
    "manual_annotation.xlsx",
)


def existing_annotation_files(project_dir: Union[str, os.PathLike]) -> List[str]:
    """Existing candidate files, in priority order"""
    paths = [os.path.join(str(project_dir), *rel.split("/")) for rel in ANNOTATION_CANDIDATES]
    return [p for p in paths if os.path.isfile(p)]


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return float("-inf")


def newest_annotation_file(project_dir: Union[str, os.PathLike], excel_only: bool = False) -> Optional[str]:
    """The most recently modified annotation file (ties keep priority order), or None"""
    files = existing_annotation_files(project_dir)
    if excel_only:
        files = [f for f in files if f.endswith(".xlsx")]
    if not files:
        return None
    return max(files, key=_mtime)  # max() returns the first of equal keys, i.e. the higher-priority file


def annotation_excel_file(project_dir: Union[str, os.PathLike], newest: Optional[str] = None) -> Optional[str]:
    """
    The Excel file to open for editing: the newest annotation file if it is an .xlsx; if the newest is the .h5 copy,
    the .xlsx next to it; otherwise the first existing .xlsx in priority order
    """
    if newest is None:
        newest = newest_annotation_file(project_dir)
    if newest is None:
        return None
    if newest.endswith(".xlsx"):
        return newest
    sibling = os.path.splitext(newest)[0] + ".xlsx"
    if os.path.isfile(sibling):
        return sibling
    return next((f for f in existing_annotation_files(project_dir) if f.endswith(".xlsx")), None)
