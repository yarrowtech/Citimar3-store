import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// Curated mark types the backend's charts.apply_chart_type can render. "column"
// = vertical bars (the usual default). "bar3d" is live-view only -- it must
// never be pinned into a report manifest (Kaleido 3D rasterization is
// unreliable server-side).
export const CHART_TYPES = ["column", "bar", "line", "area", "pie", "bar3d"] as const;
export type ChartType = (typeof CHART_TYPES)[number];

const LABELS: Record<ChartType, string> = {
  column: "Column",
  bar: "Bar",
  line: "Line",
  area: "Area",
  pie: "Pie",
  bar3d: "3D Bar",
};

export function ChartTypeToggle({
  value,
  onChange,
  allowed,
  className = "w-32",
}: {
  value: ChartType;
  onChange: (value: ChartType) => void;
  /** Subset of CHART_TYPES this chart_id supports (api CHART_TYPE_ENABLED). */
  allowed: readonly ChartType[];
  className?: string;
}) {
  if (allowed.length < 2) return null;
  return (
    <Select value={value} onValueChange={(v) => onChange(v as ChartType)}>
      <SelectTrigger className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {allowed.map((t) => (
          <SelectItem key={t} value={t}>
            {LABELS[t]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
