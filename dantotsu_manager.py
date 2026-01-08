import requests
import json
import csv
import time
import os
import re
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION (Pulled from GitHub Secrets) ---
APP_AUTH_KEY = "6*45Qp%W2RS@t38jkXoSKY588Ynj%n"
API_ADDRESS = "https://api.dantotsu.app"
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
AL_TOKEN = os.environ.get("AL_TOKEN")
FEED_CHANNEL_ID = "1180378569109671987"
MOD_BOT_ID = "1212248844398493717"
DELETE_CMD_ID = "1212448947499700316"
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
        if not AL_TOKEN:
            print("❌ AL_TOKEN secret missing.")
            return False
        try:
            r = requests.post(f"{API_ADDRESS}/authenticate", 
                              headers={"appauth": APP_AUTH_KEY}, 
                              data={"token": AL_TOKEN})
            if r.status_code == 200:
                self.d_token = r.json().get("authToken")
                print(f"✓ Authenticated as: {r.json()['user']['username']}")
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
        all_c = []
        page = 1
        headers = {"appauth": APP_AUTH_KEY, "Authorization": self.d_token}
        while True:
            r = requests.get(f"{API_ADDRESS}/comments/{m_id}/{page}?sort=newest", headers=headers)
            if r.status_code != 200: break
            data = r.json().get('comments', [])
            if not data: break
            all_c.extend(data)
            page += 1
            time.sleep(0.1)
        return all_c

    def run_smart_sync(self):
        print("🚀 Starting Smart Sync...")
        headers = {"Authorization": DISCORD_TOKEN}
        r = requests.get(f"https://discord.com/api/v9/channels/{FEED_CHANNEL_ID}/messages?limit=100", headers=headers)
        
        deleted_ids, active_media = [], set()
        if r.status_code == 200:
            for m in r.json():
                content = m.get('content', '')
                mid_m = re.search(r'\* Media: (\d+)', content)
                if mid_m: active_media.add(int(mid_m.group(1)))
                if MOD_BOT_ID in str(m.get('author', {}).get('id')) or DELETE_CMD_ID in content:
                    cid_m = re.search(r'comment_id[:\s]+(\d+)', content)
                    if cid_m: deleted_ids.append(int(cid_m.group(1)))

        if DB_PATH.exists():
            df = pd.read_csv(DB_PATH, sep='\t')
            if deleted_ids:
                df.loc[df['comment_id'].isin(deleted_ids), 'deleted'] = 1
                print(f"🔨 Flagged {len(deleted_ids)} deletions.")
            
            new_rows = []
            for mid in active_media:
                new_rows.extend([self.format_row(c) for c in self.fetch_media_comments(mid)])
            
            if new_rows:
                df = pd.concat([df, pd.DataFrame(new_rows)]).drop_duplicates(subset=['comment_id'], keep='last')
            
            df.sort_values('comment_id').to_csv(DB_PATH, sep='\t', index=False)
            print("✨ Sync Complete.")

if __name__ == "__main__":
    mgr = DantotsuManager()
    if mgr.get_auth():
        mgr.run_smart_sync()
