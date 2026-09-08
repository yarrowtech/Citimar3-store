import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api } from "@/api/client";
import { downloadDailyReport } from "@/api/reportClient";
import { useAuth } from "@/auth/AuthProvider";
import { ChartPanel } from "@/components/ChartPanel";
import { DailyHeroCard } from "@/components/DailyHeroCard";
import { KpiCard } from "@/components/KpiCard";
import { LoggedDailyEntries } from "@/components/LoggedDailyEntries";
import { Section } from "@/components/Section";
import { ThresholdPopover } from "@/components/ThresholdPopover";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DAILY_KPI_FORMATTERS, DAILY_KPI_FORMULAS, DAILY_KPI_LABELS, DAILY_KPI_ORDER, todayLocalDate } from "@/lib/format";
import { EDITABLE_THRESHOLDS } from "@/lib/kpiThresholds";
import type { FilterState, PreviousYearComparison } from "@/lib/types";

// The six gauges shown in one responsive row. Remaining %'s bands are just
// Achievement %'s mirrored around 100.
const GAUGES: { id: string; title: string }[] = [
  { id: "daily_conversion_gauge", title: "Conversion %" },
  { id: "daily_achievement_gauge", title: "Achievement %" },
  { id: "daily_remaining_gauge", title: "Remaining %" },
  { id: "daily_atv_gauge", title: "ATV" },
  { id: "daily_rpv_gauge", title: "RPV" },
  { id: "daily_basket_size_gauge", title: "Basket Size" },
];

/** Previous-year same-day comparison matrix (src/daily_context.py's
 * previous_year_same_day). "No historical data found" whenever DATASET.xlsx
 * has no prior-year rows for this store -- the usual case until the workbook
 * spans more than one year. */
function PrevYearMatrix({ data }: { data: PreviousYearComparison | null }) {
  if (!data || data.rows.every((r) => r.previous == null)) {
    return <p className="text-muted-foreground mt-0.5">No historical data found</p>;
  }
  return (
    <div className="mt-1 overflow-x-auto">
      <table className="w-full min-w-[420px] text-sm">
        <thead className="text-muted-foreground text-xs uppercase">
          <tr>
            <th className="py-1 pr-3 text-left font-semibold">KPI</th>
            <th className="py-1 px-3 text-right font-semibold">This Year</th>
            <th className="py-1 px-3 text-right font-semibold">Last Year ({data.date})</th>
            <th className="py-1 pl-3 text-right font-semibold">Δ%</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row) => {
            const fmt = DAILY_KPI_FORMATTERS[row.kpi];
            const delta = row.variance_pct;
            return (
              <tr key={row.kpi} className="border-border/50 border-t">
                <td className="py-1 pr-3">{DAILY_KPI_LABELS[row.kpi]}</td>
                <td className="py-1 px-3 text-right tabular-nums">{fmt(row.current)}</td>
                <td className="py-1 px-3 text-right tabular-nums">{fmt(row.previous)}</td>
                <td
                  className={`py-1 pl-3 text-right tabular-nums ${
                    delta == null ? "text-muted-foreground" : delta >= 0 ? "text-status-green" : "text-status-red"
                  }`}
                >
                  {delta == null ? "—" : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** One store's live Daily Dashboard: hero card (store/date/time), the store's
 * own KPI set (MongoDB, via GET /api/daily/live), six gauges, today's
 * time-slot sales performance, same-day context (weather, holiday, election),
 * then the store's logged Footfall / Bills & NOB entries (edited inline).
 * Manual per-card value overrides stay removed. The admin (only) gets the
 * <ThresholdPopover> gear on the five band-editable KPI cards -- ATV, RPV,
 * Basket Size, Conversion %, Achievement % -- editing the same global
 * PUT /api/kpi-thresholds overlay as Executive Overview; a store manager
 * sees the cards read-only. */
function StoreDailyDashboard({ store, filters }: { store: string; filters: FilterState }) {
  const today = todayLocalDate();
  const gaugeFilters: FilterState = { ...filters, stores: [store], start: today, end: today };
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const queryClient = useQueryClient();
  const [exporting, setExporting] = useState<"xlsx" | "pdf" | null>(null);

  // Admin-only: the red/yellow/green band editor on the five ratio cards.
  // The endpoint is admin-gated app-side, so a manager must not query it.
  const { data: thresholds } = useQuery({
    queryKey: ["kpi-thresholds"],
    queryFn: () => api.kpiThresholds(),
    enabled: isAdmin,
  });

  const thresholdMutation = useMutation({
    mutationFn: (action: { type: "save"; patch: Record<string, Record<string, number>> } | { type: "reset"; kpi: string }) =>
      action.type === "save" ? api.putKpiThresholds(action.patch) : api.resetKpiThreshold(action.kpi),
    onSuccess: () => {
      // Cards' statuses (GET /api/daily/live) and the gauges both resolve
      // their bands server-side at call time, so both must refetch.
      for (const key of [["daily-live"], ["chart"], ["kpi-thresholds"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });

  const { data: defaults } = useQuery({ queryKey: ["filters", "defaults"], queryFn: api.filterDefaults, enabled: isAdmin });
  const storeName = defaults?.store_names?.[store] ?? store;

  const { data, isLoading } = useQuery({
    queryKey: ["daily-live", store, today],
    queryFn: () => api.dailyLive(store, today),
  });

  const runExport = async (format: "xlsx" | "pdf") => {
    setExporting(format);
    try {
      await downloadDailyReport(store, format);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setExporting(null);
    }
  };

  return (
    <div>
      <DailyHeroCard storeName={storeName} />

      <div className="mb-4 flex flex-wrap justify-end gap-2">
        <Button variant="outline" size="sm" disabled={exporting !== null} onClick={() => runExport("xlsx")}>
          <FileSpreadsheet className="h-4 w-4" />
          {exporting === "xlsx" ? "Exporting…" : "Export Excel"}
        </Button>
        <Button variant="outline" size="sm" disabled={exporting !== null} onClick={() => runExport("pdf")}>
          <FileText className="h-4 w-4" />
          {exporting === "pdf" ? "Exporting…" : "Export PDF"}
        </Button>
      </div>

      <div className="mb-4 grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
        {isLoading || !data
          ? Array.from({ length: DAILY_KPI_ORDER.length }).map((_, i) => <Skeleton key={i} className="h-[110px] rounded-xl" />)
          : DAILY_KPI_ORDER.map((key, i) => {
              const editable = isAdmin ? EDITABLE_THRESHOLDS[key] : undefined;
              const band = editable && thresholds ? thresholds.effective[editable.kpi] : undefined;
              return (
                <KpiCard
                  key={key}
                  index={i}
                  label={DAILY_KPI_LABELS[key]}
                  value={data.kpis[key]}
                  formatter={DAILY_KPI_FORMATTERS[key]}
                  formula={DAILY_KPI_FORMULAS[key]}
                  status={data.statuses[key]}
                  thresholdControl={
                    editable && band ? (
                      <ThresholdPopover
                        kpiKey={editable.kpi}
                        kpiLabel={DAILY_KPI_LABELS[key]}
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

      {/* All six gauges on one level -- wraps to 3-up / 2-up on smaller screens. */}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {GAUGES.map((g) => (
          <div key={g.id} className="bg-card rounded-xl border p-2">
            <ChartPanel chartId={g.id} filters={gaugeFilters} className="h-[300px] w-full" />
          </div>
        ))}
      </div>

      <Section title="Today's Performance by Time Slot" className="mb-4">
        <ChartPanel chartId="daily_timeslot_breakdown" filters={gaugeFilters} className="h-[460px] w-full" />
      </Section>

      <Section title="Footfall vs NOB (based on Time Slot)" className="mb-4">
        <ChartPanel chartId="daily_footfall_nob" filters={gaugeFilters} className="h-[460px] w-full" />
      </Section>

      <Section title="Today's Context" className="mb-4">
        {isLoading || !data ? (
          <Skeleton className="h-40 w-full rounded-lg" />
        ) : (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap gap-2">
              <span className="bg-muted rounded-full px-2.5 py-1 text-xs font-semibold">{data.day_name}</span>
              <span className="bg-muted rounded-full px-2.5 py-1 text-xs font-semibold">{data.day_type}</span>
              {data.holiday_name && (
                <span className="bg-status-yellow-bg text-status-yellow rounded-full px-2.5 py-1 text-xs font-semibold">
                  {data.holiday_name}
                </span>
              )}
              {data.election_name && (
                <span className="bg-status-yellow-bg text-status-yellow rounded-full px-2.5 py-1 text-xs font-semibold">
                  {data.election_name}
                </span>
              )}
            </div>

            <div>
              <div className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Weather (Kolkata)</div>
              {data.weather ? (
                <p className="mt-0.5">
                  {data.weather.condition}
                  {data.weather.temp_max_c != null && (
                    <>
                      {" "}
                      · {Math.round(data.weather.temp_max_c)}°C / {Math.round(data.weather.temp_min_c ?? data.weather.temp_max_c)}°C
                    </>
                  )}
                  {data.weather.precipitation_mm != null && data.weather.precipitation_mm > 0 && (
                    <> · {data.weather.precipitation_mm.toFixed(0)}mm rain</>
                  )}
                </p>
              ) : (
                <p className="text-muted-foreground mt-0.5">Weather unavailable</p>
              )}
            </div>

            <div>
              <div className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                Previous Year — Same Day
              </div>
              <PrevYearMatrix data={data.previous_year} />
            </div>

            {data.reason && (
              <div>
                <div className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Remarks</div>
                <p className="mt-0.5">{data.reason}</p>
              </div>
            )}
          </div>
        )}
      </Section>

      <LoggedDailyEntries store={store} date={today} />
    </div>
  );
}

export function DailyDashboardNM({ filters }: { filters: FilterState }) {
  return <StoreDailyDashboard store="NM" filters={filters} />;
}

export function DailyDashboardHB({ filters }: { filters: FilterState }) {
  return <StoreDailyDashboard store="HB" filters={filters} />;
}

export function DailyDashboardCHW({ filters }: { filters: FilterState }) {
  return <StoreDailyDashboard store="CHW" filters={filters} />;
}
