import re
import pandas as pd

# USPS CANONICAL DICTIONARIES (Fast Lookups)
USPS_SUFFIXES = {
    'STREET': 'ST', 'ST': 'ST', 'AVENUE': 'AVE', 'AVE': 'AVE',
    'BOULEVARD': 'BLVD', 'BLVD': 'BLVD', 'DRIVE': 'DR', 'DR': 'DR',
    'ROAD': 'RD', 'RD': 'RD', 'COURT': 'CT', 'CT': 'CT',
    'LANE': 'LN', 'LN': 'LN', 'PLACE': 'PL', 'PL': 'PL',
    'TERRACE': 'TER', 'TER': 'TER', 'PARKWAY': 'PKWY', 'PKWY': 'PKWY',
    'CIRCLE': 'CIR', 'CIR': 'CIR', 'HIGHWAY': 'HWY', 'HWY': 'HWY'
}

USPS_DIRS = {
    'NORTH': 'N', 'N': 'N', 'SOUTH': 'S', 'S': 'S',
    'EAST': 'E', 'E': 'E', 'WEST': 'W', 'W': 'W',
    'NORTHEAST': 'NE', 'NE': 'NE', 'NORTHWEST': 'NW', 'NW': 'NW',
    'SOUTHEAST': 'SE', 'SE': 'SE', 'SOUTHWEST': 'SW', 'SW': 'SW'
}

STATE_TOKENS = {'CO', 'COLORADO'}
CITY_TOKENS_MULTI = [
    ('HIGHLANDS', 'RANCH'), ('COLORADO', 'SPRINGS'),
    ('FORT', 'COLLINS'), ('WHEAT', 'RIDGE'),
]
CITY_TOKENS_SINGLE = {
    'DENVER', 'AURORA', 'LAKEWOOD', 'LITTLETON', 'CENTENNIAL',
    'WESTMINSTER', 'ARVADA', 'THORNTON', 'ENGLEWOOD', 'GOLDEN',
    'PARKER', 'BROOMFIELD', 'LONGMONT', 'BOULDER'
}

def _strip_trailing_city_state(tokens):
    """Strips trailing city/state tokens before suffix detection to prevent street corruption."""
    if tokens and tokens[-1] in STATE_TOKENS:
        tokens = tokens[:-1]
    
    if len(tokens) >= 2 and (tokens[-2], tokens[-1]) in CITY_TOKENS_MULTI:
        tokens = tokens[:-2]
    elif tokens and tokens[-1] in CITY_TOKENS_SINGLE:
        tokens = tokens[:-1]
    return tokens

def standardize_address(raw_str):
    """
    Returns: (is_valid_bool, clean_display_address, strict_dedup_signature, has_zip_bool)
    """
    if not raw_str or pd.isna(raw_str):
        return False, "", "", False

    s = str(raw_str).upper().replace('.', '').replace(',', ' ')

    # 1. Explicit PO Box rejection
    if re.match(r'^\s*P\s*O\s*BOX\b', s) or re.match(r'^\s*BOX\b', s):
        return False, "", "", False

    # 2. Extract & Remove Zip Code (Matches 5 digits or ZIP+4, prevents grabbing 5-digit house numbers)
    zip_code = ""
    has_zip = False
    zip_match = re.search(r'\b\d{5}(?:-\d{4})?\b', s)
    if zip_match:
        # Check if the match is likely a house number (first token) vs a zip
        if s.find(zip_match.group(0)) > 3: 
            zip_code = zip_match.group(0)[:5] # Just keep the 5 digits for the key
            has_zip = True
            s = s.replace(zip_match.group(0), '')

    # 3. Extract & Remove Unit/Suite
    unit = ""
    unit_match = re.search(r'\b(APT|STE|SUITE|UNIT|#)\s*[\w\d]+', s)
    if unit_match:
        raw_unit = unit_match.group(0)
        unit = re.sub(r'^(APT|STE|SUITE|#)\s*', 'UNIT', raw_unit.replace(' ', ''))
        s = s.replace(raw_unit, '')

    tokens = s.split()
    if not tokens:
        return False, "", "", False

    # 4. Strip trailing city/state tokens BEFORE suffix detection
    tokens = _strip_trailing_city_state(tokens)
    if not tokens:
        return False, "", "", False

    # 5. Extract House Number (Must be first token, starting with digit)
    house_num = ""
    if re.match(r'^\d+[A-Z]?$', tokens[0]):
        house_num = tokens.pop(0)
        # Fractional unit support (e.g. 123 1/2)
        if tokens and re.match(r'^\d+/\d+$', tokens[0]):
            house_num = f"{house_num} {tokens.pop(0)}"

    # 6. Extract Pre-Directional
    pre_dir = ""
    if tokens and tokens[0] in USPS_DIRS:
        pre_dir = USPS_DIRS[tokens.pop(0)]

    # 7. Extract Post-Directional
    post_dir = ""
    if tokens and tokens[-1] in USPS_DIRS:
        post_dir = USPS_DIRS[tokens.pop(-1)]

    # 8. Extract Suffix
    suffix = ""
    if tokens and tokens[-1] in USPS_SUFFIXES:
        suffix = USPS_SUFFIXES[tokens.pop(-1)]

    street_name = " ".join(tokens)

    # RECONSTRUCTION
    clean_display = f"{house_num} {pre_dir} {street_name} {suffix} {post_dir}".strip()
    clean_display = clean_display.title()
    if unit:
        clean_display += f" {unit.replace('UNIT', 'Unit ')}"
    if zip_code:
        clean_display += f" {zip_code}"
    clean_display = ' '.join(clean_display.split())

    core_street_key = street_name.replace(' ', '')
    house_num_key = house_num.replace(' ', '').replace('/', '-')
    strict_key = f"{house_num_key}_{pre_dir}_{core_street_key}_{suffix}_{post_dir}_{unit}_{zip_code}".upper()
    strict_key = re.sub(r'_+', '_', strict_key).strip('_')

    if not house_num or not core_street_key:
        return False, clean_display, strict_key, has_zip

    return True, clean_display, strict_key, has_zip