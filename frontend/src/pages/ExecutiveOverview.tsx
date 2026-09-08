import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api/client";
import { ChartPanel } from "@/components/ChartPanel";
import { ChartTypeToggle, type ChartType } from "@/components/ChartTypeToggle";
import { DataTable } from "@/components/DataTable";
import { KpiCard } from "@/components/KpiCard";
import { KpiTable } from "@/components/KpiTable";
import { PeriodSelect, type Period } from "@/components/PeriodSelect";
import { Section } from "@/components/Section";
import { ThresholdPopover } from "@/components/ThresholdPopover";
import { Skeleton } from "@/components/ui/skeleton";
import { filterQueryKey } from "@/lib/filterParams";
import { KPI_FORMATTERS, KPI_FORMULAS, KPI_LABELS, KPI_ORDER, fmtNumberOrZero } from "@/lib/format";
import { EDITABLE_THRESHOLDS } from "@/lib/kpiThresholds";
import type { FilterState } from "@/lib/types";

// Display-only header relabels for the Sales Overview table (§1). Raw column
// names still drive fmtCell's currency/percent formatting.
const SALES_OVERVIEW_LABELS: Record<string, string> = {
  sales_target: "Sales Target",
  net_sales: "Net Sales",
  remaining: "Remaining",
  bill_quantity: "BILL QUANTITY",
  footfall: "FOOTFALL",
  nob: "NOB",
  atv: "ATV",
  rpv: "RPV",
  basket_size: "BASKET SIZE",
  conversion_pct: "CONVERSION %",
  achievement_pct: "ACHIEVEMENT %",
  remaining_pct: "Remaining %",
};

export function ExecutiveOverview({ filters }: { filters: FilterState }) {
  const queryClient = useQueryClient();
  const [granularity, setGranularity] = useState<Period>("month");
  const [chartType, setChartType] = useState<ChartType>("column");

  // keepPreviousData: on Apply Filters, keep showing the last-applied
  // filters' KPI cards (not a blank skeleton) until the new numbers land --
  // an Apply-driven refetch is an update, not a fresh load.
  const { data, isLoading } = useQuery({
    queryKey: ["kpis", filterQueryKey(filters)],
    queryFn: () => api.kpis(filters),
    placeholderData: keepPreviousData,
  });

  const { data: thresholds } = useQuery({
    queryKey: ["kpi-thresholds"],
    queryFn: () => api.kpiThresholds(),
  });

  const thresholdMutation = useMutation({
    mutationFn: (action: { type: "save"; patch: Record<string, Record<string, number>> } | { type: "reset"; kpi: string }) =>
      action.type === "save" ? api.putKpiThresholds(action.patch) : api.resetKpiThreshold(action.kpi),
    onSuccess: () => {
      for (const key of [["kpis"], ["chart"], ["table", "kpi_table"], ["kpi-thresholds"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });

  const deltas = data?.comparisons.previous_period ?? {};

  return (
    <div>
      <div className="mb-4 grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
        {isLoading || !data
          ? Array.from({ length: KPI_ORDER.length }).map((_, i) => <Skeleton key={i} className="h-[110px] rounded-xl" />)
          : KPI_ORDER.map((key, i) => {
              const editable = EDITABLE_THRESHOLDS[key];
              const band = editable && thresholds ? thresholds.effective[editable.kpi] : undefined;
              return (
                <KpiCard
                  key={key}
                  index={i}
                  label={KPI_LABELS[key]!}
                  value={data.kpis[key]}
                  formatter={KPI_FORMATTERS[key] ?? fmtNumberOrZero}
                  formula={KPI_FORMULAS[key]!}
                  status={data.statuses[key]}
                  delta={deltas[key]}
                  thresholdControl={
                    editable && band ? (
                      <ThresholdPopover
                        kpiKey={editable.kpi}
                        kpiLabel={KPI_LABELS[key]!}
                        greenKey={editable.greenKey}
                        band={band}
                        isOverridden={!!thresholds?.overrides[editable.kpi]}
                        onSave={(patch) => thresholdMutation.mutate({ type: "save", patch })}
                        onReset={() => thresholdMutation.mutate({ type: "reset", kpi: editable.kpi })}
                      />
                    ) : undefined
                  }
                />
              );
            })}
      </div>

      {data && <KpiTable kpis={data.kpis} deltas={deltas} />}

      <Section className="mt-4">
        <div className="mb-2 flex justify-end gap-2">
          <PeriodSelect value={granularity} onChange={setGranularity} />
          <ChartTypeToggle value={chartType} onChange={setChartType} allowed={["column", "bar", "line", "area", "pie", "bar3d"]} />
        </div>
        <ChartPanel
          chartId="sales_overview"
          filters={filters}
          extra={{ granularity, chart_type: chartType }}
          className="h-[460px] w-full"
        />
        <div className="mt-4">
          <DataTable
            tableId="sales_overview"
            filters={filters}
            extra={{ granularity }}
            title="Sales Overview"
            columnLabels={SALES_OVERVIEW_LABELS}
          />
        </div>
      </Section>
    </div>
  );
}
