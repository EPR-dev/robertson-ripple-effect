# Phase 6 complete — StoryMap web prototype

**Date:** 2026-08-11  
**Status:** Complete for review  
**Design:** Cartographic art + living atlas (`docs/CARTOGRAPHIC_ART_STANDARD.md`)

## What changed

| Item | Result |
|------|--------|
| Brand / question | Robertson Rainforest Conservation StoryMap |
| Chapters | **12** narrative chapters (was 6 live / 16 docs mismatch) |
| Metrics wiring | Reserve profile, Meet the Locals, gaps, Parcel Explorer |
| Handoff | `docs/storymap_handoff.md` for Esri rebuild |
| Experience | Soft-paper Story / satellite Action; quiet metric cards |

## Run the prototype

```powershell
cd C:\Users\thesn\Gis_Workstation\robertson-ripple-effect
.\.venv\Scripts\pip.exe install -r dashboard\requirements.txt
.\start-dashboard.ps1
```

Or:

```powershell
.\.venv\Scripts\streamlit.exe run dashboard\app.py
```

## Cartographic art checklist (review in browser)

- [ ] Cover feels like a story, not a GIS app
- [ ] Reserve pulse / moss remnants read as art plates
- [ ] Opportunity colours are dawn-gold stitches, not hazard zoning
- [ ] Metric callouts are quiet (not KPI scorecards)
- [ ] Meet the Locals + Parcel Explorer cards show real numbers
- [ ] Chapters 07 / 10 clearly say ArcGIS pending
- [ ] Living feed dates appear where relevant

## Known prototype limits

1. Art plates under `dashboard/assets/plates/` still use old 01–16 slugs — new chapter names may fall back to map-only until plates regenerated (`src/09_render_story_plates.py`).
2. Road-gap type returned 0 features in Phase 4 fast pass — refine in ArcGIS.
3. True sticky scroll StoryMap choreography is approximate in Streamlit sidecars — Esri StoryMaps (Phase 8) will polish map actions.

## Next

- **Phase 7:** ArcGIS Pro connectivity scenarios (runbook provided)
- **Phase 8:** Esri StoryMaps final assembly from `storymap_handoff.md`
