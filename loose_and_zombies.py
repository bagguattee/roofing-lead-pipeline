import pandas as pd
from datetime import datetime
import os
import sys
from collections import defaultdict

# Bridge path to find your root config.py if needed locally
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

# Import your gate check for Gold Zombies
from gates import check_if_gold_zombie

# Windows consoles default to cp1252, which cannot encode the emoji used in the
# status output below. Reconfigure stdout so this runs on a stock shell.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Common placeholder check
INVALID_PLACEHOLDERS = {'nan', 'none', 'null', 'na', 'n/a', '0', '0.0', 'false', 'true', '', None}

def run_downstream_marketing_pipeline(clean_master_path):
    print("🎯 Starting Loose Duplicates & Gold Zombies Generator...")
    
    if not os.path.exists(clean_master_path):
        print(f"❌ Error: Master clean file '{clean_master_path}' not found! Run main.py first.")
        return

    # Load master CRM data (treat everything as string first for raw contact parsing)
    df = pd.read_csv(clean_master_path, dtype=str)
    records = df.to_dict('records')
    print(f"📊 Loaded {len(df)} records from Master CRM.")

    # =====================================================================
    # PHASE 1: IDENTIFY POTENTIAL LOOSE CONTACTS (Audit Log Reviewer)
    # =====================================================================
    print("🔍 Scanning for loose contact duplicates (shared phone/email but different names/addresses)...")
    
    phone_groups = defaultdict(list)
    email_groups = defaultdict(list)
    
    for row in records:
        # Standardize strings for strict matching
        phone = ''.join(filter(str.isdigit, str(row.get('phone', ''))))
        email = str(row.get('email', '')).strip().lower()
        
        # Track valid phones (excluding blanks, short strings, and generic placeholders)
        if phone and len(phone) >= 10 and phone not in INVALID_PLACEHOLDERS:
            phone_groups[phone].append(row)
            
        # Track valid emails
        if email and '@' in email and email not in INVALID_PLACEHOLDERS:
            email_groups[email].append(row)

    loose_duplicates = []
    seen_combinations = set()  # (row_id, group_id) tracker to prevent double-logging a row
    
    group_counter = 1

    # Helper function to assign and log loose matches
    def log_loose_group(grouped_rows, match_type, group_id):
        for row in grouped_rows:
            # Use phone/email combination or any unique ID as record key
            record_key = f"{row.get('phone')}_{row.get('email')}"
            
            if (record_key, group_id) not in seen_combinations:
                entry = row.copy()
                entry['Match_Type'] = match_type
                entry['Loose_Group_ID'] = group_id
                loose_duplicates.append(entry)
                seen_combinations.add((record_key, group_id))

    # Evaluate Phone Matches (Ensures duplicates stay together with shared IDs for reviews)
    for phone, group in phone_groups.items():
        if len(group) > 1:
            group_id = f"LOOSE_PH_{group_counter:04d}"
            log_loose_group(group, "Phone Match", group_id)
            group_counter += 1

    # Evaluate Email Matches
    for email, group in email_groups.items():
        if len(group) > 1:
            group_id = f"LOOSE_EM_{group_counter:04d}"
            log_loose_group(group, "Email Match", group_id)
            group_counter += 1

    # =====================================================================
    # PHASE 2: GENERATE AND SHIELD GOLD ZOMBIES (Recency Survivorship Guard)
    # =====================================================================
    print("🧟 Compiling and filtering Gold Zombies via Recency Survivorship...")
    
    gold_zombies_clean = []
    suppressed_count = 0
    
    # Track contact points we have processed to isolate the absolute newest record
    processed_phones = set()
    processed_emails = set()
    
    today_date = datetime.now()

    # Because records are pre-sorted chronologically (newest first), the first time 
    # we encounter a phone or email, it is structurally the newest record.
    for row in records:
        phone = ''.join(filter(str.isdigit, str(row.get('phone', ''))))
        email = str(row.get('email', '')).strip().lower()
        
        is_valid_p = phone and len(phone) >= 10 and phone not in INVALID_PLACEHOLDERS
        is_valid_e = email and '@' in email and email not in INVALID_PLACEHOLDERS
        
        # Check if this contact point's living timeline was already determined by a newer row
        phone_already_seen = is_valid_p and phone in processed_phones
        email_already_seen = is_valid_e and email in processed_emails
        
        if phone_already_seen or email_already_seen:
            # An older record cannot step into marketing; its destiny is bound by the newest record
            continue
            
        # Register this row as the King of the Hill (newest instance) for these communication assets
        if is_valid_p: processed_phones.add(phone)
        if is_valid_e: processed_emails.add(email)
        
        # Now pass only this master survivor through the gate
        if check_if_gold_zombie(row, today_date):
            gold_zombies_clean.append(row)
        else:
            # If the newest row fails the zombie check (e.g. an active 2026 contract), 
            # it naturally blocks the contact point, counting as a structural suppression.
            # We count it if this number historically had duplicates flagged in Phase 1
            has_historical_dups = (is_valid_p and len(phone_groups[phone]) > 1) or \
                                  (is_valid_e and len(email_groups[email]) > 1)
            if has_historical_dups:
                suppressed_count += 1

    # =====================================================================
    # PHASE 3: SORTING AND EXPORTS
    # =====================================================================
    os.makedirs('outputs', exist_ok=True)

    # 1. Export Loose Contacts File
    df_loose = pd.DataFrame(loose_duplicates)
    if not df_loose.empty:
        # Move structural custom columns to the very front for human scanning
        cols = ['Loose_Group_ID', 'Match_Type'] + [c for c in df_loose.columns if c not in ['Loose_Group_ID', 'Match_Type']]
        df_loose = df_loose[cols]
        # Sort chronologically by IDs so loose matches stay paired up visually
        df_loose = df_loose.sort_values(by=['Loose_Group_ID'])
        df_loose.to_csv('outputs/Potential_Duplicates_Contact_Only.csv', index=False)
    else:
        pd.DataFrame(columns=['Loose_Group_ID', 'Match_Type']).to_csv('outputs/Potential_Duplicates_Contact_Only.csv', index=False)

    # 2. Export and Sort Gold Zombies File
    df_zombies = pd.DataFrame(gold_zombies_clean)
    if not df_zombies.empty:
        # Apply standard priority sort (Won -> Lost -> Lead)
        status_priority_map = {'won': 0, 'lost': 1, 'lead': 2}
        df_zombies['status_priority'] = df_zombies['lead_status'].str.lower().map(status_priority_map).fillna(3)
        df_zombies['sort_val'] = pd.to_numeric(df_zombies['estimated_value'], errors='coerce').fillna(0)
        
        df_zombies = df_zombies.sort_values(by=['status_priority', 'sort_val'], ascending=[True, False])
        df_zombies = df_zombies.drop(columns=['status_priority', 'sort_val'])
        df_zombies.to_csv('outputs/Gold_Zombies.csv', index=False)
    else:
        pd.DataFrame().to_csv('outputs/Gold_Zombies.csv', index=False)

    print("\n🎉 Downstream Marketing Pipeline Complete!")
    print(f"   👥 Potential_Duplicates_Contact_Only.csv -> {len(df_loose)} flagged records grouped together for review.")
    print(f"   🏆 Gold_Zombies.csv                      -> {len(df_zombies)} clean, risk-free target accounts.")
    print(f"   🛡️ Recency Shield: Safely guarded {suppressed_count} old zombie prospects because their newest record is active/unviable.")
    print("-" * 50)

if __name__ == "__main__":
    run_downstream_marketing_pipeline("outputs/CRM_Cleanout_Master.csv")