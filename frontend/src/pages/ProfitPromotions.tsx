import { useState } from "react";

import { ChartPanel } from "@/components/ChartPanel";
import { DataTable } from "@/components/DataTable";
import { PeriodSelect, type Period } from "@/components/PeriodSelect";
import { Section } from "@/components/Section";
import type { FilterState } from "@/lib/types";

// Display-only header relabels; raw column names still drive fmtCell formatting.
const DISCOUNT_LABELS: Record<string, string> = {
  segment: "Segment",
  Date: "Period",
  net_sales: "Net Sales",
  bill_quantity: "Bill Quantity",
  transactions: "Transactions",
  atv: "ATV",
  rpv: "RPV",
  basket_size: "Basket Size",
  achievement_pct: "Achievement %",
};

const PROMO_LABELS: Record<string, string> = {
  promo_type: "Promo Type",
  promo_names: "Distinct Promos",
  promo_amount: "Promo Amount",
  discount_amount: "Discount Amount",
  net_sales: "Net Sales",
  transactions: "Transactions",
  quantity: "Quantity",
  atv: "ATV",
};

export function ProfitPromotions({ filters }: { filters: FilterState }) {
  const [granularity, setGranularity] = useState<Period>("month");

  return (
    <div>
      <Section>
        <div className="mb-2 flex justify-end">
          <PeriodSelect value={granularity} onChange={setGranularity} />
        </div>
        <ChartPanel
          chartId="discount_impact"
          filters={filters}
          extra={{ granularity }}
          className="mb-4 h-[460px] w-full"
        />
        <DataTable
          tableId="discount_impact"
          filters={filters}
          extra={{ granularity }}
          title="Discounted vs Non-Discounted Sales"
          columnLabels={DISCOUNT_LABELS}
          showDownload={false}
        />
      </Section>

      <Section>
        <ChartPanel chartId="promotion_breakdown" filters={filters} className="mb-4 h-[460px] w-full" />
        <DataTable
          tableId="promotion_breakdown"
          filters={filters}
          title="Promotion Breakdown"
          columnLabels={PROMO_LABELS}
          showDownload={false}
        />
      </Section>
    </div>
  );
}
