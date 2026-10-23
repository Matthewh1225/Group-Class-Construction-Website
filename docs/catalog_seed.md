# Construction catalog seed

The editable [CSV](../sql/catalog_products.csv) contains **375 active products** across the twelve requested categories. Names, dimensions, materials, intended use, package coverage and relevant ratings are included in `details`, because the final auditor receives that field, name and selling unit. Prices, stock, manufacturers and product specifications are fictional development data, not vendor quotes or verified product certifications.

## Run locally

From the repository root, using the project's existing virtual environment:

```powershell
# Validate the file without connecting to MySQL.
.venv\Scripts\python.exe sql\seed_catalog.py --check

# Preview the configured database; no writes.
.venv\Scripts\python.exe sql\seed_catalog.py

# Apply to the database selected by your existing .env settings.
.venv\Scripts\python.exe sql\seed_catalog.py --apply
```

The schema must already exist. This uses the existing MySQL connector and dotenv dependencies. No database or AI configuration changes are required.

`--apply` upserts by unique SKU in one transaction. It updates the managed products' descriptions, fictional prices and stock on every run; use it as a development seed rather than an inventory synchronization job. Existing product IDs and selling units are preserved. Manufacturer names are reused, missing manufacturers are created, and manufacturer links are inserted without duplicates. Existing manufacturer associations remain. No products are deleted or retired, and no user, cart, order or payment tables are written.

The script refuses to change a matched product's category or selling unit, reuse another SKU's exact name, or produce an active catalog outside 350–400. It does not remove other products to reach the target. Run one seed process at a time; manufacturer names have no unique constraint in the existing schema.

## Counts and validation

Validated against the configured MySQL database on October 22, 2026:

| Category | Seed products |
|---|---:|
| Lumber & Building Materials | 50 |
| Hardware & Fasteners | 35 |
| Concrete & Masonry | 25 |
| Tools | 20 |
| Electrical | 45 |
| Drywall & Insulation | 20 |
| Roofing & Siding | 30 |
| Plumbing | 50 |
| HVAC | 25 |
| Flooring & Tile | 25 |
| Paint & Supplies | 25 |
| Doors & Windows | 25 |
| **Managed catalog** | **375** |
| Preserved existing heavy machinery | 12 |
| **Projected active database total** | **387** |

The initial database contained 110 rows: 109 active and one retired. All 97 active products in the twelve requested categories retain their SKUs and IDs; 278 rows are added. The 12 machinery products and the retired product remain unchanged. The resulting database has 388 rows, 387 active. These counts describe the inspected database; the dry run recalculates them for your database.

Validation performed:

- All 375 SKUs and names are unique, including case-insensitive comparison. Every row has a positive price and stock, valid enum values, required fields, and lengths/types matching `sql/erd_schema.sql`.
- Compared every pair of names using `difflib.SequenceMatcher` at a 0.83 threshold. Five pairs were flagged: base/wall cabinets, three pairs among 12/2, 14/2 and 12/3 NM-B cables, and 2-inch versus 3-inch drains. These have different functions or electrical/drainage sizing requirements. Human review also checked category coverage. Name comparison cannot prove that every product is functionally unique.
- Tested two consecutive applications in MySQL **session-local temporary tables**, cloned from the existing tables and populated with the current catalog. Both runs retained original IDs; the second added no products. Unmanaged rows remained identical. The actual table types, enums, uniqueness and check constraints accepted the data.
- Temporary tables do not copy MySQL foreign-key constraints. Manufacturer relationships were checked explicitly with joins, including the canonical link for every seeded product. Normal application uses the real tables' foreign keys.
- Called the existing, unmodified `get_planner_catalog()` against the seeded temporary tables: **387 results**, including every one of the **375** managed products, within its existing **500** limit. Every returned product had specifications.
- After closing the temporary-table connection, compared all rows of the real Product, Manufacturer and Manufacturer_products tables against their pre-test contents: unchanged by that test.
- All three catalog tests passed with the MySQL test enabled. The existing planner and Groq regression modules also passed: 48 tests, using mocked AI responses.

After testing, the seed was applied to Aiven with user authorization on October 22, 2026 (October 23 UTC). A catalog backup was saved to `data/backups/catalog_seed_20261023T012517661700Z/catalog_before.json`. Verification confirmed 388 total products, 387 active and one retired; all original product IDs and unrelated products were preserved. A fresh planner query retrieved all 387 active products, including every managed catalog entry.

Run the offline tests:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_catalog_seed -v
```

To repeat the MySQL temporary-table test with existing `.env` settings (requires `CREATE TEMPORARY TABLES` permission):

```powershell
$env:RUN_CATALOG_DB_TESTS = '1'
.venv\Scripts\python.exe -m unittest tests.test_catalog_seed -v
Remove-Item Env:RUN_CATALOG_DB_TESTS
```

## Matching and coverage notes

Quantities and prices use the existing **selling unit**. A box of eight tiles is one purchasable box, with its area and tile count in `details`; `itemQty` records a known package count. Weight-packed or random-length materials use one packaged unit with weight/coverage in the specifications. Do not treat `itemQty` as an automatic planner unit conversion. Examples use `piece`, `sheet`, `box`, `bag`, `roll`, `bundle`, `set`, `gallon`, `pail`, `tube`, `ft`, `sq_ft` and `cu_yd`; the planner workflow and output structure are unchanged.

Coverage includes craft lumber and mesh for small enclosures, framing and foundations, decks, cabinets and finishes, wet-area waterproofing, domestic and commercial fixtures, branch electrical distribution, motel PTAC units and commercial rooftop HVAC. Deliberate specification distinctions include sheathing versus cabinet plywood, pressure-water versus DWV pipe, PEX crimp versus expansion fittings, and underlayment versus waterproofing membranes.

Important remaining gaps include structural steel sections and engineered roof/floor trusses; commercial fire sprinkler/alarm systems and switchgear; elevator components; commercial kitchen grease interceptors; gas distribution pipe and appliance vent kits; ERV/HRV ventilation; complete refrigerant/duct fitting size ranges; roof curbs and complete membrane accessory systems; and carpet cushion/tack strips. The catalog offers representative systems rather than every compatible fitting and accessory. A complete building estimate may still require unmatched materials, which should retain `product_id: null` under the current auditor rules.

The database retrieval test does not prove AI matching accuracy or that the enlarged prompt fits every configured model's token budget. No paid AI calls were made. A useful next check is to audit sample birdhouse, deck, bathroom and motel estimates and inspect matches, units and unmatched lines.

Technical reference checks used [APA sheathing span designations](https://www.apawood.org/Data/Sites/1/documents/product-support/rated-sheathing-datasheet.pdf), [Southwire NM-B application limits](https://www.southwire.com/wire-cable/building-wire/romex-sup-sup-brand-simpull-sup-sup-copper-type-nm-b-cable/p/SPEC10028), and [Southwire THHN/THWN-2 ratings](https://www.southwire.com/wire-cable/building-wire/simpull-sup-sup-thhn-thwn-2-copper/p/SPEC10000). Catalog manufacturers are fictional; these references do not certify the generated products. Fire performance is described as depending on the complete installed assembly, rather than a gypsum panel alone.
