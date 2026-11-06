# pillars/job_type_pillar.py

# Standardize messy JobNimbus dropdowns into clean marketing tiers
MAINTENANCE_KEYWORDS = [
    'clean', 'wash', 'gutter clean', 'moss removal', 'maintenance', 'treatment', 'tune-up'
]

MAJOR_WORK_KEYWORDS = [
    'replace', 'reroof', 'install', 'repair', 'leak', 'structural', 'shingle', 'gutter installation'
]

def normalize_job_type(job_type_str: str) -> str:
    """
    Standardizes raw JobNimbus job type entries.
    Returns: 'maintenance', 'major', or 'other'
    """
    if not job_type_str or str(job_type_str).strip().lower() in ['nan', 'none', '']:
        return 'other'
        
    text = str(job_type_str).lower().strip()
    
    # 1. Check for Major Work first (more critical for protecting revenue numbers)
    if any(kw in text for kw in MAJOR_WORK_KEYWORDS):
        return 'major'
    
    # 2. Check for Maintenance Work second
    elif any(kw in text for kw in MAINTENANCE_KEYWORDS):
        return 'maintenance'
        
    return 'other'