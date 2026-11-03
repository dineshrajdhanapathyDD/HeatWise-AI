/** Shown on every tab of an incomplete report. */
export function MissingInfo({ items }: { items: string[] }) {
  return (
    <section aria-labelledby="missing-info" className="rounded-card border border-warn-line bg-warn-bg p-5 text-warn-ink">
      <h2 id="missing-info" className="text-section font-medium">
        Missing information
      </h2>
      <p className="mt-1 text-body">This report is incomplete, so no preparedness plan was built.</p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-body">
        {items.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
    </section>
  );
}
