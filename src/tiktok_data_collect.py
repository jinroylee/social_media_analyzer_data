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
import requests
import matplotlib.pyplot as plt

# ---------- tweakables ----------
SEARCH_TERMS  = ["skincare", "makeup", "cosmetics"] #, 
VIDEOS_PER_TAG     = 1       # stop earlier if you like
REQUEST_CAP        = 5000          # hard maximum attempts per run
OUT_DIR            = Path("tiktok_data")
THUMBS_DIR         = OUT_DIR / "thumbnails"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
# --------------------------------
# 
# Calculate the timestamp for 1 year ago from now
ONE_YEAR_AGO = (dt.datetime.utcnow() - dt.timedelta(days=365)).timestamp()

# Legacy date calculation (not used with new filter logic)
TARGET_DATE = (dt.datetime.utcnow() - dt.timedelta(days=30)).date() 
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
        video_comments = video.comments(count=50)
        try:
            first_comment = await anext(video_comments)
            try:
                comments.append((first_comment.as_dict["digg_count"] or 0, first_comment.text))
                print(f"Added first comment with text: {first_comment.text[:30]}...")
            except Exception as e:
                print(f"Error processing first comment: {e}")
                # if hasattr(first_comment, 'as_dict'):
                #     print(f"First comment structure: {first_comment.as_dict}")
                # else:
                #     print(f"First comment doesn't have as_dict. Type: {type(first_comment)}")
            async for c in video_comments:
                try:
                    comments.append((c.as_dict["digg_count"] or 0, c.text))
                    # print(f"Added comment: {c.text[:30]}...")
                except Exception as e:
                    print(f"Error processing comment: {e}")
                    if hasattr(c, 'as_dict'):
                        print(f"Comment structure: {c.as_dict}")
        
        except StopAsyncIteration:
            print("❌ No comments available for this video")
        except Exception as e:
            print(f"❌ Error when fetching first comment: {e}")
            traceback.print_exc()
            
        print(f"Total comments collected: {len(comments)}")
        
        # Sort by like count if we have any comments
        if comments:
            comments.sort(reverse=True)
            return [c[1] for c in comments[:n]]
        
    except Exception as e:
        print(f"Error in fetch_top_comments: {e}")
        traceback.print_exc()
        
    return []

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

def print_dataset_stats(df: pd.DataFrame) -> None:
    """Print basic statistics about the dataset."""
    print("\n----- Dataset Statistics -----")
    print(f"Total videos: {len(df)}")

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
                videos_processed = 0  # Counter for actually processed videos
                async for video in tag.videos(count=VIDEOS_PER_TAG * 10):  # Request more to find suitable videos
                    if attempts >= REQUEST_CAP:
                        print("Reached request cap")
                        break
                    
                    attempts += 1
                    
                    # Filter by timestamp - include videos from the last year
                    video_timestamp = video.create_time.timestamp()
                    if video_timestamp < ONE_YEAR_AGO:
                        print(f"Skipping video {video.id} - too old: {video.create_time}")
                        pbar.update(1)
                        continue

                    # Basic metadata
                    videoDict = video.as_dict
                    print(f"Processing video {video.id} posted at {video.create_time}")

                    stats = video.stats
                    author = video.author
                    authorStats = videoDict["authorStats"]
                    # authorDict = author.as_dict
                    # authorInfo = await author.info()

                    # print("authorDict: ", json.dumps(authorDict, indent=4))
                    # print("authorInfo: ", json.dumps(authorInfo, indent=4))

                    row = {
                        "video_id"      : video.id,
                        "posted_ts"     : video.create_time.timestamp(),
                        "description"   : videoDict["desc"],
                        #"hashtags"      : extract_hashtags(videoDict["desc"]),
                        "author_id"     : author.user_id,
                        "author_name"   : author.username,
                        "follower_count": authorStats["followerCount"],
                        "view_count"    : stats["playCount"],
                        "like_count"    : stats["diggCount"],
                        "share_count"   : stats["shareCount"],
                        "comment_count" : stats["commentCount"],
                    }
                    
                    # Thumbnail
                    thumb_path = THUMBS_DIR / f"{video.id}.jpg"
                    if not thumb_path.exists():   # avoid re-download
                        try:
                            # Get the URL from videoDict
                            cover_url = videoDict["video"]["cover"]
                            # Download the image
                            response = requests.get(cover_url)
                            if response.status_code == 200:
                                resize_and_save(response.content, thumb_path)
                            else:
                                print(f"Failed to download thumbnail: HTTP {response.status_code}")
                        except Exception as e:
                            print(f"Thumbnail failed: {e}")
                            pbar.update(1)
                            continue
                    row["thumbnail_path"] = str(thumb_path.resolve())

                    # Top 5 comments
                    print(f"Fetching top comments for video {video.id} (has {stats.get('commentCount', 0)} comments)")
                    
                    # Skip comment fetching if video has no comments to avoid wasting API calls
                    if int(stats.get('commentCount', 0)) > 0:
                        row["top_comments"] = await fetch_top_comments(video, n=5)
                    else:
                        print(f"Video {video.id} has no comments according to stats, skipping comment fetch")
                        row["top_comments"] = []
                        
                    rows.append(row)

                    # Update counter for successfully processed videos
                    videos_processed += 1
                    
                    # Break if we've processed the requested number of videos
                    if videos_processed >= VIDEOS_PER_TAG:
                        print(f"Reached target of {VIDEOS_PER_TAG} videos for {search_term}")
                        break
                        
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
        # Define a fixed parquet filename - no longer using date in filename
        parquet_name = OUT_DIR / "tiktok_beauty_dataset.parquet"
        
        # Check if the file already exists and load it
        if parquet_name.exists():
            print(f"Loading existing dataset from {parquet_name}")
            existing_df = pd.read_parquet(parquet_name)
            print(f"Existing dataset has {len(existing_df)} rows")
            
            # Convert new rows to DataFrame
            new_df = pd.DataFrame(rows)
            print(f"New data has {len(new_df)} rows")
            
            # Check for duplicates by video_id
            existing_video_ids = set(existing_df['video_id'].values)
            new_df = new_df[~new_df['video_id'].isin(existing_video_ids)]
            print(f"After removing duplicates, adding {len(new_df)} new rows")
            
            # Concatenate and save if there are new rows to add
            if len(new_df) > 0:
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df.to_parquet(parquet_name, index=False)
                print(f"\n✅ Saved {len(combined_df)} total rows to {parquet_name} (added {len(new_df)} new rows)")
                print_dataset_stats(combined_df)
            else:
                print("\n⚠️ No new unique videos to add to the dataset")
                print_dataset_stats(existing_df)
        else:
            # First time creating the file
            df = pd.DataFrame(rows)
            df.to_parquet(parquet_name, index=False)
            print(f"\n✅ Created new dataset with {len(df)} rows at {parquet_name}")
            print_dataset_stats(df)
    else:
        print("❌ No matching videos found. Try again later!")

if __name__ == "__main__":
    asyncio.run(main())
