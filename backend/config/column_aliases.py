"""Alias-based column mapping so future workbook versions can rename headers
without code changes. Matching is case-insensitive, whitespace-normalised and
punctuation-tolerant (see src/schema_detector.py:normalise_header). Add new
wording variants here, not in the loader code.
"""
from __future__ import annotations

# canonical field name -> list of accepted header spellings (order = preference)
DAY_WISE_SALE_ALIASES: dict[str, list[str]] = {
    "date": ["date", "sale date", "bill date", "transaction date"],
    "store": ["store", "store name", "location", "outlet"],
    "division": ["division"],
    "section": ["section"],
    "department": ["department"],
    "item_code": ["item code", "sku", "sku code", "product code"],
    "product_design_no": ["product design no", "product design no.", "design no", "design number"],
    "product_brand": ["product brand", "brand"],
    "product_style": ["product style", "style"],
    "product_type": ["product type", "type"],
    "product_size": ["product size", "size"],
    "isvoid": ["isvoid", "is void", "void", "void flag"],
    "vendors": ["vendors", "vendor", "supplier"],
    "ageing": ["ageing", "aging"],
    "tax_rate": ["tax rate", "gst rate", "gst %"],
    "mrp": ["maximum retail price", "mrp", "max retail price"],
    "retail_selling_price": ["retail selling price", "selling price", "rsp"],
    "promo_type": ["promo type", "promotion type"],
    "promo_name": ["promo name", "promotion name", "promo"],
    "standard_rate": ["standard rate", "standard name", "std rate"],
    "bill_quantity": ["bill quentity", "bill quantity", "quantity", "qty", "units sold"],
    "gross_amount": ["gross amount", "gross sale", "gross sales"],
    "promo_amount": ["promo amount", "promotion amount"],
    "discount_amount": ["discount amount", "discount", "discount value"],
    "net_amount": ["net amount", "net sale", "net sales"],
    "cogs": ["cost of goods sold", "cogs"],
    "cogs_with_gst": ["cost of goods solds with gst", "cost of goods sold with gst", "cogs with gst", "cogs (gst)"],
    "bill_no": ["bill no", "bill no.", "bill number", "invoice no", "receipt no"],
}

SALES_TARGET_ALIASES: dict[str, list[str]] = {
    "date": ["date"],
    "nm_target": ["nm target", "nm sales target", "new market target"],
    "hb_target": ["hb target", "hb sales target", "hatibagan target"],
    "chw_target": ["chw target", "chw sales target", "chowringhee target", "chowringee target"],
}

FOOTFALL_NOB_ALIASES: dict[str, list[str]] = {
    "date": ["date"],
    "time_slot": ["time slot", "timeslot", "time band"],
    "nm_footfall": ["nm footfall"],
    "nm_nob": ["nm nob"],
    "hb_footfall": ["hb footfall"],
    "hb_nob": ["hb nob"],
    "chw_footfall": ["chw footfall"],
    "chw_nob": ["chw nob"],
}

SHEET_ALIASES: dict[str, dict[str, list[str]]] = {
    "DAY WISE SALE": DAY_WISE_SALE_ALIASES,
    "SALES TARGET": SALES_TARGET_ALIASES,
    "TIME WISE FOOTFALL-NOB": FOOTFALL_NOB_ALIASES,
}

# Fields a KPI needs; if any are unresolved after alias matching, the KPI
# renders "N/A — required source field not available" instead of guessing.
REQUIRED_FIELDS_FOR_KPI: dict[str, list[str]] = {
    "net_sales": ["net_amount"],
    "gross_sales": ["gross_amount"],
    "discount": ["discount_amount"],
    "bill_quantity": ["bill_quantity"],
    "footfall": ["nm_footfall", "hb_footfall", "chw_footfall"],
    "nob": ["nm_nob", "hb_nob", "chw_nob"],
    "atv": ["net_amount", "bill_no"],
    "rpv": ["net_amount"],
    "basket_size": ["bill_quantity", "bill_no"],
    "conversion": [],
    "achievement": ["net_amount"],
    "remaining": ["net_amount"],
    "gross_profit": ["net_amount", "cogs_with_gst"],
    "net_profit": ["net_amount", "cogs_with_gst"],
}
