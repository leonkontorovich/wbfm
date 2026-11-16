import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "automation"))

from auto_pipeline import SEGMENTATION_RESOURCES, right_size_segmentation_resources  # noqa: E402

TEMPLATE = REPO_ROOT / "wbfm" / "new_project_defaults" / "snakemake" / "cluster_config.yaml"


def test_segmentation_blocks_are_right_sized_and_nothing_else_changes():
    text = TEMPLATE.read_text(encoding="utf-8")
    before, after = yaml.safe_load(text), yaml.safe_load(right_size_segmentation_resources(text))

    for rule in ("segmentation", "alt_segmentation"):
        assert {k: str(after[rule][k]) for k in SEGMENTATION_RESOURCES} == SEGMENTATION_RESOURCES
    for rule in before:
        if rule not in ("segmentation", "alt_segmentation"):
            assert after[rule] == before[rule], rule


def test_is_idempotent_and_keeps_line_endings():
    text = "segmentation:\r\n    time: 1-12:00:00  # long\r\n    mem: 256G\r\npreprocessing:\r\n    mem: 120G\r\n"
    once = right_size_segmentation_resources(text)
    assert once == right_size_segmentation_resources(once)
    assert once.count("\r\n") == text.count("\r\n")
    assert "mem: 48G" in once and "mem: 120G" in once and "# long" in once
