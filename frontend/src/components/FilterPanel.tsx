import { useIsFetching, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api } from "@/api/client";
import { MultiSelectField } from "@/components/MultiSelectField";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { FILTER_HIERARCHY, type FilterState } from "@/lib/types";

const FIELD_LABELS: Record<(typeof FILTER_HIERARCHY)[number], string> = {
  division: "Division",
  section: "Section",
  department: "Department",
  product_design_no: "Product Design No.",
  product_style: "Product Style",
  product_type: "Product Type",
  product_size: "Product Size",
  vendors: "Vendors",
};

interface FilterPanelProps {
  applied: FilterState;
  onApply: (next: FilterState) => void;
  onReset: (resetState: FilterState) => void;
  open: boolean;
}

export function FilterPanel({ applied, onApply, onReset, open }: FilterPanelProps) {
  const { data: defaults } = useQuery({ queryKey: ["filters", "defaults"], queryFn: api.filterDefaults });

  const [draft, setDraft] = useState<FilterState>(applied);

  // Keyed on `draft`, not `applied`: the cascading rule (Section 9 -- each
  // field's options narrow off every field selected above it) needs to
  // react to what the user is actively picking in this still-open panel,
  // not just what was last Applied. Keying on `applied` let someone pick a
  // Section that never co-occurs with an in-progress Division choice, since
  // the option list wouldn't narrow until after they clicked Apply -- and
  // apply_filters ANDs both, silently zeroing the whole dashboard.
  const { data: options } = useQuery({
    queryKey: ["filters", "options", draft],
    queryFn: () => api.filterOptions(draft),
    enabled: !!defaults,
  });

  // Keep the panel's draft selections in sync whenever the applied filters
  // change (initial load, or after a Reset triggered from elsewhere).
  useEffect(() => setDraft(applied), [applied]);

  const allStores = defaults?.stores ?? [];

  // Immediate feedback that the click registered: disable + relabel the
  // button the instant Apply fires, until every chart/table/KPI query it
  // triggered (all keyed off `filters`, so all in flight at once) settles --
  // `useIsFetching()` is the count of in-flight queries app-wide, which is
  // an honest "still working" signal since FilterPanel only renders while a
  // DATASET.xlsx-driven page (the only pages with in-flight queries at that
  // moment) is active. Cleared once fetching rises then falls back to 0
  // (`sawFetchingRef`, not a bare `isFetching === 0` check) -- checking for
  // 0 alone would clear it on the very first render after the click, before
  // React Query has actually kicked off the new queries. A short timeout is
  // still the fallback for re-applying an unchanged filter set, where no
  // query key changes and `isFetching` never ticks above 0 at all.
  const isFetching = useIsFetching();
  const [applying, setApplying] = useState(false);
  const sawFetchingRef = useRef(false);

  useEffect(() => {
    if (!applying) return;
    if (isFetching > 0) {
      sawFetchingRef.current = true;
    } else if (sawFetchingRef.current) {
      setApplying(false);
    }
  }, [applying, isFetching]);

  useEffect(() => {
    if (!applying) return;
    const id = window.setTimeout(() => setApplying(false), 1500);
    return () => window.clearTimeout(id);
  }, [applying]);

  const handleApply = () => {
    if (draft.start && draft.end && draft.start > draft.end) {
      toast.error("Start date cannot be after end date.");
      return;
    }
    onApply(draft);
    sawFetchingRef.current = false;
    setApplying(true);
  };

  const handleReset = () => {
    if (!defaults) return;
    const resetState: FilterState = {
      stores: [...defaults.stores],
      start: defaults.start_date ?? "",
      end: defaults.end_date ?? "",
      time_slot: [],
      division: [],
      section: [],
      department: [],
      product_design_no: [],
      product_style: [],
      product_type: [],
      product_size: [],
      vendors: [],
    };
    setDraft(resetState);
    onReset(resetState);
  };

  return (
    <motion.aside
      initial={false}
      animate={{ width: open ? 300 : 0, opacity: open ? 1 : 0 }}
      transition={{ duration: 0.25, ease: "easeInOut" }}
      className="sticky top-4 h-fit shrink-0 overflow-hidden"
      aria-hidden={!open}
    >
      <div className="bg-card w-[300px] rounded-xl border p-4">
        <ScrollArea className="h-[calc(100vh-8rem)] pr-3">
          <div className="space-y-5">
            <MultiSelectField
              label="Stores"
              options={allStores}
              selected={draft.stores}
              onChange={(next) => setDraft((d) => ({ ...d, stores: next }))}
              labels={defaults?.store_names}
              emptyLabel="No stores selected"
              indicator="check"
            />

            <div className="space-y-1.5">
              <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">Date Range</Label>
              <div className="space-y-2">
                <div>
                  <Label className="mb-1 block text-xs">Start date</Label>
                  <input
                    type="date"
                    className="border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm"
                    min={defaults?.start_date ?? undefined}
                    max="2999-12-31"
                    value={draft.start}
                    onChange={(e) => setDraft((d) => ({ ...d, start: e.target.value }))}
                  />
                </div>
                <div>
                  <Label className="mb-1 block text-xs">End date</Label>
                  <input
                    type="date"
                    className="border-input bg-background w-full rounded-md border px-2 py-1.5 text-sm"
                    min={defaults?.start_date ?? undefined}
                    max="2999-12-31"
                    value={draft.end}
                    onChange={(e) => setDraft((d) => ({ ...d, end: e.target.value }))}
                  />
                </div>
              </div>
            </div>

            <MultiSelectField
              label="Time Slot"
              options={defaults?.time_slot_options ?? []}
              selected={draft.time_slot}
              onChange={(next) => setDraft((d) => ({ ...d, time_slot: next }))}
              emptyLabel="All time slots"
            />

            {FILTER_HIERARCHY.map((field) => (
              <MultiSelectField
                key={field}
                label={FIELD_LABELS[field]}
                options={options?.[field] ?? []}
                selected={draft[field]}
                onChange={(next) => setDraft((d) => ({ ...d, [field]: next }))}
              />
            ))}

            <div className="space-y-2 pt-1">
              <Button className="w-full" onClick={handleApply} disabled={applying}>
                {applying ? "Applying…" : "Apply Filters"}
              </Button>
              <Button variant="secondary" className="w-full" onClick={handleReset}>
                Reset All Filters
              </Button>
            </div>
          </div>
        </ScrollArea>
      </div>
    </motion.aside>
  );
}
