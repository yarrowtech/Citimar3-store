import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";

import { api } from "@/api/client";
import { Section } from "@/components/Section";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtNumber } from "@/lib/format";

function DqTile({ label, value, index }: { label: string; value: string; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: Math.min(index, 14) * 0.02 }}
      className="bg-card rounded-lg border px-3 py-2.5"
    >
      <div className="text-muted-foreground text-[11.5px] tracking-wide uppercase">{label}</div>
      <div className="text-base font-bold">{value}</div>
    </motion.div>
  );
}

export function DataQuality() {
  const { data, isLoading } = useQuery({ queryKey: ["data-quality"], queryFn: api.dataQuality });

  if (isLoading || !data) {
    return (
      <Section title="Data Quality Panel">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2.5">
          {Array.from({ length: 16 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
      </Section>
    );
  }

  const hierarchyLabel =
    Object.entries(data.product_hierarchy_values_nulled)
      .map(([field, count]) => `${field}: ${fmtNumber(count)}`)
      .join(" · ") || "None";

  const rows: [string, string][] = [
    ["Worksheets loaded", data.worksheets_loaded.join(", ") || "None"],
    ["Worksheets skipped", data.worksheets_skipped.join(", ") || "None"],
    ["Total rows before cleaning", fmtNumber(data.total_rows_before_cleaning)],
    ["Rows retained after cleaning", fmtNumber(data.rows_retained_after_cleaning)],
    ["Date range", data.date_range ? data.date_range.join(" – ") : "N/A"],
    ["Missing date count", fmtNumber(data.missing_date_count)],
    ["Missing product count", fmtNumber(data.missing_product_count)],
    ["Missing department count", fmtNumber(data.missing_department_count)],
    ["Invalid sales count", fmtNumber(data.invalid_sales_count)],
    ["Duplicate transaction rows dropped", fmtNumber(data.duplicate_transaction_count)],
    ["Zero-amount duplicate lines flagged", fmtNumber(data.zero_amount_duplicate_flagged_count)],
    ["Negative sales / return rows", fmtNumber(data.negative_sales_or_return_count)],
    ["Missing cost count", fmtNumber(data.missing_cost_count)],
    ["Missing target count", fmtNumber(data.missing_target_count)],
    ["Missing footfall count", fmtNumber(data.missing_footfall_count)],
    ["Dates with target/footfall but no sales", data.unmatched_dates_target_only.join(", ") || "None"],
    ["Product hierarchy values nulled (Years/Numeric contamination)", hierarchyLabel],
    ["Tax rate outlier rows (not a valid GST slab)", fmtNumber(data.tax_rate_outlier_rows)],
    ["Rows with unmapped store", fmtNumber(data.unmapped_store_rows)],
  ];

  return (
    <Section title="Data Quality Panel">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-2.5">
        {rows.map(([label, value], i) => (
          <DqTile key={label} label={label} value={value} index={i} />
        ))}
      </div>
    </Section>
  );
}
