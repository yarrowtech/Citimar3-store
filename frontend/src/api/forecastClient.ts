import { authHeaders, handleUnauthorized } from "@/auth/tokenStore";
import { apiUrl } from "@/lib/apiBase";
import type { PlotlyChartFigure, TableResponse } from "@/lib/types";
import type {
  AnyForecastStatus,
  DailyHuddle,
  ForecastKind,
  ForecastMeta,
  ForecastOverview,
  ForecastStatus,
  GrowthGoal,
} from "@/lib/forecastTypes";

type Params = Record<string, string | number | undefined>;

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(apiUrl(url), { headers: { ...authHeaders() } });
  if (!res.ok) {
    if (res.status === 401) handleUnauthorized();
    throw new Error(`${url} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function qs(params: Params): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") sp.set(k, String(v));
  }
  return sp.toString();
}

export const forecastApi = {
  meta: () => getJSON<ForecastMeta>("/api/forecast/meta"),

  status: <T extends AnyForecastStatus = ForecastStatus>(kind: ForecastKind, p: Params) => getJSON<T>(`/api/forecast/${kind}/status?${qs(p)}`),

  compute: <T extends AnyForecastStatus = ForecastStatus>(kind: ForecastKind, p: Params) => getJSON<T>(`/api/forecast/${kind}/compute?${qs(p)}`),

  growthGoal: (p: Params) => getJSON<GrowthGoal>(`/api/forecast/sales/growth-goal?${qs(p)}`),

  overview: (p: Params) => getJSON<ForecastOverview>(`/api/forecast/overview?${qs(p)}`),

  huddle: (p: Params) => getJSON<DailyHuddle>(`/api/forecast/huddle?${qs(p)}`),

  forecastChart: (chartId: string, p: Params) => getJSON<PlotlyChartFigure>(`/api/forecast-charts/${chartId}?${qs(p)}`),

  forecastTable: (tableId: string, p: Params) => getJSON<TableResponse>(`/api/forecast-tables/${tableId}?${qs(p)}`),

  forecastTableCsvUrl: (tableId: string, p: Params) => apiUrl(`/api/forecast-tables/${tableId}?${qs({ ...p, format: "csv" })}`),
};
