import pandas as pd
from pathlib import Path

DB_PATH = Path("dantotsu_global_db.csv")
IDS_PATH = Path("duplicate_comments.txt")

def cleanup():
    if not DB_PATH.exists():
        print(f"❌ {DB_PATH} not found!")
        return
    if not IDS_PATH.exists():
        print(f"❌ {IDS_PATH} not found! Please upload the file.")
        return

    # Load IDs from text file
    with open(IDS_PATH, 'r') as f:
        ids_to_delete = [int(line.strip()) for line in f if line.strip().isdigit()]
    
    print(f"🔍 Found {len(ids_to_delete)} IDs to process.")

    # Load Database
    df = pd.read_csv(DB_PATH, sep='\t')
    
    # Ensure ID column is numeric for matching
    df['comment_id'] = pd.to_numeric(df['comment_id'], errors='coerce')
    
    # Create mask for the targets
    mask = df['comment_id'].isin(ids_to_delete)
    affected_count = mask.sum()

    if affected_count > 0:
        # Update fields
        df.loc[mask, 'deleted'] = 1
        df.loc[mask, 'content'] = '[deleted]'
        
        # Save back with original formatting (tab-separated)
        df.to_csv(DB_PATH, sep='\t', index=False)
        print(f"✅ Successfully updated {affected_count} comments in CSV.")
    else:
        print("⚠️ No matching IDs found in the database.")

if __name__ == "__main__":
    cleanup()
