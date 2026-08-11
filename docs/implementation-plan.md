# Phased implementation plan — The Ripple Effect

Status: **Phase 0 (inventory & scaffolding) — awaiting approval before downloads**

---

## Recommended CRS

**EPSG:7856 — GDA2020 / MGA Zone 56**

| Criterion | Assessment |
|-----------|------------|
| Location | Robertson ~150.6°E → Zone 56 |
| Metric analysis | Required for buffers, patch distance, grids, cost distance |
| ArcGIS Pro fit | Standard for Illawarra / Southern Highlands local projects |
| Source conflict | SVTM often in EPSG:3308 → reproject on ingest |

Keep source CRS in metadata fields / `data_sources.csv`.

---

## Study-area methodology (exact)

1. **Reserve extract**  
   From NSW NPWS Estate, select feature(s) where name matches `Robertson Nature Reserve` (confirm exact attribute spelling on download).

2. **Primary analysis AOI**  
   - Reproject reserve to EPSG:7856.  
   - Buffer **exterior** by **12,500 m** (12.5 km).  
   - Dissolve to a single polygon → `study_area`.  
   - Rationale: midpoint of briefed 10–15 km; large enough for Budderoo / escarpment *context* testing without a 30 km download burden.

3. **Context AOI (optional overlay)**  
   Union of:
   - `study_area`, and  
   - NPWS Estate features for named nearby conservation land of interest (Budderoo, Barren Grounds, Macquarie Pass, relevant Illawarra Escarpment parks, Wingecarribee Swamp tenure/wetland features if identifiable),  
   each with a modest **1 km** halo so edges are not clipped harshly.  
   Use context AOI only for “wider network” layers; keep metrics clipped to primary `study_area` unless labelled otherwise.

4. **Grid**  
   - Fishnet / polygon grid **250 m** over `study_area` (EPSG:7856).  
   - Optional parallel **500 m** grid for sensitivity.  
   - Stable `grid_id` primary key for CSV + GPKG joins.

5. **What this does *not* mean**  
   Features inside the buffer are **not** assumed connected to the reserve.

---

## Work split reminder

| PYTHON DATA PREP | ARCGIS ANALYSIS | DASHBOARD / CARTOGRAPHY |
|------------------|-----------------|-------------------------|
| Download, QA, clip, standardise | Cost distance, corridors | Layer groups & story UI |
| Species clean + aggregate | Scenario A/B modelling | Basemap / labels / print layouts |
| Habitat patches + basic metrics | Weighted opportunity index later | Optional web map later |
| Grid metrics export | Fragmentation tools | — |
| Master `robertson_conservation.gpkg` | Final cartography | — |

---

## Phases

### Phase 0 — Brief, structure, inventory
- [x] Folder structure  
- [x] README + settings  
- [x] `data_sources.csv`  
- [x] CRS + AOI method  
- [x] Phased plan  
- [x] **User approval to proceed**

### Phase 1 — Foundation downloads & AOI
- [x] NPWS Estate → reserve + nearby parks (REST)  
- [x] Build `study_area` (12.5 km) + `context_aoi`  
- [x] LGA boundary (SIX REST)  
- [x] Roads (NSW Transport REST preferred; OSM Overpass fallback if REST 500)  
- [x] Validation framework + logging  
- **Deliverable:** `data/interim/phase1_foundation.gpkg`  
  layers: `study_area`, `context_aoi`, `robertson_nature_reserve`, `protected_areas`, `lga`, `roads`

### Phase 2 — The Remnant (vegetation)
- [x] SVTM extant + pre-clearing Quickview (REST clip to study AOI)  
- [x] Document PCT interest list (`data/reference/pct_interest_list.csv`)  
- [x] Native vegetation + cleared/non-native contrast (SVTM mask, not cadastral landuse)  
- [x] TEC/CEEC labels attempted (include only if features returned)  
- [x] Yarrawa Brush limitation note (`outputs/reports/phase2_yarrawa_brush_limitation.md`)  
- **Deliverable:** `data/interim/phase2_remnant.gpkg`  
- **Non-deliverable:** digitised historic Yarrawa Brush polygon

### Phase 3 — The Refuge (biodiversity)
- [x] BioNet public sightings for AOI (OData `SpeciesSightings_CoreData`)  
- [x] Optional ALA supplement (`downloads.ala_enabled`; default off — BioNet primary)  
- [x] Clean taxonomy/dates; flag high uncertainty / old years  
- [x] Aggregate threatened/sensitive to **250 m grid**  
- [x] Species richness / counts by group & year  
- **Deliverable:** `data/interim/phase3_refuge.gpkg`  
  (`species_observations_clean`, `threatened_species_aggregated`, `biodiversity_grid`, `analysis_grid`)

### Phase 4 — The Network (habitat prep for ArcGIS)
- [x] Dissolve/threshold native veg → `habitat_patches` (+ core / rainforest)  
- [x] Patch area, nearest-neighbour distance, isolation proxies  
- [x] Roads as barrier inputs (`barrier_class`, `cost_hint`)  
- [x] Documented rules (`outputs/reports/phase4_habitat_rules.md`) — no suitability score  
- **Deliverable:** `data/interim/phase4_network.gpkg` + ArcGIS handoff note  
- **ArcGIS (your work):** corridors, cost distance, fragmentation, Scenario A/B

### Phase 5 — The Ripple (landscape functions)
- [x] Hydro extract + riparian proximity metrics (50/100 m + grid distance)  
- [x] DEM clip → Python slope/aspect (Copernicus GLO-30; ArcGIS can refine)  
- [x] Soils + geology (basalt/volcanic flag for association narrative)  
- [x] Bush fire prone land; DEA optional (`dea_enabled: false`)  
- [x] Association labelling (`phase5_association_note.md`)  
- **Deliverable:** `data/interim/phase5_ripple.gpkg` + rasters under `outputs/raster/phase5/`

### Phase 6 — The Opportunity (unweighted components)
- [x] Map factors independently on 250 m grid (protected, core, riparian gaps, patch edges, public/Crown land, basalt, slope)  
- [x] **No weights** — no combined opportunity index  
- [x] Export `opportunity_grid` + dissolved `component_polygons` + rules note  
- **Deliverable:** `data/interim/phase6_opportunity.gpkg`

### Phase 7 — Grid compilation & master export
- [x] Populate 250 m `analysis_grid_metrics` (biodiv + landscape + opportunity)  
- [x] Build `outputs/geopackage/robertson_conservation.gpkg` (+ `data/processed/` mirror)  
- [x] Key GeoJSON/CSV exports  
- [x] `data_quality_report.csv` / layer inventory  
- [x] ArcGIS handoff note (`docs/arcgis_handoff.md`)

### Phase 8 — Dashboard story packaging
- [x] Layer group schema (Reserve → Remnant → Refuge → Network → Ripple → Opportunity)  
- [x] Local **Streamlit** dashboard (`dashboard/app.py`) — ArcGIS Experience Builder deferred  
- [x] Meeting mode + caveats; uses Phase 7 master GPKG (corridors/scenarios optional later)

---

## Layers that cannot (yet) be created defensibly

| Desired layer | Why blocked | Defensible alternative |
|---------------|-------------|------------------------|
| Named historic **Yarrawa Brush** boundary | No official open polygon; literature areas (~2,450–2,500 ha) are estimates | SVTM **pre-clearing** rainforest PCTs labelled as modelled; narrative area from NPWS/literature |
| Reserve-driven **regional climate** change | Scale mismatch; no causal evidence pathway | Regional BOM/DEA context only, explicitly non-attributive |
| **Precise public** sensitive species points | BioNet policy — public coords denatured / licence required | Grid aggregation; public denatured points only |
| **Land for Wildlife** parcels | Typically not open cadastral | Narrative / omit |
| Opaque multi-criteria **ecological suitability score** | Brief forbids arbitrary scoring | Documented habitat rule set; weighted index only later in ArcGIS |

---

## Immediate next step after approval

Implement `src/utils.py` logging helpers + `download_data.py` for **NPWS Estate only**, build AOI, then stop for a quick review before SVTM/BioNet pulls.
