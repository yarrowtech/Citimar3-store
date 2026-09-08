import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

// Shared "view / dimension" dropdown for the mode-toggled Historical Analytics
// charts (Sales Performance, Customer & Conversion). The option `value`s mirror
// the `dimension` query param the backend's chart/table routes expect
// (api/routes_charts.py's CHART_TYPE_ENABLED comment block).
export function DimensionSelect<T extends string>({
  value,
  onChange,
  options,
  className = "w-64",
}: {
  value: T;
  onChange: (v: T) => void;
  options: readonly { value: T; label: string }[];
  className?: string;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as T)}>
      <SelectTrigger className={className}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
