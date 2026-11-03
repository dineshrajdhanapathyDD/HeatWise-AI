import { motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Check, Droplets, MapPin, Mountain, ShieldCheck, Sun, UsersRound } from "lucide-react";
import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, toApiError } from "../api/client";
import { useHealth } from "../api/healthContext";
import { AgentPipeline } from "../components/AgentPipeline";
import { useToast } from "../components/toastContext";
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

const STEPS = [
  { title: "Place", hint: "Where is the community?", icon: MapPin },
  { title: "Community", hint: "Who lives there, and how they live", icon: UsersRound },
  { title: "Settings and review", hint: "Report options and a final check", icon: ShieldCheck },
] as const;

/** Which step holds each field, so an error can send the user back to it. */
const STEP_OF: Record<FieldKey, number> = { demoLocation: 0, name: 0, district: 0, state: 0, forecastDays: 2, language: 2 };

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
        <p id={`${id}-error`} className="mt-1.5 text-small font-medium text-negative">
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

function RadioCards<T extends string>({
  name,
  legend,
  value,
  options,
  onChange,
  icon: Icon,
}: {
  name: string;
  legend: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  icon: typeof Sun;
}) {
  return (
    <fieldset>
      <legend className="flex items-center gap-2 text-body font-medium">
        <Icon size={16} aria-hidden="true" className="text-cyan" />
        {legend}
      </legend>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((o) => (
          <label
            key={o.value}
            className={`flex min-h-10 cursor-pointer items-center gap-2 rounded-control border px-3 text-body transition-colors ${
              value === o.value ? "border-amber/70 bg-amber/10 text-ink" : "border-control bg-raised/40 text-muted hover:text-ink"
            }`}
          >
            <input
              type="radio"
              name={name}
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              className="h-4 w-4 accent-amber"
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

/** Screen B: the place and community profile, step by step, mapped onto the API request. */
export function AssessForm() {
  const navigate = useNavigate();
  const notify = useToast();
  const { health } = useHealth();
  const demoLocations = health?.weather_provider === "demo" ? (health.demo_locations ?? []) : [];
  const demoMode = demoLocations.length > 0;

  const [step, setStep] = useState(0);
  const [form, setForm] = useState<FormState>(() => initialFormState());
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pendingFocus = useRef<FieldKey | "heading" | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Focus the first invalid field once its error has rendered, or the step heading after Next/Back.
  useEffect(() => {
    const key = pendingFocus.current;
    if (!key) return;
    pendingFocus.current = null;
    if (key === "heading") headingRef.current?.focus();
    else document.getElementById(key)?.focus();
  }, [errors, step]);

  const effective: FormState = demoMode ? { ...form, demoLocation: form.demoLocation || demoLocations[0] || "" } : form;
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => setForm((f) => ({ ...f, [key]: value }));

  const showErrors = (next: Errors) => {
    const first = FOCUS_ORDER.find((k) => next[k]) ?? null;
    pendingFocus.current = first;
    if (first) setStep(STEP_OF[first]);
    setErrors(next);
  };

  const goTo = (target: number) => {
    pendingFocus.current = "heading";
    setStep(target);
  };

  const next = () => {
    if (step === 0) {
      const placeErrors = validateForm(effective, demoMode);
      if (Object.keys(placeErrors).length) {
        showErrors({ ...errors, ...placeErrors });
        return;
      }
      setErrors((e) => ({ ...e, name: undefined, demoLocation: undefined }));
    }
    goTo(Math.min(step + 1, STEPS.length - 1));
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (step < STEPS.length - 1) {
      next();
      return;
    }
    setFormError(null);
    const clientErrors = validateForm(effective, demoMode);
    if (Object.keys(clientErrors).length) {
      showErrors(clientErrors);
      return;
    }
    setSubmitting(true);
    try {
      const body = toRequestBody(effective, demoMode);
      const job = await api.createAssessment(body);
      notify(`Assessment started for ${body.place.name}.`);
      navigate(`/assessments/${job.job_id}`);
    } catch (err) {
      const apiError = toApiError(err);
      const fieldErrors: Errors = {};
      const unmapped: string[] = [];
      for (const f of apiError.fields) {
        const key = fieldForServerPath(f.field, demoMode);
        if (key && !fieldErrors[key]) fieldErrors[key] = f.message;
        else if (!key) unmapped.push(f.message);
      }
      if (!Object.keys(fieldErrors).length || unmapped.length) setFormError([apiError.message, ...unmapped].join(" "));
      showErrors(fieldErrors);
      setSubmitting(false);
    }
  }

  const fieldClass = (key: FieldKey) => `field ${errors[key] ? "!border-negative" : ""}`;
  const selectedGroups = POPULATION_GROUPS.filter((g) => form.groups[g.key]);
  const current = STEPS[step]!;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
      <div className="min-w-0">
        <p className="eyebrow">Community heat assessment</p>
        <h1 className="mt-1 text-title font-semibold">New assessment</h1>
        <p className="mt-1 text-body text-muted">Describe the place and the groups who live there, one step at a time.</p>

        <ol aria-label="Assessment steps" className="mt-6 grid grid-cols-3 gap-2">
          {STEPS.map((s, i) => {
            const done = i < step;
            const active = i === step;
            const Icon = s.icon;
            return (
              <li key={s.title}>
                <button
                  type="button"
                  onClick={() => i < step && goTo(i)}
                  disabled={i > step}
                  aria-current={active ? "step" : undefined}
                  className={`flex w-full items-center gap-3 rounded-control border bg-raised/40 p-3 text-left transition-colors disabled:cursor-default ${
                    active ? "border-amber/60" : done ? "border-line hover:border-control" : "border-line opacity-60"
                  }`}
                >
                  <span
                    className={`grid h-8 w-8 flex-none place-items-center rounded-full text-small font-semibold ${
                      done ? "bg-positive/20 text-positive" : active ? "bg-amber text-surface" : "bg-raised text-muted"
                    }`}
                  >
                    {done ? <Check size={16} aria-hidden="true" /> : <Icon size={16} aria-hidden="true" />}
                  </span>
                  <span className="hidden min-w-0 sm:block">
                    <span className="block text-small text-muted">{`Step ${i + 1}`}</span>
                    <span className="block truncate text-body font-medium">{s.title}</span>
                  </span>
                  <span className="sr-only sm:hidden">{`Step ${i + 1}: ${s.title}`}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <div aria-hidden="true" className="mt-3 h-1 overflow-hidden rounded-full bg-raised">
          <motion.div
            className="h-1 rounded-full bg-amber"
            animate={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>

        {formError && (
          <p role="alert" className="mt-5 rounded-control border border-negative/40 bg-neg-bg p-3 text-body text-neg-ink">
            {formError}
          </p>
        )}

        <form noValidate onSubmit={onSubmit} className="glass mt-5 rounded-card p-5 sm:p-7">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
          >
            <p className="text-small text-muted">{`Step ${step + 1} of ${STEPS.length}`}</p>
            <h2 ref={headingRef} tabIndex={-1} className="mt-0.5 text-section font-semibold focus:outline-none">
              {current.title}
            </h2>
            <p className="text-small text-muted">{current.hint}</p>

            {step === 0 && (
              <fieldset className="mt-6 space-y-4">
                <legend className="sr-only">Place</legend>
                {demoMode ? (
                  <Field
                    id="demoLocation"
                    label="Demo location"
                    error={errors.demoLocation}
                    hint="The server is in demo mode, so only demo places can be assessed."
                  >
                    <select
                      id="demoLocation"
                      value={effective.demoLocation}
                      onChange={(e) => set("demoLocation", e.target.value)}
                      aria-invalid={errors.demoLocation ? true : undefined}
                      aria-describedby={describedBy("demoLocation", errors.demoLocation, true)}
                      className={fieldClass("demoLocation")}
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
                      <div className="relative">
                        <MapPin size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                        <input
                          id="name"
                          type="text"
                          required
                          autoComplete="address-level2"
                          placeholder="e.g. Thanjavur"
                          maxLength={MAX_PLACE_LENGTH}
                          value={form.name}
                          onChange={(e) => set("name", e.target.value)}
                          aria-invalid={errors.name ? true : undefined}
                          aria-describedby={describedBy("name", errors.name)}
                          className={`${fieldClass("name")} pl-9`}
                        />
                      </div>
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
                          className={fieldClass("district")}
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
                          className={fieldClass("state")}
                        />
                      </Field>
                    </div>
                    <p className="text-small text-muted">
                      The weather agent resolves the name with the provider's geocoding. Adding the state helps when
                      several places share a name.
                    </p>
                  </>
                )}
              </fieldset>
            )}

            {step === 1 && (
              <div className="mt-6 space-y-7">
                <fieldset>
                  <legend className="text-body font-medium">Groups present in the community</legend>
                  <p className="mt-0.5 text-small text-muted">Tick every group that lives or works here.</p>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {POPULATION_GROUPS.map((g) => {
                      const on = form.groups[g.key];
                      return (
                        <label
                          key={g.key}
                          className={`flex min-h-12 cursor-pointer items-center gap-3 rounded-control border px-3 text-body transition-colors ${
                            on ? "border-amber/70 bg-amber/10 text-ink" : "border-control bg-raised/40 text-muted hover:text-ink"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={on}
                            onChange={(e) => set("groups", { ...form.groups, [g.key]: e.target.checked })}
                            className="h-4 w-4 accent-amber"
                          />
                          {g.label}
                        </label>
                      );
                    })}
                  </div>
                </fieldset>
                <div className="space-y-5">
                  <h3 className="text-body font-medium">Living conditions</h3>
                  <RadioCards name="water" legend="Drinking water access" icon={Droplets} value={form.water} options={ACCESS_OPTIONS} onChange={(v) => set("water", v)} />
                  <RadioCards name="shade" legend="Shade and cooling" icon={Sun} value={form.shade} options={ACCESS_OPTIONS} onChange={(v) => set("shade", v)} />
                  <RadioCards name="terrain" legend="Terrain" icon={Mountain} value={form.terrain} options={TERRAIN_OPTIONS} onChange={(v) => set("terrain", v)} />
                  <p className="text-small text-muted">
                    IMD actual-maximum criteria are applied on plains (or when terrain is not given). Hilly and coastal
                    criteria need data HeatWise does not have.
                  </p>
                </div>
              </div>
            )}

            {step === 2 && (
              <div className="mt-6 space-y-6">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field id="language" label="Preferred language" error={errors.language} hint="Plans are English only for now.">
                    <select
                      id="language"
                      value={form.language}
                      onChange={(e) => set("language", e.target.value)}
                      aria-invalid={errors.language ? true : undefined}
                      aria-describedby={describedBy("language", errors.language, true)}
                      className={fieldClass("language")}
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
                      className={fieldClass("forecastDays")}
                    >
                      {[1, 2, 3, 4, 5, 6, 7].map((d) => (
                        <option key={d} value={d}>
                          {d === 1 ? "1 day" : `${d} days`}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>

                <section aria-labelledby="review-h" className="rounded-control border border-line bg-raised/40 p-4">
                  <h3 id="review-h" className="text-body font-semibold">
                    Review
                  </h3>
                  <dl className="mt-3 grid gap-3 text-body sm:grid-cols-[140px_minmax(0,1fr)]">
                    <dt className="text-muted">Place</dt>
                    <dd>
                      {demoMode
                        ? effective.demoLocation
                        : [form.name.trim(), form.district.trim(), form.state.trim()].filter(Boolean).join(", ") || "Not set"}
                    </dd>
                    <dt className="text-muted">Groups</dt>
                    <dd>{selectedGroups.length ? selectedGroups.map((g) => g.label).join(", ") : "None ticked"}</dd>
                    <dt className="text-muted">Conditions</dt>
                    <dd>
                      {`Water ${form.water}, shade and cooling ${form.shade}, terrain ${
                        form.terrain === "not_sure" ? "not given" : form.terrain
                      }`}
                    </dd>
                  </dl>
                </section>
              </div>
            )}
          </motion.div>

          <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-5">
            {step > 0 ? (
              <button type="button" onClick={() => goTo(step - 1)} className="btn-secondary">
                <ArrowLeft size={16} aria-hidden="true" />
                Back
              </button>
            ) : (
              <span />
            )}
            {step < STEPS.length - 1 ? (
              <button type="submit" className="btn-primary">
                Next
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            ) : (
              <button type="submit" disabled={submitting} className="btn-primary">
                {submitting ? "Starting the assessment…" : "Run the assessment"}
                {!submitting && <ArrowRight size={16} aria-hidden="true" />}
              </button>
            )}
          </div>
        </form>
      </div>

      <aside className="space-y-4 xl:pt-[104px]">
        <section aria-labelledby="what-is-stored" className="glass rounded-card p-5">
          <h2 id="what-is-stored" className="text-section font-semibold">
            What HeatWise keeps
          </h2>
          <ul className="mt-3 space-y-2 text-body text-muted">
            {[
              "The place, the forecast length and which groups are present. Nothing about any individual.",
              "No names, phone numbers or addresses are asked for or stored.",
              "The report, its plan and the record of what each agent did, so you can compare later runs in History.",
              "HeatWise does not send alerts or contact anyone.",
            ].map((t) => (
              <li key={t} className="flex gap-2">
                <Check size={16} aria-hidden="true" className="mt-0.5 flex-none text-positive" />
                <span>{t}</span>
              </li>
            ))}
          </ul>
        </section>
        <AgentPipeline input={{ phase: "idle" }} headingId="assess-pipeline-h" title="What happens next" vertical />
      </aside>
    </div>
  );
}
