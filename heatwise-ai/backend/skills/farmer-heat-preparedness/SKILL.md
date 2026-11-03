---
name: farmer-heat-preparedness
description: Compose the farmer part of a community heatwave preparedness plan from the verified guidance catalog - people, livestock and crops before, during and after hot days.
---

# Farmer Heat Preparedness

Use this skill when the community includes farming households (audience `farmer`).

1. **List the options once** with `list_guidance(audience="farmer", phase="all")`. This returns every phase in one call; do not call `list_guidance` again per phase.

2. **Select catalog items** with `select_guidance`, passing the catalog ids as one comma-separated string per phase. Only ids returned by `list_guidance` are allowed; never invent ids or rewrite item text.

3. **Cover every phase** (before, during, after) and make sure the farmer plan includes these topics:
   - **hydration** - stored water and clean, cool water for people and animals
   - **rest** - rest and water breaks in the shade during field work
   - **shade** - shade and ventilation for animals, priority shade for poultry
   - **escalation** - contacting local emergency services or the nearest health facility for people, and a local veterinarian for animals

4. **Also consider** `work_schedule` (early morning or evening work), `livestock_crops` (mulch, irrigation timing, produce out of the sun, watching animals after the heat) and `stay_informed`.

## Important Notes
- General advice that is not in the catalog may only be added with `add_general_advice`, kept short, and only when the catalog has nothing suitable.
- Never mention medicines or doses, never diagnose anyone or any animal, never suggest limiting water, and never say that HeatWise sends alerts or contacts anyone.
- Do not state an emergency phone number.
