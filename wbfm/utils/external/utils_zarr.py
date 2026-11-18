import logging
import os
import shutil
from pathlib import Path
import zarr
from zarr.storage import ZipStore

ZARR_MAJOR_VERSION = int(zarr.__version__.split(".")[0])

# zarr 2 (cluster) raises PathNotFoundError for a missing/corrupt array; zarr 3 raises NodeNotFoundError
_ZARR_NOT_FOUND_ERRORS = tuple(getattr(zarr.errors, name) for name in ("PathNotFoundError", "NodeNotFoundError")
                               if hasattr(zarr.errors, name))


def zeros_like_compat(arr, store=None):
    """
    zarr.zeros_like() that also works on zarr 3: same shape, dtype and chunks as ``arr``, filled with 0.

    On zarr 2 (the cluster) this is exactly ``zarr.zeros_like(arr, store=store)``. On zarr 3 (Windows GUI env) the
    array is written in zarr v2 format, uncompressed, so the cluster's zarr 2 can still read it.

    store: None for an in-memory array, a path, or (zarr 2 only) a store object such as zarr.DirectoryStore

    ``arr`` may also be a dask or numpy array (e.g. masks of an NWB-loaded project): dask's chunks are a tuple of
    tuples, which zarr.zeros_like cannot use, so non-zarr input gets one volume per chunk.
    """
    chunks = getattr(arr, "chunks", None)
    zarr_like_chunks = isinstance(chunks, tuple) and all(isinstance(c, int) for c in chunks)
    if not zarr_like_chunks:
        chunks = (1,) + tuple(arr.shape[1:])  # one volume per chunk, like the pipeline writes
    if ZARR_MAJOR_VERSION < 3:
        if zarr_like_chunks:
            return zarr.zeros_like(arr, store=store)
        return zarr.zeros(shape=arr.shape, chunks=chunks, dtype=arr.dtype, store=store)
    kwargs = dict(shape=arr.shape, chunks=chunks, dtype=arr.dtype, zarr_format=2)
    if store is None:
        return zarr.zeros(**kwargs)
    return zarr.open_array(store=str(store), mode="w", compressor=None, fill_value=0, **kwargs)


def zip_raw_data_zarr(raw_fname, delete_original=True, verbose=1):
    out_fname_zip = Path(raw_fname).with_suffix('.zarr.zip')
    assert os.path.exists(raw_fname), f"Did not find original zarr at {raw_fname}"
    if verbose >= 1:
        print(f"Zipping zarr file {raw_fname} to {out_fname_zip}")

    with zarr.ZipStore(str(out_fname_zip), mode='w') as target_data_store:
        raw_data_store = zarr.DirectoryStore(str(raw_fname))
        # Copy the data to the zip store
        zarr.copy_store(raw_data_store, target_data_store)

    if delete_original:
        if verbose >= 1:
            print(f"Deleting original: {raw_fname}")
        shutil.rmtree(raw_fname)

    return out_fname_zip

def zarr_reader_folder_or_zipstore(fname: str, depth: int = 0):
    """Enforces readonly access"""
    try:
        if Path(fname).is_dir():
            dat = zarr.open(fname, mode='r')
        elif fname.endswith('.zarr.zip'):
            store = ZipStore(fname, mode='r')
            dat = zarr.open(store)
        else:
            raise NotImplementedError(f"Not a zarr directory or zip store: {fname}")
    except OSError as e:
        if depth > 0:
            raise e
        # On Windows, if the path contains a special character, zarr.open() will fail. Retry with raw string
        dat = zarr_reader_folder_or_zipstore(rf"{fname}", depth=depth + 1)
    except _ZARR_NOT_FOUND_ERRORS as e:
        logging.error(
            f"Corrupted zarr file found at {fname}; most likely the file or folder needs to be deleted"
        )
        raise e

    return dat
