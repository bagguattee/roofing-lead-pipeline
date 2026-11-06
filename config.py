# =====================================================================
# COMPLIANCE & DNC SETTINGS (For compliance_code.py)
# =====================================================================
# config.py

DEFAULT_COMPLIANCE_STATUS = "SAFE"

COMPLIANCE_MAP = {
    "true": "DNC",
    "yes": "DNC",
    "1": "DNC",
    "y": "DNC",
    "dnc": "DNC",
    "donotcall": "DNC",
    "unsubscribe": "DNC",
    "stop": "DNC"
}

# config.py

# Safe fallback default status
DEFAULT_LEAD_STATUS = "NEW"

# Ultimate Roofing Dictionary Matrix
ROOFING_STATUS_MAPPING = {
    "won": "WON",
    "lost": "LOST",
    "dead": "DEAD",
    "active": "ACTIVE",
    "quotesent": "QUOTE SENT",
    "inspectioncompleted": "INSPECTION COMPLETED",
    "spoketoowner": "SPOKE TO OWNER",
    "new": "NEW"
}

# =====================================================================
# EMAIL DOMAIN DICTIONARIES (For emails_and_phones.py)
# =====================================================================
# Auto-correct common fat-finger typos on lead lists
DOMAIN_MAP = {
    "gamil.com": "gmail.com",
    "gmial.com": "gmail.com",
    "gmal.com": "gmail.com",
    "yaho.com": "yahoo.com",
    "yahoocom": "yahoo.com",
    "aol.co": "aol.com",
    "hotmai.com": "hotmail.com"
}

# Block fake/burner emails from hitting your lead generation metrics
DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "10minutemail.com",
    "tempmail.com",
    "yopmail.com",
    "sharklasers.com",
    "guerrillamail.com"
}

# Target market configuration for lead formatting engines
TARGET_COUNTRY = "US"

# Default average roofing job value if data is missing (e.g. $8,500)
DEFAULT_ROOF_VALUE = 8511