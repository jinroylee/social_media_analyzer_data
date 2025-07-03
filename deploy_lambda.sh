#!/bin/bash

# AWS Lambda Deployment Script for TikTok Data Collector
# This script packages the code and dependencies for Lambda deployment

set -e

# Configuration
FUNCTION_NAME="tiktok-data-collector"
RUNTIME="python3.9"
HANDLER="src/tiktok_data_collect_s3.lambda_handler"
MEMORY_SIZE=3008  # Maximum memory for Lambda
TIMEOUT=900       # 15 minutes (maximum for Lambda)
REGION="ap-northeast-2"

# Directories
PACKAGE_DIR="lambda_package"
SRC_DIR="src"

echo "🚀 Starting Lambda deployment process..."

# Clean up previous builds
echo "🧹 Cleaning up previous builds..."
rm -rf $PACKAGE_DIR
rm -f lambda_deployment.zip

# Create package directory
echo "📦 Creating package directory..."
mkdir -p $PACKAGE_DIR

# Install dependencies
echo "📚 Installing Python dependencies..."
pip install -r lambda_requirements.txt -t $PACKAGE_DIR --no-deps

# Note: Some packages like pandas and Pillow are large
# Consider using Lambda Layers for common dependencies

# Copy source code
echo "📋 Copying source code..."
cp $SRC_DIR/tiktok_data_collect_s3.py $PACKAGE_DIR/

# Create deployment package
echo "🗜️  Creating deployment package..."
cd $PACKAGE_DIR
zip -r ../lambda_deployment.zip . -x "*.pyc" "__pycache__/*" "*.git/*"
cd ..

# Check package size
PACKAGE_SIZE=$(du -sh lambda_deployment.zip | cut -f1)
echo "📏 Package size: $PACKAGE_SIZE"

if [ $(stat -f%z lambda_deployment.zip 2>/dev/null || stat -c%s lambda_deployment.zip) -gt 262144000 ]; then
    echo "⚠️  Warning: Package size exceeds 250MB. Consider using Lambda Layers."
    echo "💡 Tip: Move large dependencies like pandas, Pillow to a Lambda Layer"
fi

echo "✅ Deployment package created: lambda_deployment.zip"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo "❌ AWS CLI not configured. Please run 'aws configure' first."
    exit 1
fi

echo "🎯 Ready to deploy to AWS Lambda!"
echo ""
echo "To deploy manually using AWS CLI:"
echo "aws lambda create-function \\"
echo "  --function-name $FUNCTION_NAME \\"
echo "  --runtime $RUNTIME \\"
echo "  --role arn:aws:iam::777022888924:role/lambda-socialmediaanalyzer-collector-role \\"
echo "  --handler $HANDLER \\"
echo "  --zip-file fileb://lambda_deployment.zip \\"
echo "  --memory-size $MEMORY_SIZE \\"
echo "  --timeout $TIMEOUT \\"
echo "  --region $REGION"
echo ""
echo "Or update existing function:"
echo "aws lambda update-function-code \\"
echo "  --function-name $FUNCTION_NAME \\"
echo "  --zip-file fileb://lambda_deployment.zip \\"
echo "  --region $REGION"

# Offer to deploy automatically
read -p "Do you want to deploy/update the function now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Deploying to AWS Lambda..."
    
    # Check if function exists
    if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION &>/dev/null; then
        echo "🔄 Updating existing function..."
        aws lambda update-function-code \
            --function-name $FUNCTION_NAME \
            --zip-file fileb://lambda_deployment.zip \
            --region $REGION
    else
        echo "🆕 Creating new function..."
        echo "❌ Please create the IAM role first and update the command above with the correct role ARN."
        echo "💡 See DEPLOYMENT_GUIDE.md for detailed instructions."
    fi
fi

echo "✨ Deployment script completed!" 