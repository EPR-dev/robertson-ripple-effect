"""
PYTHON DATA PREP — validation helpers and Phase 1 QA report writer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

from utils import append_qa_rows, basic_vector_qa


def validate_foundation_layers(
    layers: dict[str, gpd.GeoDataFrame],
    *,
    qa_path: Path,
    study_area: gpd.GeoDataFrame,
    crs_analysis: str,
    logger: logging.Logger,
    context_aoi: gpd.GeoDataFrame | None = None,
) -> pd.DataFrame:
    """Run basic QA on foundation layers and write data_quality_report.csv."""
    rows: list[dict[str, Any]] = []
    sa = unary_union(list(study_area.to_crs(crs_analysis).geometry))
    ca = (
        unary_union(list(context_aoi.to_crs(crs_analysis).geometry))
        if context_aoi is not None and not context_aoi.empty
        else sa
    )

    for name, gdf in layers.items():
        rows.extend(basic_vector_qa(gdf, name))
        if gdf.empty:
            continue
        gdf_a = gdf.to_crs(crs_analysis)
        # Context layers are allowed outside the 12.5 km study buffer
        ref = ca if name in {"protected_areas", "lga", "roads", "context_aoi"} else sa
        outside = int((~gdf_a.intersects(ref)).sum())
        if name in {"study_area", "context_aoi"}:
            outside = 0
        rows.append(
            {
                "layer": name,
                "check": "features_outside_reference_aoi",
                "value": outside,
                "status": "OK" if outside == 0 else "WARN",
            }
        )
        if name == "robertson_nature_reserve":
            area_ha = float(gdf_a.geometry.area.sum() / 10000.0)
            rows.append(
                {
                    "layer": name,
                    "check": "area_ha",
                    "value": round(area_ha, 3),
                    "status": "OK" if 1.0 < area_ha < 20.0 else "WARN",
                }
            )

    frame = append_qa_rows(rows, qa_path)
    logger.info("Wrote QA report: %s (%s checks)", qa_path, len(rows))
    return frame
