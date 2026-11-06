import pandas as pd
import re
import unicodedata
import sys
import os

# Bridge the path to find your root config.py if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Pre-compiled matrices for processing speed
REGEX_CLEAN_TEXT = re.compile(r'[^\w\s\-\.\']')
REGEX_WHITESPACE = re.compile(r'\s+')

# ==============================================================================
# THE PUBLIC PIPELINE PLUGS
# ==============================================================================

def standardize_name(text_raw):
    """
    THE PIPELINE PLUG FOR NAMES:
    Standardizes first/last names to clean Title Case (e.g., "john d'oe" -> "John D'oe").
    """
    is_valid, clean, reason = standardize_text(text_raw, to_title=True)
    return clean if clean else ""

def standardize_address(text_raw):
    """
    THE PIPELINE PLUG FOR ADDRESSES:
    Cleans up punctuation noise and ensures standard capitalization for CRM mapping.
    """
    is_valid, clean, reason = standardize_text(text_raw, to_title=True)
    return clean if clean else ""

# ==============================================================================
# DATA PURIFICATION CORE ENGINE
# ==============================================================================

def standardize_text(text_raw, to_title=False):
    """
    Core normalization logic: Handles Unicode, removes noise characters, and
    strips whitespace.
    """
    if pd.isna(text_raw) or str(text_raw).strip() == "":
        return False, None, "Missing"
    
    # Unicode Normalization (e.g., handles accents and non-ASCII character cleanup safely)
    text = unicodedata.normalize('NFKD', str(text_raw)).encode('ASCII', 'ignore').decode('utf-8')
    
    # Strip noise characters
    text = REGEX_CLEAN_TEXT.sub('', text)
    
    # Clean spacing
    text = REGEX_WHITESPACE.sub(' ', text).strip()
    
    # Conditional Title Casing (with support for hyphenated names/addresses)
    if to_title:
        # Standard title case logic
        text = ' '.join([word.capitalize() for word in text.split()])
    
    if len(text) < 2:
        return False, None, "Too_Short_To_Be_Valid"
        
    return True, text, "Valid"