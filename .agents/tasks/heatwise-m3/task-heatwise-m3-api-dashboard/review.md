# HeatWise M3: FastAPI job API and React report dashboard (review pass 2)

M3 adds a FastAPI layer over the M2 agents: in-memory threaded jobs, a JSON-file assessment store, history with changes, metrics, one JSON error envelope, CORS from config and an offline scripted-agent mode. It also adds a Vite/React 19/Tailwind v4 dashboard with home, form, job progress, four report tabs and history. This pass checks the fixes for the seven pass-1 findings. The blocking IMD finding is fixed: the Climate tab now applies IMD levels only where `risk_rules.imd_indication` does. The job snapshot race, single-error polling, zero-verified plan text and route title/focus gaps are also fixed. The 500/CORS edge and the store read cost are now documented as known limits.

Watch for: nothing blocking. The production bundle is one 817 kB chunk (informational, already recorded in tasks.md). The inspector was not re-run after the Climate change. This is likely harmless because the hilly/coastal variant only removes elements and the plains layout is unchanged.

Re-run evidence (this pass): backend `.venv\Scripts\python.exe -m pytest` gave 223 passed, 4 deselected (14.4 s). Frontend `npm run typecheck` exit 0, `npm run lint` exit 0, `npm test` 7 files / 46 tests passed, `npm run build` exit 0. taste-skill `lint.mjs --app src` gave 0 FAIL, 0 WARN. package.json has 0 range specifiers. The counts match README (223 in three places, "7 files, 46 tests"), tasks.md M3 findings and design.md §9.5.

**Verdict**: APPROVED

## High-level view

The IMD fix is confirmed. `lib/imd.ts` mirrors `risk_rules.imd_indication` (plains or unknown terrain only; 40/45/47 °C), and the old 30 °C hilly threshold is gone. For hilly and coastal communities, ClimateView and ForecastChart show daily maxima with "IMD rule not applied", draw no IMD ticks or reference lines, fit the axis to the data and explain why. A parametrised hilly/coastal test pins this. design.md §9.4 now agrees with §8.2.

The job API now hands out `dataclasses.replace` copies taken under the lock from `submit`, `get` and `_update`. `job_view` can no longer see `succeeded` with a null `report_id`, and `test_job_reads_are_snapshots` covers this. On the client, `usePollJob` tolerates up to three consecutive `network_error`/5xx polls before it gives up, and both paths are tested.

The plan safety rule is unchanged and still lives only in `renderablePlanItems`. A needs-review report with zero verified items now keeps the "Not verified - needs human review" banner and says "0 items passed verification", with a test that no item text renders. AppShell sets a per-route `document.title` and moves focus to `main` on client-side navigation, but not on first load or when switching between tabs of the same report.

The pass-1 checks still hold: no personal data (`extra="forbid"`, hex-only store ids), the envelope on 422/404/405/429, CORS from `API_CORS_ORIGINS`, no Bedrock or Open-Meteo in automated tests, the disclaimer, notices and missing information on every tab, exact pins matching the lockfile, landmarks, labels and focus, text on every risk colour, and a clean taste lint.

<details>
<summary>Issues (2)</summary>

1. **Inspector not re-run after Climate change (possible)**: the hilly/coastal Climate variant has no `inspect.mjs` pass at 1440/768/390. Run it once on a hilly-profile report before M4 UI work.
2. **500 responses still lack CORS headers (confirmed, accepted)**: documented in design.md §9.1 as a known limit. The browser shows `internal_error` as "Could not reach the HeatWise API". Revisit when the API moves behind API Gateway/Lambda in M4.

</details>

<details>
<summary>Details</summary>

### Open items carried to M4

Two pass-1 items were accepted, not changed, and are documented for M4. The first is the 500/CORS edge: Starlette's ServerErrorMiddleware sits outside CORSMiddleware (design.md §9.1). The second is `store.all()` running on every history, metrics and Home request (design.md §9.3). The hilly/coastal Climate variant came after the last inspector round, so its layout at 390 px is unchecked (possible).

</details>

<details>
<summary>Files reviewed</summary>

- Changed since pass 1: `backend/api/jobs.py` (snapshot copies under the lock), `frontend/src/lib/imd.ts`, `components/ForecastChart.tsx`, `routes/report/ClimateView.tsx` (IMD parity), `routes/report/PlanView.tsx` (zero-verified banner), `api/usePollJob.ts` (transient retry), `components/AppShell.tsx` (route title and focus), tests `report.test.tsx`, `JobProgress.test.tsx`, `Landing.test.tsx`, `backend/tests/test_api.py`
- Re-checked: `backend/api/routes.py`, `backend/services/risk_rules.py` (`imd_indication`), FEAT-001..003 findings
- Docs: `.kiro/specs/heatwise-ai/{tasks.md,design.md}`, `heatwise-ai/README.md` (counts and §8.2/§9.4 agreement)
- Pass 1 reviewed every other M3 file listed in the FEAT files; those files are unchanged since then (checked by modification time).

No diff tool (not a git repo); files were read in place.

</details>
