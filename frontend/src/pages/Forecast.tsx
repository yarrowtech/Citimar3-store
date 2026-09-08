import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { forecastApi } from "@/api/forecastClient";
import { Section } from "@/components/Section";
import { MultiSelectField } from "@/components/MultiSelectField";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Backtest } from "@/pages/forecast/Backtest";
import { DailyHuddle } from "@/pages/forecast/DailyHuddle";
import { FootfallForecast } from "@/pages/forecast/FootfallForecast";
import { ForecastOverview } from "@/pages/forecast/ForecastOverview";
import { ProductsForecast } from "@/pages/forecast/ProductsForecast";
import { PromotionsEffectiveness } from "@/pages/forecast/PromotionsEffectiveness";
import { SalesForecast } from "@/pages/forecast/SalesForecast";
import { VendorsForecast } from "@/pages/forecast/VendorsForecast";

const SUB_TABS = [
  { id: "overview", label: "Overview" },
  { id: "huddle", label: "Daily Huddle" },
  { id: "sales", label: "Sales Forecast & Growth Goals" },
  { id: "footfall", label: "Footfall & NOB by Time Slot" },
  { id: "backtest", label: "Actual vs Estimation (Backtest)" },
  { id: "products", label: "Products" },
  { id: "vendors", label: "Vendors" },
  { id: "promotions", label: "Promotions Effectiveness" },
] as const;

export function Forecast() {
  const { data: meta, isLoading: metaLoading } = useQuery({ queryKey: ["forecast-meta"], queryFn: forecastApi.meta });

  const [subTab, setSubTab] = useState<(typeof SUB_TABS)[number]["id"]>("sales");
  const [stores, setStores] = useState<string[]>([]);
  const [horizon, setHorizon] = useState<number>(30);
  const [models, setModels] = useState<string[]>([]);
  const [initialized, setInitialized] = useState(false);

  // Per-sub-tab series pointers, lifted here because Overview and Backtest
  // both need to know exactly which Sales/Footfall selection is in play.
  const [salesStore, setSalesStore] = useState<string | undefined>(undefined);
  const [footfallStore, setFootfallStore] = useState<string | undefined>(undefined);
  const [footfallTimeSlot, setFootfallTimeSlot] = useState<string | undefined>(undefined);
  const [footfallMetric, setFootfallMetric] = useState<string>("footfall");

  useEffect(() => {
    if (meta && !initialized) {
      setStores(meta.active_stores);
      setHorizon(meta.default_horizon);
      setModels(meta.primary_model_roster);
      setFootfallStore(meta.active_stores[0]);
      setInitialized(true);
    }
  }, [meta, initialized]);

  if (metaLoading || !initialized || !meta) {
    return <Skeleton className="h-40 w-full rounded-lg" />;
  }

  return (
    <div>
      <Section title="Forecast Controls">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <MultiSelectField
            label="Store"
            options={meta.active_stores}
            selected={stores}
            onChange={setStores}
            labels={meta.store_names}
          />
          <div className="space-y-1.5">
            <label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Forecast Horizon (days)</label>
            <Select value={String(horizon)} onValueChange={(v) => setHorizon(Number(v))}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {meta.horizon_choices.map((h) => (
                  <SelectItem key={h} value={String(h)}>
                    {h} days
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <MultiSelectField label="Models to Compare" options={meta.primary_model_roster} selected={models} onChange={setModels} />
        </div>
        <p className="text-muted-foreground mt-3 text-sm">
          Only {meta.min_history_days}+ days of history are required, but the current workbook spans a single calendar year --
          there is no learnable yearly seasonality yet. Confidence bands widen the further out a forecast goes; treat long
          horizons as directional, not precise.
        </p>
      </Section>

      <Tabs value={subTab} onValueChange={(v) => setSubTab(v as typeof subTab)}>
        <TabsList className="h-auto flex-wrap">
          {SUB_TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview">
          <ForecastOverview
            horizon={horizon}
            models={models}
            salesStore={salesStore}
            footfallStore={footfallStore}
            footfallTimeSlot={footfallTimeSlot}
            footfallMetric={footfallMetric}
          />
        </TabsContent>
        <TabsContent value="huddle">
          <DailyHuddle horizon={horizon} models={models} salesStore={salesStore} />
        </TabsContent>
        <TabsContent value="sales">
          <SalesForecast
            stores={stores}
            storeNames={meta.store_names}
            horizon={horizon}
            models={models}
            salesStore={salesStore}
            onSalesStoreChange={setSalesStore}
          />
        </TabsContent>
        <TabsContent value="footfall">
          <FootfallForecast
            stores={stores}
            storeNames={meta.store_names}
            timeSlotOrder={meta.time_slot_order}
            horizon={horizon}
            models={models}
            store={footfallStore}
            onStoreChange={setFootfallStore}
            timeSlot={footfallTimeSlot}
            onTimeSlotChange={setFootfallTimeSlot}
            metric={footfallMetric}
            onMetricChange={setFootfallMetric}
          />
        </TabsContent>
        <TabsContent value="backtest">
          <Backtest
            horizon={horizon}
            models={models}
            salesStore={salesStore}
            footfallStore={footfallStore}
            footfallTimeSlot={footfallTimeSlot}
            footfallMetric={footfallMetric}
          />
        </TabsContent>
        <TabsContent value="products">
          <ProductsForecast
            stores={stores}
            productForecastLevels={meta.product_forecast_levels}
            topNDefault={meta.top_n_products_default}
            horizon={horizon}
            models={models}
          />
        </TabsContent>
        <TabsContent value="vendors">
          <VendorsForecast stores={stores} topNDefault={meta.top_n_vendors_default} horizon={horizon} models={models} />
        </TabsContent>
        <TabsContent value="promotions">
          <PromotionsEffectiveness stores={stores} topNCampaignsDefault={meta.top_n_promo_campaigns_default} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
