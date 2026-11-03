---
name: household-heat-preparedness
description: Compose the household part of a community heatwave preparedness plan from the verified guidance catalog, covering before, during and after hot days.
---

# Household Heat Preparedness

Use this skill when the plan includes the `household` audience.

1. **List the options once** with `list_guidance(audience="household", phase="all")`. This returns every phase in one call; do not call `list_guidance` again per phase.

2. **Select catalog items** with `select_guidance`, passing the catalog ids as one comma-separated string per phase. Only ids returned by `list_guidance` are allowed; never invent ids or rewrite item text.

3. **Cover every phase** (before, during, after) and make sure the household plan includes these topics:
   - **hydration** - drinking water within reach and regular drinking
   - **rest** - avoiding heavy activity in the hottest hours
   - **shade** - shade, a hat and light clothing outside
   - **escalation** - recognising heat illness and contacting local emergency services or the nearest health facility

4. **Also consider** `cooling` (keeping the home cool), `check_others` (older people, young children, pregnant women, people with chronic illness) and `stay_informed`.

## Important Notes
- General advice that is not in the catalog may only be added with `add_general_advice`, kept short, and only when the catalog has nothing suitable.
- Never mention medicines or doses, never diagnose anyone, never suggest limiting water, and never say that HeatWise sends alerts or contacts anyone.
- Do not state an emergency phone number.
