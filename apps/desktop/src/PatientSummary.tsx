import type { PersonDataSummary } from "./engine";

type PatientSummaryProps = {
  summary: PersonDataSummary | null;
  loading: boolean;
  error: string | null;
};

/** Show what the local record supports without dumping the full chart. */
export function PatientSummary({
  summary,
  loading,
  error,
}: PatientSummaryProps) {
  if (loading) {
    return (
      <section className="patient-summary" aria-live="polite">
        <h2 className="panel__title">Current patient</h2>
        <div className="progress">
          <span className="spinner" aria-hidden="true" />
          <span className="progress__text">Loading patient data…</span>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="patient-summary">
        <h2 className="panel__title">Current patient</h2>
        <p className="notice notice--bad">{error}</p>
      </section>
    );
  }

  if (!summary) {
    return (
      <section className="patient-summary">
        <h2 className="panel__title">Current patient</h2>
        <p className="hint">Click a resident to review available and missing data.</p>
      </section>
    );
  }

  const available = summary.categories.filter((category) => category.count > 0);

  return (
    <section className="patient-summary" aria-live="polite">
      <div className="patient-summary__heading">
        <div>
          <h2 className="panel__title">Current patient</h2>
          <h3 className="patient-summary__name">{summary.name}</h3>
        </div>
        {summary.person_identifier && (
          <span className="resident__id">{summary.person_identifier}</span>
        )}
      </div>

      <dl className="patient-summary__overview">
        {summary.overview.map((field) => (
          <div className="patient-summary__field" key={field.key}>
            <dt>{field.label}</dt>
            <dd className={field.value ? undefined : "patient-summary__empty"}>
              {field.value ?? "Not documented"}
            </dd>
          </div>
        ))}
      </dl>

      <h3 className="patient-summary__section-title">Available clinical data</h3>
      {available.length === 0 ? (
        <p className="hint">No clinical records are associated with this patient.</p>
      ) : (
        <ul className="patient-summary__categories">
          {available.map((category) => (
            <li key={category.key}>
              <span>
                <strong>{category.label}</strong>
                {category.detail && <small>{category.detail}</small>}
              </span>
              <span className="patient-summary__count">{category.count}</span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="patient-summary__section-title">Not documented</h3>
      {summary.missing.length === 0 ? (
        <p className="notice notice--ok">All core nutrition inputs are documented.</p>
      ) : (
        <ul className="patient-summary__missing">
          {summary.missing.map((item) => (
            <li key={item.key}>
              <strong>{item.label}</strong>
              <span>{item.reason}</span>
            </li>
          ))}
        </ul>
      )}

      {summary.conflicts.length > 0 && (
        <>
          <h3 className="patient-summary__section-title">Needs review</h3>
          <ul className="patient-summary__conflicts">
            {summary.conflicts.map((conflict) => (
              <li key={conflict}>{conflict}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
