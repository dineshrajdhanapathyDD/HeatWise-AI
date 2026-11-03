// IMD actual-maximum criteria as published by WHO India (backend source who_india_heat_waves).
// HeatWise shows them as an indication for one forecast point, never as an official declaration.
// Mirrors backend/services/risk_rules.py imd_indication: applied on plains (or unknown terrain,
// assumed plains) only. Hilly and coastal criteria need departure-from-normal data HeatWise does not have.

export const IMD_PLAINS_C = 40;
export const IMD_HEAT_WAVE_C = 45;
export const IMD_SEVERE_C = 47;

type Terrain = string | null | undefined;

/** False for hilly and coastal terrain, where the backend rules do not apply the IMD actual-maximum rule. */
export function imdApplies(terrain: Terrain): boolean {
  return terrain !== "hilly" && terrain !== "coastal";
}

/** Shown instead of IMD levels when the rule is not applied for this terrain. */
export function imdNotAppliedText(terrain: Terrain): string {
  return `IMD actual-maximum rule not applied for ${terrain ?? "this"} terrain`;
}

/** IMD level words for one daily maximum, or null when there is no value or the rule is not applied. */
export function imdLevel(maxC: number | null, terrain: Terrain): string | null {
  if (maxC === null || !imdApplies(terrain)) return null;
  if (maxC >= IMD_SEVERE_C) return `Severe heat wave level (${IMD_SEVERE_C} °C)`;
  if (maxC >= IMD_HEAT_WAVE_C) return `Heat wave level (${IMD_HEAT_WAVE_C} °C)`;
  if (maxC >= IMD_PLAINS_C) return `Above the ${IMD_PLAINS_C} °C threshold`;
  return `Below the ${IMD_PLAINS_C} °C threshold`;
}

const INDICATION_TEXT: Record<string, string> = {
  none: "Below the IMD criteria",
  threshold_met: "IMD minimum threshold met",
  heat_wave: "IMD heat wave criterion met",
  severe_heat_wave: "IMD severe heat wave criterion met",
};

export function imdIndicationText(indication: string | null | undefined): string | null {
  return indication ? (INDICATION_TEXT[indication] ?? indication) : null;
}
