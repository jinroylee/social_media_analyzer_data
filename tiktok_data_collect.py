#!/usr/bin/env python
"""
Collect trending TikTok videos in the beauty / cosmetics niche that were
posted exactly 30 days ago. Save:
    • description + hashtags
    • creator follower-count (current)
    • view, like, share, comment counts
    • top-5 comments
    • local path to 256×256 JPEG thumbnail
Result is written to a Parquet file ready for ML ingestion.
"""

import os, re, json, time, random, datetime as dt
import asyncio
from pathlib import Path
import traceback
from typing import List, Dict
import pandas as pd
from PIL import Image
from io import BytesIO
from tqdm import tqdm
from TikTokApi import TikTokApi

# ---------- tweakables ----------
SEARCH_TERMS  = ["beauty"] #, "makeup", "cosmetics", "skincare"
VIDEOS_PER_TAG     = 100          # stop earlier if you like
REQUEST_CAP        = 500          # hard maximum attempts per run
OUT_DIR            = Path("tiktok_data")
THUMBS_DIR         = OUT_DIR / "thumbnails"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
# --------------------------------
# 
TARGET_DATE = (dt.datetime.utcnow() - dt.timedelta(days=1)).date() #change targetdate
TARGET_START = dt.datetime.combine(TARGET_DATE, dt.time.min).timestamp()
TARGET_END   = dt.datetime.combine(TARGET_DATE, dt.time.max).timestamp()

def resize_and_save(img_bytes: bytes, out_path: Path) -> None:
    im = Image.open(BytesIO(img_bytes)).convert("RGB")
    im = im.resize((256, 256), Image.LANCZOS)
    im.save(out_path, format="JPEG", quality=90, optimize=True)

def extract_hashtags(txt: str) -> List[str]:
    return re.findall(r"#([A-Za-z0-9_]+)", txt)

async def fetch_top_comments(video, n: int = 5) -> List[str]:
    comments = []
    try:
        async for c in video.comments(count=50):    # pull a page
            comments.append((c.stats["diggCount"], c.text))
        comments.sort(reverse=True)          # by like count
    except Exception:
        return []
    return [c[1] for c in comments[:n]]

def load_cookies_txt(filepath: str) -> dict:
    cookies = {}
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, flag, path, secure, expiry, name, value = parts
                cookies[name] = value
    return cookies

async def main():
    cookies = load_cookies_txt("cookies.txt")
    ms_token = cookies.get("msToken")
    if not ms_token:
        print("Error: msToken not found in cookies.txt")
        return

    rows: List[Dict] = []
    attempts = 0

    async with TikTokApi() as api:
        await api.create_sessions(ms_tokens=[ms_token], num_sessions=1, sleep_after=3)
        
        for search_term in SEARCH_TERMS:
            try:
                # Create a progress bar
                pbar = tqdm(total=VIDEOS_PER_TAG, desc=f"Processing {search_term}")
                
                # Get the search results
                tag = api.hashtag(name=search_term)
                print(f"Starting search for {search_term}")
                
                # try:
                #     first_video = await anext(search_results)
                #     print(f"✅ Successfully got a video: {first_video.id}")
                # except StopAsyncIteration:
                #     print("❌ search_results is EMPTY!")
                # except Exception as e:
                #     print(f"❌ Error when fetching first video: {e}")
                #     traceback.print_exc()

                # Process each video
                async for video in tag.videos(count=VIDEOS_PER_TAG):
                    if attempts >= REQUEST_CAP:
                        print("Reached request cap")
                        break
                    
                    attempts += 1
                    
                    # Filter by timestamp
                    if not (TARGET_START <= video.create_time.timestamp() <= TARGET_END):
                        print(f"Skipping video {video.id} - wrong timestamp")
                        pbar.update(1)
                        continue

                    # Basic metadata
                    stats = video.stats
                    videoDict = video.as_dict
                    author = video.author
                    authorDict = author.as_dict
                    print("authorDict: ", authorDict)
                    row = {
                        "video_id"      : video.id,
                        "posted_ts"     : video.create_time.timestamp(),
                        "description"   : videoDict["desc"],
                        "hashtags"      : extract_hashtags(videoDict["desc"]),
                        "author_id"     : author.user_id,
                        "author_name"   : author.username,
                        "follower_count": authorDict["followerCount"],
                        "view_count"    : stats["playCount"],
                        "like_count"    : stats["diggCount"],
                        "share_count"   : stats["shareCount"],
                        "comment_count" : stats["commentCount"],
                    }
                    print("row: ", row)
                    # Thumbnail
                    thumb_path = THUMBS_DIR / f"{video.id}.jpg"
                    if not thumb_path.exists():   # avoid re-download
                        try:
                            resize_and_save(video.bytes_cover, thumb_path)
                        except Exception as e:
                            print(f"Thumbnail failed: {e}")
                            pbar.update(1)
                            continue
                    row["thumbnail_path"] = str(thumb_path.resolve())

                    # Top 5 comments
                    row["top_comments"] = await fetch_top_comments(video, n=5)
                    rows.append(row)

                    # polite spacing
                    await asyncio.sleep(random.uniform(2, 4))
                    if attempts % 20 == 0:
                        await asyncio.sleep(10)
                    
                    pbar.update(1)

                pbar.close()
                if attempts >= REQUEST_CAP:
                    print("Reached request cap, stopping search")
                    break
            except Exception as e:
                print(f"Error processing search term {search_term}: {e}")
                continue
                
    if rows:
        df = pd.DataFrame(rows)
        parquet_name = OUT_DIR / f"beauty_tiktok_{TARGET_DATE.isoformat()}.parquet"
        df.to_parquet(parquet_name, index=False)
        print(f"\n✅ Saved {len(df)} rows to {parquet_name}")
    else:
        print("❌ No matching videos found today. Try again tomorrow!")

if __name__ == "__main__":
    asyncio.run(main())
