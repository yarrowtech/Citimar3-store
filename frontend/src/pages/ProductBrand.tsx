import { useState } from "react";

import { ChartPanel } from "@/components/ChartPanel";
import { CHART_TYPES, ChartTypeToggle, type ChartType } from "@/components/ChartTypeToggle";
import { DataTable } from "@/components/DataTable";
import { Section } from "@/components/Section";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { FilterState } from "@/lib/types";

// The category dimension the merged "Top <category>" ranking groups by. The
// old per-item Top Products and per-brand Top Brands sections fold into this
// one section (spec: Division / Section / Department).
const CATEGORY_OPTIONS = [
  { value: "division", label: "Division" },
  { value: "section", label: "Section" },
  { value: "department", label: "Department" },
] as const;
type CategoryDim = (typeof CATEGORY_OPTIONS)[number]["value"];

// Ranking measure -- the table's displayed columns stay fixed regardless.
const MEASURE_OPTIONS = [
  { value: "net_amount", label: "Net Sales" },
  { value: "quantity", label: "Quantity" },
  { value: "transactions", label: "Transactions" },
] as const;
type Measure = (typeof MEASURE_OPTIONS)[number]["value"];

const DRILLDOWN_LABELS: Record<string, string> = {
  level: "Level",
  division: "Division",
  section: "Section",
  department: "Department",
  net_sales: "Net Sales",
  quantity: "Quantity",
  transactions: "Transactions",
  cogs_gst: "COGS + GST",
  discount: "Discount",
  gross_profit: "Gross Profit",
  gross_margin_pct: "Margin %",
  share_pct: "Share %",
};

const PAIRING_LABELS: Record<string, string> = {
  rank: "Rank",
  department: "Department",
  strong_performer: "Strong Performer",
  strong_net_sales: "Net Sales",
  weak_performer: "Weak Performer",
  weak_net_sales: "Net Sales",
  best_paired: "Possible Best Paired",
};

const TOP_N = 10;

export function ProductBrand({ filters }: { filters: FilterState }) {
  const [category, setCategory] = useState<CategoryDim>("division");
  const [measure, setMeasure] = useState<Measure>("net_amount");
  const [topChartType, setTopChartType] = useState<ChartType>("column");
  const [pairChartType, setPairChartType] = useState<ChartType>("column");

  const categoryLabel = CATEGORY_OPTIONS.find((o) => o.value === category)!.label;
  const topTableExtra = { category, measure, top_n: TOP_N };
  const topLabels: Record<string, string> = {
    category: categoryLabel,
    net_sales: "Net Sales",
    quantity: "Quantity",
    transactions: "Transactions",
    cogs_gst: "COGS + GST",
    discount: "Discount",
  };

  return (
    <div>
      <Section title="Category Drill-Down (Division → Section → Department)">
        <ChartPanel chartId="category_drilldown" filters={filters} className="h-[640px] w-full" />
        <div className="mt-4">
          <DataTable
            tableId="category_drilldown"
            filters={filters}
            columnLabels={DRILLDOWN_LABELS}
            title="Net Sales by Division / Section / Department"
          />
        </div>
      </Section>

      <Section title={`Top ${categoryLabel} by ${MEASURE_OPTIONS.find((o) => o.value === measure)!.label}`}>
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <Select value={category} onValueChange={(v) => setCategory(v as CategoryDim)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORY_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={measure} onValueChange={(v) => setMeasure(v as Measure)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MEASURE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <ChartTypeToggle value={topChartType} onChange={setTopChartType} allowed={CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="top_category"
          filters={filters}
          extra={{ ...topTableExtra, chart_type: topChartType }}
          className="mb-4 h-[460px] w-full"
        />
        <DataTable tableId="top_category" filters={filters} extra={topTableExtra} columnLabels={topLabels} showDownload />
      </Section>

      <Section title="Performer Pairing (Strong vs Weak) by Department">
        <div className="mb-2 flex justify-end">
          <ChartTypeToggle value={pairChartType} onChange={setPairChartType} allowed={CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="performer_pairing"
          filters={filters}
          extra={{ top_n: TOP_N, chart_type: pairChartType }}
          className="mb-4 h-[460px] w-full"
        />
        <DataTable tableId="performer_pairing" filters={filters} extra={{ top_n: TOP_N }} columnLabels={PAIRING_LABELS} showDownload />
      </Section>
    </div>
  );
}
