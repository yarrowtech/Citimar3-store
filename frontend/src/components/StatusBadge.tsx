import { cn } from "@/lib/utils";
import type { StatusColor } from "@/lib/types";

const STYLES: Record<StatusColor, string> = {
  red: "bg-status-red-bg text-status-red",
  yellow: "bg-status-yellow-bg text-status-yellow",
  green: "bg-status-green-bg text-status-green",
};

export function StatusBadge({ status }: { status: StatusColor | null | undefined }) {
  if (!status) return <span className="text-muted-foreground">—</span>;
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-xs font-bold capitalize", STYLES[status])}>{status}</span>
  );
}
