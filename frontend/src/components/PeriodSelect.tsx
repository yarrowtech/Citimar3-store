import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// The day/week/month/quarter/year selector shared by every Historical Analytics
// chart/table that supports period switching (Historical Analytics Overhaul).
// Values match src/period_engine.py's PERIODS and the `granularity` query param.
export const PERIODS = ["day", "week", "month", "quarter", "year"] as const;
export type Period = (typeof PERIODS)[number];

const LABELS: Record<Period, string> = {
  day: "Day",
  week: "Week",
  month: "Month",
  quarter: "Quarter",
  year: "Year",
};

export function PeriodSelect({
  value,
  onChange,
  className = "w-32",
}: {
  value: Period;
  onChange: (value: Period) => void;
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as Period)}>
      <SelectTrigger className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {PERIODS.map((p) => (
          <SelectItem key={p} value={p}>
            {LABELS[p]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
