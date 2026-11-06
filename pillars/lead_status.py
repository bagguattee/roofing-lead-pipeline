import pandas as pd
import re

# ==============================================================================
# CONFIGURATION & PRE-COMPILED MATRICES (Ultimate speed, zero runtime overhead)
# ==============================================================================
# Regex to strip everything that isn't a letter or number (e.g., "N/C" -> "nc")
REGEX_CAT_CLEAN = re.compile(r'[^a-z0-9]')

DEFAULT_LEAD_STATUS = "NEW"

# Embedded Mapping: Keeps config.py clean and scopes domain logic locally.
ROOFING_STATUS_MAPPING = {
    # New / Open
    "new": "NEW",
    "newlead": "NEW",
    "open": "NEW",
    
    # Contacted / Working
    "contacted": "CONTACTED",
    "attemptedcontact": "CONTACTED",
    "followup": "CONTACTED",
    "inprocess": "CONTACTED",
    
    # Estimating / Quoted
    "quoted": "QUOTED",
    "estimateprovided": "QUOTED",
    "inspectionset": "QUOTED",
    "appointment": "QUOTED",
    
    # Closed / Finalized
    "sold": "SOLD",
    "closedwon": "SOLD",
    "lost": "LOST",
    "closedlost": "LOST",
    "dead": "ARCHIVED",
    "archived": "ARCHIVED",
    "donotcall": "DNC",
    "dnc": "DNC"
}

# ==============================================================================
# THE PIPELINE PLUG (PUBLIC WRAPPER)
# ==============================================================================

def standardize_lead_status(status_raw, parsed_date=None):
    """
    THE PIPELINE PLUG FOR LEAD STATUS:
    Injects cross-pillar data (parsed_date) to apply time-decay logic.
    """
    is_valid, clean_status, reason, raw_fallback = _process_lead_status_logic(status_raw)
    
    # -------------------------------------------------------------------------
    # TIME-DECAY LOGIC: Auto-Archive neglected 'NEW' leads older than 2 years
    # -------------------------------------------------------------------------
    if clean_status == "NEW" and pd.notna(parsed_date):
        try:
            # Ensure we are working with a Pandas Timestamp for robust math
            date_val = pd.to_datetime(parsed_date)
            two_years_ago = pd.Timestamp.now() - pd.DateOffset(years=2)
            
            if date_val < two_years_ago:
                clean_status = "ARCHIVED"
        except Exception:
            # If date parsing fails for any reason, fail gracefully and keep as NEW
            pass
            
    return clean_status  # Returns just the pristine string to your CSV


# ==============================================================================
# DATA PURIFICATION CORE ENGINE (INTERNAL LOGIC)
# ==============================================================================

def _process_lead_status_logic(status_raw):
    """
    LAYER 1: LEAD STATUS NORMALIZATION (PRODUCTION COMPLIANT)
    """
    # Guard against nulls/blanks
    if pd.isna(status_raw) or str(status_raw).strip() == "":
        return False, DEFAULT_LEAD_STATUS, "Missing", ""
        
    # Standardize input for mapping lookup
    raw_str = str(status_raw).strip()
    lookup_key = REGEX_CAT_CLEAN.sub('', raw_str.lower())
    
    # Safe lookup
    if lookup_key in ROOFING_STATUS_MAPPING:
        return True, ROOFING_STATUS_MAPPING[lookup_key], "Valid", ""
    
    # ==============================================================================
    # FIX: Pass the raw text through instead of wiping it out with "NEW"
    # ==============================================================================
    return True, raw_str.upper(), "Unmapped_Variation", raw_str