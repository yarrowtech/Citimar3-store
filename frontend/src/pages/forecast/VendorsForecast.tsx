import { Loader2 } from "lucide-react";
import { useState } from "react";

import { ForecastChartPanel } from "@/components/forecast/ForecastChartPanel";
import { ForecastDataTable } from "@/components/forecast/ForecastDataTable";
import { Section } from "@/components/Section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useGatedForecast } from "@/hooks/useGatedForecast";
import type { BundlesStatus } from "@/lib/forecastTypes";

interface VendorsForecastProps {
  stores: string[];
  topNDefault: number;
  horizon: number;
  models: string[];
}

export function VendorsForecast({ stores, topNDefault, horizon, models }: VendorsForecastProps) {
  const [topN, setTopN] = useState(topNDefault);
  const [entity, setEntity] = useState<string | undefined>(undefined);

  const params = { top_n: topN, stores: stores.slice().sort().join(","), horizon, models: models.join(",") };
  const gated = useGatedForecast<BundlesStatus>("vendors", params);

  const entities = gated.status?.entities ?? [];
  const effectiveEntity = entity && entities.some((e) => e.name === entity) ? entity : entities[0]?.name;
  const entityInfo = entities.find((e) => e.name === effectiveEntity);
  const entityParams = effectiveEntity ? { ...params, entity: effectiveEntity } : null;

  return (
    <Section title="Vendor Performance — Future Sales Forecast">
      <p className="text-muted-foreground mb-3 text-sm">
        1,320 unique vendors exist — forecasting scopes to the top-N by revenue, with everything else rolled into "Other".
      </p>
      <div className="mb-3 space-y-1.5">
        <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Top N Vendors</Label>
        <Input type="number" min={5} max={30} value={topN} onChange={(e) => setTopN(Number(e.target.value) || topNDefault)} className="w-32" />
      </div>

      {gated.isStatusLoading ? null : !gated.computed ? (
        <div className="space-y-2">
          <Button onClick={gated.run} disabled={gated.isComputing}>
            {gated.isComputing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {gated.isComputing ? "Training & backtesting..." : `Run Vendor Forecast (${topN + 1} series)`}
          </Button>
          <p className="text-muted-foreground text-sm">
            Backtests {models.length} model(s) across {topN + 1} series (top {topN} vendors + Other) — can take a few minutes
            on first run, instant once cached.
          </p>
          {gated.computeError && <p className="text-destructive text-sm">Failed: {String(gated.computeError)}</p>}
        </div>
      ) : entities.length === 0 ? (
        <p className="text-muted-foreground text-sm">No vendor data available for the selected stores.</p>
      ) : (
        <>
          <ForecastChartPanel chartId="vendors-topn-bar" params={params} className="h-[460px] w-full" />

          <div className="mt-4 space-y-1.5">
            <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Drill in</Label>
            <Select value={effectiveEntity} onValueChange={setEntity}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {entities.map((e) => (
                  <SelectItem key={e.name} value={e.name}>
                    {e.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {entityParams &&
            (entityInfo?.insufficient_history ? (
              <p className="text-muted-foreground mt-2 text-sm">Not enough history to forecast this entity yet.</p>
            ) : (
              <div className="mt-2">
                <ForecastChartPanel chartId="vendors-drilldown-line" params={entityParams} className="h-[400px] w-full" />
                <p className="text-muted-foreground mt-2 text-sm">
                  Best model: <strong>{entityInfo?.best_model}</strong> (lowest backtest WAPE — the zero-sales-day-robust
                  metric used for per-entity series).
                </p>
                <ForecastChartPanel chartId="vendors-drilldown-leaderboard" params={entityParams} className="mt-2 h-[300px] w-full" />
                <ForecastDataTable tableId="vendors-drilldown-forecast" params={entityParams} title="Entity Forecast Series" />
              </div>
            ))}

          <div className="mt-4">
            <ForecastDataTable tableId="vendors-summary" params={params} title="Summary" />
          </div>
        </>
      )}
    </Section>
  );
}
