import { useState } from "react";

import { ChartPanel } from "@/components/ChartPanel";
import { ChartTypeToggle, type ChartType, CHART_TYPES } from "@/components/ChartTypeToggle";
import { DataTable } from "@/components/DataTable";
import { DimensionSelect } from "@/components/DimensionSelect";
import { Section } from "@/components/Section";
import type { FilterState } from "@/lib/types";

// Option `value`s mirror api/routes_charts.py's Customer & Conversion
// `dimension` vocabulary comment. Net Sales has no bill-time granularity in
// DATASET.xlsx, so the "vs Net Sales" charts deliberately offer no time-slot
// mode (see CLAUDE.md).
const NOB_CONVERSION_DIMENSIONS = [
  { value: "date", label: "Date wise" },
  { value: "timeslot", label: "Time-slot wise" },
] as const;
type NobConversionDimension = (typeof NOB_CONVERSION_DIMENSIONS)[number]["value"];

const NET_SALES_DIMENSIONS = [
  { value: "date", label: "Date wise" },
  { value: "dayofweek", label: "Day of week" },
] as const;
type NetSalesDimension = (typeof NET_SALES_DIMENSIONS)[number]["value"];

const BREAKDOWN_DIMENSIONS = [
  { value: "dayofweek", label: "Day of week" },
  { value: "timeslot", label: "Time of day" },
  { value: "date", label: "Date wise" },
] as const;
type BreakdownDimension = (typeof BREAKDOWN_DIMENSIONS)[number]["value"];

const FUNNEL_DIMENSIONS = [
  { value: "date", label: "Overall" },
  { value: "timeslot", label: "By time slot" },
] as const;
type FunnelDimension = (typeof FUNNEL_DIMENSIONS)[number]["value"];

// Dual-axis charts (secondary Conversion % / Net Sales line): column/line/area
// only -- mirrors api/routes_charts.py's _DUAL_AXIS_CHART_TYPES.
const DUAL_AXIS_CHART_TYPES: ChartType[] = ["column", "line", "area"];

export function CustomerConversion({ filters }: { filters: FilterState }) {
  const [nobConvDimension, setNobConvDimension] = useState<NobConversionDimension>("date");
  const [nobConvChartType, setNobConvChartType] = useState<ChartType>("column");

  const [footfallNetDimension, setFootfallNetDimension] = useState<NetSalesDimension>("date");
  const [footfallNetChartType, setFootfallNetChartType] = useState<ChartType>("column");

  const [nobNetDimension, setNobNetDimension] = useState<NetSalesDimension>("date");
  const [nobNetChartType, setNobNetChartType] = useState<ChartType>("column");

  const [breakdownDimension, setBreakdownDimension] = useState<BreakdownDimension>("dayofweek");
  const [breakdownChartType, setBreakdownChartType] = useState<ChartType>("column");

  const [funnelDimension, setFunnelDimension] = useState<FunnelDimension>("date");

  return (
    <div>
      <Section title="Footfall vs Number of Bills & Conversion %">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <DimensionSelect value={nobConvDimension} onChange={setNobConvDimension} options={NOB_CONVERSION_DIMENSIONS} />
          <ChartTypeToggle value={nobConvChartType} onChange={setNobConvChartType} allowed={DUAL_AXIS_CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="footfall_vs_nob"
          filters={filters}
          extra={{ dimension: nobConvDimension, chart_type: nobConvChartType }}
          className="h-[460px] w-full"
        />
        <div className="mt-4">
          <DataTable
            tableId="footfall_vs_nob"
            filters={filters}
            extra={{ dimension: nobConvDimension }}
            title="Footfall vs NOB & Conversion %"
          />
        </div>
      </Section>

      <Section title="Footfall vs Net Sales">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <DimensionSelect value={footfallNetDimension} onChange={setFootfallNetDimension} options={NET_SALES_DIMENSIONS} />
          <ChartTypeToggle value={footfallNetChartType} onChange={setFootfallNetChartType} allowed={DUAL_AXIS_CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="customer_footfall_net"
          filters={filters}
          extra={{ dimension: footfallNetDimension, chart_type: footfallNetChartType }}
          className="h-[460px] w-full"
        />
        <div className="mt-4">
          <DataTable
            tableId="customer_footfall_net"
            filters={filters}
            extra={{ dimension: footfallNetDimension }}
            title="Footfall vs Net Sales"
          />
        </div>
      </Section>

      <Section title="NOB vs Net Sales">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <DimensionSelect value={nobNetDimension} onChange={setNobNetDimension} options={NET_SALES_DIMENSIONS} />
          <ChartTypeToggle value={nobNetChartType} onChange={setNobNetChartType} allowed={DUAL_AXIS_CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="customer_nob_net"
          filters={filters}
          extra={{ dimension: nobNetDimension, chart_type: nobNetChartType }}
          className="h-[460px] w-full"
        />
        <div className="mt-4">
          <DataTable
            tableId="customer_nob_net"
            filters={filters}
            extra={{ dimension: nobNetDimension }}
            title="NOB vs Net Sales"
          />
        </div>
      </Section>

      <Section title="Footfall vs NOB Breakdown">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <DimensionSelect value={breakdownDimension} onChange={setBreakdownDimension} options={BREAKDOWN_DIMENSIONS} />
          <ChartTypeToggle value={breakdownChartType} onChange={setBreakdownChartType} allowed={CHART_TYPES} />
        </div>
        <ChartPanel
          chartId="footfall_nob_breakdown"
          filters={filters}
          extra={{ dimension: breakdownDimension, chart_type: breakdownChartType }}
          className="h-[460px] w-full"
        />
        <div className="mt-4">
          <DataTable
            tableId="footfall_nob_breakdown"
            filters={filters}
            extra={{ dimension: breakdownDimension }}
            title="Footfall vs NOB Breakdown"
          />
        </div>
      </Section>

      <Section title="Conversion %">
        <ChartPanel chartId="conversion_gauge" filters={filters} className="mx-auto h-[360px] w-full max-w-md" />
      </Section>

      <Section title="Conversion Funnel">
        <div className="mb-2 flex flex-wrap justify-end gap-2">
          <DimensionSelect value={funnelDimension} onChange={setFunnelDimension} options={FUNNEL_DIMENSIONS} />
        </div>
        <ChartPanel
          chartId="funnel"
          filters={filters}
          extra={{ dimension: funnelDimension }}
          className="h-[400px] w-full"
        />
        <div className="mt-4">
          <DataTable
            tableId="conversion_funnel"
            filters={filters}
            extra={{ dimension: funnelDimension }}
            title="Conversion Funnel"
          />
        </div>
      </Section>
    </div>
  );
}
