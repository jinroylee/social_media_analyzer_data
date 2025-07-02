#!/bin/bash

# AWS Resource Setup Script for TikTok Data Collector
# This script creates all necessary AWS resources for the Lambda function

set -e

# Configuration - Update these values
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
BUCKET_NAME="socialmediaanalyzer"
ROLE_NAME="lambda-tiktok-collector-role"
POLICY_NAME="lambda-tiktok-s3-policy"

echo "🚀 Setting up AWS resources for TikTok Data Collector..."
echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Bucket: $BUCKET_NAME"

# Step 1: Create S3 bucket
echo "📦 Creating S3 bucket..."
if aws s3 ls "s3://$BUCKET_NAME" 2>&1 | grep -q 'NoSuchBucket'; then
    aws s3 mb "s3://$BUCKET_NAME" --region $REGION
    echo "✅ Created S3 bucket: $BUCKET_NAME"
else
    echo "ℹ️  S3 bucket already exists: $BUCKET_NAME"
fi

# Create directory structure
echo "📁 Creating directory structure..."
aws s3api put-object --bucket $BUCKET_NAME --key raw/data/
aws s3api put-object --bucket $BUCKET_NAME --key raw/thumbnails/
echo "✅ Created directory structure"

# Step 2: Create IAM role
echo "🔐 Creating IAM role..."
if aws iam get-role --role-name $ROLE_NAME &>/dev/null; then
    echo "ℹ️  IAM role already exists: $ROLE_NAME"
else
    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document file://lambda-trust-policy.json
    echo "✅ Created IAM role: $ROLE_NAME"
fi

# Step 3: Create and attach custom policy
echo "📋 Creating custom IAM policy..."
POLICY_ARN="arn:aws:iam::$ACCOUNT_ID:policy/$POLICY_NAME"

if aws iam get-policy --policy-arn $POLICY_ARN &>/dev/null; then
    echo "ℹ️  Policy already exists: $POLICY_NAME"
else
    aws iam create-policy \
        --policy-name $POLICY_NAME \
        --policy-document file://lambda-s3-policy.json
    echo "✅ Created IAM policy: $POLICY_NAME"
fi

# Attach policies to role
echo "🔗 Attaching policies to role..."
aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn $POLICY_ARN || echo "Policy already attached"

aws iam attach-role-policy \
    --role-name $ROLE_NAME \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole || echo "Basic execution policy already attached"

echo "✅ Attached policies to role"

# Wait for role propagation
echo "⏳ Waiting for IAM role to propagate..."
sleep 10

# Display final information
echo ""
echo "🎉 AWS resources setup complete!"
echo ""
echo "📝 Summary:"
echo "- S3 Bucket: $BUCKET_NAME"
echo "- IAM Role: $ROLE_NAME"
echo "- IAM Policy: $POLICY_NAME"
echo "- Role ARN: arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
echo ""
echo "🔐 Next steps:"
echo "1. Extract MS tokens from your cookie files:"
echo "   grep 'msToken' cookies/*.txt"
echo ""
echo "2. Deploy the Lambda function:"
echo "   ./deploy_lambda.sh"
echo ""
echo "3. Set environment variables with your MS tokens"
echo ""
echo "📖 See DEPLOYMENT_GUIDE.md for detailed instructions" 