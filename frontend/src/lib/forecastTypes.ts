// Mirrors the JSON shapes returned by api/routes_forecast*.py. Kept separate
// from lib/types.ts -- forecasting's shapes share no fields with
// KpiBundle/FilterState/TableResponse, same split as lib/filterParams.ts.

export interface ForecastMeta {
  horizon_choices: number[];
  default_horizon: number;
  primary_model_roster: string[];
  product_vendor_model_roster: string[];
  product_forecast_levels: string[];
  top_n_products_default: number;
  top_n_vendors_default: number;
  top_n_promo_campaigns_default: number;
  min_history_days: number;
  time_slot_order: string[];
  active_stores: string[];
  store_names: Record<string, string>;
}

export interface ForecastStatus {
  computed: boolean;
  series_id?: string;
  label?: string;
  horizon?: number;
  insufficient_history?: boolean;
  best_model?: string | null;
  model_set?: string[];
}

export interface ForecastEntityStatus {
  name: string;
  insufficient_history: boolean;
  best_model: string | null;
}

export interface BundlesStatus {
  computed: boolean;
  entity_count?: number;
  entities?: ForecastEntityStatus[];
}

export interface GrowthGoal {
  computed: boolean;
  default_target_total?: number;
  target_total?: number;
  current_avg_daily?: number | null;
  required_avg_daily?: number | null;
  uplift_pct?: number | null;
  achievable_at_current_pace?: boolean;
}

export interface ForecastModelSummary {
  series: string;
  best_model: string | null;
  backtest_mape: number | null;
}

export interface ForecastOverview {
  sales_computed: boolean;
  footfall_computed: boolean;
  horizon?: number;
  flat_continuation?: number;
  model_forecast_total?: number;
  confidence_lower?: number;
  confidence_upper?: number;
  delta_vs_flat?: number;
  model_selection_summary?: ForecastModelSummary[];
}

export interface NextDayTarget {
  date: string;
  point: number;
  lower: number;
  upper: number;
}

export interface HuddleEngagement {
  window_days: number;
  conversion_pct: number | null;
  conversion_pct_delta: number | null;
  footfall: number | null;
  footfall_delta: number | null;
}

export interface PerformerPair {
  rank: number;
  category: string;
  strong_item_code: string;
  strong_product: string | null;
  weak_item_code: string;
  weak_product: string | null;
  gap_pct: number;
  [key: string]: unknown; // strong_/weak_/gap_ measure column, name varies with the measure
}

export interface DailyHuddle {
  computed: boolean;
  next_day_target?: NextDayTarget;
  configured_daily_target?: number | null;
  engagement?: HuddleEngagement | null;
  upsell_cross_sell?: PerformerPair[];
}

export type ForecastKind = "sales" | "footfall" | "products" | "vendors";

/** A ForecastStatus (sales/footfall) or BundlesStatus (products/vendors) --
 * callers narrow via "entities" in status vs not, matching bundle_status()/
 * bundles_status()'s two distinct shapes in api/forecast_support.py. */
export type AnyForecastStatus = ForecastStatus | BundlesStatus;
