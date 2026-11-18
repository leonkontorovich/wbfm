"""
Test repository hygiene, agent token efficiency, and ignore configuration.
Enforces that AGENTS.md stays concise (< 15 KB), historical setup narratives
remain archived in docs/, and token-draining assets are blocked from agent context.
"""
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def local_agent_file(name: str) -> Path:
    """AGENTS.md, CLAUDE.md and the agent ignore files are gitignored (local to each workstation): check them where
    they exist, skip in a fresh clone (CI, the cluster) instead of failing there"""
    path = REPO_ROOT / name
    if not path.exists():
        pytest.skip(f"{name} is local-only (gitignored) and not present in this checkout")
    return path


def test_agents_md_exists_and_size_bounded():
    agents_path = local_agent_file("AGENTS.md")
    
    size_bytes = agents_path.stat().st_size
    max_bytes = 15 * 1024  # 15 KB bound
    assert size_bytes < max_bytes, (
        f"AGENTS.md has ballooned to {size_bytes} bytes (limit is {max_bytes} bytes). "
        "Keep AGENTS.md compact to preserve agent context."
    )

    content = agents_path.read_text(encoding="utf-8")
    assert "agy_tool_safety" in content, "AGENTS.md must document agy_tool_safety static rules"
    assert "read_file" in content, "AGENTS.md must mandate native read_file priority"
    assert "gui_only" in content, "AGENTS.md must specify gui_only environment"
    assert "launch_gui.py" in content, "AGENTS.md must document launch_gui.py entrypoint"
    assert "go.py" in content, "AGENTS.md must document go.py entrypoint"


def test_claude_md_is_clean_pointer():
    claude_path = local_agent_file("CLAUDE.md")
    
    size_bytes = claude_path.stat().st_size
    assert size_bytes < 1024, f"CLAUDE.md is unexpectedly large ({size_bytes} bytes); should be a concise pointer."
    
    content = claude_path.read_text(encoding="utf-8")
    assert "@AGENTS.md" in content, "CLAUDE.md must reference/transclude @AGENTS.md"


def test_windows_setup_narrative_is_archived():
    root_setup = REPO_ROOT / "WINDOWS_SETUP_FOR_CLAUDE.md"
    assert not root_setup.exists(), (
        "WINDOWS_SETUP_FOR_CLAUDE.md should not be in the repository root. "
        "It must remain archived in docs/ to prevent agents from ingesting 42 KB on startup."
    )
    
    archive_setup = REPO_ROOT / "docs" / "windows_setup_archive.md"
    assert archive_setup.exists(), f"Archived setup guide missing at {archive_setup}"
    assert archive_setup.stat().st_size > 20 * 1024, "Archived setup guide appears truncated"


@pytest.mark.parametrize("filename", [".geminiignore", ".claudeignore"])
def test_ignore_rules_block_heavy_context_assets(filename):
    ignore_path = local_agent_file(filename)
    
    content = ignore_path.read_text(encoding="utf-8")
    lines = {line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")}
    
    required_patterns = [
        ".dashboard_cache.json",
        ".recent_projects.json",
        "venv_gui/",
        "conda-environments/",
        "df_pytest.pickle",
        "*.h5",
        "*.zarr/",
        "*.pickle",
    ]
    
    for pattern in required_patterns:
        assert pattern in lines, f"Pattern '{pattern}' missing from {filename}"
