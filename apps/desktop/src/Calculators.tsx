import { useEffect, useMemo, useState } from "react";
import {
  type EnergyNeeds,
  type Formula,
  calculateEnergy,
  calculateTubefeed,
  listFormulas,
} from "./engine";

/** Shared submit button that reports its own busy state.
 *
 * `disabled` is separate from `busy` so a form that is merely not ready to
 * submit stays quiet rather than claiming to be calculating.
 */
function SubmitButton({
  busy,
  label,
  disabled = false,
}: {
  busy: boolean;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="submit"
      className="btn btn--primary btn--block"
      disabled={busy || disabled}
      aria-busy={busy}
    >
      {busy ? (
        <>
          <span className="spinner spinner--onDark" aria-hidden="true" />
          Calculating…
        </>
      ) : (
        label
      )}
    </button>
  );
}

function Field({
  label,
  children,
  wide = false,
}: {
  label: string;
  children: React.ReactNode;
  /** Span the whole grid row, for values too long for a half-width control. */
  wide?: boolean;
}) {
  return (
    <label className={`calcfield${wide ? " calcfield--wide" : ""}`}>
      <span className="calcfield__label">{label}</span>
      {children}
    </label>
  );
}

function range(value: { low: number; high: number }, unit: string): string {
  return `${value.low}–${value.high} ${unit}`;
}

export function EnergyPage() {
  const [weight, setWeight] = useState("150");
  const [height, setHeight] = useState("66");
  const [age, setAge] = useState("80");
  const [gender, setGender] = useState("f");
  const [goal, setGoal] = useState("maintain");
  const [activityLevel, setActivityLevel] = useState("1.2");
  const [dialysis, setDialysis] = useState(false);
  const [amputation, setAmputation] = useState("");

  const [busy, setBusy] = useState(false);
  const [needs, setNeeds] = useState<EnergyNeeds | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setNeeds(null);
    try {
      setNeeds(
        await calculateEnergy({
          weight: Number(weight),
          height: Number(height),
          age: Number(age),
          gender,
          goal,
          activityLevel: Number(activityLevel),
          dialysis,
          amputation: amputation ? Number(amputation) : undefined,
        }),
      );
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app__columns">
      <section className="panel">
        <h2 className="panel__title">Energy needs</h2>
        <form onSubmit={submit}>
          <div className="calcgrid">
            <Field label="Weight (lb)">
              <input
                className="field__input"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                inputMode="decimal"
              />
            </Field>
            <Field label="Height (in)">
              <input
                className="field__input"
                value={height}
                onChange={(e) => setHeight(e.target.value)}
                inputMode="decimal"
              />
            </Field>
            <Field label="Age">
              <input
                className="field__input"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                inputMode="numeric"
              />
            </Field>
            <Field label="Sex">
              <select
                className="field__input"
                value={gender}
                onChange={(e) => setGender(e.target.value)}
              >
                <option value="f">Female</option>
                <option value="m">Male</option>
              </select>
            </Field>
            <Field label="Goal">
              <select
                className="field__input"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
              >
                <option value="maintain">Maintain</option>
                <option value="lose">Lose</option>
                <option value="gain">Gain</option>
              </select>
            </Field>
            <Field label="Activity (1.2–1.9)">
              <input
                className="field__input"
                value={activityLevel}
                onChange={(e) => setActivityLevel(e.target.value)}
                inputMode="decimal"
              />
            </Field>
            <Field label="Amputation %">
              <input
                className="field__input"
                value={amputation}
                onChange={(e) => setAmputation(e.target.value)}
                placeholder="none"
                inputMode="decimal"
              />
            </Field>
          </div>

          <label className="checkline">
            <input
              type="checkbox"
              checked={dialysis}
              onChange={(e) => setDialysis(e.target.checked)}
            />
            <span>On hemodialysis</span>
          </label>

          <SubmitButton busy={busy} label="Calculate" />
        </form>
        {error && <p className="notice notice--bad">{error}</p>}
      </section>

      <section className="panel panel--note">
        <h2 className="panel__title">Result</h2>
        {!needs && !error && (
          <p className="hint">Enter measurements and calculate.</p>
        )}
        {needs && (
          <dl className="result">
            <dt>BMI</dt>
            <dd>
              {needs.bmi} {needs.bmi_category && `(${needs.bmi_category})`}
            </dd>
            <dt>Ideal body weight</dt>
            <dd>{needs.ideal_weight_lb} lb</dd>
            <dt>Adjusted body weight</dt>
            <dd>{needs.adjusted_weight_lb} lb</dd>
            <dt>Calculated on</dt>
            <dd>
              {needs.weight_basis} — {needs.calculation_weight_lb} lb (
              {needs.calculation_weight_kg} kg)
            </dd>
            <dt>Mifflin</dt>
            <dd>{needs.mifflin_kcal_day} kcal/day</dd>
            <dt>Calories</dt>
            <dd>
              {range(needs.calories_kcal_day, "kcal")}
              <span className="result__factor">
                {range(needs.calorie_factor, "kcal/kg")}
              </span>
            </dd>
            <dt>Protein</dt>
            <dd>
              {range(needs.protein_g_day, "g")}
              <span className="result__factor">
                {range(needs.protein_factor, "g/kg")}
              </span>
            </dd>
            <dt>Fluids</dt>
            <dd>
              {range(needs.fluids_ml_day, "mL")}
              <span className="result__factor">
                {range(needs.fluid_factor, "mL/kg")}
              </span>
            </dd>
          </dl>
        )}
      </section>
    </div>
  );
}

/** Render one formula the way a reviewer would read it off a label. */
function formulaLabel(item: Formula): string {
  const density = item.kcal_per_ml ? ` · ${item.kcal_per_ml} kcal/mL` : "";
  return `${item.name}${density}`;
}

export function TubefeedPage() {
  const [kcalLow, setKcalLow] = useState("1800");
  const [kcalHigh, setKcalHigh] = useState("2000");
  const [formula, setFormula] = useState("");
  const [hours, setHours] = useState("18");
  const [bolus, setBolus] = useState(false);
  const [bolusFeeds, setBolusFeeds] = useState("");
  const [feedingRoute, setFeedingRoute] = useState("PEG");

  const [formulas, setFormulas] = useState<Formula[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [recommendation, setRecommendation] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    listFormulas()
      .then(setFormulas)
      .catch((caught: Error) => setCatalogError(caught.message));
  }, []);

  // The calculator resolves a continuous order against ready-to-hang products
  // and a bolus order against cartons, so offering the whole catalog would let
  // a reviewer pick something that cannot be found. Follow the schedule.
  const packageType = bolus ? "carton" : "ready_to_hang";
  const choices = useMemo(
    () => formulas.filter((item) => item.package_type === packageType),
    [formulas, packageType],
  );

  // Toggling bolus swaps the whole list, so a selection made under the other
  // schedule has to be replaced rather than silently submitted.
  useEffect(() => {
    if (choices.length === 0) return;
    setFormula((current) =>
      choices.some((item) => item.name === current) ? current : choices[0].name,
    );
  }, [choices]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !formula) return;
    setBusy(true);
    setError(null);
    setRecommendation(null);
    setCopied(false);
    try {
      setRecommendation(
        await calculateTubefeed({
          kcalLow: Number(kcalLow),
          kcalHigh: Number(kcalHigh),
          formula,
          hours: hours ? Number(hours) : undefined,
          bolus,
          bolusFeeds: bolusFeeds ? Number(bolusFeeds) : undefined,
          feedingRoute,
        }),
      );
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!recommendation) return;
    await navigator.clipboard.writeText(recommendation);
    setCopied(true);
  }

  return (
    <div className="app__columns">
      <section className="panel">
        <h2 className="panel__title">Tube feeding</h2>
        <form onSubmit={submit}>
          <div className="calcgrid">
            <Field label="kcal low">
              <input
                className="field__input"
                value={kcalLow}
                onChange={(e) => setKcalLow(e.target.value)}
                inputMode="numeric"
              />
            </Field>
            <Field label="kcal high">
              <input
                className="field__input"
                value={kcalHigh}
                onChange={(e) => setKcalHigh(e.target.value)}
                inputMode="numeric"
              />
            </Field>
            <Field
              label={bolus ? "Formula (cartons)" : "Formula (ready-to-hang)"}
              wide
            >
              <select
                className="field__input field__input--formula"
                value={formula}
                onChange={(e) => setFormula(e.target.value)}
                disabled={choices.length === 0}
              >
                {choices.length === 0 && (
                  <option value="">
                    {catalogError ? "Catalog unavailable" : "Loading…"}
                  </option>
                )}
                {choices.map((item) => (
                  <option key={item.name} value={item.name}>
                    {formulaLabel(item)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Route">
              <input
                className="field__input"
                value={feedingRoute}
                onChange={(e) => setFeedingRoute(e.target.value)}
                placeholder="PEG"
              />
            </Field>
            {bolus ? (
              <Field label="Feeds per day">
                <input
                  className="field__input"
                  value={bolusFeeds}
                  onChange={(e) => setBolusFeeds(e.target.value)}
                  inputMode="numeric"
                />
              </Field>
            ) : (
              <Field label="Hours per day">
                <input
                  className="field__input"
                  value={hours}
                  onChange={(e) => setHours(e.target.value)}
                  inputMode="numeric"
                />
              </Field>
            )}
          </div>

          <label className="checkline">
            <input
              type="checkbox"
              checked={bolus}
              onChange={(e) => setBolus(e.target.checked)}
            />
            <span>Bolus feeding</span>
          </label>

          <SubmitButton busy={busy} label="Calculate" disabled={!formula} />
        </form>
        {catalogError && <p className="notice notice--bad">{catalogError}</p>}
        {error && <p className="notice notice--bad">{error}</p>}
      </section>

      <section className="panel panel--note">
        <div className="panel__heading">
          <h2 className="panel__title">Recommendation</h2>
          {recommendation && (
            <button type="button" className="linkbtn" onClick={copy}>
              {copied ? "Copied" : "Copy"}
            </button>
          )}
        </div>
        {!recommendation && !error && (
          <p className="hint">Enter a formula and energy target.</p>
        )}
        {recommendation && <pre className="note">{recommendation}</pre>}
      </section>
    </div>
  );
}
