# HeatWise AI demo script (under 3 minutes)

Target length 2:45. The hackathon asks for a public demo video under three minutes; record, upload and link it yourself (user action, see [submission-checklist.md](submission-checklist.md)).

## Setup before recording

Fully offline run (scripted agents, labelled demo weather), so the take is repeatable and needs no AWS:

```powershell
# terminal 1, from heatwise-ai
$env:AGENT_MODE="offline"; $env:WEATHER_PROVIDER="demo"
.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
# terminal 2, from heatwise-ai\frontend
npm run build; npm run preview
```

Open http://localhost:5173 at 1440 px wide. Run one assessment beforehand (any demo location) so History and Impact are not empty, then start recording on the Home screen. Stop both servers afterwards (Ctrl+C).

Optional: to show live data instead, start the API without the two variables above (Bedrock and Open-Meteo, AWS credentials needed) and type a real place in "City, town or village"; a live run takes longer, so cut the wait in the edit.

Every value on screen comes from the running app. Do not overlay numbers that are not on screen. When the evaluation panel is shown, say "synthetic".

## Shot list

| Time | Screen | Action | Narration (matches the on-screen text) |
|---|---|---|---|
| 0:00-0:15 | Home | Hold on the title. | "HeatWise AI. From Weather Intelligence to Community Action. A volunteer types a place and who lives there, and gets a verified heat preparedness plan." |
| 0:15-0:25 | Home, "How the agents work together" | Scroll to the section. | "Behind it, a Strands coordinator agent delegates to four specialists: weather, community risk, action planning and safety verification." |
| 0:25-0:45 | New assessment | Click "Start an assessment". Choose `demo-hot-dry` under "Demo location". Under "Groups present in the community" tick "Older people", "People who work outdoors" and "Farming households". Set "Drinking water access" to "Limited". | "The form asks only community-level questions. No names, no phone numbers. This server is in demo mode, so it uses labelled demo weather." |
| 0:45-0:55 | Assessment in progress | Click "Run the assessment". | "The assessment runs as a background job, one agent after another." |
| 0:55-1:15 | Report, Climate tab | Point at "Forecast against the IMD criteria", then "Official warnings" and "Weather source". | "Climate shows the forecast against the IMD heat-wave criteria. HeatWise says plainly that these are not official warnings, and every value carries its source and retrieval time." |
| 1:15-1:30 | Risk tab | Point at "Community risk", "Contributing factors" and "Community vulnerability". | "The risk category comes from documented rules, not from the model: the heat index band, the IMD indication and the vulnerable groups present. The model only writes the explanation." |
| 1:30-1:55 | Plan tab | Point at "Preparedness plan" and the before / during / after items for households, outdoor workers and farmers. Tick one checkbox and show the "N of M done" line change. Click "Download checklist". | "The plan comes from a verified guidance catalog, each item tied to a trusted source. A volunteer can tick items as the community completes them, and download the checklist to print or share." |
| 1:55-2:10 | Agent activity tab | Scroll "Agent steps", then "Blocked tool calls". | "Agent activity is the trace: which agent called which tool, in order. Hooks block unapproved tools, and a steering handler keeps the order weather, risk, plan, safety. If safety fails, the planner gets one revision; then a person must review it." |
| 2:10-2:20 | History | Click "History" in the navigation. | "History keeps every stored report and what changed for the same place." |
| 2:20-2:40 | Impact | Click "Impact". Hold on the statement under the title, then the "Stored assessments" cards, then scroll to "Synthetic evaluation results". | "Impact counts what this instance has stored: assessments completed, plans, verified recommendations, checklist items done. As the screen says, HeatWise does not measure or claim real-world health outcomes. Below, separately, are results on synthetic test scenarios, each labelled offline scripted or live Nova, with its run date." |
| 2:40-2:45 | Home or the repository page | End card with the repository URL (TODO). | "HeatWise AI, built with the Strands Agents SDK and Amazon Bedrock, with the agents deployed on Amazon Bedrock AgentCore Runtime. The code is open source under the MIT license." |

## Checks before uploading

- Where the agents run in the recording: with the local demo server (`AGENT_MODE=offline`, demo weather), they run on your machine. To show AgentCore, point the dashboard at the deployed API (`VITE_API_BASE_URL`), use a real place instead of `demo-hot-dry`, and at 0:45 say "The assessment runs on Amazon Bedrock AgentCore Runtime." `/api/health` shows `agent_mode: agentcore` on the deployed API. Only say "AgentCore" over footage of a deployed run.

- Length under 3:00 (target 2:45).
- No real person's name, phone number or address is visible.
- Every number spoken is visible on screen at that moment, or quoted from [evaluation.md](evaluation.md) with the word "synthetic".
- The video is public (for example YouTube or Vimeo), and its link is in the submission and the README (both TODO).
