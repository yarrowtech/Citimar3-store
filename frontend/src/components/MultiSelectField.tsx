import { ChevronsUpDown } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface MultiSelectFieldProps {
  label: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  /** Optional value -> display label map (e.g. store code -> full store
   * name). The underlying `selected`/`onChange` values stay the raw option
   * values (codes) throughout -- only the rendered text changes. */
  labels?: Record<string, string>;
  /** Text shown when nothing is selected. Defaults to "All {label}", which
   * is correct for the cascading hierarchy filters (empty selection = no
   * restriction applied there). The Store field has the opposite semantics
   * -- an empty `stores` array means zero stores match, not "all stores" --
   * so it overrides this to avoid showing a misleading "All stores". */
  emptyLabel?: string;
  /** "checkbox" (default) shows a checkbox square on each row -- the right
   * affordance for the long, densely-packed hierarchy filter lists. "check"
   * drops the checkbox and instead relies on the Command list's built-in
   * trailing checkmark (shown via data-checked), which reads cleaner for a
   * short, always-visible list like Store. */
  indicator?: "checkbox" | "check";
}

/** A searchable multi-select used for every hierarchy filter (Division,
 * Section, Department, Product Design No./Style/Type/Size, Vendors) plus
 * the Store field. One shared, well-tested widget for all of them -- this
 * replaces the old frontend's dual checkbox/native-<select> split, which is
 * what caused "Section" selection to behave inconsistently. */
export function MultiSelectField({
  label,
  options,
  selected,
  onChange,
  disabled,
  labels,
  emptyLabel,
  indicator = "checkbox",
}: MultiSelectFieldProps) {
  const [open, setOpen] = useState(false);
  const labelFor = (value: string) => labels?.[value] ?? value;

  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };

  return (
    <div className="space-y-1.5">
      <Label className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">{label}</Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            disabled={disabled || options.length === 0}
            aria-expanded={open}
            className="w-full justify-between font-normal"
          >
            <span className="truncate">
              {selected.length === 0
                ? (emptyLabel ?? `All ${label.toLowerCase()}`)
                : selected.length === options.length
                  ? `All ${label.toLowerCase()}`
                  : selected.length <= 2
                    ? selected.map(labelFor).join(", ")
                    : `${selected.length} selected`}
            </span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 p-0" align="start">
          <Command>
            <CommandInput placeholder={`Search ${label.toLowerCase()}...`} />
            <CommandList className="max-h-64">
              <CommandEmpty>No results.</CommandEmpty>
              <CommandGroup>
                {options.map((option) => (
                  <CommandItem
                    key={option}
                    value={labelFor(option)}
                    onSelect={() => toggle(option)}
                    data-checked={indicator === "check" ? selected.includes(option) : undefined}
                  >
                    {indicator === "checkbox" && <Checkbox checked={selected.includes(option)} className="mr-2" />}
                    <span className="truncate">{labelFor(option)}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
