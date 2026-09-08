// Declares, per Historical Analytics tab, exactly which blocks its report
// contains -- the single source of truth for "what a tab's report is made
// of" (see src/reports/models.py's module docstring on the backend side of
// this same design). Deliberately NOT derived by reverse-engineering each
// page's JSX -- these chart_id/table_id lists are copied from
// frontend/src/pages/{ExecutiveOverview,SalesPerformance,CustomerConversion,
// ProductBrand,ProfitPromotions,DetailedTables}.tsx's own <ChartPanel>/
// <DataTable> usage, so keep this in sync if a page's charts/tables change.
//
// The Forecast tab isn't included here yet -- unlike these 7 tabs, it isn't
// driven by the shared FilterState alone (8 sub-tabs, each with its own
// store/horizon/model-roster state and gated compute), so "whatever's
// currently active" doesn't reduce to a static per-tab array the same way.
// That's a real follow-up, not an oversight.
import type { HistoricalTabId } from "@/App";

export type ReportManifestItem =
  | { kind: "kpi_grid" }
  | { kind: "chart"; chartId: string; title: string; extra?: Record<string, string | number | undefined> }
  | { kind: "table"; tableId: string; title: string; extra?: Record<string, string | number | undefined> }
  | { kind: "data_quality" };

export const REPORT_MANIFESTS: Record<HistoricalTabId, ReportManifestItem[]> = {
  overview: [
    { kind: "kpi_grid" },
    { kind: "chart", chartId: "sales_overview", title: "Sales Overview", extra: { granularity: "month" } },
    { kind: "table", tableId: "sales_overview", title: "Sales Overview", extra: { granularity: "month" } },
  ],
  sales: [
    { kind: "chart", chartId: "sales_trend", title: "Sales Trend", extra: { dimension: "period", granularity: "day" } },
    { kind: "table", tableId: "sales_trend", title: "Sales Trend", extra: { dimension: "period", granularity: "day" } },
    { kind: "chart", chartId: "avg_sales", title: "Average Sales", extra: { granularity: "day" } },
    { kind: "table", tableId: "avg_sales", title: "Average Sales", extra: { granularity: "day" } },
    { kind: "chart", chartId: "period_comparison", title: "Period Comparison", extra: { dimension: "monthly_same_day" } },
    { kind: "table", tableId: "period_comparison", title: "Period Comparison", extra: { dimension: "monthly_same_day" } },
    { kind: "chart", chartId: "atv_gauge", title: "ATV" },
    { kind: "chart", chartId: "rpv_gauge", title: "RPV" },
    { kind: "chart", chartId: "basket_size_gauge", title: "Basket Size" },
    { kind: "chart", chartId: "achievement_gauge", title: "Target Achievement %" },
    { kind: "chart", chartId: "remaining_pct_gauge", title: "Remaining %" },
    { kind: "table", tableId: "secondary_gauge_values", title: "Secondary KPI Values" },
  ],
  conversion: [
    { kind: "chart", chartId: "footfall_vs_nob", title: "Footfall vs NOB & Conversion %", extra: { dimension: "date" } },
    { kind: "table", tableId: "footfall_vs_nob", title: "Footfall vs NOB & Conversion %", extra: { dimension: "date" } },
    { kind: "chart", chartId: "customer_footfall_net", title: "Footfall vs Net Sales", extra: { dimension: "date" } },
    { kind: "table", tableId: "customer_footfall_net", title: "Footfall vs Net Sales", extra: { dimension: "date" } },
    { kind: "chart", chartId: "customer_nob_net", title: "NOB vs Net Sales", extra: { dimension: "date" } },
    { kind: "table", tableId: "customer_nob_net", title: "NOB vs Net Sales", extra: { dimension: "date" } },
    { kind: "chart", chartId: "footfall_nob_breakdown", title: "Footfall vs NOB by Day of Week", extra: { dimension: "dayofweek" } },
    { kind: "table", tableId: "footfall_nob_breakdown", title: "Footfall vs NOB by Day of Week", extra: { dimension: "dayofweek" } },
    { kind: "chart", chartId: "conversion_gauge", title: "Conversion %" },
    { kind: "chart", chartId: "funnel", title: "Conversion Funnel", extra: { dimension: "date" } },
    { kind: "table", tableId: "conversion_funnel", title: "Conversion Funnel", extra: { dimension: "date" } },
  ],
  product: [
    // The live Top <category> section is category/measure-switchable; the
    // report pins the Division / Net Sales default (same pattern as the
    // other tabs' pinned dimension defaults).
    { kind: "chart", chartId: "category_drilldown", title: "Category Drill-Down (Division → Section → Department)" },
    { kind: "table", tableId: "category_drilldown", title: "Category Drill-Down (Division / Section / Department)" },
    { kind: "chart", chartId: "top_category", title: "Top Division by Net Sales", extra: { category: "division", measure: "net_amount", top_n: 10 } },
    { kind: "table", tableId: "top_category", title: "Top Division by Net Sales", extra: { category: "division", measure: "net_amount", top_n: 10 } },
    { kind: "chart", chartId: "performer_pairing", title: "Performer Pairing (Strong vs Weak) by Department", extra: { top_n: 10 } },
    { kind: "table", tableId: "performer_pairing", title: "Performer Pairing (Strong vs Weak) by Department", extra: { top_n: 10 } },
  ],
  profit: [
    { kind: "chart", chartId: "discount_impact", title: "Discounted vs Non-Discounted Sales", extra: { granularity: "month" } },
    { kind: "table", tableId: "discount_impact", title: "Discounted vs Non-Discounted Sales", extra: { granularity: "month" } },
    { kind: "chart", chartId: "promotion_breakdown", title: "Promotion Breakdown" },
    { kind: "table", tableId: "promotion_breakdown", title: "Promotion Breakdown" },
  ],
  detailed: [
    { kind: "table", tableId: "store_scorecard", title: "Store Scorecard" },
    { kind: "table", tableId: "top_products", title: "Top Products", extra: { top_n: 500 } },
    { kind: "table", tableId: "top_brands", title: "Top Brands", extra: { top_n: 500 } },
  ],
  dataquality: [{ kind: "data_quality" }],
};
