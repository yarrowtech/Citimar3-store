import { Loader2 } from "lucide-react";
import { useState } from "react";

import { ForecastChartPanel } from "@/components/forecast/ForecastChartPanel";
import { ForecastDataTable } from "@/components/forecast/ForecastDataTable";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useGatedForecast } from "@/hooks/useGatedForecast";

const ALL_SLOTS = "__all__";

interface FootfallForecastProps {
  stores: string[];
  storeNames: Record<string, string>;
  timeSlotOrder: string[];
  horizon: number;
  models: string[];
  store: string | undefined;
  onStoreChange: (store: string) => void;
  timeSlot: string | undefined;
  onTimeSlotChange: (slot: string | undefined) => void;
  metric: string;
  onMetricChange: (metric: string) => void;
}

export function FootfallForecast({
  stores,
  storeNames,
  timeSlotOrder,
  horizon,
  models,
  store,
  onStoreChange,
  timeSlot,
  onTimeSlotChange,
  metric,
  onMetricChange,
}: FootfallForecastProps) {
  const [showLeaderboard, setShowLeaderboard] = useState(false);

  const params = { store, time_slot: timeSlot, metric, horizon, models: models.join(",") };
  const gated = useGatedForecast("footfall", params);

  return (
    <Section title="Footfall & NOB Forecast — by Time Slot">
      <div className="mb-3 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Store</Label>
          <Select value={store} onValueChange={onStoreChange}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {stores.map((s) => (
                <SelectItem key={s} value={s}>
                  {storeNames[s] ?? s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Time Slot</Label>
          <Select value={timeSlot ?? ALL_SLOTS} onValueChange={(v) => onTimeSlotChange(v === ALL_SLOTS ? undefined : v)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_SLOTS}>All Slots Summed</SelectItem>
              {timeSlotOrder.map((slot) => (
                <SelectItem key={slot} value={slot}>
                  {slot}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Metric</Label>
          <Select value={metric} onValueChange={onMetricChange}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="footfall">Footfall</SelectItem>
              <SelectItem value="nob">NOB (Transactions)</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {gated.isStatusLoading ? null : !gated.computed ? (
        <div className="space-y-2">
          <Button onClick={gated.run} disabled={gated.isComputing}>
            {gated.isComputing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {gated.isComputing ? "Training & backtesting..." : "Run Footfall/NOB Forecast"}
          </Button>
          <p className="text-muted-foreground text-sm">
            Backtests {models.length} model(s) — first run takes ~45–90s, instant once cached.
          </p>
          {gated.computeError && <p className="text-destructive text-sm">Failed: {String(gated.computeError)}</p>}
        </div>
      ) : gated.status?.insufficient_history ? (
        <p className="text-muted-foreground text-sm">Not enough history to forecast this series yet.</p>
      ) : (
        <>
          <ForecastChartPanel chartId="footfall-line" params={params} className="h-[460px] w-full" />
          <p className="text-muted-foreground mt-2 text-sm">
            Best model: <strong>{gated.status?.best_model}</strong> (lowest backtest MAPE) — see the leaderboard below for every
            model tried.
          </p>
          {timeSlot && (
            <p className="text-muted-foreground mt-1 text-sm">
              This forecast is scoped to a single time-of-day band, not summed across the whole day — switch "Time Slot" to
              "All Slots Summed" for a store-level daily view.
            </p>
          )}

          <div className="mt-3">
            <Button variant="outline" size="sm" onClick={() => setShowLeaderboard((o) => !o)}>
              {showLeaderboard ? "Hide" : "Show"} Model Leaderboard
            </Button>
            {showLeaderboard && (
              <div className="mt-2 space-y-2">
                <ForecastChartPanel chartId="footfall-leaderboard" params={params} className="h-[400px] w-full" />
                <ForecastDataTable tableId="footfall-leaderboard" params={params} />
              </div>
            )}
          </div>

          <div className="mt-4">
            <ForecastDataTable
              tableId="footfall-forecast"
              params={params}
              title="Forecast Series"
              plainNumberKeys={["point", "lower", "upper"]}
            />
          </div>
        </>
      )}
    </Section>
  );
}
