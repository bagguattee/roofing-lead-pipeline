import pandas as pd
import re
import sys
import os

# Bridge the path to find your root config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import config

# Regex to strip spaces and punctuation for a clean dictionary lookup (e.g., "D.N.C." -> "dnc")
REGEX_CODE_CLEAN = re.compile(r'[^a-z0-9]')

def standardize_compliance(row):
    """
    THE PIPELINE PLUG FOR COMPLIANCE:
    Checks if the lead is safe to dial/email or if it is a flagged DNC.
    """
    # 1. Grab raw compliance status from the lead sheet
    raw_lead_code = row.get('compliance_code')
    
    # Get the default compliance status safely from config, fallback to "SAFE" if missing
    default_status = getattr(config, "DEFAULT_COMPLIANCE_STATUS", "SAFE")
    
    # Safety net: If blank, assume it is SAFE to contact (default)
    if pd.isna(raw_lead_code) or str(raw_lead_code).strip() == "":
        return default_status
        
    # Clean the string for a reliable lookup
    lookup_key = REGEX_CODE_CLEAN.sub('', str(raw_lead_code).lower())
    
    # CRITICAL FIX: Explicitly intercept explicit negative/safe strings 
    # so they bypass the "unrecognized fallback" DNC quarantine trap.
    if lookup_key in ['false', 'no', '0', 'n', 'none']:
        return default_status
    
    # 2. Check against our mapping (e.g., "dnc", "donotcall" -> "DNC")
    if hasattr(config, "COMPLIANCE_MAP") and config.COMPLIANCE_MAP:
        if lookup_key in config.COMPLIANCE_MAP:
            return config.COMPLIANCE_MAP[lookup_key]
        
    # Fallback: If it's a truly weird value we don't recognize, mark as DNC to be safe
    return "DNC"