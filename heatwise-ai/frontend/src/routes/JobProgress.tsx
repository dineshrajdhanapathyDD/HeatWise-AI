import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { DEFAULT_POLL_TIMING, type PollTiming, usePollJob } from "../api/usePollJob";
import { placeName } from "../lib/format";

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
  const { job, error, timedOut } = usePollJob(jobId, timing);
  const [elapsed, setElapsed] = useState(0);

  const finished = job?.status === "succeeded" || job?.status === "failed" || error !== null || timedOut;

  useEffect(() => {
    if (finished) return;
    const started = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(id);
  }, [jobId, finished]);

  useEffect(() => {
    if (job?.status === "succeeded" && job.report_id) {
      navigate(`/reports/${job.report_id}/climate`, { replace: true });
    }
  }, [job, navigate]);

  const place = job ? placeName([job.request.place.name, job.request.place.district, job.request.place.state]) : "";
  const status = job?.status ?? "queued";

  return (
    <>
      <h1 className="text-title font-medium">Assessment in progress</h1>
      <p className="mt-1 text-body text-muted">{place ? `For ${place}` : "Starting the assessment"}</p>

      <section aria-labelledby="job-status" className="mt-6 max-w-[640px] rounded-card border border-line bg-surface p-5">
        <h2 id="job-status" className="text-section font-medium">
          Status
        </h2>
        <div aria-live="polite" className="mt-2 text-body">
          {error ? (
            <p>{`Couldn't check the assessment. ${error.message}`}</p>
          ) : timedOut ? (
            <p>
              The assessment is taking longer than 5 minutes, so this page stopped checking. It may still finish:
              look for it in <Link to="/history" className="underline">History</Link>.
            </p>
          ) : job?.status === "failed" ? (
            <p>{job.error?.message ?? STATUS_TEXT.failed}</p>
          ) : (
            <AnimatePresence mode="wait" initial={false}>
              <motion.p
                key={status}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15, ease: "easeOut" }}
              >
                {`${STATUS_TEXT[status]}.`}
              </motion.p>
            </AnimatePresence>
          )}
        </div>
        {!finished && <p className="num mt-1 text-small text-muted">{`${elapsed} s elapsed`}</p>}
        {(error || timedOut || job?.status === "failed") && (
          <Link
            to="/assess"
            className="mt-4 inline-flex h-9 items-center rounded-control bg-primary px-4 text-body font-medium text-surface hover:bg-ink"
          >
            Try again
          </Link>
        )}
      </section>
    </>
  );
}
