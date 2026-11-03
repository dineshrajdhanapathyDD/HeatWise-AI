---
name: outdoor-worker-heat-safety
description: Compose the outdoor-worker part of a community heatwave preparedness plan from the verified guidance catalog - water, rest, shade, work scheduling and escalation.
---

# Outdoor Worker Heat Safety

Use this skill when the community includes people who work outdoors (audience `outdoor_worker`).

1. **List the options once** with `list_guidance(audience="outdoor_worker", phase="all")`. This returns every phase in one call; do not call `list_guidance` again per phase.

2. **Select catalog items** with `select_guidance`, passing the catalog ids as one comma-separated string per phase. Only ids returned by `list_guidance` are allowed; never invent ids or rewrite item text.

3. **Cover every phase** (before, during, after) and make sure the worker plan includes these topics:
   - **hydration** - drinking water at the work site, drunk regularly through the shift
   - **rest** - regular rest breaks in the shade or a cool place
   - **shade** - shaded rest areas and working in shade where possible
   - **escalation** - stopping work and contacting local emergency services or the nearest health facility when a worker shows severe signs

4. **Also consider** `work_schedule` (moving heavy work away from midday heat), `check_others` (watching co-workers) and `stay_informed`.

## Important Notes
- General advice that is not in the catalog may only be added with `add_general_advice`, kept short, and only when the catalog has nothing suitable.
- Never mention medicines or doses, never diagnose anyone, never suggest limiting water, and never say that HeatWise sends alerts or contacts anyone.
- Do not state an emergency phone number.
