import pandas as pd  
from datetime import datetime
import os
import sys
import re
import collections
from difflib import SequenceMatcher

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import config

from pillars.phone_pillar import standardize_phone
from pillars.email_pillar import standardize_email, _clean_single_email
from pillars.string_normalization import standardize_text  
from pillars.dates import standardize_date                  
from pillars.compliance_code import standardize_compliance  
from pillars.lead_status import standardize_lead_status      
from pillars.financial_pillar import standardize_value
from pillars.job_type_pillar import normalize_job_type
from pillars.address_pillar import standardize_address

from gates import check_if_trash, check_row_for_dnc_leak

# Windows consoles default to cp1252, which cannot encode the emoji used in the
# status output below. Reconfigure stdout so this runs on a stock shell.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INVALID_PLACEHOLDERS = {'nan', 'none', 'null', 'na', 'n/a', '0', '0.0', 'false', 'true', '', '0000000000', '1111111111'}
HUB_THRESHOLD = 3 # Any phone/email touching >3 distinct households is a "Hub"

def safe_unpack(val):
    if isinstance(val, tuple):
        return str(val[1]) if len(val) > 1 else str(val[0])
    return str(val)

# =============================================================================
# EXPORT PROJECTION
#
# Export columns are rebuilt from the cleaned values on every row. The original
# code only overwrote a field when the cleaned value was truthy:
#
#     if row.get('cleaned_email'): row['email'] = row['cleaned_email']
#
# so an invalid raw value survived into "CRM_Cleanout_Master.csv" whenever its
# cleaned form was an empty string. That is how 'idk' shipped as an email
# address and as a phone number in a file named "clean". Missing data must
# become empty, never the raw junk.
# =============================================================================
_PROJECTED_FIELDS = [
    ('cleaned_phone', 'phone'),
    ('cleaned_email', 'email'),
    ('cleaned_address', 'street_address'),
    ('cleaned_first_name', 'first_name'),
    ('cleaned_last_name', 'last_name'),
    ('cleaned_estimated_value', 'estimated_value'),
    # NOTE: cleaned_job_type is deliberately NOT projected. It holds the pricing
    # tier (major / maintenance / other), not the job type. Projecting it would
    # overwrite "replacement" with "major" in the export.
]

def project_cleaned_fields(row):
    """Rebuild every export column from its cleaned source, always."""
    for source, target in _PROJECTED_FIELDS:
        value = row.get(source)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            value = ""
        row[target] = str(value).strip()
    return row


def sanitize_phone_value(phone_str):
    if not phone_str or pd.isna(phone_str):
        return ""
    digits_only = re.sub(r'\D', '', str(phone_str))
    if not digits_only:
        return ""
    if len(digits_only) == 11 and digits_only.startswith('1'):
        core = digits_only[1:]
    else:
        core = digits_only
    if len(core) != 10 or len(set(core)) == 1 or core in {'1234567890', '0123456789'}:
        return ""
    return str(phone_str)

def extract_clean_phones(raw_val):
    if not raw_val or pd.isna(raw_val): return set()
    clean_set = set()
    for p in re.split(r'[;,]', str(raw_val)):
        item = p.strip()
        if item and item.lower() not in INVALID_PLACEHOLDERS:
            cleaned = sanitize_phone_value(safe_unpack(standardize_phone(item)))
            if cleaned and cleaned.lower() not in INVALID_PLACEHOLDERS:
                clean_set.add(cleaned)
    return clean_set

def parse_all_valid_emails(raw_val):
    if not raw_val or pd.isna(raw_val):
        return set()
    valid = set()
    for piece in re.split(r'[;,]', str(raw_val)):
        piece = piece.strip()
        if not piece: continue
        clean, status = _clean_single_email(piece)
        if status == "Valid" and clean:
            valid.add(clean)
    return valid

def is_fuzzy_match(str1, str2, threshold=0.85):
    if not str1 or not str2 or pd.isna(str1) or pd.isna(str2):
        return False
    s1, s2 = str(str1).strip().lower(), str(str2).strip().lower()
    if s1 == s2: return True
    if len(s1) <= 3 or len(s2) <= 3: return s1 == s2
    return SequenceMatcher(None, s1, s2).ratio() >= threshold

def is_first_name_compatible(fn1, fn2):
    """Soft, blank-tolerant first name check"""
    if not fn1 or not fn2 or fn1 in INVALID_PLACEHOLDERS or fn2 in INVALID_PLACEHOLDERS:
        return True
    s1, s2 = fn1.lower(), fn2.lower()
    if s1 == s2: return True
    # Initial tolerance (e.g., 'J' vs 'John')
    if (len(s1) == 1 and s2.startswith(s1)) or (len(s2) == 1 and s1.startswith(s2)):
        return True
    return SequenceMatcher(None, s1, s2).ratio() >= 0.8


def run_pipeline(input_csv_path):
    print("🚀 Starting Roofing Lead Pipeline...")
    if not os.path.exists(input_csv_path):
        print(f"❌ Error: Input file '{input_csv_path}' not found!")
        return

    df = pd.read_csv(input_csv_path, dtype=str)
    
    df.columns = df.columns.astype(str).str.strip().str.lower()
    column_resolver = {
        'first name': 'first_name', 'last name': 'last_name',
        'phone number': 'phone', 'primary phone': 'phone',
        'mobile phone': 'mobile_phone', 'home phone': 'home_phone',
        'work phone': 'work_phone', 'phone 2': 'phone_2',
        'address': 'street_address', 'street address': 'street_address',
        'address 1': 'street_address', 'last contact': 'last_contact_date', 
        'last contact date': 'last_contact_date', 'date created': 'last_contact_date',
        'created date': 'last_contact_date', 'est. value': 'estimated_value', 
        'estimated value': 'estimated_value', 'estimated total': 'estimated_value', 
        'job type': 'job_type', 'lead status': 'lead_status', 'status': 'lead_status', 
        'compliance': 'compliance_code', 'compliance code': 'compliance_code',
        'opt out': 'compliance_code', 'additional email': 'additional_emails',
        'additional emails': 'additional_emails'
    }
    df = df.rename(columns=column_resolver)
    print(f"📊 Loaded & resolved {len(df)} raw rows from {input_csv_path}")
    
    structural_cols = [
        'phone', 'email', 'additional_emails', 'additional_addresses', 'additional_phones',
        'mobile_phone', 'home_phone', 'work_phone', 'phone_2',
        'last_contact_date', 'street_address', 'first_name', 'last_name', 
        'lead_status', 'estimated_value', 'job_type', 'multiple_properties_on_file'
    ]
    for col in structural_cols:
        if col not in df.columns: df[col] = ""

    # PHASE 1: VECTORIZED CLEANSING & SORTING
    print("🧹 Executing vectorized cleansing...")
    raw_phones = df['phone'].apply(standardize_phone).apply(safe_unpack)
    df['cleaned_phone'] = raw_phones.apply(sanitize_phone_value)
    
    email_tuples = df['email'].apply(standardize_email)
    df['cleaned_email'] = [t[0] for t in email_tuples]
    df['pillar_secondary_email'] = [t[1] for t in email_tuples]
    
    raw_dates = df['last_contact_date'].apply(standardize_date).apply(safe_unpack)
    df['parsed_last_contact'] = pd.to_datetime(raw_dates, errors='coerce')
    formatted_dates = df['parsed_last_contact'].dt.strftime('%m/%d/%Y')
    df['last_contact_date'] = formatted_dates.fillna(raw_dates)

    df['date_is_missing'] = df['parsed_last_contact'].isna()
    df = df.sort_values(by=['date_is_missing', 'parsed_last_contact'], ascending=[True, False]).reset_index(drop=True)
    df = df.drop(columns=['date_is_missing'])

    # Apply 4-Tuple Address Pillar
    addr_results = df['street_address'].apply(standardize_address)
    df['address_is_valid'] = addr_results.apply(lambda x: x[0])
    df['cleaned_address'] = addr_results.apply(lambda x: x[1])
    df['address_strict_key'] = addr_results.apply(lambda x: x[2])
    df['address_has_zip'] = addr_results.apply(lambda x: x[3]) # Gating field

    df['cleaned_first_name'] = df['first_name'].apply(standardize_text).apply(safe_unpack)
    df['cleaned_last_name'] = df['last_name'].apply(standardize_text).apply(safe_unpack)
    df['cleaned_job_type'] = df['job_type'].apply(normalize_job_type).apply(safe_unpack)
    
    df['lead_status'] = df.apply(lambda row: safe_unpack(standardize_lead_status(row['lead_status'], row['parsed_last_contact'])), axis=1)
    df['cleaned_estimated_value'] = df.apply(lambda row: safe_unpack(standardize_value(row['estimated_value'], job_type=row['cleaned_job_type'])), axis=1)

    # PHASE 2: TRASH GATING
    print("🗑️ Screening for Trash and Empty records...")
    trash_indices = []
    clean_rows_to_process = []
    
    records = df.to_dict('records')
    for row in records:
        eval_row = row.copy()
        eval_row['phone'] = row.get('cleaned_phone') or ''
        eval_row['email'] = row.get('cleaned_email') or ''
        eval_row['street_address'] = row.get('cleaned_address') or ''
        eval_row['first_name'] = row.get('cleaned_first_name') or ''
        eval_row['last_name'] = row.get('cleaned_last_name') or ''
        
        trash_flag, reason = check_if_trash(eval_row)
        if trash_flag:
            row['quarantine_reason'] = f"[TRASH] {reason}"
            trash_indices.append(row)
        else:
            clean_rows_to_process.append(row)
            
    print(f"      Filtered out {len(trash_indices)} trash/incomplete records.")
    print(f"      Processing {len(clean_rows_to_process)} valid clean records.")

    # =====================================================================
    # FIX #1: HUB-IDENTIFIER PRE-PASS (Prevent Phantom Properties)
    # =====================================================================
    print("🕵️ Identifying Hub Contacts (Shared tracking numbers/emails)...")
    phone_to_hhs = collections.defaultdict(set)
    email_to_hhs = collections.defaultdict(set)
    
    for row in clean_rows_to_process:
        addr_key = row.get('address_strict_key')
        lname = str(row.get('cleaned_last_name') or '').strip().lower()
        if not addr_key or not lname or lname in INVALID_PLACEHOLDERS:
            continue
            
        hh_id = f"{lname}_{addr_key}"
        
        # Gather all phones for this row
        p_set = extract_clean_phones(row.get('cleaned_phone'))
        for p_col in ['mobile_phone', 'home_phone', 'work_phone', 'phone_2']:
            p_set.update(extract_clean_phones(row.get(p_col)))
            
        # Gather all emails for this row
        e_set = parse_all_valid_emails(row.get('email'))
        e_set.update(parse_all_valid_emails(row.get('additional_emails')))
        sec = str(row.get('pillar_secondary_email') or '').strip().lower()
        if sec and "@" in sec and sec not in INVALID_PLACEHOLDERS: e_set.add(sec)
            
        for p in p_set: phone_to_hhs[p].add(hh_id)
        for e in e_set: email_to_hhs[e].add(hh_id)

    hub_phones = {p for p, hhs in phone_to_hhs.items() if len(hhs) > HUB_THRESHOLD}
    hub_emails = {e for e, hhs in email_to_hhs.items() if len(hhs) > HUB_THRESHOLD}
    print(f"      Found {len(hub_phones)} Hub Phones and {len(hub_emails)} Hub Emails to sandbox.")

    # =====================================================================
    # PHASE 3: TIERED CROSS-COLUMN DEDUPLICATION ENGINE
    # =====================================================================
    print("🧬 Running cross-column deduplication engine...")
    clusters = []
        
    for row in clean_rows_to_process:
        phone = str(row.get('cleaned_phone') or '').strip().lower()
        email = str(row.get('cleaned_email') or '').strip().lower()
        
        address = str(row.get('cleaned_address') or '')
        strict_addr_key = str(row.get('address_strict_key') or '')
        is_valid_address = bool(row.get('address_is_valid'))
        has_zip = bool(row.get('address_has_zip'))
        
        first_name = str(row.get('cleaned_first_name') or '').strip().lower()
        last_name = str(row.get('cleaned_last_name') or '').strip().lower()
        
        is_valid_phone = phone not in INVALID_PLACEHOLDERS
        is_valid_email = email not in INVALID_PLACEHOLDERS
        is_valid_name = last_name not in INVALID_PLACEHOLDERS
        
        row_all_emails = parse_all_valid_emails(row.get('additional_emails'))
        row_all_emails |= parse_all_valid_emails(row.get('email'))
        sec_email = str(row.get('pillar_secondary_email') or '').strip().lower()
        if sec_email and sec_email not in INVALID_PLACEHOLDERS and "@" in sec_email:
            row_all_emails.add(sec_email)
            
        row_all_phones = set()
        if is_valid_phone: row_all_phones.add(phone)
        for p_col in ['mobile_phone', 'home_phone', 'work_phone', 'phone_2']:
            row_all_phones.update(extract_clean_phones(row.get(p_col)))

        has_any_contact = bool(row_all_phones) or bool(row_all_emails)
        
        # Matchable contacts exclude hubs for Tier 1
        row_matchable_phones = row_all_phones - hub_phones
        row_matchable_emails = row_all_emails - hub_emails

        match_found = False
        
        for c in clusters:
            # TIER 1: Contact Match (Ignoring Hubs)
            phone_match_found = bool(row_matchable_phones.intersection(c['matchable_cluster_phones']))
            email_match_found = bool(row_matchable_emails.intersection(c['matchable_cluster_emails']))
            
            contact_match = phone_match_found or email_match_found
            name_match = is_valid_name and c['last_name'] and is_fuzzy_match(last_name, c['last_name'])
            
            tier1_match = contact_match and name_match
            
            # TIER 2: Household Match (FIX #2: Zip Gating | FIX #3: First Name Check)
            address_match = is_valid_address and has_zip and strict_addr_key in c['address_strict_keys']
            
            tier2_match = False
            fn_compatible = is_first_name_compatible(first_name, c['first_name'])

            if has_any_contact and address_match and name_match and fn_compatible:
                has_phone_conflict = len(row_all_phones) > 0 and len(c['all_cluster_phones']) > 0 and not bool(row_all_phones.intersection(c['all_cluster_phones']))
                has_email_conflict = len(row_all_emails) > 0 and len(c['all_cluster_emails']) > 0 and not bool(row_all_emails.intersection(c['all_cluster_emails']))
                if not (has_phone_conflict and has_email_conflict):
                    tier2_match = True

            # FIX #4: TIME-GAP DEMOTION
            time_gap_demoted = False
            time_gap_status = "Confirmed"
            if tier2_match and not tier1_match:
                r_date = row.get('parsed_last_contact')
                c_date = c['newest_date']
                
                if pd.isna(r_date) or pd.isna(c_date):
                    time_gap_status = "Date Unconfirmed"
                else:
                    gap_days = abs((r_date - c_date).days)
                    if gap_days > (5 * 365.25):
                        tier2_match = False
                        time_gap_demoted = True
                        demoted_target_cluster = c['cluster_id']

            if tier1_match or tier2_match:
                row['cluster_id'] = c['cluster_id']
                if tier1_match:
                    row['dedup_reason'] = "Duplicate: Tier 1 Contact/Name Match" 
                else:
                    row['dedup_reason'] = f"Duplicate: Tier 2 Household Match ({time_gap_status})"
                
                c['rows'].append(row)
                
                if is_valid_address and strict_addr_key not in c['address_strict_keys']:
                    c['address_strict_keys'].add(strict_addr_key)
                    c['all_cluster_addresses'].add(address)

                # Keep hubs attached to the master for display, just not for future matching
                c['all_cluster_emails'].update(row_all_emails)
                c['all_cluster_phones'].update(row_all_phones)
                c['matchable_cluster_emails'].update(row_matchable_emails)
                c['matchable_cluster_phones'].update(row_matchable_phones)
                
                match_found = True
                break
            
            # If we demoted, we stop searching and force it to become a new split-cluster
            if time_gap_demoted:
                # Appending _SPLIT forces it to group with the original in the Duplication Log
                new_cluster_id = f"{demoted_target_cluster}_SPLIT_{len(clusters)+1}"
                row['cluster_id'] = new_cluster_id
                row['dedup_reason'] = "Review: 5+ Year Tier 2 Gap (Split Master)"
                
                clusters.append({
                    'cluster_id': new_cluster_id,
                    'first_name': first_name if first_name else "",
                    'last_name': last_name if is_valid_name else "",
                    'address_strict_keys': {strict_addr_key} if is_valid_address else set(),
                    'all_cluster_addresses': {address} if is_valid_address else set(),
                    'all_cluster_emails': set(row_all_emails),
                    'all_cluster_phones': set(row_all_phones),
                    'matchable_cluster_emails': set(row_matchable_emails),
                    'matchable_cluster_phones': set(row_matchable_phones),
                    'newest_date': row.get('parsed_last_contact'),
                    'rows': [row]
                })
                match_found = True
                break
                
        if not match_found:
            new_cluster_id = f"CLUSTER_{len(clusters) + 1:05d}"
            row['cluster_id'] = new_cluster_id
            row['dedup_reason'] = "Master Record"

            clusters.append({
                'cluster_id': new_cluster_id,
                'first_name': first_name if first_name else "",
                'last_name': last_name if is_valid_name else "",
                'address_strict_keys': {strict_addr_key} if is_valid_address else set(),
                'all_cluster_addresses': {address} if is_valid_address else set(),
                'all_cluster_emails': set(row_all_emails),
                'all_cluster_phones': set(row_all_phones),
                'matchable_cluster_emails': set(row_matchable_emails), 
                'matchable_cluster_phones': set(row_matchable_phones), 
                'newest_date': row.get('parsed_last_contact'),
                'rows': [row]
            })

    final_masters = []
    all_processed_records_log = []
    
    for c in clusters:
        cluster_rows = c['rows']
        master_record = cluster_rows[0].copy()
        
        if len(cluster_rows) > 1:
            for older_row in cluster_rows[1:]:
                for col_name, val in older_row.items():
                    current_val = master_record.get(col_name)
                    if not current_val or str(current_val).strip().lower() in INVALID_PLACEHOLDERS:
                        master_record[col_name] = val
        
        c['has_dnc'] = any(check_row_for_dnc_leak(r) for r in cluster_rows)
        
        final_master_primary_email = str(master_record.get('cleaned_email') or '').strip().lower()
        if final_master_primary_email in c['all_cluster_emails']:
            c['all_cluster_emails'].remove(final_master_primary_email)
        master_record['additional_emails'] = ";".join(sorted(list(c['all_cluster_emails']))) if c['all_cluster_emails'] else ""
        
        final_master_primary_phone = str(master_record.get('cleaned_phone') or '').strip().lower()
        if final_master_primary_phone in c['all_cluster_phones']:
            c['all_cluster_phones'].remove(final_master_primary_phone)
        master_record['additional_phones'] = "; ".join(sorted(list(c['all_cluster_phones']))) if c['all_cluster_phones'] else ""

        final_master_primary_addr = master_record.get('cleaned_address') or ''
        if final_master_primary_addr in c['all_cluster_addresses']:
            c['all_cluster_addresses'].remove(final_master_primary_addr)
        master_record['additional_addresses'] = "; ".join(sorted(list(c['all_cluster_addresses']))) if c['all_cluster_addresses'] else ""

        # FIX: Admin Boolean flag so they don't have to read the raw text field
        master_record['multiple_properties_on_file'] = "Yes" if master_record['additional_addresses'] else "No"

        c['master_record'] = master_record
        final_masters.append(master_record)
        all_processed_records_log.extend(cluster_rows)

    # =====================================================================
    # PHASE 4: FINAL BUCKETING & EXPORT
    # =====================================================================
    dnc_quarantine_list = []
    cleanout_master_list = []
    
    for t_row in trash_indices:
        # No emoji prefix on the name. The reason is already carried by
        # quarantine_reason, and prefixing text into first_name breaks any
        # downstream import that consumes the quarantine list.
        dnc_quarantine_list.append(t_row)
        
    for c in clusters:
        cluster_rows = c['rows']
        master_rec = c['master_record']
        
        if c['has_dnc']:
            for row in cluster_rows:
                # Quarantine keeps the row as evidence, but the contact fields
                # are still cleaned and the reason lives in quarantine_reason.
                for src, dst in (
                    ('cleaned_phone', 'phone'),
                    ('cleaned_email', 'email'),
                    ('cleaned_address', 'street_address'),
                    ('cleaned_last_name', 'last_name'),
                ):
                    if row.get(src): row[dst] = row[src]
                row['quarantine_reason'] = "[DNC] Historical record opted out (Broadcasted to Cluster)"
                dnc_quarantine_list.append(row)
        else:
            cleanout_master_list.append(project_cleaned_fields(master_rec))

    cols_to_drop = [
        'cleaned_phone', 'cleaned_email', 'cleaned_address', 'address_strict_key', 'address_is_valid',
        'address_has_zip', 'parsed_last_contact', 'final_dnc_flag', 'cleaned_estimated_value',
        'cleaned_first_name', 'cleaned_last_name', 'cleaned_job_type',
        'pillar_secondary_email', 'cluster_id', 'dedup_reason', 'quarantine_reason',
        'mobile_phone', 'home_phone', 'work_phone', 'phone_2'
    ]
    
    df_quarantine = pd.DataFrame(dnc_quarantine_list).drop(columns=[c for c in cols_to_drop if c != 'quarantine_reason'], errors='ignore')
    
    df_cleanout = pd.DataFrame(cleanout_master_list)
    if not df_cleanout.empty:
        df_cleanout = df_cleanout.drop(columns=cols_to_drop, errors='ignore')

    df_full_log_pool = pd.DataFrame(all_processed_records_log)
    df_duplication_log = pd.DataFrame()
    
    if not df_full_log_pool.empty:
        # Group time-gap demoted rows alongside their original clusters for review
        df_full_log_pool['base_cluster_id'] = df_full_log_pool['cluster_id'].apply(lambda x: x.split('_SPLIT')[0])
        
        log_cluster_counts = df_full_log_pool['base_cluster_id'].value_counts()
        active_duplicate_base_ids = log_cluster_counts[log_cluster_counts > 1].index
        
        df_duplication_log = df_full_log_pool[df_full_log_pool['base_cluster_id'].isin(active_duplicate_base_ids)].copy()
        df_duplication_log = df_duplication_log.sort_values(by=['base_cluster_id', 'cluster_id', 'dedup_reason'], ascending=[True, True, False])
        
        log_internal_drops = [
            'cleaned_phone', 'cleaned_email', 'cleaned_address', 'address_strict_key', 'address_is_valid',
            'parsed_last_contact', 'final_dnc_flag', 'cleaned_estimated_value', 'cleaned_first_name', 
            'cleaned_last_name', 'cleaned_job_type', 'pillar_secondary_email', 'base_cluster_id',
            'mobile_phone', 'home_phone', 'work_phone', 'phone_2'
        ]
        df_duplication_log = df_duplication_log.drop(columns=log_internal_drops, errors='ignore')

    os.makedirs('outputs', exist_ok=True)
    df_quarantine.to_csv('outputs/DNC_and_Trash_Quarantine.csv', index=False)
    df_cleanout.to_csv('outputs/CRM_Cleanout_Master.csv', index=False)
    df_duplication_log.to_csv('outputs/Duplication_Log.csv', index=False)

    print("\n🎉 Pipeline execution complete! Results saved in '/outputs':")
    print(f"   🟢 CRM_Cleanout_Master.csv        -> {len(df_cleanout)} unique, clean, active records.")
    print(f"   🛑 DNC_and_Trash_Quarantine.csv   -> {len(df_quarantine)} records blocked from campaigns.")
    print(f"   📋 Duplication_Log.csv            -> {len(df_duplication_log)} records tracked in audit trail.")
    print(f"   🧬 Deduplication Engine Summary:")
    print(f"      - Valid raw records processed: {len(clean_rows_to_process)}")
    print(f"      - Consolidated master records: {len(final_masters)}")
    print(f"      - Duplicates merged/removed:   {len(clean_rows_to_process) - len(final_masters)}")
    print("-" * 50)

if __name__ == "__main__":
    run_pipeline("raw_leads.csv")