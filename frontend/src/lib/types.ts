// Mirrors the dataclasses in src/kpi_engine.py, src/data_validator.py, and the
// JSON shapes returned by api/routes_*.py. Keep in sync with the backend --
// these are hand-written, not code-generated.

export type StatusColor = "red" | "yellow" | "green";

export interface KpiBundle {
  net_sales: number | null;
  gross_sales: number | null;
  gross_sales_is_derived: boolean;
  discounts: number | null;
  net_profit: number | null;
  gross_profit: number | null;
  bill_quantity: number | null;
  footfall: number | null;
  nob: number | null;
  nob_transaction_count: number | null;
  atv: number | null;
  rpv: number | null;
  basket_size: number | null;
  conversion_pct: number | null;
  sales_target: number | null;
  achievement_pct: number | null;
  remaining: number | null;
  remaining_pct: number | null;
  returned_units: number | null;
  returned_value: number | null;
}

export type KpiKey = keyof KpiBundle;

/** Every KPI field except the one boolean flag -- the numeric/displayable subset. */
export type NumericKpiKey = Exclude<KpiKey, "gross_sales_is_derived">;

export interface KpiDelta {
  kpi: string;
  current: number | null;
  previous: number | null;
  absolute_variance: number | null;
  percentage_variance: number | null;
  status: StatusColor;
}

export interface KpisResponse {
  kpis: KpiBundle;
  statuses: Partial<Record<KpiKey, StatusColor>>;
  comparisons: {
    previous_period?: Partial<Record<KpiKey, KpiDelta>>;
    previous_month?: Partial<Record<KpiKey, KpiDelta>>;
    same_period_last_year?: Partial<Record<KpiKey, KpiDelta>>;
  };
}

// Order matters: mirrors src/filter_engine.py's FILTER_HIERARCHY exactly --
// each field's options are cascaded off every field before it.
export const FILTER_HIERARCHY = [
  "division",
  "section",
  "department",
  "product_design_no",
  "product_style",
  "product_type",
  "product_size",
  "vendors",
] as const;

export type FilterHierarchyField = (typeof FILTER_HIERARCHY)[number];

export interface FilterState {
  stores: string[];
  start: string;
  end: string;
  time_slot: string[];
  division: string[];
  section: string[];
  department: string[];
  product_design_no: string[];
  product_style: string[];
  product_type: string[];
  product_size: string[];
  vendors: string[];
}

export type FilterOptions = Record<FilterHierarchyField, string[]> & {
  section_widget: "checkbox" | "searchable_multiselect";
};

export interface FilterDefaults extends Record<FilterHierarchyField, string[]> {
  stores: string[];
  store_names: Record<string, string>;
  start_date: string | null;
  end_date: string | null;
  time_slot_options: string[];
}

export interface TableResponse {
  table_id: string;
  columns: string[];
  rows: Record<string, unknown>[];
}

// Plotly figure JSON as returned by /api/charts/{chart_id} (src/charts.py's
// _fig_to_dict). Typed loosely -- Plotly's own types are supplied at the
// react-plotly.js call site.
export interface PlotlyChartFigure {
  data: unknown[];
  layout: Record<string, unknown>;
}

// The other shape /api/charts/{chart_id} can return: a plain gauge
// description (src/charts.py's gauge_spec()) for the 4 *_gauge chart ids,
// rendered by components/GlossyGauge.tsx -- not a Plotly figure, since
// Plotly's Indicator can't draw a true needle. `value: null` means N/A (the
// source KPI wasn't computable), in which case every other field is absent.
export interface GaugeSpec {
  kind: "gauge";
  title: string;
  value: number | null;
  target?: number | null;
  min?: number;
  max?: number;
  redBelow?: number;
  greenAt?: number;
  reverse?: boolean;
  suffix?: string;
  prefix?: string;
}

export type ChartFigure = PlotlyChartFigure | GaugeSpec;

// GET/PUT/DELETE /api/kpi-thresholds (admin-only). A band is {red_below,
// green_at_or_above} for every KPI except achievement, which uses
// {red_below, green_above} (strict '>' per the business spec).
export type ThresholdKpi = "atv" | "rpv" | "conversion" | "achievement" | "basket_size";
export type ThresholdBand = Record<string, number>;

export interface KpiThresholdsResponse {
  defaults: Record<ThresholdKpi, ThresholdBand>;
  overrides: Partial<Record<ThresholdKpi, ThresholdBand>>;
  effective: Record<ThresholdKpi, ThresholdBand>;
}

export interface DataQualityProfile {
  worksheets_loaded: string[];
  worksheets_skipped: string[];
  total_rows_before_cleaning: number;
  rows_retained_after_cleaning: number;
  date_range: [string, string] | null;
  missing_date_count: number;
  missing_product_count: number;
  missing_department_count: number;
  invalid_sales_count: number;
  duplicate_transaction_count: number;
  zero_amount_duplicate_flagged_count: number;
  negative_sales_or_return_count: number;
  missing_cost_count: number;
  missing_target_count: number;
  missing_footfall_count: number;
  unmatched_dates_target_only: string[];
  unmatched_dates_footfall_only: string[];
  unmatched_dates_fact_only: string[];
  product_hierarchy_values_nulled: Record<string, number>;
  tax_rate_outlier_rows: number;
  categorical_numeric_contamination: Record<string, number>;
  unmapped_store_rows: number;
  unresolved_columns_by_sheet: Record<string, string[]>;
  kpi_availability: Record<string, boolean>;
}

export interface WeatherReading {
  condition: string;
  temp_max_c: number | null;
  temp_min_c: number | null;
  precipitation_mm: number | null;
}

// Mirrors src/daily_dashboard_store.py's compute_live_kpis dict shape.
export interface DailyKpis {
  sales_target: number | null;
  net_sales: number | null;
  bill_quantity: number | null;
  remaining: number | null;
  remaining_pct: number | null;
  footfall: number | null;
  nob: number | null;
  atv: number | null;
  rpv: number | null;
  basket_size: number | null;
  conversion_pct: number | null;
  achievement_pct: number | null;
}

export type DailyKpiKey = keyof DailyKpis;

// One row of the previous-year same-day comparison matrix (src/daily_context.py's
// previous_year_same_day). `kpi` is a DailyKpiKey so the UI reuses
// DAILY_KPI_LABELS / DAILY_KPI_FORMATTERS rather than carrying its own labels.
export interface PrevYearKpiRow {
  kpi: DailyKpiKey;
  current: number | null;
  previous: number | null;
  variance_pct: number | null;
}

export interface PreviousYearComparison {
  date: string; // the prior-year ISO date these figures are for
  rows: PrevYearKpiRow[];
}

// GET /api/daily/live -- one store's live KPI snapshot (MongoDB, via
// src/daily_dashboard_store.py) plus same-day weather/holiday/election/
// day-type/previous-year context (src/daily_context.py).
export interface DailyLiveSnapshot {
  store: string;
  date: string;
  day_name: string;
  is_weekend: boolean;
  day_type: string; // "Weekend" (Sat/Sun) | "Mid-Week" (Wed/Thu) | "Regular"
  holiday_name: string | null;
  election_name: string | null;
  weather: WeatherReading | null;
  // Same calendar day one year ago, from DATASET.xlsx; null when the workbook
  // has no prior-year rows for this store (rendered as "No historical data found").
  previous_year: PreviousYearComparison | null;
  kpis: DailyKpis;
  statuses: Partial<Record<DailyKpiKey, StatusColor>>;
  // Which of the five overridable ratio KPIs currently carry a manager's
  // hand-entered value (targets.overrides) rather than the computed figure.
  overridden: DailyKpiKey[];
  reason: string | null;
}

// GET /api/daily/live/overall -- blended live Daily KPIs across all three
// stores (raw totals summed, ratios recomputed) plus each store's own
// bundle. Admin-only.
export interface DailyOverallSnapshot {
  store: "ALL";
  date: string;
  kpis: DailyKpis;
  statuses: Partial<Record<DailyKpiKey, StatusColor>>;
  per_store: Record<string, DailyKpis>;
}

// The five ratio KPIs a manager can override at runtime on the Daily
// Dashboard -- must match src/daily_dashboard_store.OVERRIDABLE_KPIS.
export const OVERRIDABLE_DAILY_KPIS = ["atv", "rpv", "basket_size", "conversion_pct", "achievement_pct"] as const;
export type OverridableDailyKpi = (typeof OVERRIDABLE_DAILY_KPIS)[number];

// PUT/DELETE /api/daily/kpi-override response.
export interface KpiOverrideResult {
  store: string;
  date: string;
  kpis: DailyKpis;
  overridden: DailyKpiKey[];
}

// Admin-only "Sales Targets" page (GET/PUT/DELETE /api/targets,
// POST /api/targets/bulk). One entry per store+date; sales_target is the
// admin-set figure the Daily Dashboard's Remaining / Achievement % KPIs are
// measured against. net_sales / achievement_pct are the latest snapshot
// alongside it (null until the store logs sales), shown for target-vs-actual.
export interface StoreTargetEntry {
  date: string;
  sales_target: number | null;
  net_sales: number | null;
  achievement_pct: number | null;
}

export interface StoreTargetsResponse {
  store: string;
  entries: StoreTargetEntry[];
}

// Manual Daily Entry page -- backed by TEST_DAILY_DASHBOARD.xlsx via
// src/daily_dashboard_store.py, not DATASET.xlsx.
// time_slot is system-generated server-side (config.settings.time_slot_for_time,
// applied to bill_time/time at save) -- never user-editable, and null when
// the entry's time falls outside all 4 TIME_SLOT_ORDER bands (before 11 AM).
export interface BillEntry {
  row: number;
  date: string;
  bill_time: string | null;
  net_amount: number | null;
  bill_quantity: number | null;
  time_slot: string | null;
}

export interface BillLogResponse {
  store: string;
  date: string;
  entries: BillEntry[];
}

// Footfall and NOB are each their own separate, time-wise log -- structurally
// identical to BillEntry/BillLogResponse but with a single value column.
// Neither is derived from the other or from Bill Quantity; the KPI cards'
// Footfall/NOB figures are the live SUM of each log's entries for the day.
export interface FootfallEntry {
  row: number;
  date: string;
  time: string | null;
  footfall: number | null;
  time_slot: string | null;
}

export interface FootfallLogResponse {
  store: string;
  date: string;
  entries: FootfallEntry[];
}

export interface NobEntry {
  row: number;
  date: string;
  time: string | null;
  nob: number | null;
  time_slot: string | null;
}

export interface NobLogResponse {
  store: string;
  date: string;
  entries: NobEntry[];
}

// reason is optional -- omitted (or null) leaves that value as whatever was
// last saved. Net Sales/Bill Quantity/Footfall/NOB are never part of this
// payload -- they're always live sums of their own logs (see BillEntry/
// FootfallEntry/NobEntry).
export interface SaveEntryPayload {
  store: string;
  date: string;
  reason?: string | null;
}

export interface SaveEntryResult extends DailyKpis {
  store: string;
  date: string;
  reason: string | null;
}
