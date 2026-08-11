# Bring Back the Brush — V1 delivery checklist

Track where the build is up to. Update status as stages finish.

| Stage | Deliverable | Status |
|-------|-------------|--------|
| 1 | Architecture docs (`STORYMAP_V1_ARCHITECTURE.md`) | done |
| 2 | Rebrand `settings.yaml` + README positioning | done |
| 3 | 16 chapters in `dashboard/story_v1.py` + wired into `app.py` | done |
| 4 | Evidence chips, placeholder panels, closing narrative | done |
| 5 | Plate recipes + regenerate art plates (`generate-story-plates.ps1`) | done |
| 6 | Smoke-check StoryMap loads all 16 chapters | done |

## After V1 (your review pass)

- [ ] Edit chapter copy / tone
- [ ] Confirm published mammal research citations for Ch04
- [ ] Community site research for Ch11
- [ ] ArcGIS Scenario A/B for Ch14–15
- [ ] Typed habitat-gap classes
- [ ] Weighted Restoration Opportunity Index (only after weights)

## How to run

```powershell
cd C:\Users\thesn\Gis_Workstation\robertson-ripple-effect
.\start-dashboard.ps1
```

Regenerate plates:

```powershell
.\generate-story-plates.ps1
```
