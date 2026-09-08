import { useQuery } from "@tanstack/react-query";

import { forecastApi } from "@/api/forecastClient";
import { Section } from "@/components/Section";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtCurrency } from "@/lib/format";

interface ForecastOverviewProps {
  horizon: number;
  models: string[];
  salesStore: string | undefined;
  footfallStore: string | undefined;
  footfallTimeSlot: string | undefined;
  footfallMetric: string;
}

export function ForecastOverview({ horizon, models, salesStore, footfallStore, footfallTimeSlot, footfallMetric }: ForecastOverviewProps) {
  const params = {
    horizon,
    models: models.join(","),
    sales_store: salesStore,
    footfall_store: footfallStore,
    footfall_time_slot: footfallTimeSlot,
    footfall_metric: footfallMetric,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["forecast-overview", salesStore, footfallStore, footfallTimeSlot, footfallMetric, horizon, models.join(",")],
    queryFn: () => forecastApi.overview(params),
  });

  if (isLoading) return <Skeleton className="h-40 w-full rounded-lg" />;

  if (!data?.sales_computed) {
    return (
      <Section title="Forecasting Overview">
        <p className="text-muted-foreground text-sm">
          Not enough history to build a Sales Forecast yet — see the "Sales Forecast & Growth Goals" tab for details.
        </p>
      </Section>
    );
  }

  const delta = data.delta_vs_flat ?? 0;

  return (
    <Section title="Forecasting Overview">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <p className="text-muted-foreground text-xs">Flat Continuation of Current Pace</p>
          <p className="text-xl font-semibold">{fmtCurrency(data.flat_continuation)}</p>
        </div>
        <div>
          <p className="text-muted-foreground text-xs">Model Forecast Total ({data.horizon} days)</p>
          <p className="text-xl font-semibold">{fmtCurrency(data.model_forecast_total)}</p>
        </div>
      </div>
      <p className="text-muted-foreground mt-2 text-sm">
        90% confidence range: {fmtCurrency(data.confidence_lower)} – {fmtCurrency(data.confidence_upper)}
      </p>
      <p className="mt-1 text-sm">
        {delta > 0 && (
          <>
            The model-based forecast total is <strong>above</strong> a flat continuation of current pace by{" "}
            {fmtCurrency(delta)}.
          </>
        )}
        {delta < 0 && (
          <>
            The model-based forecast total is <strong>below</strong> a flat continuation of current pace by{" "}
            {fmtCurrency(Math.abs(delta))}.
          </>
        )}
        {delta === 0 && <>The model-based forecast total is in line with a flat continuation of current pace.</>}
      </p>

      {data.model_selection_summary && data.model_selection_summary.length > 0 && (
        <div className="mt-6">
          <h4 className="mb-3 font-semibold">Model Selection Summary</h4>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Series</TableHead>
                <TableHead>Best Model</TableHead>
                <TableHead>Backtest MAPE</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.model_selection_summary.map((row) => (
                <TableRow key={row.series}>
                  <TableCell>{row.series}</TableCell>
                  <TableCell>{row.best_model}</TableCell>
                  <TableCell>{row.backtest_mape != null ? row.backtest_mape.toFixed(2) : "N/A"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <p className="text-muted-foreground mt-4 text-sm">
        This overview covers the Sales Forecast and Footfall & NOB series computed above. Time-slot footfall/NOB,
        top-product/vendor forecasts, and promo effectiveness each have their own model leaderboard and backtest view on
        their own tabs.
      </p>
    </Section>
  );
}
