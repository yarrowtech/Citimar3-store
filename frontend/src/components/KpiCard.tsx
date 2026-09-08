import { animate, motion, useMotionValue } from "framer-motion";
import { Info, TrendingDown, TrendingUp } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import type { KpiDelta, StatusColor } from "@/lib/types";

const BORDER_BY_STATUS: Record<StatusColor, string> = {
  red: "border-l-status-red",
  yellow: "border-l-status-yellow",
  green: "border-l-status-green",
};

interface KpiCardProps {
  label: string;
  value: number | null | undefined;
  formatter: (v: number | null | undefined) => string;
  formula: string;
  status?: StatusColor | null;
  delta?: KpiDelta;
  index: number;
  /** Executive Overview only: the admin's <ThresholdPopover> gear, slotted into
   * the card's top-right control cluster next to the (i) button. */
  thresholdControl?: ReactNode;
}

/** Counts the displayed number up from 0 to `value` on first mount / whenever
 * `value` changes (filter change, refetch) -- the "dynamic indicator" polish
 * requested for the KPI cards. Non-numeric values (N/A) skip the tween. */
function useCountUp(value: number | null | undefined, formatter: (v: number | null | undefined) => string): string {
  const motionValue = useMotionValue(0);
  const [display, setDisplay] = useState(() => formatter(value));

  useEffect(() => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      setDisplay(formatter(value));
      return;
    }
    const controls = animate(motionValue, value, {
      duration: 0.8,
      ease: "easeOut",
      onUpdate: (v) => setDisplay(formatter(v)),
    });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return display;
}

export function KpiCard({
  label,
  value,
  formatter,
  formula,
  status,
  delta,
  index,
  thresholdControl,
}: KpiCardProps) {
  const pct = delta?.percentage_variance;
  const hasDelta = pct !== null && pct !== undefined;
  const isUp = hasDelta && pct > 0;
  const isDown = hasDelta && pct < 0;
  const display = useCountUp(value, formatter);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -3 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: Math.min(index, 12) * 0.03 }}
      className={cn(
        "bg-card relative rounded-xl border border-l-4 p-4 transition-shadow duration-200 hover:shadow-md",
        status ? BORDER_BY_STATUS[status] : "border-l-border",
      )}
    >
      {/* Below-threshold KPIs are marked by the static status border alone
          (BORDER_BY_STATUS above) -- an earlier version also pulsed a red
          glow on an infinite loop to draw the eye, but that read as an
          unwanted "blinking" card rather than a calm attention cue, so the
          highlight is static now. */}
      <div className="absolute top-2 right-2 flex items-center gap-1">
        {thresholdControl}
        {/* The formula used to print openly under every card; it now lives
            behind this info button so the card face stays uncluttered. */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={`${label} formula`}
              className="text-muted-foreground/70 hover:text-foreground rounded p-0.5 transition-colors"
            >
              <Info className="h-3.5 w-3.5" />
            </button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-64">
            <div className="text-xs font-semibold tracking-wide uppercase">{label}</div>
            <div className="font-mono text-xs">{formula}</div>
          </PopoverContent>
        </Popover>
      </div>

      <div className="text-muted-foreground pr-12 text-xs font-semibold tracking-wide uppercase">{label}</div>
      <div className="mt-1 font-mono text-xl font-bold tabular-nums">{display}</div>
      {hasDelta && (
        <div
          className={cn(
            "mt-1 flex items-center gap-1 font-mono text-xs font-medium tabular-nums",
            isUp && "text-status-green",
            isDown && "text-status-red",
            !isUp && !isDown && "text-muted-foreground",
          )}
        >
          {(isUp || isDown) && (
            <motion.span
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ type: "spring", stiffness: 500, damping: 15, delay: Math.min(index, 12) * 0.03 + 0.2 }}
              className="inline-flex"
            >
              {isUp ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
            </motion.span>
          )}
          {Math.round(Math.abs(pct))}% vs prev period
        </div>
      )}
    </motion.div>
  );
}
