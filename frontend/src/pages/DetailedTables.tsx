import { DataTable } from "@/components/DataTable";
import { Section } from "@/components/Section";
import type { FilterState } from "@/lib/types";

export function DetailedTables({ filters }: { filters: FilterState }) {
  return (
    <div>
      <Section title="Store Scorecard">
        <DataTable tableId="store_scorecard" filters={filters} />
      </Section>
      <Section title="All Products">
        <DataTable tableId="top_products" filters={filters} extra={{ top_n: 500 }} />
      </Section>
      <Section title="All Brands">
        <DataTable tableId="top_brands" filters={filters} extra={{ top_n: 500 }} />
      </Section>
    </div>
  );
}
