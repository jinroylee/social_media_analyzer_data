# TikTok Data Collector - AWS Lambda Version

This is an AWS Lambda-compatible version of your TikTok data collection script that stores data directly in S3 instead of local files.

## 🚀 Quick Start

1. **Setup AWS Resources** (run once):
   ```bash
   chmod +x setup_aws_resources.sh
   ./setup_aws_resources.sh
   ```

2. **Extract MS Tokens** from your cookie files:
   ```bash
   grep "msToken" cookies/*.txt | head -3
   ```

3. **Deploy the Lambda Function**:
   ```bash
   chmod +x deploy_lambda.sh
   ./deploy_lambda.sh
   ```

4. **Set Environment Variables** (replace with your actual tokens):
   ```bash
   aws lambda update-function-configuration \
     --function-name tiktok-data-collector \
     --environment Variables='{
       "S3_BUCKET":"socialmediaanalyzer",
       "MS_TOKEN_1":"your_first_ms_token",
       "MS_TOKEN_2":"your_second_ms_token",
       "MS_TOKEN_3":"your_third_ms_token"
     }'
   ```

5. **Test the Function**:
   ```bash
   aws lambda invoke \
     --function-name tiktok-data-collector \
     --payload '{}' \
     response.json && cat response.json
   ```

## 📁 Files Overview

| File | Purpose |
|------|---------|
| `src/tiktok_data_collect_s3.py` | Main Lambda function code |
| `lambda_requirements.txt` | Python dependencies for Lambda |
| `deploy_lambda.sh` | Automated deployment script |
| `setup_aws_resources.sh` | AWS resource creation script |
| `lambda-trust-policy.json` | IAM trust policy for Lambda |
| `lambda-s3-policy.json` | IAM permissions for S3 access |
| `DEPLOYMENT_GUIDE.md` | Comprehensive deployment guide |

## 🔄 Key Changes from Local Version

### S3 Storage
- **Data**: Saved to `s3://socialmediaanalyzer/raw/data/tiktok_data.parquet`
- **Thumbnails**: Uploaded to `s3://socialmediaanalyzer/raw/thumbnails/{video_id}.jpg`

### Lambda Optimizations
- **Timeout handling**: Function stops before 15-minute Lambda limit
- **Memory optimization**: Uses maximum 3008 MB for better performance
- **Batch processing**: Smaller batches (25 videos) for faster saves
- **Environment variables**: MS tokens loaded from Lambda environment

### Configuration via Environment Variables
```bash
S3_BUCKET=socialmediaanalyzer          # Your S3 bucket name
AWS_REGION=us-east-1                   # AWS region
MS_TOKEN_1=your_token_1                # TikTok authentication tokens
MS_TOKEN_2=your_token_2
MS_TOKEN_3=your_token_3
VIDEOS_PER_TAG=50                      # Videos per search term (reduced for Lambda)
REQUEST_CAP=200                        # Maximum API requests per run
BATCH_SIZE=25                          # Videos per batch save
MAX_EXECUTION_TIME=840                 # Max seconds (14 min, 1 min buffer)
```

## 📊 Expected Output

### S3 Structure After Running
```
socialmediaanalyzer/
├── raw/
│   ├── data/
│   │   └── tiktok_data.parquet        # Main dataset
│   └── thumbnails/
│       ├── 7123456789012345678.jpg    # Video thumbnails
│       ├── 7234567890123456789.jpg
│       └── ...
```

### Dataset Schema
The parquet file contains these columns:
- `video_id`: Unique TikTok video identifier
- `posted_ts`: Unix timestamp when video was posted
- `description`: Video description text
- `author_id`: Creator's user ID
- `author_name`: Creator's username
- `follower_count`: Creator's current follower count
- `view_count`: Video view count
- `like_count`: Video like count
- `share_count`: Video share count
- `comment_count`: Video comment count
- `repost_count`: Video repost count
- `thumbnail_s3_key`: S3 path to thumbnail image
- `top_comments`: List of top 5 comments (by likes)

## ⚡ Performance & Costs

### Lambda Performance
- **Duration**: ~10-14 minutes per run (optimized for 15-min limit)
- **Memory**: 3008 MB (maximum for best performance)
- **Videos per run**: ~50-200 videos (depending on search terms)

### Estimated AWS Costs (Monthly)
- **Lambda**: ~$15-30/month (daily runs)
- **S3 Storage**: ~$1-5/month (depends on data volume)
- **CloudWatch**: ~$2-5/month (logs and monitoring)

## 🔧 Advanced Usage

### Scheduling (Daily Collection)
```bash
# Run daily at 2 AM UTC
aws events put-rule \
  --name tiktok-daily-collection \
  --schedule-expression "cron(0 2 * * ? *)"
```

### Monitoring
```bash
# View logs
aws logs describe-log-streams \
  --log-group-name /aws/lambda/tiktok-data-collector

# Check S3 data
aws s3 ls s3://socialmediaanalyzer/raw/data/
aws s3 ls s3://socialmediaanalyzer/raw/thumbnails/ | wc -l
```

### Data Analysis
```python
import pandas as pd
import boto3

# Download and analyze data
s3 = boto3.client('s3')
s3.download_file('socialmediaanalyzer', 'raw/data/tiktok_data.parquet', 'local_data.parquet')

df = pd.read_parquet('local_data.parquet')
print(f"Total videos: {len(df)}")
print(f"Date range: {df['posted_ts'].min()} to {df['posted_ts'].max()}")
```

## 🆘 Troubleshooting

### Common Issues
1. **"No MS tokens found"**: Check environment variables are set correctly
2. **Package too large**: Use Lambda Layers for heavy dependencies
3. **Timeout errors**: Reduce `VIDEOS_PER_TAG` or `REQUEST_CAP`
4. **S3 permission errors**: Verify IAM role has proper S3 permissions

### Debug Commands
```bash
# Check function configuration
aws lambda get-function-configuration --function-name tiktok-data-collector

# View recent logs
aws logs tail /aws/lambda/tiktok-data-collector --follow

# Test with smaller batch
aws lambda update-function-configuration \
  --function-name tiktok-data-collector \
  --environment Variables='{"VIDEOS_PER_TAG":"10","REQUEST_CAP":"50"}'
```

## 📖 Need Help?

1. 📖 **Full Guide**: See `DEPLOYMENT_GUIDE.md` for detailed instructions
2. 🔍 **Logs**: Check CloudWatch logs for detailed error messages
3. 💰 **Costs**: Monitor AWS billing dashboard for unexpected charges
4. 🛡️ **Security**: Rotate MS tokens regularly for best security

## 🎯 Next Steps

After successful deployment, consider:
- Setting up CloudWatch alarms for failures
- Implementing data validation and quality checks
- Creating a separate Lambda for data processing/analysis
- Setting up automated data backup to Glacier for long-term storage 