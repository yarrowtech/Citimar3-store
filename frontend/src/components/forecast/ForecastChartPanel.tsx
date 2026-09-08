import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useTheme } from "next-themes";
import type { Layout, PlotData } from "plotly.js-dist-min";
import { useMemo, useState } from "react";

import { forecastApi } from "@/api/forecastClient";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { deriveTableFromFigure } from "@/lib/chartTable";
import { fmtNumber } from "@/lib/format";
import Plot from "@/lib/Plot";

type Params = Record<string, string | number | undefined>;

interface ForecastChartPanelProps {
  chartId: string;
  params: Params;
  className?: string;
  /** Skip the fetch entirely while the underlying series isn't computed yet
   * -- an optimization, not a correctness requirement: an uncomputed
   * forecast-chart already degrades to a normal "no data" figure server-side. */
  enabled?: boolean;
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "N/A";
  if (typeof v === "number") return fmtNumber(v);
  return String(v);
}

function sortedKey(params: Params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => a.localeCompare(b));
}

/** Near-duplicate of components/ChartPanel.tsx, sourcing from
 * /api/forecast-charts/{chartId} instead of /api/charts/{chartId} --
 * forecast params have no date-range/product-hierarchy shape to reuse
 * ChartPanel's FilterState-typed plumbing. */
export function ForecastChartPanel({ chartId, params, className, enabled = true }: ForecastChartPanelProps) {
  const [showTable, setShowTable] = useState(false);
  const { theme } = useTheme();
  // "neon" recolours the server figure via src/theme.py; any other theme omits
  // ?theme so the response is unchanged.
  const themedParams = useMemo(
    () => (theme === "neon" ? { ...params, theme: "neon" } : params),
    [params, theme],
  );
  const { data, isLoading, isError } = useQuery({
    queryKey: ["forecast-chart", chartId, sortedKey(themedParams)],
    queryFn: () => forecastApi.forecastChart(chartId, themedParams),
    enabled,
    placeholderData: keepPreviousData,
  });

  const table = useMemo(() => {
    try {
      return deriveTableFromFigure(data?.data, data?.layout);
    } catch {
      return null;
    }
  }, [data]);

  if (!enabled) {
    return null;
  }
  if (isLoading) {
    return <Skeleton className={className ?? "h-[460px] w-full rounded-lg"} />;
  }
  if (isError || !data) {
    return (
      <div className={`text-muted-foreground flex items-center justify-center text-sm ${className ?? "h-[460px]"}`}>
        Failed to load chart.
      </div>
    );
  }

  return (
    <div>
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        whileHover={{ y: -2 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className={`transition-shadow duration-200 hover:shadow-md ${className ?? ""}`}
      >
        <Plot
          data={data.data as PlotData[]}
          layout={{ ...(data.layout as Partial<Layout>), autosize: true }}
          useResizeHandler
          style={{ width: "100%", height: "100%" }}
          config={{ responsive: true, displaylogo: false }}
        />
      </motion.div>

      {table && table.rows.length > 0 && (
        <>
          <div className="mt-2 flex justify-end">
            <Button variant="outline" size="sm" onClick={() => setShowTable((o) => !o)}>
              {showTable ? "Hide" : "View"} Table
            </Button>
          </div>
          <AnimatePresence initial={false}>
            {showTable && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden"
              >
                <div className="mt-2 max-h-80 overflow-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {table.columns.map((col) => (
                          <TableHead key={col} className="whitespace-nowrap">
                            {col}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {table.rows.map((row, i) => (
                        <TableRow key={i}>
                          {table.columns.map((col) => (
                            <TableCell key={col} className="whitespace-nowrap">
                              {formatCell(row[col])}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </>
      )}
    </div>
  );
}
