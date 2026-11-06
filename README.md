# Roofing Lead Pipeline — v1 (legacy baseline)

> A working-but-flawed CRM cleanup pipeline. This folder is the **"before"** in a
> deliberate v1 → v2 story: it runs and produces real output, and its defects are
> documented below rather than hidden. The rebuild is `lead-integrity-engine`
> (see `project-b-c-notes.md` in the parent folder).

## The problem

A roofing contractor's lead export is a mess. The same person appears three times
with different capitalisation, a typo'd email domain, and a phone number formatted
four different ways. Some records are missing contact details entirely; some have
opted out of contact but are still on the campaign list. Unmanaged, this produces
duplicate outreach, compliance risk, and a CRM nobody trusts.

v1 takes a raw CSV and returns a clean master list, a quarantine list, and an audit
trail explaining every decision.

## How it works

```
raw_leads.csv
     │
     ▼
 main.py ── column_resolver ──> canonical snake_case schema
     │
     ├─ PHASE 1  cleanse   ── pillars/ (phone, email, name, date, address,
     │                        value, status, job type, compliance)
     ├─ PHASE 2  trash gate ── gates.check_if_trash
     ├─ PHASE 2b hub detect ── shared tracking numbers/emails -> sandbox
     ├─ PHASE 3  dedupe     ── Tier 1 contact+name / Tier 2 household+address
     │                        (+ 5-year time-gap demotion)
     └─ PHASE 4  bucket     ── clean master | DNC quarantine
     │
     ▼
 outputs/
     ├─ CRM_Cleanout_Master.csv
     ├─ DNC_and_Trash_Quarantine.csv
     └─ Duplication_Log.csv
     │
     ▼
 loose_and_zombies.py ──> Gold_Zombies.csv (recency-guarded reactivation list)
```

`pillars/` are independent column-standardisers (one per field type). `gates.py`
holds the boolean policy checks (trash, DNC, gold zombie). `main.py` orchestrates.

## Run it

```bash
cd roofing-pipeline-v1
python main.py                    # writes outputs/*.csv
python loose_and_zombies.py       # writes outputs/Gold_Zombies.csv
python run_sandbox_test.py        # column-mapping diagnostic (not a test)
```

Requires `pandas`. Run from this folder — paths are CWD-relative.

## Results on the bundled sample

Input: 9 raw rows → 1 trash, 8 valid → 5 consolidated masters.

| Output | Rows | What it is |
|---|---|---|
| `CRM_Cleanout_Master.csv` | 4 | safe to contact, deduplicated |
| `DNC_and_Trash_Quarantine.csv` | 3 | 1 incomplete + 2 DNC-broadcast rows |
| `Duplication_Log.csv` | 6 | every merged row, with `dedup_reason` |

Worked examples from the sample:

- **Robert / Bob Vance** — different names, different addresses, different email,
  but phone `555-888-9999` normalises to match `1555888-9999`. Merged on
  **Tier 1 contact + last-name match**. Bob's email and address survive as
  `additional_emails` / `additional_addresses`, and
  `multiple_properties_on_file` flips to `Yes`.
- **Mark Smith** — 2024 record opted out, 2026 record did not. The DNC flag is
  **broadcast to the whole cluster**, so a live $18k WON deal is quarantined.
  Deliberate: compliance beats revenue. Both rows land in quarantine.
- **Shared tracking numbers** — any phone/email touching >3 distinct households is
  treated as a hub, sandboxed, and excluded from Tier 1 matching so it can't glue
  unrelated people together.

## Fixed before publishing

Two defects used to make the output contradict its own name. Both are fixed, and the
bundled `outputs/` files were regenerated afterwards.

1. **Invalid placeholders leaked into the clean file.** The export only overwrote a
   field when its cleaned value was truthy:
   `if row.get('cleaned_email'): row['email'] = row['cleaned_email']`. An invalid
   value cleans down to an empty string, which is falsy, so the raw junk survived —
   the master CSV shipped `email = "idk"` (Charlie Walker) and `phone = "idk"`
   (Alice Walker). Export columns are now rebuilt from the cleaned values
   unconditionally, so missing data becomes empty instead of raw.
2. **Emoji written into the name column.** Quarantine rows had `⚠️ [TRASH]` and
   `🛑 [DNC]` prepended to `first_name`, which breaks any downstream import. Names are
   now left intact and the reason lives only in `quarantine_reason`.

## Known defects

The remaining honest list, and the reason `lead-integrity-engine` exists.

1. **`safe_unpack` is a band-aid.** Pillars return inconsistent shapes and the caller
   guesses: `str(val[1]) if len(val) > 1 else str(val[0])`. It works only because the
   pillars that return tuples happen to put the useful value second.
2. **Dead `sys.path` bridges.** `main.py` and every `pillars/*` module append
   `dirname(__file__)/..`, which resolves one level *above* the project root. Imports
   only work because Python auto-inserts the script's directory. Running via
   `import main` from anywhere else fails.
3. **CWD-dependent.** `raw_leads.csv` and `outputs/` are relative paths, so it only
   runs from the project root.
4. **No tests.** `run_sandbox_test.py` prints a column-mapping diagnostic and always
   exits 0 — nothing fails if the pipeline regresses. The 4/3/6 row counts below are
   unverified by any assertion.
5. **9-pillar sprawl with fossilised config.** `config.py` carries Colorado-specific
   address assumptions and an AU-era `TARGET_COUNTRY` path; `DEFAULT_ROOF_VALUE` is
   8511, a magic number rooted in one contractor's pricing.
6. **Placeholder detection is per-field, not centralised.** Each pillar re-declares
   its own view of what "empty" means, so `INVALID_PLACEHOLDERS` disagrees between
   `main.py` and `loose_and_zombies.py`.
7. **The compliance column is a raw passthrough.** `compliance_code` in the clean
   export is the source's opt-out flag echoed as `true`/`false` rather than normalised
   to SAFE/DNC. DNC clusters are quarantined, so the clean file never contains an
   opted-out record.

## What v2 changes

`lead-integrity-engine` keeps the parts that work — tiered dedup, hub detection,
DNC quarantine, `dedup_reason` auditing, recency-guarded reactivation — and rebuilds
around them:

- `CONTRACTS.md` first, so return shapes are defined rather than guessed
- one lightweight normaliser instead of nine pillars
- placeholder handling driven by data, not a hardcoded set
- a real end-to-end test that fails on regression
- Supabase + SQL attribution, and a Looker Studio dashboard on top

Full ladder: `../project-b-c-notes.md`.
