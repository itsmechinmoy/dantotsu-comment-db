#!/usr/bin/env python3
import sys
import requests
import json
import csv
import time
import os
import re
import pandas as pd
from pathlib import Path
from datetime import datetime

# Force unbuffered output for real-time logs in GitHub Actions
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# --- CONFIGURATION ---
APP_AUTH_KEY = "6*45Qp%W2RS@t38jkXoSKY588Ynj%n"
API_ADDRESS = "https://api.dantotsu.app"
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
AL_TOKEN = os.environ.get("AL_TOKEN")
GUILD_ID = "1163949787213746248"  # Dantotsu Discord server
MOD_BOT_ID = "1212248844398493717"  # Dantotsu Comment Bot
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
        """Authenticate with Dantotsu API with retry logic"""
        print("🔐 Authenticating with Dantotsu...")
        max_retries = 5
        base_wait = 5
        
        for attempt in range(max_retries):
            try:
                r = requests.post(
                    f"{API_ADDRESS}/authenticate",
                    headers={"appauth": APP_AUTH_KEY},
                    data={"token": AL_TOKEN},
                    timeout=30  # Increased from 10 to 30 seconds
                )
                if r.status_code == 200:
                    self.d_token = r.json().get("authToken")
                    print("✓ Authentication successful")
                    sys.stdout.flush()
                    return True
                else:
                    print(f"❌ Auth failed: {r.status_code}")
                    if attempt < max_retries - 1:
                        wait_time = base_wait * (2 ** attempt)
                        print(f"   Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                        sys.stdout.flush()
                        time.sleep(wait_time)
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = base_wait * (2 ** attempt)
                    print(f"⚠️  Timeout! Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    sys.stdout.flush()
                    time.sleep(wait_time)
                else:
                    print(f"❌ Auth timeout after {max_retries} attempts")
            except Exception as e:
                print(f"❌ Auth error: {e}")
                if attempt < max_retries - 1:
                    wait_time = base_wait * (2 ** attempt)
                    print(f"   Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    sys.stdout.flush()
                    time.sleep(wait_time)
        
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
    
    def fetch_single_comment(self, comment_id, max_retries=3):
        """Fetch a single comment by ID with retry logic"""
        headers = self.get_headers()
        base_wait = 2
        
        for attempt in range(max_retries):
            try:
                r = requests.get(
                    f"{API_ADDRESS}/comments/{comment_id}",
                    headers=headers,
                    timeout=30
                )
                
                if r.status_code == 429:
                    print(f"⚠️  Rate limited, waiting 30s...")
                    sys.stdout.flush()
                    time.sleep(30)
                    continue
                
                if r.status_code == 200:
                    return r.json()
                
                return None
            
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = base_wait * (2 ** attempt)
                    print(f"⚠️  Timeout fetching comment {comment_id}, retry in {wait_time}s...")
                    sys.stdout.flush()
                    time.sleep(wait_time)
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"❌ Error fetching comment {comment_id}: {e}")
                    sys.stdout.flush()
                return None
        
        return None
    
    def fetch_media_comments(self, media_id):
        """Fetch all comments for a media with retry logic"""
        all_comments = []
        page = 1
        headers = self.get_headers()
        max_page_retries = 3
        base_wait = 2
        
        while True:
            page_success = False
            
            for attempt in range(max_page_retries):
                try:
                    r = requests.get(
                        f"{API_ADDRESS}/comments/{media_id}/{page}?sort=newest",
                        headers=headers,
                        timeout=30
                    )
                    
                    if r.status_code == 429:
                        print(f"⚠️  Rate limited on media {media_id}, waiting 30s...")
                        sys.stdout.flush()
                        time.sleep(30)
                        continue
                    
                    if r.status_code != 200:
                        return all_comments
                    
                    data = r.json().get('comments', [])
                    if not data:
                        return all_comments
                    
                    all_comments.extend(data)
                    page += 1
                    page_success = True
                    time.sleep(0.15)  # Rate limiting
                    break
                
                except requests.exceptions.Timeout:
                    if attempt < max_page_retries - 1:
                        wait_time = base_wait * (2 ** attempt)
                        print(f"⚠️  Timeout on media {media_id} page {page}, retry in {wait_time}s...")
                        sys.stdout.flush()
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Failed to fetch media {media_id} page {page} after {max_page_retries} attempts")
                        sys.stdout.flush()
                        return all_comments
                        
                except Exception as e:
                    print(f"❌ Error fetching media {media_id}: {e}")
                    sys.stdout.flush()
                    return all_comments
            
            if not page_success:
                break
        
        return all_comments
    
    def check_discord_deletions(self, existing_comment_ids):
        """Check Discord server-wide for mod deletions"""
        if not DISCORD_TOKEN:
            print("⚠️  No Discord token, skipping deletion check")
            return set()
        
        print("🔨 Checking Discord for mod deletions (server-wide)...")
        sys.stdout.flush()
        deleted_ids = set()
        
        try:
            # Search server-wide for bot's deletion messages
            # Using Discord's search API to find messages from the bot
            
            # Search query: messages from bot containing "has been deleted"
            search_url = f"https://discord.com/api/v9/guilds/{GUILD_ID}/messages/search"
            params = {
                "author_id": MOD_BOT_ID,
                "content": "has been deleted",
                "include_nsfw": "true"
            }
            
            r = requests.get(
                search_url,
                headers={"Authorization": DISCORD_TOKEN},
                params=params,
                timeout=15
            )
            
            if r.status_code == 200:
                data = r.json()
                messages = data.get('messages', [])
                
                # Discord returns messages in nested arrays
                for msg_group in messages:
                    if isinstance(msg_group, list):
                        for msg in msg_group:
                            content = msg.get('content', '')
                            # Extract comment ID from "Comment with id 1148 has been deleted"
                            match = re.search(r'Comment with id (\d+) has been deleted', content, re.IGNORECASE)
                            if match:
                                cid = int(match.group(1))
                                if cid in existing_comment_ids:
                                    deleted_ids.add(cid)
                                    print(f"  Found deletion: Comment {cid}")
                                    sys.stdout.flush()
                    elif isinstance(msg_group, dict):
                        content = msg_group.get('content', '')
                        match = re.search(r'Comment with id (\d+) has been deleted', content, re.IGNORECASE)
                        if match:
                            cid = int(match.group(1))
                            if cid in existing_comment_ids:
                                deleted_ids.add(cid)
                                print(f"  Found deletion: Comment {cid}")
                                sys.stdout.flush()
                
                print(f"✓ Scanned deletion messages, found {len(deleted_ids)} deletions")
                sys.stdout.flush()
            else:
                print(f"⚠️  Discord search returned {r.status_code}: {r.text[:200]}")
                sys.stdout.flush()
                
        except Exception as e:
            print(f"⚠️  Discord check failed: {e}")
            sys.stdout.flush()
        
        return deleted_ids
    
    def discover_new_comments(self, last_known_id):
        """Discover new comments by checking sequential IDs"""
        print(f"🔍 Scanning for new comments after ID {last_known_id}...")
        sys.stdout.flush()  # Force output
        
        new_comments = []
        active_media = set()
        consecutive_404s = 0
        current_id = last_known_id + 1
        max_consecutive_404s = 50  # Stop after 50 empty IDs
        
        while consecutive_404s < max_consecutive_404s:
            comment = self.fetch_single_comment(current_id)
            
            if comment:
                print(f"  ✨ Found new comment: {current_id}")
                sys.stdout.flush()
                new_comments.append(self.format_row(comment))
                active_media.add(int(comment.get('media_id')))
                consecutive_404s = 0
            else:
                consecutive_404s += 1
                if consecutive_404s % 10 == 0:
                    print(f"  ⏳ Checked {consecutive_404s} empty IDs...")
                    sys.stdout.flush()
            
            current_id += 1
            time.sleep(0.1)
        
        print(f"✓ Discovered {len(new_comments)} new comments")
        sys.stdout.flush()
        return new_comments, active_media
    
    def refresh_active_media(self, media_ids, existing_comment_ids):
        """Refresh comments from active media threads"""
        if not media_ids:
            return []
        
        print(f"🔄 Refreshing {len(media_ids)} active media threads...")
        sys.stdout.flush()
        new_comments = []
        
        for idx, media_id in enumerate(media_ids, 1):
            comments = self.fetch_media_comments(media_id)
            
            # Only add comments we don't have
            for c in comments:
                cid = c.get('comment_id')
                if cid not in existing_comment_ids:
                    new_comments.append(self.format_row(c))
            
            print(f"  [{idx}/{len(media_ids)}] Media {media_id}: {len(comments)} comments fetched")
            sys.stdout.flush()
        
        print(f"✓ Found {len(new_comments)} new comments from active threads")
        sys.stdout.flush()
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
        
        # Clean up: remove rows with invalid comment IDs
        df = df.dropna(subset=['comment_id'])
        df = df[df['comment_id'] != '']
        df['comment_id'] = pd.to_numeric(df['comment_id'], errors='coerce')
        df = df.dropna(subset=['comment_id'])
        df['comment_id'] = df['comment_id'].astype(int)
        
        initial_count = len(df)
        print(f"✓ Loaded {initial_count} valid comments")
        
        last_id = int(df['comment_id'].max())
        existing_comment_ids = set(df['comment_id'])
        
        # 1. Discover new comments
        new_comments, active_media = self.discover_new_comments(last_id)
        
        # 2. Refresh active media threads
        thread_comments = self.refresh_active_media(active_media, existing_comment_ids)
        new_comments.extend(thread_comments)
        
        # 3. Check for deletions and update content
        deleted_ids = self.check_discord_deletions(existing_comment_ids)
        if deleted_ids:
            # Only update comments that are NOT already marked as deleted
            not_deleted_mask = (df['comment_id'].isin(deleted_ids)) & (df['deleted'] != 1)
            newly_deleted_count = not_deleted_mask.sum()
            
            if newly_deleted_count > 0:
                # Mark as deleted AND change content to [deleted]
                df.loc[not_deleted_mask, 'deleted'] = 1
                df.loc[not_deleted_mask, 'content'] = '[deleted]'
                print(f"✓ Marked {newly_deleted_count} NEW deletions (skipped {len(deleted_ids) - newly_deleted_count} already deleted)")
            else:
                print(f"✓ Found {len(deleted_ids)} deletion messages but all were already marked")
            sys.stdout.flush()
        
        # 4. Merge new data
        if new_comments:
            print(f"\n💾 Adding {len(new_comments)} new comments to database...")
            df_new = pd.DataFrame(new_comments)
            # Ensure comment_id is int in new data
            if len(df_new) > 0:
                df_new['comment_id'] = pd.to_numeric(df_new['comment_id'], errors='coerce')
                df_new = df_new.dropna(subset=['comment_id'])
                df_new['comment_id'] = df_new['comment_id'].astype(int)
            df = pd.concat([df, df_new], ignore_index=True)
        
        # 5. Deduplicate and sort
        df = df.drop_duplicates(subset=['comment_id'], keep='last')
        df = df.sort_values('comment_id')
        
        # 6. Fix data types - ensure integers don't have .0
        int_columns = ['comment_id', 'user_id', 'media_id', 'parent_comment_id', 
                       'deleted', 'tag', 'upvotes', 'downvotes', 'user_vote_type',
                       'is_mod', 'is_admin', 'reply_count', 'total_votes']
        
        for col in int_columns:
            if col in df.columns:
                # Convert to Int64 (pandas nullable integer) to handle NaN properly
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].fillna(0).astype('Int64')
                # Replace 0 with empty string for parent_comment_id and tag if needed
                if col in ['parent_comment_id', 'tag']:
                    df[col] = df[col].replace(0, pd.NA)
        
        # 7. Save
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
