# Robertson Nature Reserve — Ecological Profile

**Generated:** 2026-08-11T05:06:06Z  
**Profile version:** 1.0.0  
**Analysis CRS:** EPSG:7856 (metres)  
**Geometry:** Polygon

> Transparent metrics only — no composite importance score.

## Reserve identity

| Metric | Value | Evidence |
|--------|-------|----------|
| Name | Robertson Nature Reserve | OBSERVED |
| Reserve number | N0525 | OBSERVED |
| Type / IUCN | NATURE RESERVE / IV | OBSERVED |
| Area (calculated) | **5.324 ha** | CALCULATED |
| Gazetted area | 5.391 ha | OBSERVED |

## Threatened ecological community

| Item | Value | Evidence |
|------|-------|----------|
| Community | Robertson Rainforest in the Sydney Basin Bioregion | PUBLISHED |
| NSW status | Endangered Ecological Community | PUBLISHED |
| EPBC status | Critically Endangered | PUBLISHED |
| Primary associated PCT | 3047 Sydney Montane Basalt Rainforest | PUBLISHED |
| CEEC indicative intersects reserve | False | OBSERVED/indicative |
| CEEC features in AOI | 0 | OBSERVED/indicative |

NSW determination: https://www.environment.nsw.gov.au/topics/animals-and-plants/threatened-species/nsw-threatened-species-scientific-committee/determinations/final-determinations/2000-2003/robertson-rainforest-sydney-basin-bioregion-endangered-ecological-community-listing

## Vegetation inside the reserve

- Majority PCT: **Sydney Montane Basalt Rainforest**
- Veg class / form: Southern Warm Temperate Rainforests / Rainforests
- Rainforest intersect: 5.313 ha
- Native vegetation intersect: 5.313 ha

## Surrounding native vegetation

| Ring | Native veg (ha) | Rainforest (ha) | Cleared contrast (ha) |
|------|-----------------|-----------------|------------------------|
| 500 m | 37.992 | 31.585 | 91.873 |
| 1 km | 93.12 | 78.927 | 318.116 |
| 2 km | 327.833 | 262.47 | 1116.63 |

## Water, habitat neighbours, terrain

- Distance to nearest waterway: **80.7 m**
- Rainforest patches within 1 km (excl. touching): **15**
- Nearest other rainforest patch: **264.3 m** (2.278 ha)
- Nearest other core habitat patch: **158.0 m** (0.849 ha)
- Mean elevation: 771.0 m; mean slope: 7.7°
- Soil landscape (majority): Robertson
- Geology unit (majority): Bringelly Shale
- Basalt/volcanic rock-unit flag: False
- Robertson basalt soil association: True
- Note: PTB seamless geology may map sedimentary rock units under the plateau; Robertson soil landscape + published TEC text support basalt-soil association. Do not treat rock-unit flag alone as proof of Tertiary basalt outcrop.

## Biodiversity nearby (BioNet public)

| Buffer | Records | Species | Threatened spp. | Flora spp. |
|--------|---------|---------|-----------------|------------|
| 1 km | 1086 | 345 | 3 | 209 |
| 2 km | 2372 | 432 | 6 | 267 |

*Caveat:* BioNet public observations; effort-biased; sensitive taxa denatured/aggregated. Absence of records is not absence of species.

## Canopy proxy

- Method: NDVI class contrast (Planetary Computer living feed) — NOT LiDAR canopy percent
- NDVI rainforest remnant (AOI): 0.4670563638210296
- NDVI cleared (AOI): 0.4104264378547668
- Delta: 0.0566299259662628
- Reserve % canopy: None (pending DEA FC/LiDAR)

## Limitations

- No composite ecological importance score is calculated.
- SVTM is regional vegetation mapping — edges are not field-survey cadastre.
- CEEC polygons are indicative if present.
- Canopy percent inside reserve not yet available without DEA FC / LiDAR.
- NSW Landuse layer not enabled — cleared/native contrast used as proxy.
- Yarrawa Brush historic surveyed boundary is not fabricated.

## Cartographic use

Present these metrics as quiet callouts on an artful reserve map — not as a dashboard scorecard.
See `docs/CARTOGRAPHIC_ART_STANDARD.md`.
