import pandas as pd
import re
import sys
import os

# Bridge the path to find your root config.py
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from config import DOMAIN_MAP, DISPOSABLE_DOMAINS

# ==============================================================================
# 1. PRE-COMPILED MATRICES
# ==============================================================================
REGEX_NON_PRINTABLE = re.compile(r'[^\x20-\x7E]')
REGEX_WHITESPACE    = re.compile(r'\s+')
REGEX_RFC_EMAIL     = re.compile(r"^[\w\.\-\+'&]+@[\w\-]+(\.[\w\-]+)+$")
REGEX_JUNK_PREFIX   = re.compile(r'^(test|dummy|noemail|fake|placeholder|none|na)\d*$|^[\-\+]+$')

# ==============================================================================
# 2. THE PUBLIC PIPELINE PLUG
# ==============================================================================
def standardize_email(email_raw):
    """
    THE PIPELINE PLUG FOR EMAILS:
    Returns a tuple: (primary_clean_string, secondary_clean_string)
    """
    is_valid, p_clean, s_clean, status, fallback = _process_email_logic(email_raw)
    
    # Ensure we return empty strings instead of None so safe_unpack doesn't stringify "None"
    primary_out = p_clean if p_clean else ""
    secondary_out = s_clean if s_clean else ""
    
    return (primary_out, secondary_out)

# ==============================================================================
# 3. INTERNAL DATA PURIFICATION CORE ENGINES
# ==============================================================================
def _clean_single_email(email_raw):
    if not email_raw or str(email_raw).strip() == "": 
        return None, "Missing"
        
    email = str(email_raw).lower()
    email = REGEX_NON_PRINTABLE.sub('', email) 
    email = REGEX_WHITESPACE.sub('', email).strip('.')
    
    if '@' not in email or len(email) < 5 or not any(c.isalpha() for c in email):
        return None, "Unrecognizable"
    
    local, domain = email.split('@', 1)
    if REGEX_JUNK_PREFIX.match(local) or domain == 'example.com':
        return None, "Junk_Placeholder"
    
    # 🛑 PRESERVED SAFETY GATE: Check for high-risk burner domains
    if domain in DISPOSABLE_DOMAINS:
        return None, "Disposable_Email"
    
    # Correct common consumer typos automatically from config
    if domain in DOMAIN_MAP: 
        domain = DOMAIN_MAP[domain]
        
    final_email = f"{local}@{domain}"
    if not REGEX_RFC_EMAIL.match(final_email): 
        return final_email, "Fixable_Typo"
        
    return final_email, "Valid"

def _process_email_logic(email_raw):
    if pd.isna(email_raw) or str(email_raw).strip() == "": 
        return False, None, None, "Missing", ""
        
    raw_str = str(email_raw).strip()
    
    # SAFE SPLIT: Split, strip whitespace, and filter out any empty strings
    split_emails = [e.strip() for e in re.split(r'[;,]', raw_str) if e.strip()]
    
    if not split_emails:
        return False, None, None, "Missing", ""
        
    primary_raw = split_emails[0]
    secondary_raw = split_emails[1] if len(split_emails) > 1 else None
    
    p_clean, p_status = _clean_single_email(primary_raw)
    s_clean, _ = _clean_single_email(secondary_raw) if secondary_raw else (None, None)
    
    if p_status == "Valid":
        return True, p_clean, s_clean, "Valid", ""
    elif p_status == "Disposable_Email":
        return False, None, s_clean, "Disposable_Email", primary_raw
    elif p_status == "Fixable_Typo" and p_clean:
        return False, None, s_clean, "Fixable_Typo", p_clean
    else:
        return False, None, s_clean, p_status, primary_raw