import { api } from "@/api/client";
import { authHeaders, handleUnauthorized } from "@/auth/tokenStore";
import { apiUrl } from "@/lib/apiBase";
import type { ReportManifestItem } from "@/lib/reportManifests";
import { KPI_FORMATTERS, KPI_LABELS, KPI_ORDER, fmtNumber } from "@/lib/format";
import type { ReportBlock, ReportFormat, ReportPayload } from "@/lib/reportTypes";
import { makeBlockId } from "@/lib/reportTypes";
import type { DataQualityProfile, FilterState, PlotlyChartFigure } from "@/lib/types";

/** Human-readable "Store: NM, HB | Date: 01 Aug 2026 - 26 Aug 2026 | ..." line
 * -- the FiltersSummaryBlock's text, and every renderer's cover-page filters
 * line (spec item 3, "Selected filters"). */
export function filtersSummaryText(filters: FilterState): string {
  const parts: string[] = [];
  if (filters.stores.length) parts.push(`Store: ${filters.stores.join(", ")}`);
  if (filters.start || filters.end) parts.push(`Date: ${filters.start || "…"} to ${filters.end || "…"}`);
  if (filters.time_slot.length) parts.push(`Time Slot: ${filters.time_slot.join(", ")}`);
  if (filters.division.length) parts.push(`Division: ${filters.division.join(", ")}`);
  if (filters.section.length) parts.push(`Section: ${filters.section.join(", ")}`);
  if (filters.department.length) parts.push(`Department: ${filters.department.join(", ")}`);
  if (filters.vendors.length) parts.push(`Vendors: ${filters.vendors.join(", ")}`);
  return parts.length ? parts.join(" | ") : "All stores, all dates (no filters applied)";
}

async function buildKpiGridBlock(filters: FilterState): Promise<ReportBlock> {
  const data = await api.kpis(filters);
  return {
    id: makeBlockId(),
    type: "kpi_grid",
    heading: "KPI Summary",
    items: KPI_ORDER.map((key) => ({
      label: KPI_LABELS[key]!,
      value: (KPI_FORMATTERS[key] ?? fmtNumber)(data.kpis[key]),
      status: data.statuses[key] ?? null,
    })),
  };
}

async function buildChartOrGaugeBlock(
  chartId: string,
  title: string,
  filters: FilterState,
  extra: Record<string, string | number | undefined> | undefined,
): Promise<ReportBlock> {
  const data = await api.chart(chartId, filters, extra ?? {});
  if ("kind" in data && data.kind === "gauge") {
    return { id: makeBlockId(), type: "gauge", spec: data as unknown as Record<string, unknown> };
  }
  return { id: makeBlockId(), type: "chart", title, figure: data as PlotlyChartFigure };
}

/** Missing numeric cell -> 0 (Historical Analytics Overhaul), matching the
 * on-screen <DataTable>. A column is "numeric" only if every non-null value in
 * it is a number, so date/text columns (previous_year_date, promo_type, ...)
 * keep their nulls (rendered N/A by the renderers). */
function zeroFillNumericColumns(columns: string[], rows: Record<string, unknown>[]): Record<string, unknown>[] {
  const numericCols = columns.filter((col) => {
    const values = rows.map((r) => r[col]).filter((v) => v !== null && v !== undefined);
    return values.length > 0 && values.every((v) => typeof v === "number");
  });
  if (numericCols.length === 0) return rows;
  return rows.map((row) => {
    const filled = { ...row };
    for (const col of numericCols) {
      if (filled[col] === null || filled[col] === undefined) filled[col] = 0;
    }
    return filled;
  });
}

async function buildTableBlock(
  tableId: string,
  title: string,
  filters: FilterState,
  extra: Record<string, string | number | undefined> | undefined,
): Promise<ReportBlock> {
  const data = await api.table(tableId, filters, extra ?? {});
  return {
    id: makeBlockId(),
    type: "table",
    title,
    columns: data.columns,
    rows: zeroFillNumericColumns(data.columns, data.rows),
  };
}

function dataQualityWarningLines(data: DataQualityProfile): string[] {
  const hierarchyLabel =
    Object.entries(data.product_hierarchy_values_nulled)
      .map(([field, count]) => `${field}: ${fmtNumber(count)}`)
      .join(" · ") || "None";
  return [
    `Worksheets loaded: ${data.worksheets_loaded.join(", ") || "None"}`,
    `Worksheets skipped: ${data.worksheets_skipped.join(", ") || "None"}`,
    `Total rows before cleaning: ${fmtNumber(data.total_rows_before_cleaning)}`,
    `Rows retained after cleaning: ${fmtNumber(data.rows_retained_after_cleaning)}`,
    `Date range: ${data.date_range ? data.date_range.join(" – ") : "N/A"}`,
    `Missing date count: ${fmtNumber(data.missing_date_count)}`,
    `Missing product count: ${fmtNumber(data.missing_product_count)}`,
    `Missing department count: ${fmtNumber(data.missing_department_count)}`,
    `Invalid sales count: ${fmtNumber(data.invalid_sales_count)}`,
    `Duplicate transaction rows dropped: ${fmtNumber(data.duplicate_transaction_count)}`,
    `Zero-amount duplicate lines flagged: ${fmtNumber(data.zero_amount_duplicate_flagged_count)}`,
    `Negative sales / return rows: ${fmtNumber(data.negative_sales_or_return_count)}`,
    `Missing cost count: ${fmtNumber(data.missing_cost_count)}`,
    `Missing target count: ${fmtNumber(data.missing_target_count)}`,
    `Missing footfall count: ${fmtNumber(data.missing_footfall_count)}`,
    `Product hierarchy values nulled (Years/Numeric contamination): ${hierarchyLabel}`,
    `Tax rate outlier rows (not a valid GST slab): ${fmtNumber(data.tax_rate_outlier_rows)}`,
    `Rows with unmapped store: ${fmtNumber(data.unmapped_store_rows)}`,
  ];
}

async function buildDataQualityBlock(): Promise<ReportBlock> {
  const data = await api.dataQuality();
  return { id: makeBlockId(), type: "data_quality", heading: "Data Quality Warnings", items: dataQualityWarningLines(data) };
}

/** Fetches every block a tab's manifest declares, for the current filters --
 * reuses the exact same api.kpis/api.chart/api.table/api.dataQuality calls
 * the dashboard pages themselves use, so an already-viewed tab's data comes
 * straight out of TanStack Query's cache. */
export async function buildReportBlocks(items: ReportManifestItem[], filters: FilterState): Promise<ReportBlock[]> {
  return Promise.all(
    items.map((item) => {
      if (item.kind === "kpi_grid") return buildKpiGridBlock(filters);
      if (item.kind === "chart") return buildChartOrGaugeBlock(item.chartId, item.title, filters, item.extra);
      if (item.kind === "table") return buildTableBlock(item.tableId, item.title, filters, item.extra);
      return buildDataQualityBlock();
    }),
  );
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") return body.detail;
  } catch {
    // fall through
  }
  return `${res.status} ${res.statusText}`;
}

/** Strips the frontend-only `id` field, POSTs to the render endpoint, and
 * triggers a real browser download of the returned file -- a real download,
 * not the sandboxed kind an Artifact page would be blocked from doing. */
export async function downloadReport(blocks: ReportBlock[], meta: ReportPayload["meta"], format: ReportFormat): Promise<void> {
  const payload: ReportPayload = {
    meta,
    blocks: blocks.map(({ id: _id, ...rest }) => rest),
  };

  const res = await fetch(apiUrl(`/api/reports/render?format=${format}`), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    if (res.status === 401) handleUnauthorized();
    throw new Error(await errorMessage(res));
  }

  await triggerDownload(res, `report.${format}`);
}

async function triggerDownload(res: Response, fallbackName: string): Promise<void> {
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] ?? fallbackName;

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Per-store Daily Operations export (GET /api/daily/report). Standalone --
 * not the block-model ReportBuilder flow above; the backend assembles the
 * whole report from the live MongoDB logs (src/daily_report.py). */
export async function downloadDailyReport(store: string, format: "xlsx" | "pdf"): Promise<void> {
  const res = await fetch(apiUrl(`/api/daily/report?${new URLSearchParams({ store, format })}`), {
    headers: { ...authHeaders() },
  });
  if (!res.ok) {
    if (res.status === 401) handleUnauthorized();
    throw new Error(await errorMessage(res));
  }
  await triggerDownload(res, `daily-report.${format}`);
}
