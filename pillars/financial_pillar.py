import pandas as pd
import re
import sys
import os

# Bridge the path to find your root config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import config

# ==============================================================================
# 1. PRE-COMPILED MATRICES FOR MAXIMUM ITERATION SPEED
# ==============================================================================
# Extracts numbers, periods, and commas for structural analysis
REGEX_RAW_NUMERIC = re.compile(r'[^\d\.,]')

# ==============================================================================
# 2. THE PUBLIC PIPELINE PLUG
# ==============================================================================
def standardize_value(value_raw, job_type=None):
    """
    THE PIPELINE PLUG FOR FINANCIALS:
    Converts messy text estimates ($12,450.00, 8000) into pure floats.
    Falls back to dynamic defaults based on job_type if empty/corrupted.
    """
    cleaned_value = _process_financial_logic(value_raw)
    
    # If the value returned is 0.0 or less, apply dynamic roofing job defaults
    if cleaned_value <= 0.0:
        # Sanitize incoming string to be completely safe against trailing spaces/cases
        jt_str = str(job_type).strip().lower() if job_type else ""
        
        if jt_str == 'maintenance':
            return 411.0
        elif jt_str == 'major':
            return 8511.0
        else:
            # Fallback to config default if job_type couldn't be determined
            return float(getattr(config, "DEFAULT_ROOF_VALUE", 8511.0))
        
    return cleaned_value

# ==============================================================================
# 3. INTERNAL PURIFICATION ENGINE
# ==============================================================================
def _process_financial_logic(value_raw):
    # 💎 BYPASS LAYER: If it's already a clean number, return instantly!
    if isinstance(value_raw, (int, float)) and not pd.isna(value_raw):
        return round(float(value_raw), 2)

    # Safeguard 1: Handle empty cells
    if pd.isna(value_raw) or str(value_raw).strip() == "":
        return 0.0
        
    raw_str = str(value_raw).strip()

    try:
        # Phase A: Strip currency indicators ($) and text symbols
        clean_str = REGEX_RAW_NUMERIC.sub('', raw_str)
        
        if not clean_str:
            return 0.0
            
        # Phase B: Formatting Normalization (Supports both 1,450.00 and 1250,50)
        if ',' in clean_str and '.' in clean_str:
            if clean_str.rfind(',') > clean_str.rfind('.'):
                clean_str = clean_str.replace('.', '').replace(',', '.')
            else:
                clean_str = clean_str.replace(',', '')
        elif ',' in clean_str and '.' not in clean_str:
            if len(clean_str.split(',')[1]) == 2:
                clean_str = clean_str.replace(',', '.')
            else:
                clean_str = clean_str.replace(',', '')

        # Extra Check: Guard against double-decimal input typos
        if clean_str.count('.') > 1:
            parts = clean_str.split('.')
            clean_str = "".join(parts[:-1]) + "." + parts[-1]

        # Phase C: Cast to float (No currency multipliers needed for US local work!)
        return round(float(clean_str), 2)
        
    except (ValueError, IndexError):
        return 0.0


def verify_transaction_viability(financial_status_raw):
    """
    BUSINESS SHIELD: Filter out canceled/lost contract values.
    Roofing statuses usually focus on whether a contract was canceled or is actively invoiced.
    """
    if pd.isna(financial_status_raw):
        return False
        
    status = str(financial_status_raw).strip().lower()
    
    # Non-viable statuses for local contractors
    NON_VIABLE_STATUSES = [
        'canceled',
        'voided',
        'disputed',
        'lost_bid',
        'dead'
    ]
    
    if status in NON_VIABLE_STATUSES:
        return False
        
    return True