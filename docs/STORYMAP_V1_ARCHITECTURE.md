# Bring Back the Brush — StoryMap V1 architecture

**Status:** Version 1 narrative integration  
**Working title:** Bring Back the Brush — Reconnecting Robertson's Lost Rainforest  
**Guiding question:** What if Robertson Nature Reserve is the seed, not the museum?

This document maps the expanded 16-chapter story onto the existing Streamlit StoryMap in `dashboard/app.py` without discarding prior data prep or map craft.

---

## Stage checklist

| Stage | Deliverable | Status |
|-------|-------------|--------|
| 1 | Architecture docs (this file + inventories) | done |
| 2 | Rebrand settings + README positioning | done |
| 3 | 16 art-forward chapters + map recipes | done |
| 4 | Evidence labels, placeholders, closing | done |
| 5 | Story plate recipes + regenerate plates | done |
| 6 | Smoke-check dashboard; V1 handoff | done |

---

## Old → new chapter mapping

| Old (7) | New (16) | Reuse |
|---------|----------|-------|
| The small patch | 01 This little patch | reserve close zoom + pulse |
| What still remains | 02 The forest that was | preclear / cleared / rainforest |
| *(split)* | 03 What survived | rainforest remnants + patches |
| Who still lives here | 04 Life in the fragments | threatened grid + species panel |
| The living network | 05 An island or a network? | core patches + roads |
| *(new educational)* | 06 Follow an animal | illustrative connectivity only |
| Where the ripple grows *(part)* | 07 The missing pieces | opportunity gaps |
| *(new story beat)* | 08 What could 50 trees do? | edge / short-gap focus |
| Where the ripple grows *(part)* | 09 Restoration opportunity | unweighted components |
| *(new)* | 10 Beyond the park boundary | Crown / public / protected |
| *(new / vision)* | 11 People putting rainforest back | community placeholder |
| Why rainforest holds here | 12 Why should Robertson care? | basalt / water / identity |
| *(new conceptual)* | 13 Rainforest village | conceptual concepts panel |
| *(ArcGIS backlog)* | 14 With and without the reserve | scenario placeholder |
| *(ArcGIS backlog)* | 15 Adding one more piece | connectivity-gain placeholder |
| A living atlas *(evolved)* | 16 The 2040 landscape | conceptual + living feeds |

---

## Evidence vocabulary (shown in UI)

| Tag | Meaning |
|-----|---------|
| **OBSERVED** | Present in source spatial data (e.g. NPWS estate, SVTM extant) |
| **PUBLISHED** | Supported by credible research / government text |
| **CALCULATED** | Derived by this project's GIS metrics |
| **MODELLED** | Scenario, pre-clear model, or illustrative connectivity |

---

## Layer inventory (V1 dashboard groups)

### Available now (master GPKG / living feeds)

| Group | Layer keys / GPKG | Evidence |
|-------|-------------------|----------|
| THE RESERVE | `reserve`, aerial basemap | OBSERVED |
| LOST RAINFOREST | `preclear`, `rainforest`, `cleared` | MODELLED / OBSERVED / CALCULATED |
| WHAT SURVIVED | `rainforest`, `core`, `protected_areas` | OBSERVED / CALCULATED |
| WILDLIFE | `threat_grid`, species panel, living neighbours | OBSERVED (aggregated) |
| CONNECTIONS | `core`, patch metrics | CALCULATED (prep) |
| BARRIERS | `roads_high`, `roads_med`, `cleared` | OBSERVED / CALCULATED |
| WATER | `hydro`, `riparian` | OBSERVED / CALCULATED |
| THE LAND | `hillshade`, `elev`, `basalt` | OBSERVED / CALCULATED |
| BEYOND PARKS | `opp_public`, crown / protected | OBSERVED |
| MISSING PIECES | `opp_edge`, `opp_riparian`, `opp_isolated` | CALCULATED (unweighted) |
| FUTURE | living feeds; conceptual 2040 panel | OBSERVED / MODELLED |

### Missing or restricted (placeholders in V1)

| Desired | Gap | Plan |
|---------|-----|------|
| Surveyed Yarrawa Brush polygon | No authoritative open boundary | Keep modelled pre-clear + published ~2,500 ha text |
| Habitat gap typology (SHORT / RIPARIAN / ROAD / LARGE) | Opportunity components exist; typed gap layer not built | Python backlog |
| Rainforest remnant attribute table (edge ratio, nearest larger block…) | Partial patch metrics exist | Extend `prepare_connectivity` |
| Weighted Restoration Opportunity Index | Explicitly deferred | After variables documented |
| Scenario A/B connectivity | ArcGIS | Placeholder chapters 14–15 |
| Connectivity gain per hectare | Needs scenario runs | ArcGIS + Python export |
| Community conservation sites (REPS, Bushcare, Caalang) | Needs research + consent | Placeholder + citation list |
| Land for Wildlife / BCT public polygons | Restricted / incomplete | Do not fabricate |
| Walking track geometry | Not in master GPKG | Optional later |
| Taxonomic filter UI (all groups) | BioNet clean exists; UI thin | Phase backlog |
| Click-a-patch / click-opportunity panels | Craft map tooltips only | Enhance later |

---

## Analysis backlog

### PYTHON DATA PREP

1. Typed habitat-gap layer from patch NN distances + road/riparian context  
2. Richer `rainforest_patches` attributes for pop-ups  
3. Optional ALA enable + mammal/bird group summaries  
4. Headline metrics table (never hard-code until calculated)  
5. Community sites layer when sources verified  

### ARCGIS ANALYSIS

1. Cost distance / least-cost corridors  
2. Scenario A: without reserve  
3. Scenario B / Ch15: add restoration pieces; connectivity gain/ha  
4. Weighted ROI (after weights agreed)  
5. Cartographic polish for public StoryMap export if desired  

### DASHBOARD / CARTOGRAPHY (V1)

1. 16-chapter narrative + Soft paper craft recipes  
2. Evidence badges + placeholder panels  
3. Art plates for each chapter  
4. Grow-the-map zoom sequence (`close` → `context` → `aoi`)  
5. Closing current vs connected framing (conceptual)  

---

## Recommended implementation order (after V1 narrative)

1. Typed habitat gaps + remnant attributes (unlocks Ch7–8 depth)  
2. ArcGIS Scenario A/B (unlocks Ch14–15 numbers)  
3. Community conservation research layer (unlocks Ch11)  
4. Weighted ROI (only after transparent weights)  
5. Optional ArcGIS Online StoryMap publish path  

---

## Integrity rules (unchanged)

- No fabricated historic Brush boundary  
- No precise sensitive species points  
- No causal climate claims from the reserve  
- Scenarios labelled MODELLED  
- Illustrative animal paths labelled illustrative habitat-connectivity modelling  
- Agriculture, homes, and roads remain in any 2040 concept  
