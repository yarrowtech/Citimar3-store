import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";

import { forecastApi } from "@/api/forecastClient";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtCell, fmtNumber } from "@/lib/format";

type Params = Record<string, string | number | undefined>;

interface ForecastDataTableProps {
  tableId: string;
  params: Params;
  title?: string;
  showDownload?: boolean;
  enabled?: boolean;
  /** Columns to always render as plain counts (fmtNumber), overriding fmtCell's
   * name-based currency heuristic -- needed because "point"/"lower"/"upper" mean
   * currency on the sales-forecast table but a footfall/NOB count on the
   * footfall-forecast table, and fmtCell has no per-table context to tell them apart. */
  plainNumberKeys?: string[];
}

function sortedKey(params: Params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => a.localeCompare(b));
}

/** Near-duplicate of components/DataTable.tsx, sourcing from
 * /api/forecast-tables/{tableId} instead of /api/tables/{tableId}. */
export function ForecastDataTable({
  tableId,
  params,
  title,
  showDownload = true,
  enabled = true,
  plainNumberKeys,
}: ForecastDataTableProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["forecast-table", tableId, sortedKey(params)],
    queryFn: () => forecastApi.forecastTable(tableId, params),
    enabled,
  });

  if (!enabled) return null;
  if (isLoading) return <Skeleton className="h-40 w-full rounded-lg" />;
  if (!data || data.rows.length === 0) {
    return <div className="text-muted-foreground p-6 text-center text-sm">No data available yet.</div>;
  }

  return (
    <div>
      {(title || showDownload) && (
        <div className="mb-2 flex items-center justify-between">
          {title && <h3 className="font-semibold">{title}</h3>}
          {showDownload && (
            <Button variant="outline" size="sm" onClick={() => window.location.assign(forecastApi.forecastTableCsvUrl(tableId, params))}>
              <Download className="h-3.5 w-3.5" /> CSV
            </Button>
          )}
        </div>
      )}
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              {data.columns.map((col) => (
                <TableHead key={col} className="whitespace-nowrap">
                  {col}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.rows.map((row, i) => (
              <TableRow key={i}>
                {data.columns.map((col) => (
                  <TableCell key={col} className="whitespace-nowrap">
                    {plainNumberKeys?.includes(col) ? fmtNumber(row[col] as number | null | undefined) : fmtCell(col, row[col])}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
