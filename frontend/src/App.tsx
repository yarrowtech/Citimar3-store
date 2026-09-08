import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { DAILY_STORE_ID_BY_CODE } from "@/lib/authUsers";
import { FilterPanel } from "@/components/FilterPanel";
import { TopBar } from "@/components/TopBar";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { emptyFilterState } from "@/lib/filterParams";
import type { FilterState } from "@/lib/types";
import { CustomerConversion } from "@/pages/CustomerConversion";
import { DataQuality } from "@/pages/DataQuality";
import { DetailedTables } from "@/pages/DetailedTables";
import { ExecutiveOverview } from "@/pages/ExecutiveOverview";
import { Forecast } from "@/pages/Forecast";
import { ManualEntryCHW, ManualEntryHB, ManualEntryNM } from "@/pages/ManualEntryDashboard";
import { OverallStoresSummary } from "@/pages/OverallStoresSummary";
import { ProductBrand } from "@/pages/ProductBrand";
import { ProfitPromotions } from "@/pages/ProfitPromotions";
import { ReportBuilder } from "@/pages/ReportBuilder";
import { SalesPerformance } from "@/pages/SalesPerformance";
import { SalesTargetCHW, SalesTargetHB, SalesTargetNM } from "@/pages/SalesTargetEntry";
import { DailyDashboardCHW, DailyDashboardHB, DailyDashboardNM } from "@/pages/StoreDailyDashboard";

// Part 1 (Daily Operations) is its own 3-level nav: store -> Dashboard /
// Manual Data Entry / Sales Target -- each lives *under* its store, not as a
// sibling tab, since it's only ever meaningful for that one store. "Manual
// Data Entry" is manager-only (the admin logs nothing); "Sales Target"
// (monthly SALES TARGET entry) is admin-only. The admin also gets an
// "Overall Stores Summary" pseudo-store, first in the list, blending all
// three stores' live daily KPIs.
const DAILY_STORES = [
  { id: "nm", label: "New Market", dashboard: DailyDashboardNM, manualEntry: ManualEntryNM, salesTarget: SalesTargetNM },
  { id: "hb", label: "Hatibagan", dashboard: DailyDashboardHB, manualEntry: ManualEntryHB, salesTarget: SalesTargetHB },
  { id: "chw", label: "Chowringhee", dashboard: DailyDashboardCHW, manualEntry: ManualEntryCHW, salesTarget: SalesTargetCHW },
] as const;
type DailyStoreId = (typeof DAILY_STORES)[number]["id"];
const OVERALL_STORE_ID = "overall" as const;
type DailyStoreSel = DailyStoreId | typeof OVERALL_STORE_ID;
type DailyView = "dashboard" | "manual" | "target";

// Parts 2 and 3 stay flat single-level tab lists -- they're plain
// DATASET.xlsx-driven pages that all share the sidebar's filters.
const HISTORICAL_TABS = [
  { id: "overview", label: "Executive Overview", content: ExecutiveOverview },
  { id: "sales", label: "Sales Performance", content: SalesPerformance },
  { id: "conversion", label: "Customer & Conversion", content: CustomerConversion },
  { id: "product", label: "Product & Brand", content: ProductBrand },
  { id: "profit", label: "Profit & Promotions", content: ProfitPromotions },
  { id: "detailed", label: "Detailed Tables", content: DetailedTables },
  { id: "dataquality", label: "Data Quality", content: DataQuality },
] as const;
const FORECAST_TABS = [{ id: "forecast", label: "Forecast", content: Forecast }] as const;
export type HistoricalTabId = (typeof HISTORICAL_TABS)[number]["id"];

const PARTS = [
  { id: "daily", label: "Daily Operations" },
  { id: "historical", label: "Historical Analytics" },
  { id: "forecast", label: "Forecast & Analysis" },
] as const;
type PartId = (typeof PARTS)[number]["id"];

export default function App() {
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  // A store manager only ever sees their own store's Daily Operations. The
  // admin sees the full three-part nav.
  const isManager = user?.role === "manager";
  const forcedStore: DailyStoreId | undefined = user?.storeCode
    ? DAILY_STORE_ID_BY_CODE[user.storeCode]
    : undefined;
  const isAdmin = user?.role === "admin";

  const { data: defaults } = useQuery({
    queryKey: ["filters", "defaults"],
    queryFn: api.filterDefaults,
    enabled: isAdmin, // /api/filters/* is admin-only
  });
  const { data: meta } = useQuery({ queryKey: ["meta"], queryFn: api.meta });

  const [filters, setFilters] = useState<FilterState>(emptyFilterState());
  const [initialized, setInitialized] = useState(false);
  const [partId, setPartId] = useState<PartId>("daily");
  const [dailyStore, setDailyStore] = useState<DailyStoreSel>(OVERALL_STORE_ID);
  const [dailyView, setDailyView] = useState<DailyView>("dashboard");
  const [historicalTab, setHistoricalTab] = useState<HistoricalTabId>(HISTORICAL_TABS[0].id);
  const [panelOpen, setPanelOpen] = useState(true);
  const [reportOpen, setReportOpen] = useState(false);

  useEffect(() => {
    if (!isAdmin) {
      // Managers don't hit /api/filters/defaults; seed a minimal filter state.
      if (!initialized) setInitialized(true);
      return;
    }
    if (defaults && !initialized) {
      setFilters({
        ...emptyFilterState(),
        stores: defaults.stores,
        start: defaults.start_date ?? "",
        end: defaults.end_date ?? "",
      });
      setInitialized(true);
    }
  }, [defaults, initialized, isAdmin]);

  // Force a manager's nav to their one store's Daily Operations.
  const effectivePart: PartId = isManager ? "daily" : partId;
  const effectiveDailyStore: DailyStoreSel = isManager && forcedStore ? forcedStore : dailyStore;
  const isOverallDaily = effectivePart === "daily" && effectiveDailyStore === OVERALL_STORE_ID;

  if (!initialized) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Skeleton className="h-10 w-64" />
      </div>
    );
  }

  // The sidebar filter panel (store/date/product hierarchy) only applies to
  // the DATASET.xlsx-driven Parts 2 and 3 -- Part 1's pages pin their own
  // store and "today" internally, so the panel would have nothing to do there.
  const panelApplies = effectivePart !== "daily";

  // "Manual Data Entry" is manager-only and "Sales Target" is admin-only --
  // fall back to the Dashboard if the other role ever lands on that state.
  const effectiveDailyView: DailyView =
    (isAdmin && dailyView === "manual") || (!isAdmin && dailyView === "target") ? "dashboard" : dailyView;

  const dailyStoreEntry = isOverallDaily ? undefined : DAILY_STORES.find((s) => s.id === effectiveDailyStore);
  const ActivePage =
    effectivePart === "daily"
      ? isOverallDaily
        ? OverallStoresSummary
        : effectiveDailyView === "dashboard"
          ? dailyStoreEntry!.dashboard
          : effectiveDailyView === "manual"
            ? dailyStoreEntry!.manualEntry
            : dailyStoreEntry!.salesTarget
      : effectivePart === "historical"
        ? HISTORICAL_TABS.find((t) => t.id === historicalTab)!.content
        : FORECAST_TABS[0].content;
  const animationKey =
    effectivePart === "daily"
      ? `daily-${effectiveDailyStore}-${isOverallDaily ? "overall" : effectiveDailyView}`
      : effectivePart === "historical"
        ? `historical-${historicalTab}`
        : "forecast";

  if (reportOpen && effectivePart === "historical") {
    const activeTabLabel = HISTORICAL_TABS.find((t) => t.id === historicalTab)!.label;
    return <ReportBuilder filters={filters} tabId={historicalTab} tabLabel={activeTabLabel} onClose={() => setReportOpen(false)} />;
  }

  return (
    <div className="bg-background min-h-screen">
      <TopBar
        activeStores={meta?.store_names ?? []}
        dateRange={meta?.date_range ?? ""}
        lastRefresh={meta?.last_refresh ?? ""}
        panelOpen={panelOpen}
        onTogglePanel={() => setPanelOpen((o) => !o)}
        showPanelToggle={panelApplies}
        showReportButton={effectivePart === "historical"}
        onOpenReport={() => setReportOpen(true)}
        username={user?.username}
        roleLabel={isAdmin ? "Administrator" : user?.storeCode ? `Manager · ${user.storeCode}` : "Manager"}
        onSignOut={async () => {
          await signOut();
          navigate("/", { replace: true });
        }}
      />

      <div className="flex items-start gap-4 p-5">
        <main className="min-w-0 flex-1">
          {!isManager && (
            <Tabs value={effectivePart} onValueChange={(v) => setPartId(v as PartId)} className="mb-3 items-center">
              <TabsList className="h-auto flex-wrap">
                {PARTS.map((p) => (
                  <TabsTrigger key={p.id} value={p.id} className="font-semibold">
                    {p.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          )}

          {effectivePart === "daily" && (
            <>
              {!isManager && (
                <Tabs value={effectiveDailyStore} onValueChange={(v) => setDailyStore(v as DailyStoreSel)} className="mb-3">
                  <TabsList variant="line" className="h-auto flex-wrap">
                    <TabsTrigger value={OVERALL_STORE_ID}>Overall Stores Summary</TabsTrigger>
                    {DAILY_STORES.map((s) => (
                      <TabsTrigger key={s.id} value={s.id}>
                        {s.label}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                </Tabs>
              )}

              {!isOverallDaily && (
                <Tabs value={effectiveDailyView} onValueChange={(v) => setDailyView(v as DailyView)} className="mb-4">
                  <TabsList className="h-auto flex-wrap">
                    <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
                    {!isAdmin && <TabsTrigger value="manual">Manual Data Entry</TabsTrigger>}
                    {isAdmin && <TabsTrigger value="target">Sales Target</TabsTrigger>}
                  </TabsList>
                </Tabs>
              )}
            </>
          )}

          {effectivePart === "historical" && (
            <Tabs value={historicalTab} onValueChange={(v) => setHistoricalTab(v as HistoricalTabId)} className="mb-4">
              <TabsList variant="line" className="h-auto flex-wrap">
                {HISTORICAL_TABS.map((t) => (
                  <TabsTrigger key={t.id} value={t.id}>
                    {t.label}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          )}

          <AnimatePresence mode="wait">
            <motion.div
              key={animationKey}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.15 }}
            >
              <ActivePage filters={filters} />
            </motion.div>
          </AnimatePresence>
        </main>

        {panelApplies && <FilterPanel applied={filters} onApply={setFilters} onReset={setFilters} open={panelOpen} />}
      </div>

      <Toaster />
    </div>
  );
}
