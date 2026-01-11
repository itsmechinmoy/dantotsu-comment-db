import requests
import json
import csv
import time
import os
import re
import pandas as pd
from pathlib import Path
from datetime import datetime

# --- CONFIGURATION ---
APP_AUTH_KEY = "6*45Qp%W2RS@t38jkXoSKY588Ynj%n"
API_ADDRESS = "https://api.dantotsu.app"
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
AL_TOKEN = os.environ.get("AL_TOKEN")
FEED_CHANNEL_ID = "1180378569109671987"
MOD_BOT_ID = "1212248844398493717"
DB_PATH = Path("dantotsu_global_db.csv")

# CSV headers
FIELD_NAMES = [
    'comment_id', 'user_id', 'media_id', 'parent_comment_id', 'content', 
    'timestamp', 'deleted', 'tag', 'upvotes', 'downvotes', 
    'user_vote_type', 'username', 'profile_picture_url', 
    'is_mod', 'is_admin', 'reply_count', 'total_votes'
]

class DantotsuDailySync:
    def __init__(self):
        self.d_token = None
        
    def authenticate(self):
        """Authenticate with Dantotsu API"""
        print("🔐 Authenticating with Dantotsu...")
        try:
            r = requests.post(
                f"{API_ADDRESS}/authenticate",
                headers={"appauth": APP_AUTH_KEY},
                data={"token": AL_TOKEN},
                timeout=10
            )
            if r.status_code == 200:
                self.d_token = r.json().get("authToken")
                print("✓ Authentication successful")
                return True
            else:
                print(f"❌ Auth failed: {r.status_code}")
        except Exception as e:
            print(f"❌ Auth error: {e}")
        return False
    
    def get_headers(self):
        """Get request headers"""
        return {
            "appauth": APP_AUTH_KEY,
            "Authorization": self.d_token
        }
    
    def format_row(self, c):
        """Format comment data for CSV"""
        u = c.get('user', {}) if isinstance(c.get('user'), dict) else {}
        
        return {
            'comment_id': c.get('comment_id', ''),
            'user_id': c.get('user_id', ''),
            'media_id': c.get('media_id', ''),
            'parent_comment_id': c.get('parent_comment_id', 'NULL'),
            'content': str(c.get('content', '')).replace('\t', ' ').replace('\n', ' '),
            'timestamp': c.get('timestamp', ''),
            'deleted': 1 if c.get('deleted') in [True, 1, '1'] else 0,
            'tag': c.get('tag', 'NULL'),
            'upvotes': int(c.get('upvotes', 0)),
            'downvotes': int(c.get('downvotes', 0)),
            'user_vote_type': c.get('user_vote_type', 0),
            'username': c.get('username', u.get('username', 'NULL')),
            'profile_picture_url': c.get('profile_picture_url', u.get('profile_picture_url', 'NULL')),
            'is_mod': 1 if (c.get('is_mod') or u.get('is_mod')) in [True, 1, '1'] else 0,
            'is_admin': 1 if (c.get('is_admin') or u.get('is_admin')) in [True, 1, '1'] else 0,
            'reply_count': int(c.get('reply_count', 0)),
            'total_votes': int(c.get('total_votes', 0))
        }
    
    def fetch_single_comment(self, comment_id, max_retries=2):
        """Fetch a single comment by ID"""
        headers = self.get_headers()
        
        for attempt in range(max_retries):
            try:
                r = requests.get(
                    f"{API_ADDRESS}/comments/{comment_id}",
                    headers=headers,
                    timeout=10
                )
                
                if r.status_code == 429:
                    print(f"⚠️  Rate limited, waiting 30s...")
                    time.sleep(30)
                    continue
                
                if r.status_code == 200:
                    return r.json()
                
                return None
                
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"❌ Error fetching comment {comment_id}: {e}")
                return None
        
        return None
    
    def fetch_media_comments(self, media_id):
        """Fetch all comments for a media"""
        all_comments = []
        page = 1
        headers = self.get_headers()
        
        while True:
            try:
                r = requests.get(
                    f"{API_ADDRESS}/comments/{media_id}/{page}?sort=newest",
                    headers=headers,
                    timeout=15
                )
                
                if r.status_code == 429:
                    print(f"⚠️  Rate limited on media {media_id}, waiting 30s...")
                    time.sleep(30)
                    continue
                
                if r.status_code != 200:
                    break
                
                data = r.json().get('comments', [])
                if not data:
                    break
                
                all_comments.extend(data)
                page += 1
                time.sleep(0.15)  # Rate limiting
                
            except Exception as e:
                print(f"❌ Error fetching media {media_id}: {e}")
                break
        
        return all_comments
    
    def check_discord_deletions(self, existing_comment_ids):
        """Check Discord for mod deletions"""
        if not DISCORD_TOKEN:
            print("⚠️  No Discord token, skipping deletion check")
            return set()
        
        print("🔨 Checking Discord for mod deletions...")
        deleted_ids = set()
        
        try:
            r = requests.get(
                f"https://discord.com/api/v9/channels/{FEED_CHANNEL_ID}/messages?limit=100",
                headers={"Authorization": DISCORD_TOKEN},
                timeout=10
            )
            
            if r.status_code == 200:
                for msg in r.json():
                    content = msg.get('content', '')
                    author_id = str(msg.get('author', {}).get('id', ''))
                    
                    # Check if message is from mod bot
                    if MOD_BOT_ID in author_id:
                        # Extract comment ID from deletion message
                        match = re.search(r'comment[_\s]*id[:\s]+(\d+)', content, re.IGNORECASE)
                        if match:
                            cid = int(match.group(1))
                            if cid in existing_comment_ids:
                                deleted_ids.add(cid)
                                print(f"  Found deletion: Comment {cid}")
        except Exception as e:
            print(f"⚠️  Discord check failed: {e}")
        
        return deleted_ids
    
    def discover_new_comments(self, last_known_id):
        """Discover new comments by checking sequential IDs"""
        print(f"🔍 Scanning for new comments after ID {last_known_id}...")
        
        new_comments = []
        active_media = set()
        consecutive_404s = 0
        current_id = last_known_id + 1
        max_consecutive_404s = 50  # Stop after 50 empty IDs
        
        while consecutive_404s < max_consecutive_404s:
            comment = self.fetch_single_comment(current_id)
            
            if comment:
                print(f"  ✨ Found new comment: {current_id}")
                new_comments.append(self.format_row(comment))
                active_media.add(int(comment.get('media_id')))
                consecutive_404s = 0
            else:
                consecutive_404s += 1
                if consecutive_404s % 10 == 0:
                    print(f"  ⏳ Checked {consecutive_404s} empty IDs...")
            
            current_id += 1
            time.sleep(0.1)
        
        print(f"✓ Discovered {len(new_comments)} new comments")
        return new_comments, active_media
    
    def refresh_active_media(self, media_ids, existing_comment_ids):
        """Refresh comments from active media threads"""
        if not media_ids:
            return []
        
        print(f"🔄 Refreshing {len(media_ids)} active media threads...")
        new_comments = []
        
        for idx, media_id in enumerate(media_ids, 1):
            comments = self.fetch_media_comments(media_id)
            
            # Only add comments we don't have
            for c in comments:
                cid = c.get('comment_id')
                if cid not in existing_comment_ids:
                    new_comments.append(self.format_row(c))
            
            print(f"  [{idx}/{len(media_ids)}] Media {media_id}: {len(comments)} comments fetched")
        
        print(f"✓ Found {len(new_comments)} new comments from active threads")
        return new_comments
    
    def run_daily_sync(self):
        """Main sync function"""
        print("="*70)
        print("DANTOTSU DAILY SYNC")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)
        
        # Check if database exists
        if not DB_PATH.exists():
            print("❌ Database file not found!")
            print("   Please run the initial scrape first with your local script.")
            return False
        
        # Load existing data
        print(f"\n📂 Loading database: {DB_PATH}")
        df = pd.read_csv(DB_PATH, sep='\t')
        initial_count = len(df)
        print(f"✓ Loaded {initial_count} existing comments")
        
        last_id = int(df['comment_id'].max())
        existing_comment_ids = set(df['comment_id'].astype(int))
        
        # 1. Discover new comments
        new_comments, active_media = self.discover_new_comments(last_id)
        
        # 2. Refresh active media threads
        thread_comments = self.refresh_active_media(active_media, existing_comment_ids)
        new_comments.extend(thread_comments)
        
        # 3. Check for deletions
        deleted_ids = self.check_discord_deletions(existing_comment_ids)
        if deleted_ids:
            df.loc[df['comment_id'].isin(deleted_ids), 'deleted'] = 1
            print(f"✓ Marked {len(deleted_ids)} comments as deleted")
        
        # 4. Merge new data
        if new_comments:
            print(f"\n💾 Adding {len(new_comments)} new comments to database...")
            df_new = pd.DataFrame(new_comments)
            df = pd.concat([df, df_new], ignore_index=True)
        
        # 5. Deduplicate and sort
        df = df.drop_duplicates(subset=['comment_id'], keep='last')
        df = df.sort_values('comment_id')
        
        # 6. Save
        df.to_csv(DB_PATH, sep='\t', index=False)
        
        final_count = len(df)
        added = final_count - initial_count
        
        print("\n" + "="*70)
        print("✅ SYNC COMPLETE")
        print("="*70)
        print(f"Initial comments: {initial_count}")
        print(f"New comments added: {added}")
        print(f"Deletions marked: {len(deleted_ids)}")
        print(f"Final total: {final_count}")
        print("="*70)
        
        return True


def main():
    """Entry point for GitHub Actions"""
    # Check environment variables
    if not AL_TOKEN:
        print("❌ AL_TOKEN environment variable not set!")
        return False
    
    if not DISCORD_TOKEN:
        print("⚠️  DISCORD_TOKEN not set - deletion checking will be skipped")
    
    # Run sync
    sync = DantotsuDailySync()
    
    if not sync.authenticate():
        print("❌ Authentication failed")
        return False
    
    return sync.run_daily_sync()


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
