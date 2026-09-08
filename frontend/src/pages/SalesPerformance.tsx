import { useState } from "react";

import { ChartPanel } from "@/components/ChartPanel";
import { ChartTypeToggle, type ChartType } from "@/components/ChartTypeToggle";
import { DataTable } from "@/components/DataTable";
import { DimensionSelect } from "@/components/DimensionSelect";
import { PeriodSelect, type Period } from "@/components/PeriodSelect";
import { Section } from "@/components/Section";
import type { FilterState } from "@/lib/types";

// The mode-toggle vocabulary mirrors api/routes_charts.py's CHART_TYPE_ENABLED
// comment (Historical Analytics Overhaul A5).
const TREND_DIMENSIONS = [
  { value: "period", label: "Net Sales over time" },
  { value: "timeslot", label: "Footfall & NOB by time slot" },
] as const;
type TrendDimension = (typeof TREND_DIMENSIONS)[number]["value"];

const COMPARISON_DIMENSIONS = [
  { value: "monthly_same_day", label: "Monthly — same day of month" },
  { value: "weekly_same_day", label: "Weekly — same day of week" },
  { value: "yearly_month", label: "Yearly — same month" },
  { value: "same_period_yoy", label: "Year-over-year — same period" },
] as const;
type ComparisonDimension = (typeof COMPARISON_DIMENSIONS)[number]["value"];

const LINEAR_CHART_TYPES: ChartType[] = ["column", "bar", "line", "area"];

const SECONDARY_GAUGES = ["atv_gauge", "rpv_gauge", "basket_size_gauge", "achievement_gauge", "remaining_pct_gauge"];

export function SalesPerformance({ filters }: { filters: FilterState }) {
  const [trendDimension, setTrendDimension] = useState<TrendDimension>("period");
  const [trendGranularity, setTrendGranularity] = useState<Period>("day");
  const [trendChartType, setTrendChartType] = useState<ChartType>("column");

  const [avgGranularity, setAvgGranularity] = useState<Period>("day");
  const [avgChartType, setAvgChartType] = useState<ChartType>("column");

  const [comparisonDimension, setComparisonDimension] = useState<ComparisonDimension>("monthly_same_day");
  const [comparisonChartType, setComparisonChartType] = useState<ChartType>("line");

  const trendExtra =
    trendDimension === "timeslot"
      ? { dimension: trendDimension, chart_type: trendChartType }
      : { dimension: trendDimension, granularity: trendGranularity, chart_type: trendChartType };

  return (
    <div>
      <Section title="Sales Trend">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <DimensionSelect value={trendDimension} onChange={setTrendDimension} options={TREND_DIMENSIONS} />
          {trendDimension === "period" && <PeriodSelect value={trendGranularity} onChange={setTrendGranularity} />}
          <ChartTypeToggle value={trendChartType} onChange={setTrendChartType} allowed={LINEAR_CHART_TYPES} />
        </div>
        <ChartPanel chartId="sales_trend" filters={filters} extra={trendExtra} className="h-[460px] w-full" />
        <div className="mt-4">
          <DataTable
            tableId="sales_trend"
            filters={filters}
            extra={
              trendDimension === "timeslot"
                ? { dimension: trendDimension }
                : { dimension: trendDimension, granularity: trendGranularity }
            }
            title="Sales Trend"
          />
        </div>
      </Section>

      <Section title="Average Sales">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <PeriodSelect value={avgGranularity} onChange={setAvgGranularity} />
          <ChartTypeToggle value={avgChartType} onChange={setAvgChartType} allowed={LINEAR_CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="avg_sales"
          filters={filters}
          extra={{ granularity: avgGranularity, chart_type: avgChartType }}
          className="h-[460px] w-full"
        />
        <div className="mt-4">
          <DataTable tableId="avg_sales" filters={filters} extra={{ granularity: avgGranularity }} title="Average Sales" />
        </div>
      </Section>

      <Section title="Period Comparison">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <DimensionSelect value={comparisonDimension} onChange={setComparisonDimension} options={COMPARISON_DIMENSIONS} />
          <ChartTypeToggle value={comparisonChartType} onChange={setComparisonChartType} allowed={LINEAR_CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="period_comparison"
          filters={filters}
          extra={{ dimension: comparisonDimension, chart_type: comparisonChartType }}
          className="h-[460px] w-full"
        />
        <div className="mt-4">
          <DataTable
            tableId="period_comparison"
            filters={filters}
            extra={{ dimension: comparisonDimension }}
            title={comparisonDimension === "same_period_yoy" ? "Day-by-Day Comparison" : "Period Comparison"}
          />
        </div>
      </Section>

      <Section title="Secondary KPI Gauges">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {SECONDARY_GAUGES.map((id) => (
            <ChartPanel key={id} chartId={id} filters={filters} className="h-[360px] w-full" />
          ))}
        </div>
        <div className="mt-4">
          <DataTable tableId="secondary_gauge_values" filters={filters} title="Secondary KPI Values" showDownload={false} />
        </div>
      </Section>
    </div>
  );
}
