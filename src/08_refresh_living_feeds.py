"""
Twin Lakes living feeds refresh (all four steps in order).

1. BioNet (+ optional iNaturalist) → blooms / neighbours this season
2. Sentinel-2 greenness → remnant vs cleared NDVI
3. NSW RFS major incidents → fire pressure near AOI
4. Write outputs/twin_lakes/story_package.json for the StoryMap

Usage:
  python src/08_refresh_living_feeds.py
  python src/08_refresh_living_feeds.py --force-species-download
  python src/08_refresh_living_feeds.py --skip-greenness --skip-fire
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from living_feeds import (  # noqa: E402
    refresh_fire_feed,
    refresh_greenness_feed,
    refresh_species_feed,
    write_story_package,
)
from utils import ensure_dirs, setup_logging  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Twin Lakes living feeds for The Ripple Effect")
    parser.add_argument("--force-species-download", action="store_true", help="Re-download BioNet + iNat (ignore cache)")
    parser.add_argument("--skip-species", action="store_true")
    parser.add_argument("--skip-greenness", action="store_true")
    parser.add_argument("--skip-fire", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    paths = settings["resolved_paths"]
    logger = setup_logging(
        paths["logs_dir"],
        name="living_feeds",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(paths["twin_lakes_dir"], paths["raw_dir"] / "species")

    feeds: dict = {}

    logger.info("=== 1/4 Species (BioNet + iNaturalist) ===")
    if args.skip_species:
        feeds["species"] = {"status": "skipped"}
    else:
        feeds["species"] = refresh_species_feed(
            settings, logger, force_download=args.force_species_download
        )
        logger.info(
            "Species OK — season neighbours=%s top=%s",
            feeds["species"].get("neighbours_season_n"),
            feeds["species"].get("top_neighbour"),
        )

    logger.info("=== 2/4 Greenness (Sentinel-2 / Planetary Computer) ===")
    if args.skip_greenness:
        feeds["greenness"] = {"status": "skipped"}
    else:
        try:
            feeds["greenness"] = refresh_greenness_feed(settings, logger)
            logger.info(
                "Greenness status=%s delta=%s",
                feeds["greenness"].get("status"),
                feeds["greenness"].get("ndvi_delta"),
            )
        except Exception as exc:
            logger.exception("Greenness feed failed")
            feeds["greenness"] = {"status": "error", "message": str(exc)}

    logger.info("=== 3/4 Fire pressure (NSW RFS major incidents) ===")
    if args.skip_fire:
        feeds["fire"] = {"status": "skipped"}
    else:
        try:
            feeds["fire"] = refresh_fire_feed(settings, logger)
            logger.info("Fire incidents in watch window: %s", feeds["fire"].get("incidents_in_watch"))
        except Exception as exc:
            logger.exception("Fire feed failed")
            feeds["fire"] = {"status": "error", "message": str(exc)}

    logger.info("=== 4/4 Twin Lakes story package ===")
    package_path = write_story_package(settings, feeds, logger)
    logger.info("Done. StoryMap can load: %s", package_path)


if __name__ == "__main__":
    main()
