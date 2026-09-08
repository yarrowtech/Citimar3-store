import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtNumber, fmtPercent, KPI_FORMATTERS, KPI_LABELS, KPI_ORDER } from "@/lib/format";
import type { KpiBundle, KpiDelta } from "@/lib/types";

interface KpiTableProps {
  kpis: KpiBundle;
  deltas: Partial<Record<keyof KpiBundle, KpiDelta>>;
}

/** The "View KPI Table" toggle. Every row is formatted using ITS OWN kpi's
 * formatter (KPI_FORMATTERS[key]), not a shared per-column rule -- that bug
 * in the old vanilla-JS frontend forced Bill Quantity/Footfall/NOB/Basket
 * Size/Conversion %/Achievement %/Return Units into ₹ currency formatting
 * regardless of what the row actually was. */
export function KpiTable({ kpis, deltas }: KpiTableProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-card rounded-xl border p-4">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={() => setOpen((o) => !o)}>
          {open ? "Hide" : "View"} KPI Table
        </Button>
      </div>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-3 overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>KPI</TableHead>
                    <TableHead>Current value</TableHead>
                    <TableHead>Previous-period value</TableHead>
                    <TableHead>Absolute variance</TableHead>
                    <TableHead>Percentage variance</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {KPI_ORDER.map((key) => {
                    const formatter = KPI_FORMATTERS[key] ?? fmtNumber;
                    const delta = deltas[key];
                    return (
                      <TableRow key={key}>
                        <TableCell>{KPI_LABELS[key]}</TableCell>
                        <TableCell>{formatter(kpis[key])}</TableCell>
                        <TableCell>{delta ? formatter(delta.previous) : "N/A"}</TableCell>
                        <TableCell>{delta ? formatter(delta.absolute_variance) : "N/A"}</TableCell>
                        <TableCell>{delta ? fmtPercent(delta.percentage_variance) : "N/A"}</TableCell>
                        <TableCell>
                          <StatusBadge status={delta?.status} />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
