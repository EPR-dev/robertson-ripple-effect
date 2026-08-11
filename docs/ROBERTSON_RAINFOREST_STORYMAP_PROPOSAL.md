# Robertson Rainforest Conservation StoryMap — Project Proposal

**Status:** Awaiting review before significant development  
**Date:** 2026-08-11  
**Working title:** Robertson Rainforest Conservation StoryMap  
**Predecessor:** Bring Back the Brush (`robertson-ripple-effect`)  
**Guiding question (revised):**

> What ecological role does Robertson Nature Reserve play today, and where could other small areas of land around Robertson strengthen that role?

---

## Decision / operational outcome

This project supports **community conservation conversation** — not land acquisition targets. GIS identifies ecological opportunities (habitat, connectivity, restoration potential). Land feasibility (ownership intent, cost, planning) remains outside the model.

| Item | Value |
|------|--------|
| Primary geometry (seed) | Polygon — Robertson Nature Reserve (NPWS) |
| Analysis CRS | EPSG:7856 (GDA2020 / MGA Zone 56) — metres |
| Web / API CRS | EPSG:4326 |
| Study area | ~12.5 km buffer around reserve (~existing AOI) |
| Master package | `outputs/geopackage/robertson_conservation.gpkg` (~27 layers) |

---

## 1. Revised StoryMap narrative

### Central arc

```text
ONE RESERVE
  → plants & animals it protects
  → rainforest fragments around it
  → connections between fragments
  → gaps in the network
  → other pieces that could strengthen the network
```

Question shift:

| Start | End |
|-------|-----|
| Why does this tiny reserve matter? | Where else could a relatively small conservation effort make a meaningful difference? |

### Proposed chapters (12 — Esri StoryMap–style)

| # | Chapter | Purpose | Evidence stance |
|---|---------|---------|-----------------|
| 01 | The Little Reserve | Meet Robertson Nature Reserve; ecological profile metrics | OBSERVED / CALCULATED |
| 02 | The Rainforest That Survived | Robertson Rainforest / TEC context; modelled loss vs extant remnants | PUBLISHED / MODELLED / OBSERVED |
| 03 | Who Lives Here? | Wildlife + plants as the reason connectivity matters | OBSERVED (aggregated) |
| 04 | Beyond the Boundary | Habitat surrounding the reserve | OBSERVED / CALCULATED |
| 05 | Islands of Green | Fragmentation: patches, isolation, agricultural matrix | CALCULATED |
| 06 | The Wildlife Network | Potential habitat connections (not tracked movement) | CALCULATED / MODELLED |
| 07 | What Does Five Hectares Do? | Network with vs without the reserve | MODELLED (ArcGIS) |
| 08 | The Other Little Pieces | Small patches with location-driven value | CALCULATED |
| 09 | The Missing Links | Typed habitat connection opportunities | CALCULATED |
| 10 | What Could One Hectare Do? | Connectivity gain per hectare scenarios | MODELLED (ArcGIS) |
| 11 | Where Should We Look Next? | Ecological Opportunity Areas + Parcel Explorer | CALCULATED |
| 12 | A More Connected Robertson | Conceptual restoration scenario + community landscape | MODELLED |

### Language rules (carry forward + tighten)

- Use: *ecological opportunity*, *may warrant further investigation*, *potential habitat connection*
- Avoid: *should acquire*, *must protect this property*, *actual wildlife corridor* (unless tracking exists)
- Keep evidence tags: **OBSERVED · PUBLISHED · CALCULATED · MODELLED**
- Distinguish: ecological value vs restoration potential vs land feasibility

### Brand note

Predecessor brand (“Bring Back the Brush”) can remain as secondary / archive label. Primary public title for this revision: **Robertson Rainforest Conservation StoryMap** (or shorter: *Robertson Rainforest — Connected Country*).

---

## 2. Datasets already available

All under `robertson-ripple-effect/` unless noted. Master GPKG: `outputs/geopackage/robertson_conservation.gpkg` (also `data/processed/`).

### Foundation / tenure

| Dataset | Status | Notes |
|---------|--------|-------|
| Robertson Nature Reserve | Downloaded | ~5.32 ha calc; RES_NO N0525; IUCN IV |
| NPWS estate (AOI) | Downloaded | 9 protected areas in AOI |
| Wingecarribee LGA | Downloaded | Context only |
| Crown land | Downloaded | Public tenure proxy (no private owner names) |
| Roads | Downloaded | NSW Transport Theme preferred; OSM fallback labelled |

### Vegetation

| Dataset | Status | Notes |
|---------|--------|-------|
| SVTM extant PCT | Downloaded | Rainforest ~5,055 ha in AOI; dominant local PCT includes **3047 Sydney Montane Basalt Rainforest** |
| SVTM pre-clear PCT | Downloaded | Modelled — not surveyed Yarrawa Brush boundary |
| Derived: native / rainforest / wet sclerophyll / cleared | Derived | In master GPKG |
| PCT interest list | Derived | `data/reference/pct_interest_list.csv` |

### Biodiversity

| Dataset | Status | Notes |
|---------|--------|-------|
| BioNet sightings (raw) | Downloaded | ~123k rows parquet |
| Species observations clean | Derived | ~57.7k; Flora ~22.6k; threatened ~8.3k |
| Threatened species aggregated grid | Derived | 953 cells — sensitive locations obscured |
| iNaturalist (living) | Downloaded | Supplemental citizen science |
| Threatened species list CSV | Derived | Potoroo, koala, quoll, Mittagong Geebung, etc. |

### Water / terrain / soils / fire

| Dataset | Status | Notes |
|---------|--------|-------|
| HydroLine / HydroArea / named watercourses | Downloaded | Master: hydro_lines, hydro_areas, named_watercourses |
| Riparian buffers 50/100 m | Derived | |
| DEM (Copernicus GLO-30) | Downloaded | Slope/aspect derived |
| Soil landscapes | Downloaded | |
| Geology (basalt/volcanic flag) | Downloaded | Association narrative only |
| Bushfire prone land | Downloaded | |

### Connectivity / opportunity prep

| Dataset | Status | Notes |
|---------|--------|-------|
| habitat_patches | Derived | 702 patches; min 0.5 ha; 15 m gap-close |
| core_habitat_patches | Derived | 784; rainforest + wet sclerophyll |
| rainforest_patches | Derived | 481 |
| roads_barriers + cost_hint | Derived | Prep for ArcGIS cost surface |
| analysis_grid_metrics (250 m) | Derived | 8,210 cells; unweighted opportunity flags |
| component_polygons | Derived | riparian_gap, patch_gap_edge, isolated_patch_context, etc. |

### Prototype / exports

- Streamlit dashboard (`dashboard/`) — currently **6 live chapters** (docs still describe 16)
- GeoJSON subset, CSV grid, living Twin Lakes package
- ArcGIS handoff drafts: `docs/arcgis_handoff.md`, `outputs/reports/phase7_arcgis_handoff.md`

---

## 3. Additional datasets needed

| Priority | Dataset | Why | Defensibility note |
|----------|---------|-----|-------------------|
| **P0** | NSW TEC / CEEC indicative mapping for Robertson Rainforest | Part 1–2 TEC status story | Indicative mapping ≠ cadastral TEC boundary; cite listing determination text |
| **P0** | Reserve ecological profile table (new derived product) | Transparent metrics chapter 01 | Compute from existing layers — no invented scores |
| **P1** | DEA Fractional Cover / woody canopy (or NSW woody vegetation) | Canopy % for reserve + patches | 25–30 m; report as remote-sensing proxy |
| **P1** | NSW Landuse (clipped) | Surrounding land use; agricultural matrix | Vintage matters — document year |
| **P1** | Typed habitat-gap layer | Part 8 “Missing Links” | Derive from existing patches + roads + hydro |
| **P2** | ALA occurrences (enable + dedupe) | Cross-check BioNet; plant/wildlife cards | Record-level licences; effort bias |
| **P2** | Catchments / nested drainage | Water chapter context | Regional, not fine-scale hydrology |
| **P2** | Schools, public spaces, village POIs | Part 12 community landscape | ABS / Data.NSW / OSM labelled |
| **P2** | Walking tracks (NPWS / OSM) | Community access narrative | Optional |
| **P3** | Cadastre lots (if licence allows) | Parcel Explorer geographic reference only | Anonymous IDs; no owner names; prefer opportunity zones if restricted |
| **P3** | Formal canopy LiDAR / high-res tree cover | Better than DEM/NDVI for canopy % | Only if free/licensed product exists for AOI |
| **Exclude** | Fabricated Yarrawa Brush polygon | Historic literature only (~2,500 ha text) | Already documented limitation |
| **Exclude** | Precise sensitive species points | Licence / ethics | Grid aggregate only |
| **Exclude** | Reserve-driven climate attribution | Not defensible at ~5 ha | Keep out |

---

## 4. Wildlife datasets available

| Source | On disk? | Use |
|--------|----------|-----|
| NSW BioNet Species Sightings | Yes | Primary wildlife evidence; taxon groups; threatened flags |
| Threatened species aggregated grid | Yes | Public StoryMap layer |
| iNaturalist AOI extract | Yes | Citizen-science supplement; lower weight |
| ALA | Configured, **disabled** | Enable in Phase 2 if API stable |
| Local ecological research / council Env datasets | Not catalogued as files | Literature citations + manual ingest if polygons exist |

**Taxon groups for “Meet the Locals” cards:** Mammals, Birds, Amphibians, Reptiles, Threatened species (cross-cutting). Cards must state: recorded in AOI / near reserve buffer / illustrative for community only — never invent local occurrence.

**Sensitivity:** Keep `sensitivityClass` / grid aggregation rules from Phase 3. Do not publish precise dens/roosts.

---

## 5. Native plant datasets available

| Source | On disk? | Use |
|--------|----------|-----|
| BioNet flora records (`kingdom=Plantae` / Flora group) | Yes (~22.6k clean) | Plant story + richness |
| Threatened flora in BioNet | Yes | e.g. *Persoonia glaucescens*, *Rhodamnia rubescens*, *Grevillea rivularis* |
| SVTM PCT / veg class / formation | Yes | Rainforest community storytelling |
| Vegetation condition (field survey) | **No** | Do not invent; use PCT + remote proxies only with caveats |
| Invasive vegetation systematic layer | **No** | Only if a defensible public layer is found; else narrative |

Plant chapter must treat **Robertson Rainforest as a plant community / TEC story**, not only as animal habitat.

---

## 6. Available cadastral / parcel data

| Product | Status |
|---------|--------|
| Private cadastre / lots | **Not downloaded** — marked Experimental / licence-sensitive in `data_sources.csv` |
| Crown land | Available — use as public-land opportunity context |
| NPWS estate | Available — protected land |

**Recommendation:** Build Parcel Explorer on **ecological opportunity polygons** (anonymous `AREA_###` IDs) first. If cadastre becomes available under licence, join as **geographic reference only** — never publish owner names, contacts, or assumed intentions. Prefer aggregated opportunity zones over naming private holdings in the public StoryMap.

---

## 7. Vegetation and rainforest datasets

| Layer | Role |
|-------|------|
| `rainforest_extant` | Current mapped rainforest remnants |
| `rainforest_preclear_modelled` | Then/now contrast (MODELLED) |
| `wet_sclerophyll_extant` | Core habitat matrix with rainforest |
| `native_vegetation` | Broader habitat patches |
| `cleared_or_non_native` | Contrast / gap context |
| PCT 3047 Sydney Montane Basalt Rainforest | Primary local rainforest narrative |
| TEC/CEEC polygons | **Gap — must acquire for Part 1–2** |

**Known limitation:** Historic “Yarrawa Brush” surveyed boundary is unavailable. Use literature area as **PUBLISHED text** + SVTM pre-clear as **MODELLED** extent. Do not draw a fake historic outline.

---

## 8. Proposed habitat metrics

### A. Robertson Nature Reserve Ecological Profile (transparent, no composite score)

| Metric | Method | Source |
|--------|--------|--------|
| Hectares protected | GIS area in EPSG:7856 | NPWS + calc |
| Vegetation types present | PCT / veg_class intersect reserve | SVTM extant |
| TEC status (if mapped) | Intersect TEC product + listing citation | TEC/CEEC + determination text |
| % canopy proxy | Mean woody/FC or NDVI class inside reserve | DEA FC or living NDVI — labelled proxy |
| Native veg within 500 m / 1 km / 2 km | Buffer + intersect area | SVTM native |
| Distance to nearest waterway | Edge distance | HydroLine |
| Nearby rainforest remnant count + nearest distance | Patch NN from reserve | rainforest_patches |
| Nearest significant habitat patch | NN to core patches excluding self | core_habitat_patches |
| Nearby native / threatened species richness | Grid or buffer counts (aggregated) | BioNet clean |
| Elevation / slope / soils / geology summary | Zonal stats / majority | DEM, soils, geology |
| Surrounding land use summary | Majority / area by class in 1–2 km | NSW Landuse (when acquired) |

**Rule:** Publish each metric separately. No “importance score” until Part 7 framework is reviewed.

### B. Habitat patch attributes (extend existing)

Existing: `patch_id`, `area_ha`, `perimeter_m`, `nn_distance_m`, `n_patches_within_*`, `dist_to_reserve_m`, `touches_reserve`, habitat class.

**Add (Python):**

- vegetation community majority PCT
- protection status (intersects NPWS / Crown / none)
- canopy proxy if raster available
- waterway proximity
- nearby species richness (grid join)
- threatened-species context flag (grid, not points)
- edge/area ratio (edge-effect proxy — labelled as geometric proxy only)

---

## 9. Proposed connectivity methodology

### Python / Cursor (prep — not movement truth)

1. **Patch graph prep:** nodes = core/rainforest patches; edges = edge-to-edge distance under thresholds (e.g. 50 / 100 / 250 / 500 m).
2. **Nearest-neighbour & isolation:** already partly done — extend attributes.
3. **Barrier prep:** roads with `cost_hint`; cleared matrix as high resistance candidate.
4. **Connector candidates:** riparian buffers, roadside veg strips, small patches between large patches.
5. **Typed gaps:** SHORT (~50 m), CREEK, ROAD, STEPPING_STONE, REMNANT_EXPANSION.
6. Export analysis-ready layers for ArcGIS.

### ArcGIS Pro (authoritative connectivity modelling)

1. Resistance / cost surface (roads + land cover + optional canopy gaps).
2. Least-cost pathways / corridors between core patches.
3. Scenario A: network **without** Robertson Nature Reserve habitat contribution.
4. Scenario B: test 1 ha restoration cells → **connectivity gain per hectare**.
5. Graph / equivalent connected area metrics as appropriate.

**Labelling:** *potential habitat connections* / *modelled connectivity pathways* — never “known animal movement corridors” without tracking data.

---

## 10. Proposed ecological-opportunity methodology

### Stage 1 — Independent factors (Python; map separately)

| Theme | Variables |
|-------|-----------|
| Habitat value | native veg present, rainforest PCT, canopy proxy, patch size |
| Biodiversity context | nearby richness, threatened context (aggregated) |
| Connectivity value | gap length, bridge potential, patches nearby, dist to large forest |
| Water value | stream distance, riparian gap, wetland proximity |
| Landscape value | slope plantability, basalt association (context only), position |

Reuse and refine Phase 6 unweighted flags (`riparian_gap`, `patch_gap_edge`, `isolated_patch_context`, `near_core`, `on_public_land`, etc.).

### Stage 2 — Opportunity typology (not acquisition list)

Categories for public layer **Ecological Opportunity Areas**:

| Code | Meaning |
|------|---------|
| PROTECT | Existing high-quality veg needing conservation attention |
| CONNECT | Between patches / gap fillers |
| RESTORE | Cleared/degraded where revegetation could help |
| BUFFER | Adjacent to important remnants |
| RIPARIAN | Streamside strengthening |
| INVESTIGATE | Interesting metrics; needs field check |

### Stage 3 — Conservation Opportunity Index (later, optional)

Only after Stage 1–2 are visible and documented. Any weights must be:

- published in `docs/`
- adjustable
- never presented as land-use decisions

### Parcel Explorer fields (must be calculated, never invented)

`AREA_ID`, existing veg ha, nearest rainforest remnant m, habitat patches nearby, potential habitat connected ha, waterway distance, native spp nearby, threatened context Y/N, opportunity type, plain-language “why it matters”.

---

## 11. Analyses that should remain in ArcGIS Pro

| Analysis | Why ArcGIS |
|----------|------------|
| Cost / resistance surface | Spatial Analyst; transparent raster algebra |
| Least-cost corridors / Linkage Mapper–style | Industry-standard connectivity tooling |
| Scenario A: without reserve | Controlled habitat removal + recalculate |
| Scenario B: 1 ha restoration experiments | Iterative what-if modelling |
| Connectivity gain per hectare | Depends on corridor/graph outputs |
| Weighted Conservation Opportunity Index (if approved) | After Python factors exist |
| Final cartography / layouts | Publication quality |
| Advanced terrain / hillshade products | Optional polish |

---

## 12. Components Cursor should build

| Component | Deliverable |
|-----------|-------------|
| Data pipeline updates | TEC ingest, landuse, canopy proxy, ALA optional, profile metrics |
| `reserve_ecological_profile` table + report | JSON/CSV + markdown summary |
| Extended patch attributes | Update `prepare_connectivity` / Phase 4 |
| Typed `habitat_connection_opportunities` layer | Part 8 |
| Ecological opportunity areas (unweighted typology) | Part 9–10 |
| Species / plant card content from real BioNet summaries | Meet the Locals |
| StoryMap web prototype restructure | 12 chapters; scroll-driven; sticky maps |
| Parcel Explorer UI | Click opportunity → real metrics panel |
| Before/after placeholders wired to ArcGIS exports when ready | Ch 07 / 10 / 12 |
| `robertson_conservation.gpkg` refresh + GeoJSON/CSV | ArcGIS-ready |
| `storymap_handoff.md` | Chapter-by-chapter Esri rebuild guide |
| Photography slots / asset checklist | Not fake ecology |

**Prototype stack recommendation:** Evolve existing Streamlit craft map toward clearer StoryMap choreography **or** migrate chapters to a lightweight scroll site (HTML/React) if Streamlit cannot deliver sticky sidecars well. Decision in Phase 6 kickoff — data pipeline remains Python either way.

---

## 13. Proposed ArcGIS StoryMap handoff structure

Maintain `storymap_handoff.md` (replace/extend current `docs/arcgis_handoff.md`) with **one block per chapter**:

```markdown
### CHAPTER
### PURPOSE
### NARRATIVE
### MAP EXTENT
### ACTIVE LAYERS
### HIDDEN LAYERS
### REQUIRED ARCGIS WEB MAP
### SUGGESTED INTERACTION
### DATA SOURCE
### ANALYSIS STATUS
### VISUAL ASSETS NEEDED
```

Plus global sections:

- Layer library (Base / Conservation / Vegetation / Wildlife / Plants / Water / Connectivity / Opportunity)
- Evidence vocabulary
- Sensitivity & privacy rules
- What is MODELLED vs OBSERVED
- Export inventory (`robertson_conservation.gpkg` layer list)

---

## 14. Scientific and data limitations

1. **SVTM is regional mapping** — edges are not cadastral field survey; do not over-interpret 5 m precision.
2. **Pre-clear SVTM ≠ historic Yarrawa Brush survey** — literature ~2,500 ha is PUBLISHED context only.
3. **No TEC polygons on disk yet** — TEC narrative incomplete until download validated.
4. **BioNet / iNat effort bias** — absence of records ≠ absence of species; richness is sampling-dependent.
5. **Sensitive species** — public product uses aggregation; richness understates precise ecology.
6. **No animal tracking** — connectivity is landscape structure / cost modelling only.
7. **Canopy %** — without LiDAR/FC, only NDVI/greenness proxies exist today.
8. **Vegetation condition** — not available as systematic field layer.
9. **Private parcels** — unavailable; opportunity zones must not imply owner targeting.
10. **Scenario A/B not yet run** — chapters 07/10 must stay honest placeholders until ArcGIS outputs exist.
11. **Community planting sites** — still research/consent dependent; do not invent.
12. **Predecessor StoryMap mismatch** — docs/plates ≠ live 6-chapter runtime; revision should resolve this deliberately.

---

# Implementation backlog (checklist)

## PHASE 1 — Robertson Nature Reserve ecological profile

- [ ] Freeze AOI + CRS rules (keep 12.5 km / EPSG:7856 unless review changes)
- [ ] Ingest / validate TEC–CEEC indicative layer for AOI; document listing text for Robertson Rainforest
- [ ] Build `reserve_ecological_profile` metrics table (all transparent metrics in §8A)
- [ ] Surrounding land-use summary (download NSW Landuse if accepted)
- [ ] Canopy proxy for reserve (DEA FC or documented NDVI method)
- [ ] Export profile JSON/CSV + short markdown “Ecological Profile” card
- [ ] QA: geometry valid, CRS, nulls, area vs gazetted ha

## PHASE 2 — Wildlife + plants

- [ ] Taxon-group summaries (mammals, birds, amphibians, reptiles, flora)
- [ ] Threatened species / TEC storytelling layers (aggregated)
- [ ] Optional ALA enable + dedupe against BioNet
- [ ] “Meet the Locals” / “Who Uses This Landscape?” species card schema from real records
- [ ] Plant-first chapter content scaffold (rainforest community, not only fauna)
- [ ] Sensitivity audit of any new exports

## PHASE 3 — Rainforest remnants + habitat network

- [ ] Enrich `rainforest_patches` / `habitat_patches` attributes (§8B)
- [ ] Small-patch emphasis layer (e.g. <5 ha, <2 ha classes) for “other little pieces”
- [ ] Remnant distance matrix / counts within 500 m & 1 km
- [ ] Roadside / riparian vegetation extracts where defensible from SVTM + hydro
- [ ] Refresh master GPKG habitat group

## PHASE 4 — Connectivity + gaps

- [ ] Patch graph edges by distance bands
- [ ] Typed `habitat_connection_opportunities` (50 m / creek / road / stepping-stone / remnant expansion)
- [ ] Gap attributes: length, area, adjacent habitat, barriers, nearby spp context
- [ ] Export ArcGIS-ready barrier + habitat inputs
- [ ] Document methodology in `outputs/reports/` (no fake corridors)

## PHASE 5 — Other parcels / ecological opportunity areas

- [ ] Build Ecological Opportunity Areas typology (PROTECT/CONNECT/RESTORE/BUFFER/RIPARIAN/INVESTIGATE)
- [ ] Anonymous `AREA_###` IDs + Parcel Explorer attribute schema
- [ ] Keep factors unweighted; document any future index separately
- [ ] Cadastre: only if licensed — else opportunity zones only
- [ ] Privacy review (no owners, no pressure language)

## PHASE 6 — StoryMap web prototype

- [ ] Rebrand narrative to revised guiding question
- [ ] Implement 12-chapter scroll StoryMap experience
- [ ] Sticky / sidecar map choreography; progressive zoom
- [ ] Metric callouts wired to real profile + opportunity stats
- [ ] Meet the Locals + Plant Story modules
- [ ] Parcel Explorer click panel
- [ ] Before/after UI shells for ArcGIS scenario layers
- [ ] Community landscape overlays (roads, village, public land, streams)
- [ ] Evidence tags + limitation footnotes throughout

## PHASE 7 — ArcGIS Pro analysis

- [ ] Cost surface + least-cost / linkage products
- [ ] Scenario A: landscape without reserve contribution
- [ ] Scenario B: one-hectare restoration tests; connectivity gain/ha
- [ ] Optional weighted opportunity index (documented weights)
- [ ] Cartographic refinement; web map packages for StoryMaps
- [ ] Validate Python prep layers against Pro geometry tools

## PHASE 8 — ArcGIS StoryMaps final presentation

- [ ] Complete `storymap_handoff.md` for all 12 chapters
- [ ] Build AGOL web maps per chapter recipe
- [ ] Assemble Esri StoryMap (sidecars, media, map actions)
- [ ] Photography / field assets checklist filled
- [ ] Stakeholder language review (opportunity ≠ acquisition)
- [ ] Publish draft for community conversation (not as council plan)

---

## What this revision changes vs Bring Back the Brush

| Aspect | Previous emphasis | Revised emphasis |
|--------|-------------------|------------------|
| Guiding question | Seed vs museum / ripple growth | Ecological role of reserve + where small efforts strengthen network |
| Scoring | Soft opportunity flags; ROI deferred | Explicit: no black-box scores until factors mapped |
| Chapters | 16 in docs / 6 in live app | Single 12-chapter narrative aligned to brief |
| Opportunity framing | Restoration opportunity cells | Ecological Opportunity Areas + Missing Links typology |
| Plants | Secondary to wildlife | Dedicated plant / TEC storyline |
| Parcel story | Implied “other plots” | Anonymous explorer; feasibility separated |
| Connectivity language | Sometimes illustrative animal follow | Strict potential/modelled pathway wording |
| Scenario honesty | Placeholders in Ch 14–15 | Ch 07/10 clearly ArcGIS-gated |

---

## Recommended reuse strategy

**Do not restart from zero.** Fork narrative and dashboard from `robertson-ripple-effect`, keep the Phase 1–6 Python pipeline and master GPKG, then:

1. Add missing defensible datasets (TEC, landuse, canopy proxy).
2. Compute reserve profile + typed gaps + opportunity areas.
3. Rebuild StoryMap chapters to the 12-part structure.
4. Leave true connectivity scenarios for ArcGIS Pro.

Sibling folder `ripple-effect/` is an empty Phase-0 scaffold — ignore for production work.

---

## Design amendment (approved)

Maps must be **cartographic art with data entrenched** — not a GIS tech dashboard.
See binding rules in [`CARTOGRAPHIC_ART_STANDARD.md`](CARTOGRAPHIC_ART_STANDARD.md).

The prototype is also a **living atlas**: metrics and layers refresh when newer
public data arrives (BioNet, vegetation editions, greenness, fire watch). Failed
feeds keep last-good values with honest timestamps — never invented numbers.

## Implementation status

| Gate | Status |
|------|--------|
| Proposal review | Accepted 2026-08-11 |
| Cartographic art + living atlas clarification | Accepted |
| Proceed phase-by-phase without per-step permission | Approved — user reviews after each complete phase |
| Phase 1 Reserve ecological profile | Complete — `outputs/reports/PHASE1_COMPLETE.md` |
| Phase 2 Wildlife + plants | Complete — `outputs/reports/PHASE2_COMPLETE.md` |
| Phase 3 Habitat network enrichment | Complete — `outputs/reports/PHASE3_COMPLETE.md` |
| Phase 4 Missing links / gaps | Complete — `outputs/reports/PHASE4_COMPLETE.md` |
| Phase 5 Opportunity areas | Complete — `outputs/reports/PHASE5_COMPLETE.md` |
| Phase 6 StoryMap prototype (12 ch) | Complete — `outputs/reports/PHASE6_COMPLETE.md` |
| Phase 7 ArcGIS Pro scenarios | Runbook ready — execute in Pro |
| Phase 8 Esri StoryMaps | Handoff ready — `docs/storymap_handoff.md` |
