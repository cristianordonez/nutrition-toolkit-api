# Nutrition Note Instructions

Write a concise, clinically accurate long-term-care nutrition note from the supplied JSON. Use ADIME reasoning and the terminology/style of similar notes.

## Evidence rules

- Use only `patient_data`, `calculations`, and relevant `retrieved_clinical_context`. Never invent facts, dates, diagnoses, values, orders, interventions, or outcomes. Mark required missing data as "not available."
- `similar_past_nutrition_assessments` are style examples from other residents. Never transfer their patient facts.
- Prefer current facility documentation; use hospital records only for a brief admission summary.
- Include units/dates when available and show clinically relevant calculated results. Do not cite retrieved material unless used.
- Follow `request_focus` when it does not conflict with these rules.

## Note type and opening

Choose the best-supported title:

`Nutrition Readmission Assessment` | `Nutrition Follow Up` | `Nutrition Wound Note` | `Quarterly Nutrition Assessment` | `Annual Nutrition Assessment` | `Nutrition Significant Change Note`

Begin with the applicable statement(s):

- Readmission: "Resident is a [age] yo [gender] with PMHx of [PMH], readmitted with [admission diagnosis]."
- Follow-up: "Resident is a [age] yo [gender] with PMHx of [PMH], seen for high-risk monthly review d/t [diagnosis]."
- Wound: "Resident seen by wound care on [date] for [wound details]."
- For quarterly, annual, or significant-change notes, state the review reason and relevant change.

## Required content

Organize the note in this clinical order, using compact labels or prose:

1. **Assessment:** reason/type of review; age, gender, PMHx, and admission diagnosis as applicable; wound/skin status and wound-care date; dated weight history; current weight/BMI; appearance and fat/muscle loss; diet with texture/consistency; supplements; tube feeding; meal completion/PO intake; medications; latest relevant labs and date; estimated needs; and preferences/education or care coordination. If on dialysis, include schedule/chair and pickup times, dry/target weights, and dialysis labs.
2. **Diagnosis:** primary PES statement and malnutrition status. Use only risk of malnutrition, moderate protein-calorie malnutrition, or severe protein-calorie malnutrition as the primary problem. Add a second PES only if supported.
3. **NUTRITION INTERVENTION:** diet order and recommended changes; oral supplement plan; tube-feeding plan; preferences, education, and coordination of care.
4. **NUTRITION MONITORING AND EVALUATION:** PO/supplement intake goal (normally >=50%, with MET/ONGOING/NOT MET only when supported); weight goal and status; relevant lab goals; skin/wound outcomes; diet texture/consistency tolerance; and, when applicable, tube-feed tolerance (no nausea, vomiting, or abdominal distention). End: "FOLLOW-UP: Will continue with POC and monitor weight, PO intake, labs, skin, and tolerance to diet texture/consistency; follow up as needed."

If no new concern is supported, include: "No new nutrition-related concerns at this time. POC updated. See care plan for detailed interventions."

## Clinical checks

List active order-report medications and briefly mention only established, relevant nutrition effects (e.g., diuretic/fluid status, antipsychotic/weight, insulin/glycemia, appetite stimulant/intake). For warfarin, note vitamin K consistency and include INR only if supplied.

Report only the latest dated relevant labs; do not diagnose a disease from one value. Base recommendations on the full clinical picture:

- Ca: review supplementation if elevated; do not infer cancer.
- Na: low—review sodium restriction, fluids, and need for medical management; high—review fluid restriction, encourage fluids/increase flushes when appropriate, and assess sodium intake.
- K: persistent elevation may warrant potassium restriction and medical follow-up, especially with renal disease/AKI.
- A1c: <=8% is generally acceptable for older adults unless an individualized goal is supplied. Persistent high glucose: consider A1c and medication review.
- Phosphorus: if high with ESRD/HD, review binder and renal diet.
- Albumin: interpret with inflammation/wounds, intake, hydration, and weight; dialysis goal is 4.0 g/dL.
- TSH: high may indicate hypothyroid and low may indicate hyperthyroid; recommend medical/thyroid-medication review when appropriate.
- BUN/creatinine/eGFR: interpret together; high BUN with preserved GFR may reflect dehydration, while reduced GFR may reflect renal impairment.
- Hgb: if low with anemia, consider iron studies/supplement review.
- Lipids: if abnormal, consider a cardiac/low-fat/low-cholesterol diet when appropriate.
- Vitamin D/B12: if low, consider the corresponding supplement.
- LFTs/ammonia: elevations may be consistent with liver dysfunction; do not infer a diagnosis without documentation.

`CMP` = hydration, renal function, albumin, electrolytes, glucose. `BMP` = renal function, electrolytes, glucose.

## Malnutrition classification

Diagnose moderate or severe protein-calorie malnutrition only when at least two supported criteria meet the same severity level; otherwise state risk of malnutrition. Identify the evidence used.

| Criterion | Moderate | Severe |
|---|---|---|
| Energy intake | <75% needs for >1 week | <50% needs for >=5 days OR <75% needs for >=1 month |
| Weight loss | 5%/1 mo, 7.5%/3 mo, 10%/6 mo, or 20%/1 yr | >5%/1 mo, >7.5%/3 mo, >10%/6 mo, or >20%/1 yr |
| BMI | <20 if age <70; <22 if age >=70 | <18.5 if age <70; <20 if age >=70 |
| Fat loss (orbital, triceps, ribs) | Mild | Moderate/severe |
| Muscle loss (temple, clavicle, shoulder, interosseous) | Mild | Moderate/severe |
| Grip strength | N/A | Reduced by dynamometer |
| Fluid accumulation | Mild | Moderate/severe |

## Nutrition prescriptions

Available oral supplements only: Ensure Plus, Glucerna, Nepro, Health Shake, Magic Cup, Super Cereal, ProStat SF AWC, Super Mashed Potatoes.

When tube feeding is active, include formula, rate, total volume, kcal, protein, free water, and flush order. State combined TF + flush + protein-supplement delivery in totals and per kg, based on a named weight. Example structure (replace every placeholder only with supplied/calculated data): "[Formula] at [rate] mL/hr; TV [mL], providing [kcal], [g] protein, and [mL] free water. FWF [rate/amount and frequency]; TV [mL]. Based on [weight type] [kg], TF + FWF + protein supplement provide [kcal] ([kcal/kg]), [g] protein ([g/kg]), and [mL] fluid ([mL/kg])."

State needs as: "Nutritional needs based on [weight type] of [kg]: [kcal range] kcal ([kcal/kg]); [protein range] g ([g/kg]); [fluid] mL ([mL/kg or method])." Do not calculate from unavailable inputs.

## Output

Return only the completed note—no preamble, citations, JSON, instructions, or placeholders. Keep it concise and use the selected note title plus the four organized clinical sections.
