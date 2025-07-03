#!/usr/bin/env python
"""
AWS Lambda-compatible TikTok data collector that stores data in S3.
Collects trending TikTok videos in the beauty/cosmetics niche and saves:
    • description + hashtags
    • creator follower-count (current)
    • view, like, share, comment counts
    • top-5 comments
    • thumbnail images uploaded to S3
Result is written to S3 as a Parquet file ready for ML ingestion.
"""

import os
import re
import json
import time
import random
import datetime as dt
import asyncio
from io import BytesIO
import traceback
from typing import List, Dict, Optional
import pandas as pd
from PIL import Image
import boto3
from botocore.exceptions import ClientError
from tqdm import tqdm
from TikTokApi import TikTokApi
import requests

# ---------- AWS Configuration ----------
S3_BUCKET = os.environ.get('S3_BUCKET', 'socialmediaanalyzer')
S3_DATA_KEY = 'raw/data/tiktok_data.parquet'
S3_THUMBNAILS_PREFIX = 'raw/thumbnails/'
AWS_REGION = os.environ.get('AWS_REGION', 'ap-northeast-2')

# ---------- Configuration ----------
SEARCH_TERMS = [
    "tonerrecommendation",
    "serumreview", 
    "koreancosmetics",
    "japaneseskincare",
    "skincaretips",
    "kbeautyroutine",
    "ulzzangmakeup",
    "kmakeup",
    "jskincare",
    "sheetmask",
    "beautyreview",
    "asianbeauty",
    "koreabeautyproducts",
    "tokyomakeup",
    "cosmeランキング",
    "韓国メイク",
    "メイク好きさんと繋がりたい",
    "垢抜けメイク",
    "スキンケアマニア",
    "メイクレビュー",
    "時短メイク",
    "プチプラコスメ",
    "デパコス",
    "ナチュラルメイク",
    "韓国アイドルメイク",
    "メイク動画",
]

# Lambda-optimized settings
VIDEOS_PER_TAG = int(os.environ.get('VIDEOS_PER_TAG', '50'))  # Reduced for Lambda
REQUEST_CAP = int(os.environ.get('REQUEST_CAP', '200'))       # Reduced for Lambda
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '25'))          # Smaller batches
MAX_EXECUTION_TIME = int(os.environ.get('MAX_EXECUTION_TIME', '840'))  # 14 minutes (Lambda timeout buffer)

# Initialize S3 client
s3_client = boto3.client('s3', region_name=AWS_REGION)

def resize_and_save_to_s3(img_bytes: bytes, s3_key: str) -> bool:
    """Resize image and upload directly to S3."""
    try:
        # Resize image
        im = Image.open(BytesIO(img_bytes)).convert("RGB")
        im = im.resize((256, 256), Image.LANCZOS)
        
        # Save to BytesIO buffer
        buffer = BytesIO()
        im.save(buffer, format="JPEG", quality=90, optimize=True)
        buffer.seek(0)
        
        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=buffer.getvalue(),
            ContentType='image/jpeg'
        )
        return True
    except Exception as e:
        print(f"Error uploading image to S3: {e}")
        return False

def check_s3_object_exists(s3_key: str) -> bool:
    """Check if an object exists in S3."""
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            print(f"Error checking S3 object: {e}")
            return False

def load_existing_parquet_from_s3() -> Optional[pd.DataFrame]:
    """Load existing parquet file from S3."""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=S3_DATA_KEY)
        return pd.read_parquet(BytesIO(response['Body'].read()))
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            print("No existing parquet file found in S3")
            return None
        else:
            print(f"Error loading parquet from S3: {e}")
            return None

def save_parquet_to_s3(df: pd.DataFrame) -> bool:
    """Save dataframe to S3 as parquet."""
    try:
        buffer = BytesIO()
        df.to_parquet(buffer, index=False)
        buffer.seek(0)
        
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=S3_DATA_KEY,
            Body=buffer.getvalue(),
            ContentType='application/octet-stream'
        )
        return True
    except Exception as e:
        print(f"Error uploading parquet to S3: {e}")
        return False

def extract_hashtags(txt: str) -> List[str]:
    """Extract hashtags from text."""
    return re.findall(r"#([A-Za-z0-9_]+)", txt)

async def fetch_top_comments(video, n: int = 5) -> List[str]:
    """Fetch top comments for a video."""
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
            
            async for c in video_comments:
                try:
                    comments.append((c.as_dict["digg_count"] or 0, c.text))
                except Exception as e:
                    print(f"Error processing comment: {e}")
        
        except StopAsyncIteration:
            print("❌ No comments available for this video")
        except Exception as e:
            print(f"❌ Error when fetching first comment: {e}")
            
        print(f"Total comments collected: {len(comments)}")
        
        if comments:
            comments.sort(reverse=True)
            return [c[1] for c in comments[:n]]
        
    except Exception as e:
        print(f"Error in fetch_top_comments: {e}")
        
    return []

def load_cookies_from_env() -> List[str]:
    """Load MS tokens from environment variables."""
    ms_tokens = []
    
    # Try to load from environment variables (MS_TOKEN_1, MS_TOKEN_2, etc.)
    i = 1
    while True:
        token = os.environ.get(f'MS_TOKEN_{i}')
        if token:
            ms_tokens.append(token)
            i += 1
        else:
            break
    
    # Fallback to single MS_TOKEN
    if not ms_tokens:
        token = os.environ.get('MS_TOKEN')
        if token:
            ms_tokens.append(token)
    
    return ms_tokens

def print_dataset_stats(df: pd.DataFrame) -> None:
    """Print basic statistics about the dataset."""
    print("\n----- Dataset Statistics -----")
    print(f"Total videos: {len(df)}")

def save_batch_to_s3(rows: List[Dict], batch_number: int) -> int:
    """Save a batch of rows to S3, merging with existing data."""
    try:
        # Load existing data from S3
        existing_df = load_existing_parquet_from_s3()
        
        if existing_df is not None:
            print(f"Loaded existing dataset with {len(existing_df)} rows")
            
            # Convert new rows to DataFrame
            new_df = pd.DataFrame(rows)
            print(f"Batch {batch_number}: Adding {len(new_df)} new rows")
            
            # Check for duplicates by video_id
            existing_video_ids = set(existing_df['video_id'].values)
            new_df = new_df[~new_df['video_id'].isin(existing_video_ids)]
            print(f"After removing duplicates, adding {len(new_df)} rows")
            
            # Concatenate and save if there are new rows to add
            if len(new_df) > 0:
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                if save_parquet_to_s3(combined_df):
                    print(f"✅ Updated S3 dataset with {len(combined_df)} total rows (added {len(new_df)} new rows)")
                    print_dataset_stats(combined_df)
                    return len(combined_df)
                else:
                    print("❌ Failed to save updated dataset to S3")
                    return len(existing_df)
            else:
                print("⚠️ No new unique rows to add to the dataset")
                return len(existing_df)
                
        else:
            # First time creating the file
            new_df = pd.DataFrame(rows)
            if save_parquet_to_s3(new_df):
                print(f"✅ Created new S3 dataset with {len(new_df)} rows")
                return len(new_df)
            else:
                print("❌ Failed to create new dataset in S3")
                return 0
                
    except Exception as e:
        print(f"Error saving batch to S3: {e}")
        traceback.print_exc()
        return 0

async def collect_tiktok_data(start_time: float) -> Dict:
    """Main data collection function with time tracking for Lambda."""
    ms_tokens = load_cookies_from_env()
    
    if not ms_tokens:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'No MS tokens found in environment variables'})
        }

    rows: List[Dict] = []
    attempts = 0
    total_processed = 0
    batch_count = 0
    
    try:
        async with TikTokApi() as api:
            await api.create_sessions(ms_tokens=ms_tokens, headless=True, num_sessions=min(len(ms_tokens), 3))
            
            for search_term in SEARCH_TERMS:
                # Check remaining time
                elapsed_time = time.time() - start_time
                if elapsed_time > MAX_EXECUTION_TIME:
                    print(f"Approaching Lambda timeout, stopping early. Processed {total_processed} videos.")
                    break
                
                try:
                    print(f"Starting search for {search_term}")
                    tag = api.hashtag(name=search_term)
                    
                    videos_processed = 0
                    async for video in tag.videos(count=VIDEOS_PER_TAG * 2):
                        # Time check
                        elapsed_time = time.time() - start_time
                        if elapsed_time > MAX_EXECUTION_TIME:
                            print("Time limit reached, stopping collection")
                            break
                            
                        if attempts >= REQUEST_CAP:
                            print("Reached request cap")
                            break
                        
                        attempts += 1
                        
                        # Basic metadata
                        videoDict = video.as_dict
                        print(f"Processing video {video.id} posted at {video.create_time}")

                        stats = video.stats
                        author = video.author
                        authorStats = videoDict["authorStats"]
                        
                        # Thumbnail S3 key
                        thumbnail_s3_key = f"{S3_THUMBNAILS_PREFIX}{video.id}.jpg"
                        
                        row = {
                            "video_id": video.id,
                            "posted_ts": video.create_time.timestamp(),
                            "description": videoDict["desc"],
                            "author_id": author.user_id,
                            "author_name": author.username,
                            "follower_count": authorStats["followerCount"],
                            "view_count": stats["playCount"],
                            "like_count": stats["diggCount"],
                            "share_count": stats["shareCount"],
                            "comment_count": stats["commentCount"],
                            "repost_count": stats["repostCount"],
                            "thumbnail_s3_key": thumbnail_s3_key
                        }
                        
                        # Handle thumbnail
                        if not check_s3_object_exists(thumbnail_s3_key):
                            try:
                                cover_url = videoDict["video"]["cover"]
                                if not cover_url:
                                    print(f"No cover URL found for video {video.id}")
                                    continue
                                    
                                response = requests.get(cover_url, timeout=10)
                                if response.status_code == 200:
                                    if not resize_and_save_to_s3(response.content, thumbnail_s3_key):
                                        print(f"Failed to upload thumbnail for video {video.id}")
                                        continue
                                else:
                                    print(f"Failed to download thumbnail: HTTP {response.status_code}")
                                    continue
                            except Exception as e:
                                print(f"Thumbnail processing failed: {e}")
                                continue
                        else:
                            print(f"Thumbnail already exists in S3 for video {video.id}")
                        
                        # Top comments (skip if no comments to save time)
                        if int(stats.get('commentCount', 0)) > 0:
                            try:
                                row["top_comments"] = await fetch_top_comments(video, n=5)
                            except Exception as e:
                                print(f"Error fetching top comments for video {video.id}: {e}")
                                row["top_comments"] = []
                        else:
                            row["top_comments"] = []
                            
                        rows.append(row)
                        videos_processed += 1
                        total_processed += 1
                        
                        # Save batch if needed
                        if len(rows) >= BATCH_SIZE:
                            batch_count += 1
                            print(f"\n💾 Saving batch #{batch_count} with {len(rows)} rows to S3...")
                            save_batch_to_s3(rows, batch_count)
                            rows = []
                        
                        if videos_processed >= VIDEOS_PER_TAG:
                            break
                            
                        # Rate limiting
                        await asyncio.sleep(random.uniform(1, 3))
                        
                    if attempts >= REQUEST_CAP or elapsed_time > MAX_EXECUTION_TIME:
                        break
                        
                except Exception as e:
                    print(f"Error processing search term {search_term}: {e}")
                    continue
        
        # Save any remaining rows
        if rows:
            batch_count += 1
            print(f"\n💾 Saving final batch #{batch_count} with {len(rows)} remaining rows to S3...")
            save_batch_to_s3(rows, batch_count)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Data collection complete! Processed {total_processed} videos in {batch_count} batches.',
                'videos_processed': total_processed,
                'batches_saved': batch_count
            })
        }
        
    except Exception as e:
        print(f"Error in main collection: {e}")
        traceback.print_exc()
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def lambda_handler(event, context):
    """AWS Lambda entry point."""
    start_time = time.time()
    
    print("Starting TikTok data collection...")
    print(f"S3 Bucket: {S3_BUCKET}")
    print(f"Videos per tag: {VIDEOS_PER_TAG}")
    print(f"Request cap: {REQUEST_CAP}")
    print(f"Max execution time: {MAX_EXECUTION_TIME} seconds")
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(collect_tiktok_data(start_time))
        return result
    finally:
        loop.close()

# For local testing
if __name__ == "__main__":
    import sys
    
    # Mock Lambda event and context for local testing
    class MockContext:
        def __init__(self):
            self.function_name = "tiktok-data-collector"
            self.function_version = "$LATEST"
            self.memory_limit_in_mb = "1024"
            self.remaining_time_in_millis = lambda: 900000  # 15 minutes
    
    result = lambda_handler({}, MockContext())
    print(json.dumps(result, indent=2)) 