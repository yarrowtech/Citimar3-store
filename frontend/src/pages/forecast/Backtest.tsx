import { useState } from "react";

import { ForecastChartPanel } from "@/components/forecast/ForecastChartPanel";
import { ForecastDataTable } from "@/components/forecast/ForecastDataTable";
import { Section } from "@/components/Section";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useGatedForecast } from "@/hooks/useGatedForecast";

type SeriesKind = "sales" | "footfall";

interface BacktestProps {
  horizon: number;
  models: string[];
  salesStore: string | undefined;
  footfallStore: string | undefined;
  footfallTimeSlot: string | undefined;
  footfallMetric: string;
}

export function Backtest({ horizon, models, salesStore, footfallStore, footfallTimeSlot, footfallMetric }: BacktestProps) {
  const salesParams = { store: salesStore, horizon, models: models.join(",") };
  const footfallParams = { store: footfallStore, time_slot: footfallTimeSlot, metric: footfallMetric, horizon, models: models.join(",") };

  // Read-only -- never .run() here. Backtest only ever reuses whichever
  // series the Sales/Footfall tabs already computed (same query keys, so
  // React Query dedupes the network call with those tabs' own hook instances).
  const salesGated = useGatedForecast("sales", salesParams);
  const footfallGated = useGatedForecast("footfall", footfallParams);

  const seriesOptions: { value: SeriesKind; label: string }[] = [];
  if (salesGated.computed && salesGated.status?.insufficient_history === false) {
    seriesOptions.push({ value: "sales", label: salesGated.status.label ?? "Sales Forecast" });
  }
  if (footfallGated.computed && footfallGated.status?.insufficient_history === false) {
    seriesOptions.push({ value: "footfall", label: footfallGated.status.label ?? "Footfall/NOB Forecast" });
  }

  const [seriesKind, setSeriesKind] = useState<SeriesKind>("sales");
  const availableKinds = seriesOptions.map((o) => o.value);
  const effectiveSeriesKind = availableKinds.includes(seriesKind) ? seriesKind : availableKinds[0];

  const activeGated = effectiveSeriesKind === "footfall" ? footfallGated : salesGated;
  const modelOptions = activeGated.status?.model_set ?? [];

  const [model, setModel] = useState<string | undefined>(undefined);
  const effectiveModel = model && modelOptions.includes(model) ? model : (activeGated.status?.best_model ?? modelOptions[0]);

  const chartParams =
    effectiveSeriesKind === "footfall"
      ? { ...footfallParams, series_kind: "footfall", model: effectiveModel }
      : { ...salesParams, series_kind: "sales", model: effectiveModel };

  return (
    <Section title="Actual vs Estimation (Backtest)">
      <p className="text-muted-foreground mb-3 text-sm">
        This compares each model's held-out backtest predictions against what actually happened on those same historical
        days — it is not a preview of the real future (the workbook has no actuals beyond its own last date yet). It will
        keep working the same way once new months are appended to the workbook.
      </p>

      {seriesOptions.length === 0 ? (
        <p className="text-muted-foreground text-sm">
          No backtested forecast is available yet — visit the Sales Forecast or Footfall & NOB tabs first.
        </p>
      ) : (
        <>
          <div className="mb-3 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Series</Label>
              <Select value={effectiveSeriesKind} onValueChange={(v) => setSeriesKind(v as SeriesKind)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {seriesOptions.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Model</Label>
              <Select value={effectiveModel} onValueChange={setModel}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {modelOptions.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <ForecastChartPanel chartId="backtest-actual-vs-predicted" params={chartParams} className="h-[460px] w-full" />
          <div className="mt-4">
            <ForecastDataTable tableId="backtest-folds" params={chartParams} title="Fold Scores" />
          </div>
        </>
      )}
    </Section>
  );
}
