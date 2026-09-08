import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { forecastApi } from "@/api/forecastClient";
import type { AnyForecastStatus, ForecastKind, ForecastStatus } from "@/lib/forecastTypes";

type Params = Record<string, string | number | undefined>;

function sortedKey(params: Params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => a.localeCompare(b));
}

/** The React equivalent of streamlit_forecast_app.py's cached_result_with_button:
 * a status check that never computes, plus an explicit compute trigger the
 * caller fires via `run()`. Every forecast kind (sales/footfall/products/
 * vendors) is gated this way -- see the plan doc for why even the "cheap"
 * single-series kinds are gated in the SPA, not just the expensive multi-
 * series ones like in Streamlit. */
export function useGatedForecast<TStatus extends AnyForecastStatus = ForecastStatus>(
  kind: ForecastKind,
  params: Params,
  options: { autoRun?: boolean } = {},
) {
  const queryClient = useQueryClient();
  const statusKey = ["forecast-status", kind, sortedKey(params)] as const;

  const statusQuery = useQuery({ queryKey: statusKey, queryFn: () => forecastApi.status<TStatus>(kind, params) });

  const computeMutation = useMutation({
    mutationFn: () => forecastApi.compute<TStatus>(kind, params),
    onSuccess: (data: TStatus) => {
      queryClient.setQueryData(statusKey, data);
      queryClient.invalidateQueries({ queryKey: ["forecast-chart"] });
      queryClient.invalidateQueries({ queryKey: ["forecast-table"] });
    },
  });

  const computed = statusQuery.data?.computed ?? false;

  // Effect, not an inline call during render -- mutate() is a side effect
  // and must not run in the render body (React 18 double-invocation under
  // StrictMode would fire it twice). autoRun defaults unset everywhere in
  // this app (always button-gated), so this path is inert unless opted into.
  useEffect(() => {
    if (options.autoRun && statusQuery.isSuccess && !computed && !computeMutation.isPending && !computeMutation.isSuccess) {
      computeMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.autoRun, statusQuery.isSuccess, computed]);

  return {
    status: statusQuery.data,
    isStatusLoading: statusQuery.isLoading,
    computed,
    isComputing: computeMutation.isPending,
    computeError: computeMutation.error,
    run: () => computeMutation.mutate(),
  };
}
