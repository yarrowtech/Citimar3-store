import { DndContext, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, arrayMove, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { Download, Printer, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { filtersSummaryText, buildReportBlocks, downloadReport } from "@/api/reportClient";
import { ReportBlockCard } from "@/components/report/ReportBlockCard";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { HistoricalTabId } from "@/App";
import { REPORT_MANIFESTS } from "@/lib/reportManifests";
import { REPORT_FORMATS, makeBlockId, type ReportBlock, type ReportFormat } from "@/lib/reportTypes";
import type { FilterState } from "@/lib/types";

interface ReportBuilderProps {
  filters: FilterState;
  tabId: HistoricalTabId;
  tabLabel: string;
  onClose: () => void;
}

function reportTitle(tabLabel: string): string {
  return `CITIMART — ${tabLabel} Report`;
}

export function ReportBuilder({ filters, tabId, tabLabel, onClose }: ReportBuilderProps) {
  const [blocks, setBlocks] = useState<ReportBlock[] | null>(null);
  const [format, setFormat] = useState<ReportFormat>("pdf");
  const [downloading, setDownloading] = useState(false);
  const generatedAt = useState(() => new Date().toLocaleString("en-IN"))[0];

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  useEffect(() => {
    let cancelled = false;
    setBlocks(null);
    (async () => {
      try {
        const fetched = await buildReportBlocks(REPORT_MANIFESTS[tabId], filters);
        if (cancelled) return;
        setBlocks([
          { id: makeBlockId(), type: "title", text: reportTitle(tabLabel) },
          { id: makeBlockId(), type: "filters_summary", heading: "Selected Filters", text: filtersSummaryText(filters) },
          ...fetched,
        ]);
      } catch (error) {
        if (!cancelled) toast.error(`Failed to build report preview: ${(error as Error).message}`);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabId, JSON.stringify(filters)]);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id || !blocks) return;
    const oldIndex = blocks.findIndex((b) => b.id === active.id);
    const newIndex = blocks.findIndex((b) => b.id === over.id);
    setBlocks(arrayMove(blocks, oldIndex, newIndex));
  }

  function updateBlock(id: string, updated: ReportBlock) {
    setBlocks((prev) => prev?.map((b) => (b.id === id ? updated : b)) ?? prev);
  }

  function removeBlock(id: string) {
    setBlocks((prev) => prev?.filter((b) => b.id !== id) ?? prev);
  }

  async function handleDownload() {
    if (!blocks) return;
    setDownloading(true);
    try {
      await downloadReport(
        blocks,
        { title: reportTitle(tabLabel), generated_at: generatedAt, filters_summary_text: filtersSummaryText(filters) },
        format,
      );
      toast.success(`${REPORT_FORMATS.find((f) => f.value === format)?.label} report downloaded.`);
    } catch (error) {
      toast.error(`Download failed: ${(error as Error).message}`);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="bg-background fixed inset-0 z-[60] flex flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3 print:hidden">
        <div>
          <h2 className="text-lg font-bold">Export Report — {tabLabel}</h2>
          <p className="text-muted-foreground text-xs">Reorder, edit, or remove anything below before downloading.</p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={format} onValueChange={(v) => setFormat(v as ReportFormat)}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REPORT_FORMATS.map((f) => (
                <SelectItem key={f.value} value={f.value}>
                  {f.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" onClick={() => window.print()} disabled={!blocks}>
            <Printer className="h-4 w-4" /> Print
          </Button>
          <Button onClick={handleDownload} disabled={!blocks || downloading}>
            <Download className="h-4 w-4" /> {downloading ? "Generating..." : "Download"}
          </Button>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close report builder">
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="mx-auto w-full max-w-3xl flex-1 overflow-y-auto p-6 print:max-w-none print:overflow-visible">
        {!blocks ? (
          <div className="space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-32 w-full rounded-lg" />
            ))}
          </div>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={blocks.map((b) => b.id)} strategy={verticalListSortingStrategy}>
              <div className="space-y-3">
                {blocks.map((block) => (
                  <ReportBlockCard
                    key={block.id}
                    block={block}
                    onChange={(updated) => updateBlock(block.id, updated)}
                    onRemove={() => removeBlock(block.id)}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
      </div>
    </div>
  );
}
