import os
from pathlib import Path

import numpy as np

# Precalculated camera alignment matrix relative to package root
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CAMERA_ALIGNMENT = _PACKAGE_ROOT / "nn_checkpoints" / "warp_mat_green_to_red_2022-04-09.npy"
CAMERA_ALIGNMENT_MATRIX = str(_DEFAULT_CAMERA_ALIGNMENT)


def get_precalculated_camera_alignment_matrix():
    matrix_path = Path(CAMERA_ALIGNMENT_MATRIX)
    if matrix_path.exists():
        return np.load(matrix_path)
    return None


def get_pretrained_network_path(num_neurons):
    return os.path.join(PRETRAINED_DLC_DIR, f"{num_neurons}", "snapshot-100000")
