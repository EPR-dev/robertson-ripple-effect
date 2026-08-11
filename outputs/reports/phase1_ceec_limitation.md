# Phase 1 — CEEC indicative mapping limitation

**Date:** 2026-08-11  
**Service tried:** `VIS/CEEC_NSW` MapServer layer 3 (`CEEC_NSW_LABELS`)  
**Result:** Envelope query for the 12.5 km study AOI returned **0 features**.

## What we still use (defensible)

| Item | Status | Evidence |
|------|--------|----------|
| Robertson Rainforest in the Sydney Basin Bioregion | NSW Endangered Ecological Community | PUBLISHED determination |
| Same community (EPBC) | Critically Endangered | PUBLISHED Commonwealth listing |
| Primary PCT association | 3047 Sydney Montane Basalt Rainforest | PUBLISHED BioNet vegetation associations |
| SVTM rainforest inside reserve | 5.313 ha of mapped rainforest PCT | CALCULATED from OBSERVED SVTM |

## Interpretation

Absence of CEEC label polygons in this particular VIS service for the AOI
**does not** mean the TEC is absent. The service appears incomplete or
geographically selective for Southern Highlands occurrences.

Do **not** invent a TEC polygon. Prefer:

1. Published listing text + determination URLs
2. SVTM PCT 3047 / rainforest formation as mapped vegetation proxy
3. Re-try alternate TEC products later (SEED downloads / BioNet vegetation TEC products)

## Living atlas

Re-run `src/10_build_reserve_profile.py` when a better TEC geometry product is licensed/downloaded.
Empty CEEC cache file may be deleted to force re-query.
