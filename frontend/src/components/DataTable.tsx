import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Download } from "lucide-react";

import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { filterQueryKey } from "@/lib/filterParams";
import { fmtCell } from "@/lib/format";
import type { FilterState } from "@/lib/types";

interface DataTableProps {
  tableId: string;
  filters: FilterState;
  extra?: Record<string, string | number | undefined>;
  title?: string;
  showDownload?: boolean;
  /** Display-only header relabels, keyed by the raw backend column name. The
   * raw name is still what drives `fmtCell`'s currency/percent formatting. */
  columnLabels?: Record<string, string>;
}

export function DataTable({ tableId, filters, extra = {}, title, showDownload = true, columnLabels }: DataTableProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["table", tableId, filterQueryKey(filters, extra)],
    queryFn: () => api.table(tableId, filters, extra),
    placeholderData: keepPreviousData,
  });

  if (isLoading) return <Skeleton className="h-40 w-full rounded-lg" />;
  if (!data || data.rows.length === 0) {
    return <div className="text-muted-foreground p-6 text-center text-sm">No data available for the selected filters</div>;
  }

  return (
    <div>
      {(title || showDownload) && (
        <div className="mb-2 flex items-center justify-between">
          {title && <h3 className="font-semibold">{title}</h3>}
          {showDownload && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.location.assign(api.tableCsvUrl(tableId, filters, extra))}
            >
              <Download className="h-3.5 w-3.5" /> CSV
            </Button>
          )}
        </div>
      )}
      <motion.div
        key={data.rows.length}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        className="overflow-x-auto rounded-lg border"
      >
        <Table>
          <TableHeader>
            <TableRow>
              {data.columns.map((col) => (
                <TableHead key={col} className="whitespace-nowrap">
                  {columnLabels?.[col] ?? col}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((row, i) => (
              <TableRow key={i}>
                {data.columns.map((col) => (
                  <TableCell key={col} className="whitespace-nowrap">
                    {fmtCell(col, row[col])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </motion.div>
    </div>
  );
}
