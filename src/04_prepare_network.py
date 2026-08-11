"""
Phase 4 — The Network (habitat prep for ArcGIS).

Dissolve/threshold native vegetation into habitat patches, compute isolation
proxies, prepare road barrier inputs, export phase4_network.gpkg + rule docs.

Does not run least-cost corridors / Scenario A/B (ArcGIS handoff).
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from config import load_settings  # noqa: E402
from prepare_connectivity import (  # noqa: E402
    add_patch_network_metrics,
    dissolve_habitat_patches,
    filter_core_habitat,
    patch_summary_table,
    prepare_road_barriers,
)
from utils import (  # noqa: E402
    append_qa_rows,
    basic_vector_qa,
    ensure_dirs,
    setup_logging,
    write_gdf,
)


def _write_rules_doc(path: Path, cfg: dict, summary: pd.DataFrame) -> None:
    path.write_text(
        f"""# Phase 4 — Habitat network rules (Python prep)

These layers are **analysis-ready inputs** for ArcGIS connectivity work.
They are **not** a connectivity model and **not** a suitability / opportunity score.

## Habitat patches

| Rule | Value |
|------|-------|
| Source | Phase 2 `native_vegetation` (SVTM classified PCTs; excludes Not classified) |
| Gap-close (core / rainforest) | Merge polygons with edge gap ≤ **{cfg.get('gap_close_m')} m** (buffer graph / union-find), dissolve each component |
| Gap-close (all native) | **{cfg.get('native_gap_close_m')} m** (0 keeps SVTM mapping units — native cover is nearly continuous) |
| Minimum patch area | **{cfg.get('min_patch_area_ha')} ha** (source slivers below ~25% of this dropped first) |
| Core habitat filter | veg_form/class contains: {', '.join(cfg.get('core_veg_form_contains') or [])} |
| CRS | Analysis CRS from settings (EPSG:7856) |

### Layers
- `habitat_patches` — all classified native vegetation patches after rules
- `core_habitat_patches` — rainforest + wet sclerophyll focus (corridor candidate habitat)
- `rainforest_patches` — rainforest-only patches (story layer)

### Patch attributes (proxies only)
- `area_ha`, `perimeter_m`, `shape_isoperimetric`
- `nn_distance_m` — edge-to-edge distance to nearest other patch (search capped)
- `n_patches_within_isolation_r` — count of other patches within isolation radius
- `dist_to_reserve_m`, `touches_reserve` — relationship to Robertson Nature Reserve

## Road barriers

| Field | Meaning |
|-------|---------|
| `barrier_class` | high / medium / low from NSW `functionhierarchy` |
| `cost_hint` | Ordinal hint for ArcGIS Cost Distance setup (higher = stronger barrier candidate) |

**Explicitly not included:** species-specific resistance, traffic volume calibration,
or any weighted Restoration Opportunity Index.

## ArcGIS handoff (your analysis)
1. Build cost surface from `roads_barriers.cost_hint` (+ optional land-cover costs you define)
2. Least-cost corridors / linkage mapper style products between `core_habitat_patches`
3. Scenario A — network with Robertson Nature Reserve removed
4. Scenario B — where small restoration yields largest connectivity gain
5. Fragmentation / equivalent connected area metrics as needed

## Patch summary (this run)

```
{summary.to_string(index=False) if not summary.empty else '(no patches)'}
```
""",
        encoding="utf-8",
    )


def main() -> None:
    settings = load_settings()
    paths = settings["resolved_paths"]
    study_cfg = settings["study_area"]
    conn = settings.get("connectivity", {})
    crs = str(study_cfg["crs_analysis"])

    logger = setup_logging(
        paths["logs_dir"],
        name="phase4_network",
        level=str(settings.get("logging", {}).get("level", "INFO")),
    )
    ensure_dirs(paths["interim_dir"], paths["reports_dir"], paths["gpkg_dir"])

    phase1 = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase1_interim_gpkg", "phase1_foundation.gpkg")
    )
    phase2 = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase2_interim_gpkg", "phase2_remnant.gpkg")
    )
    if not phase1.is_file():
        raise FileNotFoundError(f"Phase 1 GPKG missing: {phase1}")
    if not phase2.is_file():
        raise FileNotFoundError(f"Phase 2 GPKG missing: {phase2}")

    logger.info("=== Phase 4: The Network (habitat prep) ===")
    study_area = gpd.read_file(phase1, layer="study_area")
    reserve = gpd.read_file(phase1, layer="robertson_nature_reserve")
    roads = gpd.read_file(phase1, layer="roads")
    native = gpd.read_file(phase2, layer="native_vegetation")
    rainforest = gpd.read_file(phase2, layer="rainforest_extant")

    gap = float(conn.get("gap_close_m", 15))
    native_gap = float(conn.get("native_gap_close_m", 0))
    min_ha = float(conn.get("min_patch_area_ha", 0.5))
    nn_cap = float(conn.get("nn_search_cap_m", 10000))
    iso_r = float(conn.get("isolation_radius_m", 1000))
    core_needles = list(conn.get("core_veg_form_contains") or ["Rainforest", "Wet Sclerophyll"])

    logger.info("Building habitat_patches (all native, gap_close=%sm)…", native_gap)
    habitat_patches = dissolve_habitat_patches(
        native,
        crs_analysis=crs,
        gap_close_m=native_gap,
        min_patch_area_ha=min_ha,
        habitat_class="native",
    )
    habitat_patches = add_patch_network_metrics(
        habitat_patches,
        reserve=reserve,
        nn_search_cap_m=nn_cap,
        isolation_radius_m=iso_r,
    )
    logger.info("habitat_patches: %s", len(habitat_patches))

    logger.info("Building core_habitat_patches…")
    core_src = filter_core_habitat(native, form_contains=core_needles)
    core_patches = dissolve_habitat_patches(
        core_src,
        crs_analysis=crs,
        gap_close_m=gap,
        min_patch_area_ha=min_ha,
        habitat_class="core",
    )
    core_patches = add_patch_network_metrics(
        core_patches,
        reserve=reserve,
        nn_search_cap_m=nn_cap,
        isolation_radius_m=iso_r,
    )
    logger.info("core_habitat_patches: %s (from %s source polys)", len(core_patches), len(core_src))

    logger.info("Building rainforest_patches…")
    rf_patches = dissolve_habitat_patches(
        rainforest,
        crs_analysis=crs,
        gap_close_m=gap,
        min_patch_area_ha=min_ha,
        habitat_class="rainforest",
    )
    rf_patches = add_patch_network_metrics(
        rf_patches,
        reserve=reserve,
        nn_search_cap_m=nn_cap,
        isolation_radius_m=iso_r,
    )
    logger.info("rainforest_patches: %s", len(rf_patches))

    # Road barriers
    barrier_map = conn.get("road_barrier_map") or {}
    # YAML may load keys as ints
    barrier_map = {int(k) if str(k).isdigit() else k: v for k, v in barrier_map.items()}
    default_barrier = conn.get("road_barrier_default") or {"barrier_class": "low", "cost_hint": 5}
    roads_barriers = prepare_road_barriers(
        roads,
        crs_analysis=crs,
        study_area=study_area,
        barrier_map=barrier_map,
        default_barrier=default_barrier,
    )
    logger.info("roads_barriers: %s", len(roads_barriers))

    # Combined summary
    all_patches = gpd.GeoDataFrame(
        pd.concat([habitat_patches, core_patches, rf_patches], ignore_index=True),
        crs=crs,
    )
    summary = patch_summary_table(all_patches)
    summary.to_csv(paths["reports_dir"] / "phase4_patch_summary.csv", index=False)

    if not roads_barriers.empty:
        road_sum = (
            roads_barriers.groupby("barrier_class", dropna=False)
            .agg(segments=("barrier_class", "count"), length_km=("length_m", lambda s: s.sum() / 1000.0))
            .reset_index()
        )
        road_sum.to_csv(paths["reports_dir"] / "phase4_road_barrier_summary.csv", index=False)

    rules_path = paths["reports_dir"] / "phase4_habitat_rules.md"
    _write_rules_doc(rules_path, conn, summary)

    handoff = paths["reports_dir"] / "phase4_arcgis_handoff.md"
    handoff.write_text(
        """# ArcGIS handoff — Phase 4 network inputs

## Inputs (GeoPackage)
`data/interim/phase4_network.gpkg`

| Layer | Use |
|-------|-----|
| `habitat_patches` | Full native remnant network units |
| `core_habitat_patches` | Preferred terminals / habitat for corridor analysis |
| `rainforest_patches` | Rainforest story / reserve context |
| `roads_barriers` | Barrier lines with `cost_hint` / `barrier_class` |
| `study_area` / `robertson_nature_reserve` | AOI + Scenario A removal feature |

## Suggested ArcGIS workflow
1. **Cost surface** — rasterize `cost_hint` (and any additional land costs you define). Keep a written cost table.
2. **Cost distance / corridors** — between `core_habitat_patches` (or selected large patches).
3. **Scenario A** — erase / mask out `robertson_nature_reserve` from habitat and re-run corridors.
4. **Scenario B** — test restoration slices (e.g. gaps with high `nn_distance_m` between large core patches).
5. Export corridor / fragmentation products back into `data/processed/` for Phase 7–8 packaging.

## Do not
- Treat Python `cost_hint` as a finished ecological resistance model
- Publish a weighted opportunity index before Phase 6 unweighted components exist
""",
        encoding="utf-8",
    )

    out_gpkg = paths["interim_dir"] / str(
        settings.get("outputs", {}).get("phase4_interim_gpkg", "phase4_network.gpkg")
    )
    if out_gpkg.is_file():
        out_gpkg.unlink()

    layers = {
        "study_area": study_area.to_crs(crs),
        "robertson_nature_reserve": reserve.to_crs(crs),
        "habitat_patches": habitat_patches,
        "core_habitat_patches": core_patches,
        "rainforest_patches": rf_patches,
        "roads_barriers": roads_barriers,
    }
    for name, gdf in layers.items():
        write_gdf(gdf, out_gpkg, layer=name)
        logger.info("Wrote %-28s %6s features", name, len(gdf))

    qa_rows = []
    for name, gdf in layers.items():
        qa_rows.extend(basic_vector_qa(gdf, f"phase4::{name}"))
    append_qa_rows(qa_rows, paths["reports_dir"] / "data_quality_report.csv")

    layer_summary = pd.DataFrame(
        [{"layer": k, "features": len(v), "crs": str(v.crs)} for k, v in layers.items()]
    )
    layer_summary.to_csv(paths["reports_dir"] / "phase4_layer_summary.csv", index=False)

    logger.info("Phase 4 complete.")
    logger.info("Interim GPKG: %s", out_gpkg)
    logger.info("Rules: %s", rules_path)
    logger.info("Patch summary:\n%s", summary.to_string(index=False))


if __name__ == "__main__":
    main()
