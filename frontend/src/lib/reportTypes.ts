// TS mirror of src/reports/models.py's block union -- field names must match
// exactly (this is serialized straight to JSON and parsed by FastAPI's
// Pydantic models on the other end, no transformation layer in between).
import type { StatusColor } from "@/lib/types";

export interface KpiItem {
  label: string;
  value: string;
  status?: StatusColor | null;
}

export interface TitleBlock {
  id: string;
  type: "title";
  text: string;
}

export interface TextBlock {
  id: string;
  type: "text";
  heading?: string | null;
  text: string;
}

export interface FiltersSummaryBlock {
  id: string;
  type: "filters_summary";
  heading: string;
  text: string;
}

export interface KpiGridBlock {
  id: string;
  type: "kpi_grid";
  heading?: string | null;
  items: KpiItem[];
}

export interface ChartBlock {
  id: string;
  type: "chart";
  title: string;
  figure: { data: unknown[]; layout: Record<string, unknown> };
}

export interface GaugeBlock {
  id: string;
  type: "gauge";
  spec: Record<string, unknown>;
}

export interface TableBlock {
  id: string;
  type: "table";
  title: string;
  columns: string[];
  rows: Record<string, unknown>[];
}

export interface DataQualityBlock {
  id: string;
  type: "data_quality";
  heading: string;
  items: string[];
}

export interface ForecastSummaryBlock {
  id: string;
  type: "forecast_summary";
  heading: string;
  items: KpiItem[];
  note?: string | null;
}

export type ReportBlock =
  | TitleBlock
  | TextBlock
  | FiltersSummaryBlock
  | KpiGridBlock
  | ChartBlock
  | GaugeBlock
  | TableBlock
  | DataQualityBlock
  | ForecastSummaryBlock;

export interface ReportMeta {
  title: string;
  generated_at: string;
  filters_summary_text: string;
  workbook_note?: string;
}

export interface ReportPayload {
  meta: ReportMeta;
  blocks: Omit<ReportBlock, "id">[]; // `id` is a frontend-only key for reordering/removal, stripped before POSTing
}

export const REPORT_FORMATS = [
  { value: "pdf", label: "PDF" },
  { value: "pptx", label: "PowerPoint (PPTX)" },
  { value: "docx", label: "Word (DOCX)" },
  { value: "xlsx", label: "Excel (XLSX)" },
  { value: "csv", label: "CSV" },
  { value: "md", label: "Markdown" },
  { value: "html", label: "HTML" },
  { value: "xml", label: "XML" },
] as const;
export type ReportFormat = (typeof REPORT_FORMATS)[number]["value"];

let nextBlockId = 1;
export function makeBlockId(): string {
  return `block-${nextBlockId++}`;
}
