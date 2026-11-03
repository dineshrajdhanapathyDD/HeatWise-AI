# HeatWise AI demo script (under 3 minutes)

Target length 2:45. The hackathon asks for a public demo video under three minutes; record, upload and link it yourself (user action, see [submission-checklist.md](submission-checklist.md)).

## Setup before recording

Record against the live deployment, so the agents in the video really run on Amazon Bedrock AgentCore Runtime:

1. Open https://main.dmupjpltx9cou.amplifyapp.com at 1440 px wide.
2. Run one assessment beforehand with a real place (for example Thanjavur, Tamil Nadu), so Home, History and Impact are not empty.
3. Start recording on Home.

A live run takes about 20-25 s. Cut the wait in the edit, and say that it was cut.

Fallback if the live API is unavailable: a fully offline run (scripted agents, labelled demo weather) that needs no AWS. In this mode the agents run on your machine, so do not say "AgentCore" over this footage.

```powershell
# terminal 1, from heatwise-ai
$env:AGENT_MODE="offline"; $env:WEATHER_PROVIDER="demo"
.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
# terminal 2, from heatwise-ai\frontend
npm run build; npm run preview
```

Open http://localhost:5173 and pick `demo-hot-dry` under "Demo location" instead of typing a place. Stop both servers afterwards (Ctrl+C).

Every value on screen comes from the running app. Do not overlay numbers that are not on screen. When the evaluation panel is shown, say "synthetic".

## Shot list

| Time | Screen | Action | Narration (matches the on-screen text) |
|---|---|---|---|
| 0:00-0:15 | Home, hero | Hold on "HeatWise AI" and "From Weather Intelligence to Community Action." | "HeatWise AI. A volunteer enters a place and who lives there, and gets a verified heat preparedness plan." |
| 0:15-0:35 | Home, "How serious is the heat?" and "What is the weather doing?" | Scroll slowly through the risk overview and the forecast chart. Pause on "Hourly timeline not available". | "The latest assessment shows the risk category from documented rules and the daily forecast. Data the backend does not have, like hourly readings, is labelled as not available, never filled in." |
| 0:35-0:45 | Home, "Agent workflow, latest run" | Scroll to the pipeline. | "Behind it, a Strands coordinator agent delegates to four specialists: weather, community risk, action planning and safety verification." |
| 0:45-1:05 | New assessment, steps 1 and 2 | Click "Start an assessment". Type the place in "City, town or village", click "Next". Under "Groups present in the community" tick "Older people", "People who work outdoors" and "Farming households". Set "Drinking water access" to "Limited". Click "Next". | "The form has three steps and asks only community-level questions. No names, no phone numbers." |
| 1:05-1:15 | Step 3, "Settings and review", then "Assessment in progress" | Click "Run the assessment". Cut the wait. | "The assessment runs as a background job on Amazon Bedrock AgentCore Runtime, with Amazon Nova 2 Lite. We cut the wait." |
| 1:15-1:30 | Report, Climate tab | Point at "Forecast against the IMD criteria", then "Official warnings" and "Weather source". | "Climate shows the forecast against the IMD heat-wave criteria. HeatWise says plainly that these are not official warnings, and every value carries its source and retrieval time." |
| 1:30-1:45 | Risk tab | Point at "Community risk", "Contributing factors" and "Community vulnerability". | "The risk category comes from documented rules, not from the model: the heat index band, the IMD indication and the vulnerable groups present. The model only writes the explanation." |
| 1:45-2:05 | Plan tab | Point at "Preparedness plan" and the before / during / after items. Tick one checkbox and show the "N of M done" line change. Click "Download checklist". | "The plan comes from a verified guidance catalog, each item tied to a trusted source. A volunteer can tick items as the community completes them, and download the checklist to print or share." |
| 2:05-2:20 | Agent activity tab | Scroll "Agent steps", then "Blocked tool calls". | "Agent activity is the trace: which agent called which tool, in order. Hooks block unapproved tools, and a steering handler keeps the order weather, risk, plan, safety. If safety fails, the planner gets one revision; then a person must review it." |
| 2:20-2:40 | Impact | Click "Impact" in the navigation. Hold on "Stored assessments", then scroll to "Synthetic evaluation results". | "Impact counts what this instance has stored. HeatWise does not measure or claim real-world health outcomes. Below, separately, are results on synthetic test scenarios, each labelled offline scripted or live Nova, with its run date." |
| 2:40-2:45 | End card | Show the repository URL https://github.com/dineshrajdhanapathyDD/HeatWise-AI and the live site URL. | "HeatWise AI, built with the Strands Agents SDK, Amazon Bedrock and AgentCore Runtime. The code is open source under the MIT license." |

## Checks before uploading

- Only say "AgentCore" over footage of a deployed run. `https://pwnenvmo71.execute-api.us-east-1.amazonaws.com/api/health` shows `agent_mode: agentcore` on the deployed API.
- Start from Home and use the navigation, not typed deep links. Deep links return HTTP 404 on Amplify until the rewrite rule is added (see [deployment.md](deployment.md)).
- Length under 3:00 (target 2:45).
- No real person's name, phone number or address is visible.
- Every number spoken is visible on screen at that moment, or quoted from [evaluation.md](evaluation.md) with the word "synthetic".
- The video is public (for example YouTube or Vimeo), and its link is in the submission and the README (both TODO).
