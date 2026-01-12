import pandas as pd
from pathlib import Path

DB_PATH = Path("dantotsu_global_db.csv")
IDS_PATH = Path("duplicate_comments.txt")

def cleanup():
    if not DB_PATH.exists():
        print(f"❌ {DB_PATH} not found!")
        return
    if not IDS_PATH.exists():
        print(f"❌ {IDS_PATH} not found!")
        return

    # 1. Load IDs and force them to be standard integers
    with open(IDS_PATH, 'r') as f:
        ids_to_delete = [int(float(line.strip())) for line in f if line.strip()]
    
    print(f"🔍 Target IDs to mark as deleted: {ids_to_delete}")

    # 2. Load Database with tab separator
    # We read everything as strings initially to avoid Pandas "guessing" floats
    df = pd.read_csv(DB_PATH, sep='\t')

    # 3. List of columns that MUST be integers (no .0)
    int_columns = [
        'comment_id', 'user_id', 'media_id', 'parent_comment_id', 
        'deleted', 'tag', 'upvotes', 'downvotes', 'user_vote_type', 
        'is_mod', 'is_admin', 'reply_count', 'total_votes'
    ]

    # 4. Convert columns to Nullable Integers ('Int64') 
    # This keeps them as integers even if there are NaN/NULL values
    for col in int_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')

    # 5. PERFORM UPDATE (In-place)
    # Find rows where comment_id is in our list
    mask = df['comment_id'].isin(ids_to_delete)
    
    if mask.any():
        df.loc[mask, 'deleted'] = 1
        df.loc[mask, 'content'] = '[deleted]'
        print(f"✅ Updated {mask.sum()} existing rows.")
    else:
        print("⚠️ No matching IDs found in the CSV.")

    # 6. DEDUPLICATE (Just in case duplicates already existed)
    df = df.drop_duplicates(subset=['comment_id'], keep='first')

    # 7. Final Clean: Ensure no decimals on save
    # Float format is not used because we are using Int64 type
    df.to_csv(DB_PATH, sep='\t', index=False)
    print(f"💾 Database saved to {DB_PATH}")

if __name__ == "__main__":
    cleanup()