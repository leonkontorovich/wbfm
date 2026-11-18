"""zeros_like_compat: same layout as the source, zero-filled, on zarr 2 (cluster) and zarr 3 (Windows GUI env)"""
import numpy as np
import pytest
import zarr

from wbfm.utils.external.utils_zarr import zeros_like_compat


def _check(z, shape, chunks):
    assert z.shape == shape and z.chunks == chunks
    assert int(np.asarray(z[2]).max()) == 0
    z[3] = 5
    assert int(np.asarray(z[3]).min()) == 5


def test_zarr_source_keeps_its_chunks(tmp_path):
    src = zarr.open_array(str(tmp_path / "src.zarr"), mode="w", shape=(6, 2, 4, 4), chunks=(1, 2, 4, 4),
                          dtype="uint16", fill_value=0)
    _check(zeros_like_compat(src), (6, 2, 4, 4), (1, 2, 4, 4))
    _check(zeros_like_compat(src, store=str(tmp_path / "out.zarr")), (6, 2, 4, 4), (1, 2, 4, 4))


@pytest.mark.parametrize("kind", ["numpy", "dask"])
def test_non_zarr_source_gets_one_volume_per_chunk(tmp_path, kind):
    arr = np.zeros((6, 2, 4, 4), dtype="uint16")
    if kind == "dask":
        da = pytest.importorskip("dask.array")
        arr = da.from_array(arr, chunks=(1, 2, 4, 4))  # dask chunks are a tuple of tuples (NWB-loaded masks)
    _check(zeros_like_compat(arr), (6, 2, 4, 4), (1, 2, 4, 4))
    _check(zeros_like_compat(arr, store=str(tmp_path / "out.zarr")), (6, 2, 4, 4), (1, 2, 4, 4))
