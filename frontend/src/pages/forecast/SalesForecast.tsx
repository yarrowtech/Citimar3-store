import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";

import { forecastApi } from "@/api/forecastClient";
import { ForecastChartPanel } from "@/components/forecast/ForecastChartPanel";
import { ForecastDataTable } from "@/components/forecast/ForecastDataTable";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useGatedForecast } from "@/hooks/useGatedForecast";
import { fmtCurrency } from "@/lib/format";

const ALL_STORES = "__all__";

interface SalesForecastProps {
  stores: string[];
  storeNames: Record<string, string>;
  horizon: number;
  models: string[];
  salesStore: string | undefined;
  onSalesStoreChange: (store: string | undefined) => void;
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}

export function SalesForecast({ stores, storeNames, horizon, models, salesStore, onSalesStoreChange }: SalesForecastProps) {
  const [showLeaderboard, setShowLeaderboard] = useState(false);
  const [targetTotal, setTargetTotal] = useState<number | undefined>(undefined);

  const params = { store: salesStore, horizon, models: models.join(",") };
  const gated = useGatedForecast("sales", params);

  const growthGoalQuery = useQuery({
    queryKey: ["forecast-growth-goal", salesStore, horizon, models.join(","), targetTotal],
    queryFn: () => forecastApi.growthGoal({ ...params, target_total: targetTotal }),
    enabled: gated.computed && gated.status?.insufficient_history === false,
  });

  return (
    <Section title="Sales Forecast">
      <div className="mb-3 flex items-center gap-3">
        <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Store</Label>
        <Select value={salesStore ?? ALL_STORES} onValueChange={(v) => onSalesStoreChange(v === ALL_STORES ? undefined : v)}>
          <SelectTrigger className="w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_STORES}>All Stores</SelectItem>
            {stores.map((s) => (
              <SelectItem key={s} value={s}>
                {storeNames[s] ?? s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {gated.isStatusLoading ? null : !gated.computed ? (
        <div className="space-y-2">
          <Button onClick={gated.run} disabled={gated.isComputing}>
            {gated.isComputing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {gated.isComputing ? "Training & backtesting..." : "Run Sales Forecast"}
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
          <ForecastChartPanel chartId="sales-line" params={params} className="h-[460px] w-full" />
          <p className="text-muted-foreground mt-2 text-sm">
            Best model: <strong>{gated.status?.best_model}</strong> (lowest backtest MAPE) — see the leaderboard below for every
            model tried.
          </p>

          <div className="mt-3">
            <Button variant="outline" size="sm" onClick={() => setShowLeaderboard((o) => !o)}>
              {showLeaderboard ? "Hide" : "Show"} Model Leaderboard
            </Button>
            {showLeaderboard && (
              <div className="mt-2 space-y-2">
                <ForecastChartPanel chartId="sales-leaderboard" params={params} className="h-[400px] w-full" />
                <ForecastDataTable tableId="sales-leaderboard" params={params} />
              </div>
            )}
          </div>

          <div className="mt-4">
            <ForecastDataTable tableId="sales-forecast" params={params} title="Forecast Series" />
          </div>

          <div className="mt-6 border-t pt-4">
            <h4 className="mb-3 font-semibold">Growth / Up-Scaling Goal</h4>
            <div className="mb-3 flex items-center gap-3">
              <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
                Target Net Sales for the next {horizon} days
              </Label>
              <Input
                type="number"
                value={targetTotal ?? growthGoalQuery.data?.default_target_total ?? ""}
                onChange={(e) => setTargetTotal(e.target.value === "" ? undefined : Number(e.target.value))}
                className="w-48"
              />
            </div>
            {growthGoalQuery.data?.computed && (
              <>
                <div className="grid grid-cols-3 gap-4">
                  <StatTile label="Current Avg Daily Sales" value={fmtCurrency(growthGoalQuery.data.current_avg_daily)} />
                  <StatTile label="Required Avg Daily Sales" value={fmtCurrency(growthGoalQuery.data.required_avg_daily)} />
                  <StatTile
                    label="Uplift Needed"
                    value={growthGoalQuery.data.uplift_pct != null ? `${growthGoalQuery.data.uplift_pct.toFixed(1)}%` : "N/A"}
                  />
                </div>
                <p className="text-muted-foreground mt-2 text-sm">
                  {growthGoalQuery.data.achievable_at_current_pace ? "✅ Achievable at current pace" : "⚠️ Needs acceleration above current pace"}
                </p>
                <ForecastChartPanel
                  chartId="sales-growth-trajectory"
                  params={{ ...params, target_total: targetTotal ?? growthGoalQuery.data.default_target_total }}
                  className="mt-2 h-[400px] w-full"
                />
              </>
            )}
          </div>
        </>
      )}
    </Section>
  );
}
