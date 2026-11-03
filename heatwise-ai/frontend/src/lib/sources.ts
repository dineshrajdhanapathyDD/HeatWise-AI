// Mirror of backend/guidance/sources.py TRUSTED_SOURCES (ids, titles, publishers, urls).

export interface TrustedSource {
  id: string;
  title: string;
  publisher: string;
  url: string;
}

const SOURCES: TrustedSource[] = [
  {
    id: "nws_heat_index",
    title: "What is the heat index?",
    publisher: "US National Weather Service (NWS Amarillo)",
    url: "https://www.weather.gov/ama/heatindex",
  },
  {
    id: "wpc_heat_index_equation",
    title: "The Heat Index Equation",
    publisher: "NOAA Weather Prediction Center",
    url: "https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml",
  },
  {
    id: "who_india_heat_waves",
    title: "Heat waves (WHO India)",
    publisher: "World Health Organization, Country Office for India",
    url: "https://www.who.int/india/heat-waves",
  },
  {
    id: "who_heat_health_factsheet",
    title: "Climate change, heat and health (fact sheet)",
    publisher: "World Health Organization",
    url: "https://www.who.int/news-room/fact-sheets/detail/climate-change-heat-and-health",
  },
  {
    id: "ready_gov_extreme_heat",
    title: "Extreme Heat",
    publisher: "Ready.gov (US Department of Homeland Security / FEMA)",
    url: "https://www.ready.gov/heat",
  },
  {
    id: "nws_heat_safety",
    title: "Heat Safety Tips and Resources",
    publisher: "US National Weather Service",
    url: "https://www.weather.gov/safety/heat",
  },
  {
    id: "who_workplace_heat_stress",
    title: "Workplace heat stress (questions and answers)",
    publisher: "World Health Organization",
    url: "https://www.who.int/news-room/questions-and-answers/item/workplace-heat-stress",
  },
  {
    id: "fao_extreme_heat_agrifood",
    title: "Extreme heat in an El Niño year: how agrifood systems can prepare",
    publisher: "Food and Agriculture Organization of the United Nations",
    url: "https://www.fao.org/climate-change/news/news-detail/extreme-heat-in-an-el-ni%C3%B1o-year--how-agrifood-systems-can-prepare/en",
  },
  {
    id: "wsu_livestock_heat_wave",
    title: "Protect livestock, pets during summer heat wave",
    publisher: "Washington State University Extension (WSU Insider)",
    url: "https://news.wsu.edu/news/2022/07/28/protect-livestock-pets-during-summer-heat-wave/",
  },
];

export const TRUSTED_SOURCES: Record<string, TrustedSource> = Object.fromEntries(SOURCES.map((s) => [s.id, s]));

export function sourceFor(id: string): TrustedSource | null {
  return TRUSTED_SOURCES[id] ?? null;
}
