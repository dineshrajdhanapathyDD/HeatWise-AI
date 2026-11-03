import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, toApiError } from "../api/client";
import { useHealth } from "../api/healthContext";
import {
  type Access,
  type FieldKey,
  type FormState,
  LANGUAGES,
  MAX_PLACE_LENGTH,
  POPULATION_GROUPS,
  type TerrainChoice,
  fieldForServerPath,
  initialFormState,
  toRequestBody,
  validateForm,
} from "../lib/profile";

type Errors = Partial<Record<FieldKey, string>>;
const FOCUS_ORDER: FieldKey[] = ["demoLocation", "name", "district", "state", "forecastDays", "language"];

const INPUT = "h-10 w-full rounded-control border bg-surface px-3 text-body";
const legendClass = "text-section font-medium";

function Field({
  id,
  label,
  error,
  hint,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-body font-medium">
        {label}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="mt-0.5 text-small text-muted">
          {hint}
        </p>
      )}
      <div className="mt-2">{children}</div>
      {error && (
        <p id={`${id}-error`} className="mt-1 text-small text-negative">
          {error}
        </p>
      )}
    </div>
  );
}

function describedBy(id: string, error?: string, hint?: boolean): string | undefined {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

function RadioGroup<T extends string>({
  name,
  legend,
  value,
  options,
  onChange,
}: {
  name: string;
  legend: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <fieldset>
      <legend className="text-body font-medium">{legend}</legend>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
        {options.map((o) => (
          <label key={o.value} className="flex min-h-6 items-center gap-2 text-body">
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              className="h-4 w-4 accent-primary"
            />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

const ACCESS_OPTIONS: { value: Access; label: string }[] = [
  { value: "adequate", label: "Adequate" },
  { value: "limited", label: "Limited" },
];

const TERRAIN_OPTIONS: { value: TerrainChoice; label: string }[] = [
  { value: "plains", label: "Plains" },
  { value: "hilly", label: "Hilly" },
  { value: "coastal", label: "Coastal" },
  { value: "not_sure", label: "Not sure" },
];

/** Screen B: the place and community profile, mapped onto the API request. */
export function AssessForm() {
  const navigate = useNavigate();
  const { health } = useHealth();
  const demoLocations = health?.weather_provider === "demo" ? (health.demo_locations ?? []) : [];
  const demoMode = demoLocations.length > 0;

  const [form, setForm] = useState<FormState>(() => initialFormState());
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pendingFocus = useRef<FieldKey | null>(null);

  // Each field's id is its FieldKey; focus the first invalid one once its error has rendered.
  useEffect(() => {
    const key = pendingFocus.current;
    if (key) {
      pendingFocus.current = null;
      document.getElementById(key)?.focus();
    }
  }, [errors]);

  const effective: FormState = demoMode ? { ...form, demoLocation: form.demoLocation || demoLocations[0] || "" } : form;
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));

  const showErrors = (next: Errors) => {
    pendingFocus.current = FOCUS_ORDER.find((k) => next[k]) ?? null;
    setErrors(next);
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const clientErrors = validateForm(effective, demoMode);
    if (Object.keys(clientErrors).length) {
      showErrors(clientErrors);
      return;
    }
    setSubmitting(true);
    try {
      const job = await api.createAssessment(toRequestBody(effective, demoMode));
      navigate(`/assessments/${job.job_id}`);
    } catch (err) {
      const apiError = toApiError(err);
      const next: Errors = {};
      const unmapped: string[] = [];
      for (const f of apiError.fields) {
        const key = fieldForServerPath(f.field, demoMode);
        if (key && !next[key]) next[key] = f.message;
        else if (!key) unmapped.push(f.message);
      }
      if (!Object.keys(next).length || unmapped.length) setFormError([apiError.message, ...unmapped].join(" "));
      showErrors(next);
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,640px)_minmax(0,1fr)]">
      <div>
        <h1 className="text-title font-medium">New assessment</h1>
        <p className="mt-1 text-body text-muted">Describe the place and the groups who live there.</p>

        {formError && (
          <p role="alert" className="mt-4 rounded-card border border-neg-bg bg-neg-bg p-3 text-body text-neg-ink">
            {formError}
          </p>
        )}

        <form noValidate onSubmit={onSubmit} className="mt-6 space-y-8">
          <fieldset className="space-y-4">
            <legend className={legendClass}>Place</legend>
            {demoMode ? (
              <Field id="demoLocation" label="Demo location" error={errors.demoLocation} hint="The server is in demo mode, so only demo places can be assessed.">
                <select
                  id="demoLocation"
                  value={effective.demoLocation}
                  onChange={(e) => set("demoLocation", e.target.value)}
                  aria-invalid={errors.demoLocation ? true : undefined}
                  aria-describedby={describedBy("demoLocation", errors.demoLocation, true)}
                  className={`${INPUT} ${errors.demoLocation ? "border-negative" : "border-control"}`}
                >
                  {demoLocations.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </Field>
            ) : (
              <>
                <Field id="name" label="City, town or village" error={errors.name}>
                  <input
                    id="name"
                    type="text"
                    required
                    autoComplete="address-level2"
                    maxLength={MAX_PLACE_LENGTH}
                    value={form.name}
                    onChange={(e) => set("name", e.target.value)}
                    aria-invalid={errors.name ? true : undefined}
                    aria-describedby={describedBy("name", errors.name)}
                    className={`${INPUT} ${errors.name ? "border-negative" : "border-control"}`}
                  />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field id="district" label="District (optional)" error={errors.district}>
                    <input
                      id="district"
                      type="text"
                      maxLength={MAX_PLACE_LENGTH}
                      value={form.district}
                      onChange={(e) => set("district", e.target.value)}
                      aria-invalid={errors.district ? true : undefined}
                      aria-describedby={describedBy("district", errors.district)}
                      className={`${INPUT} ${errors.district ? "border-negative" : "border-control"}`}
                    />
                  </Field>
                  <Field id="state" label="State (optional)" error={errors.state}>
                    <input
                      id="state"
                      type="text"
                      autoComplete="address-level1"
                      maxLength={MAX_PLACE_LENGTH}
                      value={form.state}
                      onChange={(e) => set("state", e.target.value)}
                      aria-invalid={errors.state ? true : undefined}
                      aria-describedby={describedBy("state", errors.state)}
                      className={`${INPUT} ${errors.state ? "border-negative" : "border-control"}`}
                    />
                  </Field>
                </div>
              </>
            )}
          </fieldset>

          <fieldset>
            <legend className={legendClass}>Groups present in the community</legend>
            <p className="mt-1 text-small text-muted">Tick every group that lives or works here.</p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {POPULATION_GROUPS.map((g) => (
                <label key={g.key} className="flex min-h-6 items-center gap-2 text-body">
                  <input
                    type="checkbox"
                    checked={form.groups[g.key]}
                    onChange={(e) => set("groups", { ...form.groups, [g.key]: e.target.checked })}
                    className="h-4 w-4 accent-primary"
                  />
                  {g.label}
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="space-y-5">
            <legend className={legendClass}>Living conditions</legend>
            <RadioGroup name="water" legend="Drinking water access" value={form.water} options={ACCESS_OPTIONS} onChange={(v) => set("water", v)} />
            <RadioGroup name="shade" legend="Shade and cooling" value={form.shade} options={ACCESS_OPTIONS} onChange={(v) => set("shade", v)} />
            <RadioGroup name="terrain" legend="Terrain" value={form.terrain} options={TERRAIN_OPTIONS} onChange={(v) => set("terrain", v)} />
          </fieldset>

          <fieldset className="grid gap-4 sm:grid-cols-2">
            <legend className={`${legendClass} mb-4`}>Report</legend>
            <Field id="language" label="Preferred language" error={errors.language} hint="Plans are English only for now.">
              <select
                id="language"
                value={form.language}
                onChange={(e) => set("language", e.target.value)}
                aria-invalid={errors.language ? true : undefined}
                aria-describedby={describedBy("language", errors.language, true)}
                className={`${INPUT} ${errors.language ? "border-negative" : "border-control"}`}
              >
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field id="forecastDays" label="Forecast days" error={errors.forecastDays} hint="From 1 to 7 days.">
              <select
                id="forecastDays"
                value={form.forecastDays}
                onChange={(e) => set("forecastDays", Number(e.target.value))}
                aria-invalid={errors.forecastDays ? true : undefined}
                aria-describedby={describedBy("forecastDays", errors.forecastDays, true)}
                className={`${INPUT} ${errors.forecastDays ? "border-negative" : "border-control"}`}
              >
                {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                  <option key={d} value={d}>
                    {d === 1 ? "1 day" : `${d} days`}
                  </option>
                ))}
              </select>
            </Field>
          </fieldset>

          <button
            type="submit"
            disabled={submitting}
            className="inline-flex h-10 items-center rounded-control bg-primary px-5 text-body font-medium text-surface hover:bg-ink disabled:bg-muted"
          >
            {submitting ? "Starting the assessment…" : "Run the assessment"}
          </button>
        </form>
      </div>

      <aside aria-labelledby="what-is-stored" className="self-start rounded-card bg-raised p-5 lg:mt-16">
        <h2 id="what-is-stored" className="text-section font-medium">
          What HeatWise keeps
        </h2>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-body">
          <li>The place, the forecast length and which groups are present. Nothing about any individual.</li>
          <li>No names, phone numbers or addresses are asked for or stored.</li>
          <li>The report, its plan and the record of what each agent did, so you can compare later runs in History.</li>
          <li>HeatWise does not send alerts or contact anyone.</li>
        </ul>
      </aside>
    </div>
  );
}
