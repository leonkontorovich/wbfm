"""`go` runner safety: raw-folder sanitizing, already-analysed detection, project job filtering, path translation"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "automation"))

import auto_pipeline as ap  # noqa: E402


def make_raw_worm(root: Path, name="ZIM2165_worm1", ch0="2026-09-17_worm1_Ch0", ch1="2026-09-17_worm1_Ch1",
                  config=True) -> Path:
    worm = root / name
    for ch in (ch0, ch1):
        (worm / ch).mkdir(parents=True)
        (worm / ch / "img.tif").write_bytes(b"x")
    if config:
        (worm / "config.yaml").write_text("exposure_time: 12\n")
    return worm


# --- path translation -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("win, linux", [
    (r"Z:\neurobiology\zimmer\LeonK\raw\w1", "/lisc/data/scratch/neurobiology/zimmer/LeonK/raw/w1"),
    (r"Z:\LeonK\raw\w1", "/lisc/data/scratch/neurobiology/zimmer/LeonK/raw/w1"),
    ("//samba.lisc.univie.ac.at/scratch/neurobiology/zimmer/LeonK/w1",
     "/lisc/data/scratch/neurobiology/zimmer/LeonK/w1"),
    ("/lisc/data/scratch/neurobiology/zimmer/x", "/lisc/data/scratch/neurobiology/zimmer/x"),
])
def test_win_to_linux_path(win, linux):
    assert ap.win_to_linux_path(Path(win) if not win.startswith("/") else win) == linux


@pytest.mark.parametrize("bad", [r"C:\Users\me\raw\w1", r"D:\data\w1", "relative/folder"])
def test_win_to_linux_path_refuses_paths_the_cluster_cannot_see(bad):
    with pytest.raises(ValueError):
        ap.win_to_linux_path(bad)


# --- sanitizing raw folders -------------------------------------------------------------------------------------

def test_missing_config_is_an_error_by_default(tmp_path):
    worm = make_raw_worm(tmp_path, config=False)
    with pytest.raises(FileNotFoundError, match="config.yaml"):
        ap.sanitize_raw_folder(worm)
    assert not (worm / "config.yaml").exists()  # nothing invented in the raw data


def test_default_config_only_on_request(tmp_path):
    worm = make_raw_worm(tmp_path, config=False)
    ap.sanitize_raw_folder(worm, allow_default_config=True)
    assert "exposure_time" in (worm / "config.yaml").read_text()


def test_registered_folder_is_not_mistaken_for_the_red_channel(tmp_path):
    worm = make_raw_worm(tmp_path, ch0="worm1_red", ch1="worm1_green")
    (worm / "registered_stack").mkdir()
    ap.sanitize_raw_folder(worm)
    names = sorted(p.name for p in worm.iterdir() if p.is_dir())
    assert names == ["registered_stack", "worm1_green_Ch1", "worm1_red_Ch0"]


def test_dry_run_changes_nothing(tmp_path):
    worm = make_raw_worm(tmp_path, name="ZIM2165_worm1.5", ch0="worm1_red", ch1="worm1_green", config=False)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    out = ap.sanitize_raw_folder(worm, dry_run=True)
    assert out == worm
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == before


# --- already-analysed recordings ----------------------------------------------------------------------------------

def make_project(parent: Path, name: str, raw_linux: str) -> Path:
    proj = parent / name
    proj.mkdir(parents=True)
    (proj / "project_config.yaml").write_text(f"# Raw Data\nparent_data_folder: \n  {raw_linux}\nred_fname: \n")
    return proj


def test_existing_projects_are_found_by_their_raw_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "win_to_linux_path", lambda p: "/lisc/x/" + Path(p).name)
    raw = tmp_path / "raw" / "worm1"
    out = tmp_path / "analysis"
    mine = make_project(out, "worm1-2026-09-17", "/lisc/x/worm1")
    make_project(out, "worm10-2026-09-17", "/lisc/x/worm10")  # name prefix, different recording
    make_project(out, "other-2026-09-17", "/lisc/x/worm1/")  # same recording, other naming; trailing slash
    (out / "no_config").mkdir()
    found = ap.find_existing_projects(raw, out)
    assert sorted(p.name for p in found) == ["other-2026-09-17", mine.name]
    assert ap.find_existing_projects(raw, tmp_path / "does_not_exist") == []


# --- go status ------------------------------------------------------------------------------------------------------

def test_status_lists_only_this_projects_jobs():
    proj = "/lisc/data/scratch/neurobiology/zimmer/LeonK/A/worm1-x"
    lines = [
        f"111|wbfm_worm1|RUNNING|1:00:00|node1|/lisc/home/user",                     # master job (by id)
        f"222|segmentation|RUNNING|0:30:00|node2|{proj}/snakemake",                # child of this project
        f"333|segmentation|PENDING|0:00|(Priority)|{proj}2/snakemake",            # other project, same prefix
        f"444|alt_segmentation|RUNNING|0:10:00|node3|/lisc/.../worm2-x/snakemake",  # other project
        "",
    ]
    jobs = ap.select_project_jobs(lines, proj, master_ids={"111"})
    assert [j.split()[0] for j in jobs] == ["111", "222"]


def test_go_skips_analysed_recordings_unless_forced(tmp_path, monkeypatch):
    monkeypatch.setattr(ap, "win_to_linux_path", lambda p: "/lisc/x/" + Path(p).name)
    submitted = []
    monkeypatch.setattr(ap, "initialize_project", lambda raw, out, exp, imm: (out / f"{exp}-new", "/lisc/new"))
    monkeypatch.setattr(ap, "submit_dual_pipeline", lambda d, l: submitted.append(d) or "123")
    raw = make_raw_worm(tmp_path / "raw")
    out = tmp_path / "analysis"
    make_project(out, "ZIM2165_worm1-2026-09-17", "/lisc/x/ZIM2165_worm1")

    assert ap.process_single_worm(raw, out, "LeonK") is None
    assert submitted == []
    info = ap.process_single_worm(raw, out, "LeonK", force=True)
    assert info["job_id"] == "123" and len(submitted) == 1
