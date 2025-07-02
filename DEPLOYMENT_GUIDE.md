# AWS Lambda Deployment Guide for TikTok Data Collector

## Overview
This guide walks you through deploying the TikTok data collector as an AWS Lambda function that saves data to S3.

## Prerequisites

### 1. AWS Account Setup
- AWS account with appropriate permissions
- AWS CLI installed and configured
- S3 bucket `socialmediaanalyzer` created with the following structure:
```
socialmediaanalyzer/
├── raw/
│   ├── data/
│   └── thumbnails/
```

### 2. Required AWS Services
- **S3**: For data and thumbnail storage
- **Lambda**: For running the data collection function
- **IAM**: For permissions
- **CloudWatch**: For monitoring and logs

## Step 1: Create S3 Bucket

```bash
# Create the S3 bucket (if not already created)
aws s3 mb s3://socialmediaanalyzer --region us-east-1

# Create the directory structure
aws s3api put-object --bucket socialmediaanalyzer --key raw/data/
aws s3api put-object --bucket socialmediaanalyzer --key raw/thumbnails/
```

## Step 2: Create IAM Role for Lambda

### 2.1 Create Trust Policy
Create a file named `lambda-trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### 2.2 Create Permissions Policy
Create a file named `lambda-s3-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:HeadObject"
      ],
      "Resource": "arn:aws:s3:::socialmediaanalyzer/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::socialmediaanalyzer"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

### 2.3 Create IAM Role

```bash
# Create the IAM role
aws iam create-role \
  --role-name lambda-tiktok-collector-role \
  --assume-role-policy-document file://lambda-trust-policy.json

# Create and attach the custom policy
aws iam create-policy \
  --policy-name lambda-tiktok-s3-policy \
  --policy-document file://lambda-s3-policy.json

# Attach the custom policy to the role
aws iam attach-role-policy \
  --role-name lambda-tiktok-collector-role \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/lambda-tiktok-s3-policy

# Attach basic Lambda execution policy
aws iam attach-role-policy \
  --role-name lambda-tiktok-collector-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

**Note**: Replace `YOUR_ACCOUNT_ID` with your actual AWS account ID.

## Step 3: Set Up Environment Variables

You need to extract MS tokens from your TikTok cookie files. The Lambda function expects these as environment variables:

### Extract MS Tokens
```bash
# Extract MS tokens from your cookie files
grep "msToken" cookies/*.txt | head -3
```

## Step 4: Deploy the Lambda Function

### 4.1 Using the Deployment Script (Recommended)

```bash
# Make script executable
chmod +x deploy_lambda.sh

# Run deployment script
./deploy_lambda.sh
```

### 4.2 Manual Deployment

```bash
# Package dependencies
pip install -r lambda_requirements.txt -t lambda_package

# Copy source code
cp src/tiktok_data_collect_s3.py lambda_package/

# Create deployment package
cd lambda_package
zip -r ../lambda_deployment.zip .
cd ..

# Create Lambda function
aws lambda create-function \
  --function-name tiktok-data-collector \
  --runtime python3.9 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-tiktok-collector-role \
  --handler tiktok_data_collect_s3.lambda_handler \
  --zip-file fileb://lambda_deployment.zip \
  --memory-size 3008 \
  --timeout 900 \
  --region us-east-1
```

## Step 5: Configure Environment Variables

```bash
# Set environment variables for the Lambda function
aws lambda update-function-configuration \
  --function-name tiktok-data-collector \
  --environment Variables='{
    "S3_BUCKET":"socialmediaanalyzer",
    "AWS_REGION":"us-east-1",
    "MS_TOKEN_1":"your_first_ms_token",
    "MS_TOKEN_2":"your_second_ms_token", 
    "MS_TOKEN_3":"your_third_ms_token",
    "VIDEOS_PER_TAG":"50",
    "REQUEST_CAP":"200",
    "BATCH_SIZE":"25",
    "MAX_EXECUTION_TIME":"840"
  }' \
  --region us-east-1
```

## Step 6: Test the Function

```bash
# Test the Lambda function
aws lambda invoke \
  --function-name tiktok-data-collector \
  --payload '{}' \
  --region us-east-1 \
  response.json

# Check the response
cat response.json
```

## Step 7: Set up Scheduling (Optional)

### Create EventBridge Rule for Automatic Execution

```bash
# Create a rule to run daily at 2 AM UTC
aws events put-rule \
  --name tiktok-data-collection-schedule \
  --schedule-expression "cron(0 2 * * ? *)" \
  --description "Daily TikTok data collection"

# Add Lambda as target
aws events put-targets \
  --rule tiktok-data-collection-schedule \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:YOUR_ACCOUNT_ID:function:tiktok-data-collector"

# Grant EventBridge permission to invoke Lambda
aws lambda add-permission \
  --function-name tiktok-data-collector \
  --statement-id allow-eventbridge \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-east-1:YOUR_ACCOUNT_ID:rule/tiktok-data-collection-schedule
```

## Important Considerations

### 1. Lambda Limitations
- **15-minute timeout**: The function is optimized to work within this limit
- **Memory limit**: Set to maximum (3008 MB) for better performance
- **Package size**: Large dependencies may require Lambda Layers

### 2. Cost Optimization
- Monitor CloudWatch costs for frequent executions
- Consider using reserved capacity for predictable workloads
- Use S3 Intelligent Tiering for cost-effective storage

### 3. Error Handling
- Check CloudWatch logs for debugging
- Set up CloudWatch alarms for failures
- Consider implementing dead letter queues

### 4. Security Best Practices
- Rotate MS tokens regularly
- Use least privilege IAM policies
- Enable S3 bucket versioning and encryption

## Monitoring and Troubleshooting

### View Logs
```bash
# Get recent log streams
aws logs describe-log-streams \
  --log-group-name /aws/lambda/tiktok-data-collector \
  --order-by LastEventTime \
  --descending

# View specific log stream
aws logs get-log-events \
  --log-group-name /aws/lambda/tiktok-data-collector \
  --log-stream-name 'LOG_STREAM_NAME'
```

### Check S3 Data
```bash
# List data files
aws s3 ls s3://socialmediaanalyzer/raw/data/

# List thumbnails
aws s3 ls s3://socialmediaanalyzer/raw/thumbnails/ | head -10

# Download and inspect data
aws s3 cp s3://socialmediaanalyzer/raw/data/tiktok_data.parquet ./local_data.parquet
```

### Performance Monitoring
- Monitor Lambda duration and memory usage in CloudWatch
- Set up alarms for timeouts or errors
- Track S3 storage costs and data growth

## Updating the Function

```bash
# Update function code
./deploy_lambda.sh

# Or manually update
aws lambda update-function-code \
  --function-name tiktok-data-collector \
  --zip-file fileb://lambda_deployment.zip
```

## Advanced Options

### Using Lambda Layers
For large dependencies like pandas and Pillow, consider creating Lambda Layers:

```bash
# Create layer for pandas and dependencies
mkdir -p python/lib/python3.9/site-packages
pip install pandas pyarrow -t python/lib/python3.9/site-packages
zip -r pandas-layer.zip python/

# Create the layer
aws lambda publish-layer-version \
  --layer-name pandas-layer \
  --zip-file fileb://pandas-layer.zip \
  --compatible-runtimes python3.9
```

### Parallel Processing
For higher throughput, consider:
- Multiple Lambda functions processing different search terms
- AWS Step Functions for orchestration
- SQS for queuing video processing tasks

## Support

For issues or questions:
1. Check CloudWatch logs first
2. Verify IAM permissions
3. Ensure S3 bucket access
4. Validate MS token freshness 