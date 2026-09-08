import { useState } from "react";

import { ForecastChartPanel } from "@/components/forecast/ForecastChartPanel";
import { ForecastDataTable } from "@/components/forecast/ForecastDataTable";
import { Section } from "@/components/Section";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface PromotionsEffectivenessProps {
  stores: string[];
  topNCampaignsDefault: number;
}

export function PromotionsEffectiveness({ stores, topNCampaignsDefault }: PromotionsEffectivenessProps) {
  const [campaignsTopN, setCampaignsTopN] = useState(topNCampaignsDefault);
  const params = { stores: stores.slice().sort().join(",") };

  return (
    <Section title="Promotions Effectiveness">
      <p className="text-muted-foreground mb-4 text-sm">
        DATASET.xlsx has no forward-looking promo calendar — there is no signal to forecast "which promotions will run
        when." This tab instead measures how much each historical promo type and named campaign lifted sales versus a
        no-promo baseline, to help plan future promotions rather than predict them.
      </p>

      <h4 className="mb-2 font-semibold">Promo Type Effectiveness</h4>
      <ForecastChartPanel chartId="promo-uplift" params={params} className="h-[460px] w-full" />
      <div className="mt-2">
        <ForecastDataTable tableId="promo-uplift" params={params} />
      </div>

      <div className="mt-6 border-t pt-4">
        <h4 className="mb-2 font-semibold">Top Named Campaigns</h4>
        <div className="mb-3 space-y-1.5">
          <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Top N Campaigns</Label>
          <Input
            type="number"
            min={5}
            max={30}
            value={campaignsTopN}
            onChange={(e) => setCampaignsTopN(Number(e.target.value) || topNCampaignsDefault)}
            className="w-32"
          />
        </div>
        <ForecastDataTable tableId="promo-campaigns" params={{ ...params, top_n: campaignsTopN }} />
      </div>
    </Section>
  );
}
