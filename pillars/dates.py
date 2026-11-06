import pandas as pd
import re
import datetime
import sys
import os

# Bridge the path to find your root config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import config

# ==============================================================================
# PILLAR 3: DATE CONFIGURATION & PRE-COMPILED MATRICES
# ==============================================================================
REGEX_EXCEL_SERIAL = re.compile(r'^\d+(\.0+)?$')
REGEX_DATE_CLEAN   = re.compile(r'(?i)(approx|est|date|md|at|:|[\(\)])')

def standardize_date(date_raw):
    """
    THE PIPELINE PLUG: 
    This is what pipeline.py calls. It catches the 4 values from the engine
    and returns ONLY the clean string (or an empty string) so your CSV stays clean.
    """
    is_valid, clean_date, reason, raw_fallback = _parse_date_logic(date_raw)
    
    # Return an empty string instead of None to prevent safe_unpack 
    # from accidentally turning it into the literal string "None"
    return clean_date if clean_date is not None else ""


def _parse_date_logic(date_raw):
    """
    LAYER 1: DATE NORMALIZATION ENGINE (INTERNAL)
    Returns: (is_valid, clean_date_iso_or_None, reason, raw_fallback)
    """
    # Guard against nulls/blanks
    if pd.isna(date_raw) or str(date_raw).strip() == "":
        return False, None, "Missing", ""
        
    # Determine country logic based on central config
    target_country = getattr(config, "TARGET_COUNTRY", "US")
    day_first = True if target_country == "AU" else False

    # Get dynamic bounds to prevent hardcoded expiration errors
    current_year = datetime.datetime.now().year
    max_year_gate = current_year + 1 # Allows scheduling inspections into next year
    min_year_gate = 1980

    # 1. Handle native datetime/timestamp objects instantly
    if isinstance(date_raw, (pd.Timestamp, datetime.date, datetime.datetime)):
        return True, date_raw.strftime('%Y-%m-%d'), "Valid", ""

    # Clean structural noise
    d_str = str(date_raw).strip()
    d_str = REGEX_DATE_CLEAN.sub('', d_str).strip()
    
    # 2. EDGE CASE: Handle Excel Serial Integer/Float Dates
    if REGEX_EXCEL_SERIAL.match(d_str):
        try:
            serial_num = int(float(d_str))
            
            # Guard against random IDs/Zip codes masquerading as dates
            # 29221 = 1980-01-01 | Serial bounds updated dynamically
            min_serial = 29221 
            max_serial = (datetime.datetime(max_year_gate, 12, 31) - datetime.datetime(1899, 12, 30)).days
            
            if not (min_serial <= serial_num <= max_serial):
                return False, None, "Excel_Serial_Out_Of_Range", d_str
                
            # Convert using Excel's leap-year bug offset origin
            ts = pd.to_datetime(serial_num, unit='D', origin='1899-12-30')
            return True, ts.strftime('%Y-%m-%d'), "Valid", ""
        except Exception:
            return False, None, "Unparsable_Excel_Serial", d_str

    # Fail fast on pure alphabet text remnants
    if not any(c.isdigit() for c in d_str):
        return False, None, "Unrecognizable", d_str

    # 3. EDGE CASE: Standard Date Strings (ISO Check)
    # Fast-path for cleanly formatted ISO strings (YYYY-MM-DD)
    if len(d_str) == 10 and d_str[4] == '-' and d_str[7] == '-':
        try:
            dt = datetime.datetime.strptime(d_str, '%Y-%m-%d')
            if min_year_gate <= dt.year <= max_year_gate:
                return True, d_str, "Valid", ""
        except ValueError:
            pass

    # Fallback to Pandas parsing for complex variations (e.g., "12th of May 26")
    try:
        # Dynamically uses dayfirst setting depending on whether the market is US or AU
        ts = pd.to_datetime(d_str, dayfirst=day_first, format='mixed', errors='raise')
        
        if ts.year > max_year_gate:
            return False, None, "Future_Date_Anomaly", d_str
        if ts.year < min_year_gate:
            return False, None, "Out_Of_Bounds", d_str
            
        return True, ts.strftime('%Y-%m-%d'), "Valid", ""
    except (ValueError, TypeError):
        return False, None, "Unparsable_Format", d_str