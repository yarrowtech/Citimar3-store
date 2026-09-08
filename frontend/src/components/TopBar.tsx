import { motion } from "framer-motion";
import { FileOutput, LogOut, Moon, PanelRightClose, PanelRightOpen, Sparkles, Sun, UserRound } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import citimartLogo from "@/assets/citimart-logo.png";

interface TopBarProps {
  activeStores: string[];
  dateRange: string;
  lastRefresh: string;
  panelOpen: boolean;
  onTogglePanel: () => void;
  showPanelToggle?: boolean;
  showReportButton?: boolean;
  onOpenReport?: () => void;
  username?: string;
  roleLabel?: string;
  onSignOut?: () => void;
}

// Light -> Dark -> Neon -> Light. Uses `theme` (the explicit choice), not
// `resolvedTheme`, so cycling is deterministic; falls back to "light" for the
// unresolved / "system" state.
const THEME_CYCLE = ["light", "dark", "neon"] as const;
const THEME_META: Record<(typeof THEME_CYCLE)[number], { label: string; Icon: typeof Sun }> = {
  light: { label: "Light", Icon: Sun },
  dark: { label: "Dark", Icon: Moon },
  neon: { label: "Neon", Icon: Sparkles },
};

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const current = (THEME_CYCLE as readonly string[]).includes(theme ?? "") ? (theme as (typeof THEME_CYCLE)[number]) : "light";
  const next = THEME_CYCLE[(THEME_CYCLE.indexOf(current) + 1) % THEME_CYCLE.length];
  const { Icon } = THEME_META[current];

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={`Theme: ${THEME_META[current].label} — switch to ${THEME_META[next].label}`}
      title={`Theme: ${THEME_META[current].label} — switch to ${THEME_META[next].label}`}
      className="text-slate-300 hover:bg-white/10 hover:text-white"
      onClick={() => setTheme(next)}
    >
      {mounted ? <Icon className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

export function TopBar({
  activeStores,
  dateRange,
  lastRefresh,
  panelOpen,
  onTogglePanel,
  showPanelToggle = true,
  showReportButton = false,
  onOpenReport,
  username,
  roleLabel,
  onSignOut,
}: TopBarProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="topbar flex items-start justify-between bg-[#0f172a] px-6 py-3.5 text-white"
    >
      <div className="flex items-center gap-3">
        <img src={citimartLogo} alt="CitiMart" className="h-10 w-auto rounded bg-white/95 p-1" />
        <div>
          <h1 className="text-xl font-bold">
            <span className="text-blue-300">CITIMART™</span> SALES KPI DASHBOARD REPORT
          </h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-slate-300">
            <span className="inline-flex items-center gap-1.5" title="Dashboard is live on the current workbook">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              <span className="font-semibold text-emerald-300">Live</span>
            </span>
            &nbsp;|&nbsp; Active stores: {activeStores.join(", ") || "—"} &nbsp;|&nbsp; Reporting period: {dateRange} &nbsp;|&nbsp;
            Last workbook refresh: {lastRefresh}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1">
        {showReportButton && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Export report"
            title="Export Report"
            className="text-slate-300 hover:bg-white/10 hover:text-white"
            onClick={onOpenReport}
          >
            <FileOutput className="h-4 w-4" />
          </Button>
        )}
        {showPanelToggle && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={panelOpen ? "Hide filter panel" : "Show filter panel"}
            className="text-slate-300 hover:bg-white/10 hover:text-white"
            onClick={onTogglePanel}
          >
            {panelOpen ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
          </Button>
        )}
        <ThemeToggle />

        {username && (
          <div className="ml-2 flex items-center gap-2 border-l border-white/15 pl-3">
            <span className="hidden items-center gap-1.5 text-xs text-slate-300 sm:flex">
              <UserRound className="h-3.5 w-3.5" />
              <span className="font-medium text-white">{username}</span>
              {roleLabel && <span className="text-slate-400">· {roleLabel}</span>}
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Sign out"
              title="Sign out"
              className="text-slate-300 hover:bg-white/10 hover:text-white"
              onClick={onSignOut}
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </motion.header>
  );
}
