import { useQuery } from "@tanstack/react-query";

import { forecastApi } from "@/api/forecastClient";
import { Section } from "@/components/Section";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtCurrency, fmtNumber, fmtPercent } from "@/lib/format";

interface DailyHuddleProps {
  horizon: number;
  models: string[];
  salesStore: string | undefined;
}

export function DailyHuddle({ horizon, models, salesStore }: DailyHuddleProps) {
  const params = { horizon, models: models.join(","), sales_store: salesStore };

  const { data, isLoading } = useQuery({
    queryKey: ["forecast-huddle", salesStore, horizon, models.join(",")],
    queryFn: () => forecastApi.huddle(params),
  });

  if (isLoading) return <Skeleton className="h-40 w-full rounded-lg" />;

  if (!data?.computed) {
    return (
      <Section title="Daily Huddle Briefing">
        <p className="text-muted-foreground text-sm">
          Not enough history to build a Sales Forecast yet — compute it on the "Sales Forecast &amp; Growth Goals" tab
          first, then this briefing fills in with tomorrow's target.
        </p>
      </Section>
    );
  }

  const { next_day_target, configured_daily_target, engagement, upsell_cross_sell } = data;
  const footfallDelta = engagement?.footfall_delta;

  return (
    <Section title="Daily Huddle Briefing">
      <p className="text-muted-foreground mb-4 text-sm">
        Agenda for this morning's huddle: daily sales target, upselling goals, cross-selling, and engagement.
      </p>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <p className="text-muted-foreground text-xs">1. Daily Sales Target — {next_day_target?.date}</p>
          <p className="text-xl font-semibold">{fmtCurrency(next_day_target?.point)}</p>
          <p className="text-muted-foreground text-xs">
            Model range: {fmtCurrency(next_day_target?.lower)} – {fmtCurrency(next_day_target?.upper)}
            {configured_daily_target != null && <> · Configured target: {fmtCurrency(configured_daily_target)}</>}
          </p>
        </div>

        {engagement && (
          <div>
            <p className="text-muted-foreground text-xs">4. Engagement — trailing {engagement.window_days} days</p>
            <p className="text-xl font-semibold">{fmtPercent(engagement.conversion_pct)} conversion</p>
            <p className="text-muted-foreground text-xs">
              {fmtNumber(engagement.footfall)} footfall
              {footfallDelta != null && (
                <>
                  {" "}
                  ({footfallDelta >= 0 ? "+" : ""}
                  {fmtNumber(footfallDelta)} vs prior {engagement.window_days}d)
                </>
              )}
            </p>
          </div>
        )}
      </div>

      <div className="mt-6">
        <h4 className="mb-1 font-semibold">2 &amp; 3. Upselling Goals / Cross-Selling Pairs</h4>
        <p className="text-muted-foreground mb-3 text-sm">
          Push each weak performer today — anchor the pitch on its strong-performer partner from the same category.
        </p>
        {!upsell_cross_sell || upsell_cross_sell.length === 0 ? (
          <p className="text-muted-foreground text-sm">No pairing data available for the selected stores.</p>
        ) : (
          <ul className="space-y-2">
            {upsell_cross_sell.map((pair) => (
              <li key={`${pair.category}-${pair.rank}`} className="rounded-lg border p-3 text-sm">
                <span className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">{pair.category}</span>
                <div>
                  Upsell <strong>{pair.weak_product ?? pair.weak_item_code}</strong> by pairing with strong seller{" "}
                  <strong>{pair.strong_product ?? pair.strong_item_code}</strong>
                  <span className="text-muted-foreground"> ({fmtPercent(pair.gap_pct)} gap)</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}
