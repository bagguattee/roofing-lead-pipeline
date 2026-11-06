import sys

import pandas as pd
import io

# Windows consoles default to cp1252, which cannot encode the emoji used in the
# diagnostic output below. Reconfigure stdout so this runs on a stock shell.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def create_mock_csv():
    """Generates a sample CSV string with mismatched, real-world column headers"""
    csv_data = """First Name,lname,Phone Number,email,Address,Last Contact,lead_status,Est. Value
John,Doe,123-456-7890,john@example.com,123 Main St,2025-05-12,WON,$12000
Jane,Smith,9876543210,jane@sample.net,456 Oak Ave,,LOST,7500
Test,User,0000000000,test@dummy.com,999 Fake Rd,2024-01-01,dead,0
"""
    return csv_data

def run_diagnostic():
    print("🛠️  Generating dirty mock lead data...")
    raw_csv_content = create_mock_csv()
    
    # Load the mock CSV file into memory as a dataframe
    df = pd.read_csv(io.StringIO(raw_csv_content), dtype=str)
    actual_columns = list(df.columns)
    
    # This is the exact list of lower_case_snake columns your pipeline expects
    expected_columns = [
        'first_name', 
        'last_name', 
        'phone', 
        'email', 
        'street_address', 
        'last_contact_date', 
        'lead_status', 
        'estimated_value'
    ]
    
    print("\n🔍 --- COLUMN MATCHING DIAGNOSTIC REPORT ---")
    print(f"📊 Total Columns Found in Input: {len(actual_columns)}")
    print("-" * 50)
    
    matched = []
    mismatched = []
    
    for col in actual_columns:
        if col in expected_columns:
            matched.append(col)
        else:
            mismatched.append(col)
            
    print("✅ Perfectly Matching Columns (Your code can read these natively):")
    if matched:
        for col in matched:
            print(f"  • '{col}'")
    else:
        print("  • None!")
        
    print("\n❌ Mismatched Columns (Your code will ignore or crash on these):")
    if mismatched:
        for col in mismatched:
            print(f"  • '{col}'")
    else:
        print("  • None! Clean sweep.")
        
    print("-" * 50)
    
    # Calculate what expected fields are completely unfulfilled
    missing_expectations = [col for col in expected_columns if col not in actual_columns]
    print("💡 Target Columns Still Missing Data Fields:")
    for col in missing_expectations:
        print(f"  → Pipeline expects a field named exactly: '{col}'")
        
    print("\n📋 Dynamic Mapping Suggestion Matrix:")
    print("Based on this run, you would need to write this mapping rule:")
    print("column_map = {")
    for col in mismatched:
        # Give an educational guess example based on simple similarities
        guess = "???"
        normalized = col.lower().replace(" ", "_").replace(".", "")
        if "first" in normalized: guess = "first_name"
        elif "l" in normalized and "name" in normalized: guess = "last_name"
        elif "phone" in normalized: guess = "phone"
        elif "address" in normalized: guess = "street_address"
        elif "contact" in normalized or "date" in normalized: guess = "last_contact_date"
        elif "value" in normalized or "est" in normalized: guess = "estimated_value"
        
        print(f"    '{col}': '{guess}',")
    print("}")

if __name__ == "__main__":
    run_diagnostic()