# CRM Data Cleansing & Entity Resolution Engine

A Python data engineering pipeline designed to ingest, cleanse, deduplicate, and audit messy lead exports for high-ticket home services contractors. 

It handles dirty contact details, resolves entity identity across multi-tiered matching rules, isolates shared communication hubs, enforces strict TCPA/DNC compliance broadcasting, and generates an auditable merge log alongside dormant lead reactivation lists.

---

## Key Data Engineering Capabilities

1. **Multi-Tiered Entity Resolution & Identity Linkage:**
   - **Tier 1 (Contact + Name):** Matches records on normalized phone numbers and last names. Preserves secondary emails/addresses into array fields (dditional_emails, dditional_addresses) and flags multi-property ownership.
   - **Tier 2 (Household + Address):** Matches records on normalized street addresses and surnames.
   - **Time-Gap Demotion:** Records with contact dates > 5 years apart are demoted to manual review to avoid merging stale historical profiles.

2. **Shared-Identifier Guard (Hub Detection):**
   - Any phone number or email associated with more than 3 distinct households is identified as a shared tracking number or commercial line.
   - These "Hubs" are automatically sandboxed and excluded from Tier 1 matching, preventing unrelated people from being incorrectly merged.

3. **Strict Compliance Broadcasting (TCPA / DNC Isolation):**
   - Compliance overrides revenue. If *any* record within a merged cluster carries a Do-Not-Call (DNC) or opt-out flag, the **entire cluster** (including active high-value deals) is quarantined. 
   - Prevents compliance leakage into active outreach lists while preserving data provenance.

4. **Multi-Market Date & Data Normalization:**
   - Dynamic locale switch handling date formats (AU day-first vs. US month-first parsing).
   - Standardizes phone numbers to E.164-style digit patterns, cleans domain typos in emails, and strips invalid raw placeholders ("idk", "null", "0000000000").

5. **Recency-Guarded Dormant Reactivation Engine:**
   - loose_and_zombies.py identifies high-value dormant assets (older than 730 days) and buckets them into target reactivation campaigns:
     - **Dormant Maintenance Repeat:** Won recurring maintenance services.
     - **Re-Open Cold Estimate:** Unconverted quotes on high-ticket replacements ($5,000+).

---

## Pipeline Architecture & Execution Flow

`
                     raw_leads.csv (Messy CRM Export)
                                   │
                                   ▼
                       main.py (Column Resolver)
                                   │
      ┌────────────────────────────┼────────────────────────────┐
      ▼                            ▼                            ▼
Phase 1: Cleanse            Phase 2: Policy Gates       Phase 2b: Hub Detect
Standardize phone, email,   Check trash/gibberish       Sandbox shared tracking
address, date, value        and non-viable status       remote/shared lines
      │                            │                            │
      └────────────────────────────┼────────────────────────────┘
                                   │
                                   ▼
                   Phase 3: Tiered Deduplication
              (Tier 1 Contact | Tier 2 Household | 5-Yr Demotion)
                                   │
                                   ▼
                      Phase 4: Output Bucketing
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
CRM_Cleanout_Master.csv  DNC_Quarantine.csv       Duplication_Log.csv
(Clean contact list)     (Quarantined records)    (Audit trail of all merges)
                                   │
                                   ▼
               loose_and_zombies.py -> Gold_Zombies.csv
                  (Targeted reactivation lists)
`

---

## Data Input vs Output (Bundled Sample Results)

**Input:** 9 Raw Lead Records  
**Output:** 4 Clean Masters, 3 Quarantined, 6 Logged Merges  

- **Reconciliation Rule:** Input Rows (9) = Clean Master (4) + Quarantine (3) + Merged Duplicates (2)
- **Audit Log (Duplication_Log.csv):** Every merge records the exact match reason (dedup_reason), source record IDs, and timestamps.

---

## Setup & Running the Pipeline

`ash
# Clone the repository
git clone https://github.com/bagguattee/roofing-lead-pipeline.git
cd roofing-lead-pipeline

# Run the core ingestion and deduplication engine
python main.py

# Run the dormant lead reactivation engine
python loose_and_zombies.py
`

*Requirements:* Python 3.9+, pandas.

---

## Engineering Retrospective & Roadmap (v1 → v2 Evolution)

This baseline pipeline demonstrates core entity resolution principles. The next architectural iteration (2 / lead-integrity-engine) focuses on:

1. **Strict Data Contracts:** Replacing custom tuple unpacking with Pydantic schemas across all standardization pillars.
2. **Centralized Configuration:** Moving hardcoded US state tokens and country parameters into dynamic environment configs.
3. **Automated Integration Testing:** Adding PyTest suites to validate row reconciliation and fuzzy-matching thresholds automatically in CI/CD.
4. **Cloud Warehouse Sync:** Direct streaming from PostgreSQL/Supabase to Looker Studio reporting dashboards.

