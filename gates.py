import re
from datetime import datetime
from pillars.compliance_code import standardize_compliance
from pillars.job_type_pillar import normalize_job_type

def check_if_trash(row):
    """Identifies if a row is absolute gibberish, test data, or an unviable account status."""
    # 1. Contact check
    if not row.get('cleaned_phone') and not row.get('cleaned_email'):
        return True, "Missing both Phone and Email fields"
        
    first_name = str(row.get('cleaned_first_name', '')).strip().lower()
    last_name = str(row.get('cleaned_last_name', '')).strip().lower()
    
    # 2. Strict Name Keywords Check (Only flags actual bad placeholder values)
    trash_keywords = {'test', 'dummy', 'asdf', 'aaaa', 'user', 'unknown', 'none', 'null', 'nan'}
    
    # Check for exact matches to avoid killing names like "Leone" or "Clayuser"
    if first_name in trash_keywords or last_name in trash_keywords:
        return True, f"Gibberish/Test lead indicators found in name: '{first_name} {last_name}'"
    
    # Check if the combined name is completely empty
    if not first_name and not last_name:
        return True, "Lead has no name provided"
            
    # 3. Status check
    status = str(row.get('lead_status', '')).strip().lower()
    NON_VIABLE = ['canceled', 'voided', 'disputed', 'lost_bid', 'dead']
    if any(x in status for x in NON_VIABLE):
        return True, f"Non-viable status detected: {status}"
        
    return False, ""

def check_row_for_dnc_leak(row):
    """
    STRICT COMPLIANCE CATCH-ALL: Checks compliance flags accurately 
    without false positive leaking from empty 'nan' cells or clean names.
    """
    compliance_result = standardize_compliance(row)
    
    # 1. Unpack compliance pillar cleanly if it's a tuple
    if isinstance(compliance_result, tuple):
        is_dnc_flag = compliance_result[0]
        if is_dnc_flag:
            return True
    elif str(compliance_result).strip().upper() == "DNC":
        return True
        
    # 2. Safety net scan (Targeted solely to specific explicit compliance keywords/fields)
    dnc_keywords = ['dnc', 'do not call', 'unsubscribe', 'do_not_call', 'do_not_market']
    
    for key, value in row.items():
        val_str = str(value).strip().lower()
        
        # Skip empty cells, null fields, or engineering flags
        if val_str in ['nan', 'none', 'null', '']:
            continue
        if 'name' in key.lower() or key in ['quarantine_reason', 'final_dnc_flag']: 
            continue
            
        # Check text fields for aggressive opt-out phrases
        if any(keyword in val_str for keyword in dnc_keywords):
            return True
            
        # Enforce exact matching for explicit opt-out toggles (e.g., "Opt Out" column)
        if 'opt' in key.lower() or 'compliance' in key.lower():
            if val_str in ['1', 'true', 'yes', 'y', 'dnc']:
                return True
            
    return False

def check_if_gold_zombie(row, current_time):
    """
    PRECISION ROOFING ENGINE: Filters and tags high-converting dormant assets.
    Returns: True if the lead qualifies for a Gold Zombie campaign, False otherwise.
    Appends: row['recommended_campaign'] if True.
    """
    # 1. Date Check: Must be dormant (e.g., older than 2 years / 730 days)
    date_str = row.get('parsed_last_contact')
    if not date_str or str(date_str).strip().lower() in ['nan', 'none', '']:
        return False
        
    try:
        last_contact = datetime.strptime(str(date_str).split()[0], '%Y-%m-%d')
        days_dormant = (current_time - last_contact).days
        # Restrict to true dormant leads (2 years / 730 days)
        if days_dormant < 730:
            return False
    except Exception:
        return False
        
    # Get status and normalize the job type using our new pillar
    status = str(row.get('lead_status', '')).strip().upper()
    job_type_raw = row.get('job_type', '') or row.get('cleaned_job_type', '')
    service_tier = normalize_job_type(job_type_raw)
    
    try:
        val = float(row.get('cleaned_estimated_value', 0.0))
    except Exception:
        val = 0.0
        
    # ==========================================
    # CAMPAIGN 1: "Dormant Maintenance Repeat"
    # ==========================================
    # Must be WON + a high-frequency service (like gutter cleaning, roof wash)
    if status == 'WON' and service_tier == 'maintenance':
        row['recommended_campaign'] = "Dormant Maintenance Repeat"
        return True
        
    # ==========================================
    # CAMPAIGN 2: "Re-Open Cold Estimate"
    # ==========================================
    # Must be LOST/LEAD/UNCONVERTED + a major high-value ticket (Replacement/Leak Repair)
    high_intent = ['LOST', 'LEAD', 'QUOTE SENT', 'INSPECTION COMPLETED', 'SPOKE TO OWNER']
    
    if any(hi in status for hi in high_intent) and service_tier == 'major':
        # Let's verify it's a high-value ticket (equal to or over $5,000)
        if val >= 5000.0:
            row['recommended_campaign'] = "Re-Open Cold Estimate"
            return True
            
    # If they are a WON major replacement (Emma's case), they don't get the flag!
    return False