"""Environment checks shared by the skill CLI."""

import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def check_environment(cache_dir: Path, artifact_dir: Path) -> dict:
    """Create external work directories and report currently available capabilities."""
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required")

    paths = {"cache_dir": cache_dir.resolve(), "artifact_dir": artifact_dir.resolve()}
    if paths["cache_dir"] == paths["artifact_dir"]:
        raise ValueError("Cache and artifact directories must differ")

    for label, path in paths.items():
        if path.is_relative_to(SKILL_ROOT):
            raise ValueError(f"{label} must be outside the skill directory")

    for label, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise ValueError(f"{label} is not a directory: {path}")

    return {
        "status": "ready",
        "stage": 7,
        "python": sys.version.split()[0],
        "cache_dir": str(paths["cache_dir"]),
        "artifact_dir": str(paths["artifact_dir"]),
        "capabilities": {
            "environment_check": True,
            "article_resolution": True,
            "pageviews_fetch": True,
            "trend_analysis": True,
            "chart": True,
            "pdf_report": True,
            "one_command_workflow": True,
        },
    }
