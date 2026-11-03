import { Download } from "lucide-react";
import { useState } from "react";

import { type ApiError, api, toApiError } from "../../api/client";
import type { AssessmentRecord, PlanItem } from "../../api/types";
import { renderablePlanItems } from "../../lib/safety";
import { sourceFor } from "../../lib/sources";
import { useReportRecord } from "./reportContext";

const CARD = "glass rounded-card p-5 sm:p-6";
const AUDIENCES = [
  { key: "household", title: "Households" },
  { key: "outdoor_worker", title: "Outdoor workers" },
  { key: "farmer", title: "Farmers" },
];
const PHASES = [
  { key: "before", title: "Before the heat" },
  { key: "during", title: "During the heat" },
  { key: "after", title: "After the heat" },
];

export const REVIEW_BANNER = "Not verified - needs human review";

/** Downloads exactly report.checklist_markdown, never a checklist rebuilt here. */
function downloadChecklist(markdown: string, reportId: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `heatwise-checklist-${reportId}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

interface ItemProps {
  item: PlanItem;
  done: boolean;
  saving: boolean;
  onToggle: (item: PlanItem, completed: boolean) => void;
}

function Item({ item, done, saving, onToggle }: ItemProps) {
  const sources = item.source_ids.map(sourceFor).filter((s) => s !== null);
  const id = `check-${item.id}`;
  return (
    <li className="flex gap-2.5">
      <input
        id={id}
        type="checkbox"
        checked={done}
        disabled={saving}
        onChange={(e) => onToggle(item, e.target.checked)}
        className="mt-0.5 size-4 flex-none accent-ink"
      />
      <div className="min-w-0">
        <label htmlFor={id} className="block text-body">
          {item.text}
        </label>
        <p className="mt-0.5 text-small text-muted">
          {sources.length
            ? sources.map((s, i) => (
                <span key={s.id}>
                  {i > 0 && "; "}
                  <a href={s.url} target="_blank" rel="noreferrer" className="underline">
                    {s.title}
                  </a>
                </span>
              ))
            : "General advice, no source"}
        </p>
      </div>
    </li>
  );
}

/** Checklist progress for the rendered items only; saved per item through the API. */
function useChecklist(record: AssessmentRecord, items: PlanItem[]) {
  const [done, setDone] = useState<Set<string>>(() => {
    const stored = record.checklist_completed ?? {};
    return new Set(items.filter((i) => i.id in stored).map((i) => i.id));
  });
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function toggle(item: PlanItem, completed: boolean) {
    setSaving(item.id);
    setError(null);
    try {
      const progress = await api.setChecklistItem(record.report_id, item.id, completed);
      setDone(new Set(progress.completed_item_ids));
    } catch (err) {
      setError(toApiError(err));
    } finally {
      setSaving(null);
    }
  }

  return { done, saving, error, toggle };
}

/** Screen E: what should people do, and has it been verified? Renders only renderablePlanItems(report). */
export function PlanView() {
  const record = useReportRecord();
  const { report } = record;
  const plan = report.recommended_actions;
  const items = renderablePlanItems(report);
  const needsReview = report.status === "needs_human_review";
  const checklist = useChecklist(record, items);

  // A needs-review plan with no verified items still shows the review banner, never "no plan".
  if (!plan || (items.length === 0 && !needsReview)) {
    return (
      <section aria-labelledby="plan-h" className={CARD}>
        <h2 id="plan-h" className="text-section font-medium">
          Preparedness plan
        </h2>
        <p className="mt-1 text-body">No preparedness plan was built for this report.</p>
      </section>
    );
  }

  const withheld = needsReview ? plan.items.length - items.length : 0;
  const usedSources = [...new Set(items.flatMap((i) => i.source_ids))].map(sourceFor).filter((s) => s !== null);
  const markdown = report.checklist_markdown;

  return (
    <div className="space-y-6">
      {needsReview && (
        <section aria-labelledby="review-h" className="rounded-card border border-warn-line bg-warn-bg p-5 text-warn-ink">
          <h2 id="review-h" className="text-section font-medium">
            {REVIEW_BANNER}
          </h2>
          <p className="mt-1 text-body">
            {`The plan did not pass automated safety verification after one revision. ${
              items.length === 0 ? "0 items passed verification, so no actions are shown" : `Only the ${items.length} items that passed are shown`
            }${
              withheld > 0 ? `; ${withheld === 1 ? "1 item was" : `${withheld} items were`} withheld` : ""
            }. A person should review the plan before it is shared.`}
          </p>
        </section>
      )}

      <section aria-labelledby="plan-h" className={CARD}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="plan-h" className="text-section font-medium">
              Preparedness plan
            </h2>
            <p className="mt-1 text-body text-muted">
              {`${items.length} ${needsReview ? "verified " : ""}actions for the community`}
            </p>
            {items.length > 0 && (
              <p className="num mt-0.5 text-small text-muted" aria-live="polite">
                {`${checklist.done.size} of ${items.length} done`}
              </p>
            )}
          </div>
          {markdown && (
            <button
              type="button"
              onClick={() => downloadChecklist(markdown, report.report_id)}
              className="inline-flex h-9 items-center gap-2 rounded-control bg-primary px-4 text-body font-medium text-surface hover:bg-ink"
            >
              <Download size={16} strokeWidth={1.5} aria-hidden="true" />
              Download checklist
            </button>
          )}
        </div>
        {plan.intro && <p className="mt-3 text-body">{plan.intro}</p>}
        {plan.language_notice && <p className="mt-2 text-body text-muted">{plan.language_notice}</p>}
        {checklist.error && (
          <p role="alert" className="mt-2 text-body">
            {`Couldn't save the checklist change. ${checklist.error.message}`}
          </p>
        )}

        <div className="mt-6 space-y-8">
          {AUDIENCES.map((aud) => {
            const forAudience = items.filter((i) => i.audience === aud.key);
            if (!forAudience.length) return null;
            return (
              <section key={aud.key} aria-labelledby={`aud-${aud.key}`}>
                <h3 id={`aud-${aud.key}`} className="text-section font-medium">
                  {aud.title}
                </h3>
                <div className="mt-3 grid gap-5 lg:grid-cols-3">
                  {PHASES.map((ph) => {
                    const entries = forAudience.filter((i) => i.phase === ph.key);
                    return (
                      <div key={ph.key}>
                        <h4 className="text-body font-medium text-muted">{ph.title}</h4>
                        {entries.length ? (
                          <ul className="mt-2 space-y-3">
                            {entries.map((i) => (
                              <Item
                                key={i.id}
                                item={i}
                                done={checklist.done.has(i.id)}
                                saving={checklist.saving === i.id}
                                onToggle={checklist.toggle}
                              />
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-2 text-body text-muted">No actions for this phase.</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      </section>

      <section aria-labelledby="sources-h" className={CARD}>
        <h2 id="sources-h" className="text-section font-medium">
          Source references
        </h2>
        {usedSources.length ? (
          <ul className="mt-2 space-y-1.5 text-body">
            {usedSources.map((s) => (
              <li key={s.id}>
                <a href={s.url} target="_blank" rel="noreferrer" className="underline">
                  {s.title}
                </a>{" "}
                <span className="text-muted">{s.publisher}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-body">No sources are cited by the items shown.</p>
        )}
      </section>
    </div>
  );
}
