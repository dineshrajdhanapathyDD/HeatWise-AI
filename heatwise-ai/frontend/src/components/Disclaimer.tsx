export const DISCLAIMER =
  "HeatWise AI is an informational tool. It is not medical advice, not an emergency service and not a " +
  "substitute for official warnings from your meteorological and disaster management authorities.";

/** Shown on every report tab together with the report's own notices. */
export function Disclaimer({ notices }: { notices: string[] }) {
  return (
    <section aria-labelledby="about-report" className="rounded-card bg-raised p-5">
      <h2 id="about-report" className="text-body font-medium">
        About this report
      </h2>
      <p className="mt-1 text-body">{DISCLAIMER}</p>
      {notices.length > 0 && (
        <ul aria-label="Report notices" className="mt-3 list-disc space-y-1 pl-5 text-body">
          {notices.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
