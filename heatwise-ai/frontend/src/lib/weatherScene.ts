import type { CurrentConditions } from "../api/types";

/**
 * Which visual treatment the weather hero uses. It is derived only from values the backend returned:
 * precipitation, air temperature and the rules' heat index. Open-Meteo cloud cover is not requested by the
 * backend, so there is no "cloudy" or "clear sky" scene; the visual never claims a sky condition.
 */
export type WeatherScene = "extreme-heat" | "hot" | "warm" | "mild" | "rain" | "none";

export const SCENE_TEXT: Record<WeatherScene, string> = {
  "extreme-heat": "Extreme heat",
  hot: "Hot",
  warm: "Warm",
  mild: "Mild",
  rain: "Precipitation reported",
  none: "No weather data",
};

export function sceneFor(current: CurrentConditions | null | undefined, heatIndexC: number | null | undefined): WeatherScene {
  if (!current) return "none";
  const temp = current.temperature_c;
  const felt = Math.max(temp ?? -Infinity, heatIndexC ?? -Infinity, current.apparent_temperature_c ?? -Infinity);
  if ((current.precipitation_mm ?? 0) > 0) return "rain";
  if (!Number.isFinite(felt)) return "none";
  if (felt >= 40) return "extreme-heat";
  if (felt >= 33) return "hot";
  if (felt >= 26) return "warm";
  return "mild";
}

/** One line saying what the visual is based on, shown under the hero. */
export function sceneBasis(scene: WeatherScene): string {
  if (scene === "none") return "No weather values are available for this visual.";
  if (scene === "rain") return "Visual based on the precipitation the provider reported.";
  return "Visual based on temperature, feels-like and heat index. The data has no cloud-cover field.";
}
