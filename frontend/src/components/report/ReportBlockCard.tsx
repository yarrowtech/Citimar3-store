import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Trash2 } from "lucide-react";
import type { PlotData, Layout } from "plotly.js-dist-min";

import { GlossyGauge } from "@/components/GlossyGauge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import Plot from "@/lib/Plot";
import type { ReportBlock } from "@/lib/reportTypes";
import type { GaugeSpec } from "@/lib/types";

interface ReportBlockCardProps {
  block: ReportBlock;
  onChange: (updated: ReportBlock) => void;
  onRemove: () => void;
}

function StatusDot({ status }: { status?: string | null }) {
  if (!status) return null;
  const color = status === "red" ? "bg-red-500" : status === "yellow" ? "bg-yellow-500" : "bg-green-500";
  return <span className={`inline-block h-2 w-2 rounded-full ${color}`} />;
}

function BlockBody({ block, onChange }: { block: ReportBlock; onChange: (updated: ReportBlock) => void }) {
  switch (block.type) {
    case "title":
      return <Input value={block.text} onChange={(e) => onChange({ ...block, text: e.target.value })} className="text-xl font-bold" />;

    case "text":
      return (
        <div className="space-y-2">
          <Input
            placeholder="Heading (optional)"
            value={block.heading ?? ""}
            onChange={(e) => onChange({ ...block, heading: e.target.value })}
            className="font-semibold"
          />
          <Textarea value={block.text} onChange={(e) => onChange({ ...block, text: e.target.value })} rows={3} />
        </div>
      );

    case "filters_summary":
      return (
        <div className="space-y-2">
          <Input value={block.heading} onChange={(e) => onChange({ ...block, heading: e.target.value })} className="font-semibold" />
          <Textarea value={block.text} onChange={(e) => onChange({ ...block, text: e.target.value })} rows={2} />
        </div>
      );

    case "kpi_grid":
      return (
        <div className="space-y-2">
          <Input
            placeholder="Heading (optional)"
            value={block.heading ?? ""}
            onChange={(e) => onChange({ ...block, heading: e.target.value })}
            className="font-semibold"
          />
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {block.items.map((item, i) => (
              <div key={i} className="flex items-center gap-2 rounded-md border p-2">
                <StatusDot status={item.status} />
                <Input
                  value={item.label}
                  onChange={(e) => {
                    const items = [...block.items];
                    items[i] = { ...item, label: e.target.value };
                    onChange({ ...block, items });
                  }}
                  className="h-8 flex-1"
                />
                <Input
                  value={item.value}
                  onChange={(e) => {
                    const items = [...block.items];
                    items[i] = { ...item, value: e.target.value };
                    onChange({ ...block, items });
                  }}
                  className="h-8 w-32"
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0"
                  onClick={() => onChange({ ...block, items: block.items.filter((_, idx) => idx !== i) })}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      );

    case "chart":
      return (
        <div>
          <Input value={block.title} onChange={(e) => onChange({ ...block, title: e.target.value })} className="mb-2 font-semibold" />
          <div className="h-[360px] w-full">
            <Plot
              data={block.figure.data as PlotData[]}
              layout={{ ...(block.figure.layout as Partial<Layout>), autosize: true }}
              useResizeHandler
              style={{ width: "100%", height: "100%" }}
              config={{ responsive: true, displaylogo: false, staticPlot: true }}
            />
          </div>
        </div>
      );

    case "gauge":
      return <GlossyGauge spec={block.spec as unknown as GaugeSpec} className="h-[300px] w-full" />;

    case "table":
      return (
        <div>
          <Input value={block.title} onChange={(e) => onChange({ ...block, title: e.target.value })} className="mb-2 font-semibold" />
          <div className="max-h-96 overflow-auto rounded-md border">
            <table className="w-full text-xs">
              <thead className="bg-muted sticky top-0">
                <tr>
                  {block.columns.map((col) => (
                    <th key={col} className="px-2 py-1.5 text-left font-semibold whitespace-nowrap">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, r) => (
                  <tr key={r} className="border-t">
                    {block.columns.map((col) => (
                      <td key={col} className="px-1 py-0.5">
                        <Input
                          value={String(row[col] ?? "")}
                          onChange={(e) => {
                            const rows = block.rows.map((rw, idx) => (idx === r ? { ...rw, [col]: e.target.value } : rw));
                            onChange({ ...block, rows });
                          }}
                          className="h-7 border-none px-1 shadow-none focus-visible:ring-1"
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      );

    case "data_quality":
      return (
        <div className="space-y-2">
          <Input value={block.heading} onChange={(e) => onChange({ ...block, heading: e.target.value })} className="font-semibold" />
          {block.items.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <Textarea
                value={item}
                rows={1}
                onChange={(e) => {
                  const items = [...block.items];
                  items[i] = e.target.value;
                  onChange({ ...block, items });
                }}
                className="min-h-8"
              />
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => onChange({ ...block, items: block.items.filter((_, idx) => idx !== i) })}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>
          ))}
        </div>
      );

    case "forecast_summary":
      return (
        <div className="space-y-2">
          <Input value={block.heading} onChange={(e) => onChange({ ...block, heading: e.target.value })} className="font-semibold" />
          {block.items.map((item, i) => (
            <div key={i} className="flex items-center gap-2">
              <Input
                value={item.label}
                onChange={(e) => {
                  const items = [...block.items];
                  items[i] = { ...item, label: e.target.value };
                  onChange({ ...block, items });
                }}
                className="h-8 flex-1"
              />
              <Input
                value={item.value}
                onChange={(e) => {
                  const items = [...block.items];
                  items[i] = { ...item, value: e.target.value };
                  onChange({ ...block, items });
                }}
                className="h-8 w-32"
              />
            </div>
          ))}
          {block.note !== undefined && (
            <Textarea
              value={block.note ?? ""}
              placeholder="Note"
              rows={1}
              onChange={(e) => onChange({ ...block, note: e.target.value })}
            />
          )}
        </div>
      );
  }
}

export function ReportBlockCard({ block, onChange, onRemove }: ReportBlockCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: block.id });

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }}
      className="bg-card group relative rounded-lg border p-4"
    >
      <div className="mb-2 flex items-center justify-between">
        <button
          {...attributes}
          {...listeners}
          type="button"
          className="text-muted-foreground hover:text-foreground cursor-grab touch-none active:cursor-grabbing"
          aria-label="Drag to reorder"
        >
          <GripVertical className="h-4 w-4" />
        </button>
        <Button variant="ghost" size="icon" className="text-muted-foreground h-7 w-7 hover:text-red-600" onClick={onRemove} aria-label="Remove block">
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
      <BlockBody block={block} onChange={onChange} />
    </div>
  );
}
