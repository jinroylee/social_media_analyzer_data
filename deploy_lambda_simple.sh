#!/bin/bash

# Simple AWS Lambda Deployment Script for TikTok Data Collector
# This script creates a single deployment package without Lambda layers

set -e

# Configuration
FUNCTION_NAME="tiktok-data-collector"
RUNTIME="python3.9"
HANDLER="tiktok_data_collect_s3.lambda_handler"
MEMORY_SIZE=3008  # Maximum memory for Lambda
TIMEOUT=900       # 15 minutes (maximum for Lambda)
REGION="ap-northeast-2"

# Directories
PACKAGE_DIR="lambda_package_simple"
SRC_DIR="src"

echo "🚀 Starting simple Lambda deployment process..."

# Clean up previous builds
echo "🧹 Cleaning up previous builds..."
rm -rf $PACKAGE_DIR
rm -f lambda_deployment_simple.zip

# Create package directory
echo "📦 Creating package directory..."
mkdir -p $PACKAGE_DIR

# Create optimized requirements (exclude heavy packages that might not be needed)
echo "📚 Installing optimized Python dependencies..."
cat > simple_requirements.txt << 'EOF'
boto3==1.34.34
botocore==1.34.34
requests==2.31.0
TikTokApi==6.1.0
aiofiles==23.2.1
pyarrow==14.0.2
pandas==2.1.4
Pillow==10.2.0
EOF

# Install dependencies with optimizations
pip install -r simple_requirements.txt -t $PACKAGE_DIR --no-deps --no-cache-dir

# Remove unnecessary files to reduce size
echo "🗑️  Removing unnecessary files to reduce package size..."
find $PACKAGE_DIR -name "*.pyc" -delete
find $PACKAGE_DIR -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -name "*.so" -delete 2>/dev/null || true
find $PACKAGE_DIR -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -name "test" -type d -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
find $PACKAGE_DIR -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true

# Remove specific large files/directories that aren't needed
rm -rf $PACKAGE_DIR/pandas/tests 2>/dev/null || true
rm -rf $PACKAGE_DIR/PIL/tests 2>/dev/null || true
rm -rf $PACKAGE_DIR/numpy/tests 2>/dev/null || true

# Copy optimized source code
echo "📋 Copying optimized source code..."
cp $SRC_DIR/tiktok_data_collect_s3_optimized.py $PACKAGE_DIR/tiktok_data_collect_s3.py

# Create deployment package
echo "🗜️  Creating deployment package..."
cd $PACKAGE_DIR
zip -r ../lambda_deployment_simple.zip . -x "*.pyc" "__pycache__/*" "*.git/*" "tests/*" "test/*"
cd ..

# Check package size
PACKAGE_SIZE=$(du -sh lambda_deployment_simple.zip | cut -f1)
PACKAGE_SIZE_BYTES=$(stat -f%z lambda_deployment_simple.zip 2>/dev/null || stat -c%s lambda_deployment_simple.zip)
echo "📏 Package size: $PACKAGE_SIZE"

# Check if package is still too large
if [ $PACKAGE_SIZE_BYTES -gt 52428800 ]; then  # 50MB limit
    echo "⚠️  Warning: Package size is ${PACKAGE_SIZE}, which may still be too large for direct upload."
    echo "💡 Consider using S3 upload method or further optimization."
    
    # Create S3 upload commands
    echo ""
    echo "Alternative deployment using S3:"
    echo "1. Upload to S3:"
    echo "   aws s3 cp lambda_deployment_simple.zip s3://socialmediaanalyzer/lambda-deployments/"
    echo ""
    echo "2. Create function from S3:"
    echo "   aws lambda create-function \\"
    echo "     --function-name $FUNCTION_NAME \\"
    echo "     --runtime $RUNTIME \\"
    echo "     --role arn:aws:iam::777022888924:role/lambda-socialmediaanalyzer-collector-role \\"
    echo "     --handler $HANDLER \\"
    echo "     --code S3Bucket=socialmediaanalyzer,S3Key=lambda-deployments/lambda_deployment_simple.zip \\"
    echo "     --memory-size $MEMORY_SIZE \\"
    echo "     --timeout $TIMEOUT \\"
    echo "     --region $REGION"
else
    echo "✅ Package size is within Lambda limits!"
fi

echo "✅ Simple deployment package created: lambda_deployment_simple.zip"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo "❌ AWS CLI not configured. Please run 'aws configure' first."
    exit 1
fi

echo "🎯 Ready to deploy to AWS Lambda!"

# Offer to deploy automatically
read -p "Do you want to deploy/update the function now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Deploying to AWS Lambda..."
    
    if [ $PACKAGE_SIZE_BYTES -gt 52428800 ]; then
        echo "📤 Package too large for direct upload, using S3..."
        
        # Upload to S3 first
        aws s3 cp lambda_deployment_simple.zip s3://socialmediaanalyzer/lambda-deployments/
        
        # Check if function exists
        if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION &>/dev/null; then
            echo "🔄 Updating existing function from S3..."
            aws lambda update-function-code \
                --function-name $FUNCTION_NAME \
                --s3-bucket socialmediaanalyzer \
                --s3-key lambda-deployments/lambda_deployment_simple.zip \
                --region $REGION
        else
            echo "🆕 Creating new function from S3..."
            aws lambda create-function \
                --function-name $FUNCTION_NAME \
                --runtime $RUNTIME \
                --role arn:aws:iam::777022888924:role/lambda-socialmediaanalyzer-collector-role \
                --handler $HANDLER \
                --code S3Bucket=socialmediaanalyzer,S3Key=lambda-deployments/lambda_deployment_simple.zip \
                --memory-size $MEMORY_SIZE \
                --timeout $TIMEOUT \
                --region $REGION
        fi
    else
        # Direct upload
        if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION &>/dev/null; then
            echo "🔄 Updating existing function..."
            aws lambda update-function-code \
                --function-name $FUNCTION_NAME \
                --zip-file fileb://lambda_deployment_simple.zip \
                --region $REGION
        else
            echo "🆕 Creating new function..."
            aws lambda create-function \
                --function-name $FUNCTION_NAME \
                --runtime $RUNTIME \
                --role arn:aws:iam::777022888924:role/lambda-socialmediaanalyzer-collector-role \
                --handler $HANDLER \
                --zip-file fileb://lambda_deployment_simple.zip \
                --memory-size $MEMORY_SIZE \
                --timeout $TIMEOUT \
                --region $REGION
        fi
    fi
    
    echo "✅ Function deployed successfully!"
fi

# Cleanup
echo "🧹 Cleaning up temporary files..."
rm -f simple_requirements.txt

echo "✨ Simple deployment script completed!" 