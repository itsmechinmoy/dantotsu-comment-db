import requests
import json
import csv
import time
import os
import re
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION ---
APP_AUTH_KEY = "6*45Qp%W2RS@t38jkXoSKY588Ynj%n"
API_ADDRESS = "https://api.dantotsu.app"
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
AL_TOKEN = os.environ.get("AL_TOKEN")
FEED_CHANNEL_ID = "1180378569109671987"
MOD_BOT_ID = "1212248844398493717"
DB_PATH = Path("dantotsu_global_db.csv")

class DantotsuManager:
    def __init__(self):
        self.d_token = None
        self.field_names = [
            'comment_id', 'user_id', 'media_id', 'parent_comment_id', 'content', 
            'timestamp', 'deleted', 'tag', 'upvotes', 'downvotes', 
            'user_vote_type', 'username', 'profile_picture_url', 
            'is_mod', 'is_admin', 'reply_count', 'total_votes'
        ]

    def get_auth(self):
        try:
            r = requests.post(f"{API_ADDRESS}/authenticate", headers={"appauth": APP_AUTH_KEY}, data={"token": AL_TOKEN})
            if r.status_code == 200:
                self.d_token = r.json().get("authToken")
                return True
        except: return False
        return False

    def format_row(self, c):
        u = c.get('user', {})
        return {
            'comment_id': c.get('comment_id'),
            'user_id': c.get('user_id'),
            'media_id': c.get('media_id'),
            'parent_comment_id': c.get('parent_comment_id', 'NULL'),
            'content': str(c.get('content', '')).replace('\t', ' ').replace('\n', ' '),
            'timestamp': c.get('timestamp'),
            'deleted': 1 if c.get('deleted') is True else 0,
            'tag': c.get('tag', 'NULL'),
            'upvotes': int(c.get('upvotes', 0)),
            'downvotes': int(c.get('downvotes', 0)),
            'user_vote_type': c.get('user_vote_type', 0),
            'username': u.get('username', 'NULL'),
            'profile_picture_url': u.get('profile_picture_url', 'NULL'),
            'is_mod': 1 if u.get('is_mod') is True else 0,
            'is_admin': 1 if u.get('is_admin') is True else 0,
            'reply_count': int(c.get('reply_count', 0)),
            'total_votes': int(c.get('total_votes', 0))
        }

    def fetch_media_comments(self, m_id):
        all_c, page = [], 1
        headers = {"appauth": APP_AUTH_KEY, "Authorization": self.d_token}
        while True:
            r = requests.get(f"{API_ADDRESS}/comments/{m_id}/{page}", headers=headers)
            data = r.json().get('comments', []) if r.status_code == 200 else []
            if not data: break
            all_c.extend(data)
            page += 1
            time.sleep(0.1)
        return all_c

    def fetch_single(self, cid):
        headers = {"appauth": APP_AUTH_KEY, "Authorization": self.d_token}
        try:
            r = requests.get(f"{API_ADDRESS}/comments/{cid}", headers=headers, timeout=10)
            return r.json() if r.status_code == 200 else None
        except: return None

    def run_daily_sync(self):
        if not DB_PATH.exists(): return
        print("🔍 Scanning for new comments...")
        df = pd.read_csv(DB_PATH, sep='\t')
        last_id = int(df['comment_id'].max())
        
        new_comments = []
        active_media = set()
        consecutive_404s = 0
        current_id = last_id + 1

        # 1. Discover new IDs sequentially
        while consecutive_404s < 20: # Stop when we hit 20 empty IDs in a row
            res = self.fetch_single(current_id)
            if res:
                print(f"✨ Found new comment: {current_id}")
                new_comments.append(self.format_row(res))
                active_media.add(int(res.get('media_id')))
                consecutive_404s = 0
            else:
                consecutive_404s += 1
            current_id += 1
            time.sleep(0.1)

        # 2. Refresh active media threads
        if active_media:
            print(f"🔄 Refreshing {len(active_media)} active threads...")
            for mid in active_media:
                thread = self.fetch_media_comments(mid)
                new_comments.extend([self.format_row(c) for c in thread])

        # 3. Sync Mod Deletes from Discord Logs
        print("🔨 Checking Mod Logs for deletes...")
        log_r = requests.get(f"https://discord.com/api/v9/channels/{FEED_CHANNEL_ID}/messages?limit=100", 
                             headers={"Authorization": DISCORD_TOKEN})
        if log_r.status_code == 200:
            for m in log_r.json():
                if MOD_BOT_ID in str(m.get('author', {}).get('id')):
                    cid_m = re.search(r'comment_id[:\s]+(\d+)', m.get('content', ''))
                    if cid_m: 
                        df.loc[df['comment_id'] == int(cid_m.group(1)), 'deleted'] = 1

        # 4. Merge and Save
        if new_comments:
            df_new = pd.DataFrame(new_comments)
            df = pd.concat([df, df_new])
        
        df.drop_duplicates(subset=['comment_id'], keep='last').sort_values('comment_id').to_csv(DB_PATH, sep='\t', index=False)
        print("✅ Sync complete.")

if __name__ == "__main__":
    mgr = DantotsuManager()
    if mgr.get_auth():
        mgr.run_daily_sync()
