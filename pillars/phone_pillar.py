import pandas as pd
import re
import sys
import os

# Bridge the path to find your root config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from config import TARGET_COUNTRY

# ==============================================================================
# 1. PRE-COMPILED MATRICES (OPTIMIZED FOR ROOFING LEADS)
# ==============================================================================
# Cleans up pandas float conversions of integers (e.g. "5551234567.0" -> "5551234567")
REGEX_EXCEL_FLOAT   = re.compile(r'\.0+$')
# Isolates primary phone before ext, commas, or alternative numbers
REGEX_PHONE_SPLIT   = re.compile(r'(?i)\s*(ext|x|/|or|aest|am|pm|\,)')
# Strips all formatting characters like spaces, dashes, and parentheses
REGEX_NON_DIGIT     = re.compile(r'\D')

# ==============================================================================
# 2. THE PUBLIC PIPELINE PLUG
# ==============================================================================
def standardize_phone(phone_raw):
    """
    THE PIPELINE PLUG FOR PHONES:
    Call this in main.py to get ONLY clean, formatted US phone strings.
    """
    is_valid, p_str = _process_phone_logic(phone_raw)
    return p_str if p_str else ""  # Return string or clean fallback empty string

# ==============================================================================
# 3. INTERNAL DATA PURIFICATION CORE ENGINE
# ==============================================================================
def _process_phone_logic(phone_raw):
    # Safeguard against empty cells
    if pd.isna(phone_raw) or str(phone_raw).strip() == "": 
        return False, None
        
    # Phase A: Strip formatting, trailing floats, and extraction fragments
    p_str = str(phone_raw).strip()
    p_str = REGEX_EXCEL_FLOAT.sub('', p_str) 
    p_str = REGEX_PHONE_SPLIT.split(p_str)[0]
    p_str = REGEX_NON_DIGIT.sub('', p_str)
    
    # --------------------------------------------------------------------------
    # BRANCH 1: UNITED STATES RULES (Standard 10/11 Digit Lookup)
    # --------------------------------------------------------------------------
    if TARGET_COUNTRY == "US":
        # Rule 1: Clean 11-digit number already prefixed with the country code '1'
        if len(p_str) == 11 and p_str.startswith('1'):
            return True, p_str
        # Rule 2: Standard 10-digit local number -> Inject the country code '1' (critical for dialing systems)
        elif len(p_str) == 10:
            return True, '1' + p_str
        # Rule 3: Anything else is garbage/corrupted data
        else:
            return False, None

    # Fallback in case of unexpected config changes
    return False, None
