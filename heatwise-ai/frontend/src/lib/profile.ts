import type { AssessmentRequest, ProfileInput } from "../api/types";

// Assessment form state and its mapping onto the API request (design decision D-M3-5).
// Only fields the backend accepts are sent: place, forecast_days and CommunityProfile fields.

export const POPULATION_GROUPS = [
  { key: "elderly", label: "Older people" },
  { key: "young_children", label: "Young children" },
  { key: "pregnant_women", label: "Pregnant women" },
  { key: "chronic_illness_group", label: "People living with chronic illness" },
  { key: "outdoor_workers", label: "People who work outdoors" },
  { key: "farmers", label: "Farming households" },
] as const;

export type PopulationGroup = (typeof POPULATION_GROUPS)[number]["key"];
export type Access = "adequate" | "limited";
export type TerrainChoice = "plains" | "hilly" | "coastal" | "not_sure";

export const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "mr", label: "Marathi" },
  { code: "bn", label: "Bengali" },
  { code: "ta", label: "Tamil" },
  { code: "te", label: "Telugu" },
  { code: "gu", label: "Gujarati" },
] as const;

export const MAX_PLACE_LENGTH = 120;

export interface FormState {
  name: string;
  district: string;
  state: string;
  demoLocation: string;
  groups: Record<PopulationGroup, boolean>;
  water: Access;
  shade: Access;
  terrain: TerrainChoice;
  language: string;
  forecastDays: number;
}

export function initialFormState(demoLocation = ""): FormState {
  return {
    name: "",
    district: "",
    state: "",
    demoLocation,
    groups: {
      elderly: false,
      young_children: false,
      pregnant_women: false,
      chronic_illness_group: false,
      outdoor_workers: false,
      farmers: false,
    },
    water: "adequate",
    shade: "adequate",
    terrain: "not_sure",
    language: "en",
    forecastDays: 3,
  };
}

/** The request body for POST /api/assessments. In demo mode the place is the chosen demo key. */
export function toRequestBody(form: FormState, demoMode: boolean): AssessmentRequest {
  const profile: ProfileInput = {
    ...form.groups,
    limited_water_access: form.water === "limited",
    limited_shade_or_cooling: form.shade === "limited",
    terrain: form.terrain === "not_sure" ? null : form.terrain,
    preferred_language: form.language,
  };
  const place = demoMode
    ? { name: form.demoLocation }
    : {
        name: form.name.trim(),
        district: form.district.trim() || null,
        state: form.state.trim() || null,
      };
  return { place, forecast_days: form.forecastDays, profile };
}

export type FieldKey = "name" | "district" | "state" | "demoLocation" | "forecastDays" | "language";

/** Client checks that mirror the backend: a place name is required and each part is at most 120 characters. */
export function validateForm(form: FormState, demoMode: boolean): Partial<Record<FieldKey, string>> {
  const errors: Partial<Record<FieldKey, string>> = {};
  if (demoMode) {
    if (!form.demoLocation) errors.demoLocation = "Choose a demo location.";
    return errors;
  }
  if (!form.name.trim()) errors.name = "Enter the city, town or village.";
  else if (form.name.trim().length > MAX_PLACE_LENGTH) errors.name = `Use at most ${MAX_PLACE_LENGTH} characters.`;
  if (form.district.trim().length > MAX_PLACE_LENGTH) errors.district = `Use at most ${MAX_PLACE_LENGTH} characters.`;
  if (form.state.trim().length > MAX_PLACE_LENGTH) errors.state = `Use at most ${MAX_PLACE_LENGTH} characters.`;
  return errors;
}

/** Maps a server 422 field path ("place.name", "forecast_days", ...) onto a form field. */
export function fieldForServerPath(path: string, demoMode: boolean): FieldKey | null {
  if (path === "place.name" || path === "place") return demoMode ? "demoLocation" : "name";
  if (path === "place.district") return "district";
  if (path === "place.state") return "state";
  if (path === "forecast_days") return "forecastDays";
  if (path === "profile.preferred_language") return "language";
  return null;
}
