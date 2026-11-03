import { AnimatePresence, motion } from "framer-motion";
import { Clock, MapPin } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { DEFAULT_POLL_TIMING, type PollTiming, usePollJob } from "../api/usePollJob";
import { AgentPipeline } from "../components/AgentPipeline";
import { useToast } from "../components/toastContext";
import { placeName } from "../lib/format";
import { POPULATION_GROUPS } from "../lib/profile";

const STATUS_TEXT = {
  queued: "Waiting for a free worker",
  running: "The agents are working on the assessment",
  succeeded: "Assessment finished. Opening the report",
  failed: "The assessment could not be completed",
} as const;

/** Job progress: polls the job and opens the report when it succeeds. */
export function JobProgress({ timing = DEFAULT_POLL_TIMING }: { timing?: PollTiming }) {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const notify = useToast();
  const { job, error, timedOut } = usePollJob(jobId, timing);
  const [elapsed, setElapsed] = useState(0);

  const finished = job?.status === "succeeded" || job?.status === "failed" || error !== null || timedOut;
  const stopped = Boolean(error || timedOut || job?.status === "failed");

  useEffect(() => {
    if (finished) return;
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [jobId, finished]);

  useEffect(() => {
    if (job?.status === "succeeded" && job.report_id) {
      notify("The report is ready.");
      navigate(`/reports/${job.report_id}/climate`, { replace: true });
    }
  }, [job, navigate, notify]);

  const place = job ? placeName([job.request.place.name, job.request.place.district, job.request.place.state]) : "";
  const status = job?.status ?? "queued";
  const groups = job ? POPULATION_GROUPS.filter((g) => job.request.profile?.[g.key]).map((g) => g.label) : [];

  return (
    <div className="space-y-6">
      <div>
        <p className="eyebrow">Assessment job</p>
        <h1 className="mt-1 text-title font-semibold">Assessment in progress</h1>
        <p className="mt-1 flex items-center gap-1.5 text-body text-muted">
          <MapPin size={16} aria-hidden="true" className="text-cyan" />
          {place ? `For ${place}` : "Starting the assessment"}
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section aria-labelledby="job-status" className="glass-strong relative overflow-hidden rounded-card p-6">
          {!finished && <div aria-hidden="true" className="hw-indeterminate absolute inset-x-0 top-0 h-1" />}
          <h2 id="job-status" className="text-section font-semibold">
            Status
          </h2>
          <div aria-live="polite" className="mt-3 text-section">
            {error ? (
              <p>{`Couldn't check the assessment. ${error.message}`}</p>
            ) : timedOut ? (
              <p>
                The assessment is taking longer than 5 minutes, so this page stopped checking. It may still finish:
                look for it in{" "}
                <Link to="/history" className="text-amber underline">
                  History
                </Link>
                .
              </p>
            ) : job?.status === "failed" ? (
              <p>{job.error?.message ?? STATUS_TEXT.failed}</p>
            ) : (
              <AnimatePresence mode="wait" initial={false}>
                <motion.p
                  key={status}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15, ease: "easeOut" }}
                >
                  {`${STATUS_TEXT[status]}.`}
                </motion.p>
              </AnimatePresence>
            )}
          </div>
          {!finished && (
            <p className="num mt-2 flex items-center gap-1.5 text-small text-muted">
              <Clock size={14} aria-hidden="true" />
              {`${elapsed} s elapsed`}
            </p>
          )}
          {!finished && (
            <p className="mt-4 text-small text-muted">
              A live assessment usually takes 20 to 40 seconds. You can leave this page; the report appears in
              History when it is ready.
            </p>
          )}
          {stopped && (
            <Link to="/assess" className="btn-primary mt-5">
              Try again
            </Link>
          )}
        </section>

        {job && (
          <aside aria-labelledby="job-request-h" className="glass rounded-card p-5">
            <h2 id="job-request-h" className="text-body font-semibold">
              Request
            </h2>
            <dl className="mt-3 space-y-2 text-body">
              <div>
                <dt className="text-small text-muted">Forecast</dt>
                <dd>{`${job.request.forecast_days} days`}</dd>
              </div>
              <div>
                <dt className="text-small text-muted">Groups</dt>
                <dd>{groups.length ? groups.join(", ") : "None ticked"}</dd>
              </div>
            </dl>
          </aside>
        )}
      </div>

      {!stopped && (
        <AgentPipeline
          input={job?.status === "succeeded" && job.report ? { phase: "finished", report: job.report } : { phase: "running", status }}
          headingId="job-pipeline-h"
          title="Agent workflow"
        />
      )}
    </div>
  );
}
