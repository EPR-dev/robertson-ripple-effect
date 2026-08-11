# Phase 1 complete — Reserve ecological profile

**Date:** 2026-08-11  
**Status:** Complete for review  
**Design standard:** `docs/CARTOGRAPHIC_ART_STANDARD.md` (cartographic art + living atlas)

## GIS concept practiced

Building a **transparent ecological profile** for a protected-area polygon: intersect vegetation, buffer rings, nearest-neighbour habitat, and biodiversity counts — without inventing a composite “importance score”.

## Deliverables

| Output | Path |
|--------|------|
| Profile report | `outputs/reports/reserve_ecological_profile.md` |
| Profile JSON | `outputs/csv/reserve_ecological_profile.json` |
| Profile CSV | `outputs/csv/reserve_ecological_profile.csv` |
| Profile GeoJSON | `outputs/geojson/reserve_ecological_profile.geojson` |
| Interim GPKG | `data/interim/phase1_reserve_profile.gpkg` |
| Master GPKG layer | `reserve_ecological_profile` in `robertson_conservation.gpkg` |
| CEEC limitation note | `outputs/reports/phase1_ceec_limitation.md` |
| Pipeline script | `src/10_build_reserve_profile.py` |

## Key calculated metrics (verify manually in ArcGIS Pro)

| Metric | Value |
|--------|-------|
| Area (EPSG:7856) | **5.324 ha** |
| Majority PCT | Sydney Montane Basalt Rainforest |
| Rainforest in reserve | 5.313 ha |
| Native veg within 500 m / 1 km / 2 km | 38.0 / 93.1 / 327.8 ha |
| Nearest waterway | 80.7 m |
| Other rainforest patches within 1 km | 15 |
| Nearest other rainforest patch | 264.3 m |
| BioNet species within 1 km | 345 (3 threatened spp. in public layer) |
| TEC (published) | Robertson Rainforest — NSW EEC / EPBC Critically Endangered |

## Known gaps (honest)

1. **CEEC indicative polygons:** VIS/CEEC_NSW labels returned 0 features in AOI — TEC status uses PUBLISHED determination + PCT association.
2. **% canopy inside reserve:** not available; AOI NDVI contrast only.
3. **NSW Landuse:** not enabled; cleared/native contrast used as surrounding land proxy.
4. **Geology:** PTB unit under reserve = Bringelly Shale; soil landscape = Robertson (basalt-soil association flagged separately).

## How to refresh (living atlas)

```powershell
cd C:\Users\thesn\Gis_Workstation\robertson-ripple-effect
.\.venv\Scripts\python.exe src\10_build_reserve_profile.py
```

## Manual validation

1. Open `robertson_nature_reserve` in ArcGIS Pro (EPSG:7856).
2. Calculate Geometry → area hectares; compare to 5.324.
3. Clip SVTM rainforest to reserve; area should ≈ 5.313 ha.
4. Buffer reserve 1 km; Spatial Join rainforest patches; count ≈ 15 non-touching.

## Next

Phase 2 — Wildlife + plants storytelling datasets and Meet the Locals cards.
