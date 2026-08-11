"""
Project configuration loader for The Ripple Effect.

Reads config/settings.yaml and resolves absolute paths under the project root.
No downloads or analysis happen here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT / "config" / "settings.yaml"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load YAML settings and attach resolved_paths for common folders."""
    settings_file = path or SETTINGS_PATH
    with settings_file.open(encoding="utf-8") as handle:
        settings: dict[str, Any] = yaml.safe_load(handle) or {}

    twin = ROOT / str(settings.get("living_feeds", {}).get("package_dir", "outputs/twin_lakes"))
    settings["resolved_paths"] = {
        "root": ROOT,
        "raw_dir": ROOT / "data" / "raw",
        "interim_dir": ROOT / "data" / "interim",
        "processed_dir": ROOT / "data" / "processed",
        "reference_dir": ROOT / "data" / "reference",
        "csv_dir": ROOT / "outputs" / "csv",
        "gpkg_dir": ROOT / "outputs" / "geopackage",
        "geojson_dir": ROOT / "outputs" / "geojson",
        "raster_dir": ROOT / "outputs" / "raster",
        "maps_dir": ROOT / "outputs" / "maps",
        "reports_dir": ROOT / "outputs" / "reports",
        "twin_lakes_dir": twin,
        "logs_dir": ROOT / "logs",
        "data_sources_csv": ROOT / "data" / "reference" / "data_sources.csv",
    }
    return settings
