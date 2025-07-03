#!/bin/bash

# Optimized AWS Lambda Deployment Script for TikTok Data Collector
# This script creates Lambda Layers for large dependencies and a minimal deployment package

set -e

# Configuration
FUNCTION_NAME="tiktok-data-collector"
LAYER_NAME="tiktok-data-deps"
RUNTIME="python3.9"
HANDLER="src/tiktok_data_collect_s3.lambda_handler"
MEMORY_SIZE=3008  # Maximum memory for Lambda
TIMEOUT=900       # 15 minutes (maximum for Lambda)
REGION="ap-northeast-2"

# Directories
LAYER_DIR="lambda_layer"
PACKAGE_DIR="lambda_package_minimal"
SRC_DIR="src"

echo "🚀 Starting optimized Lambda deployment process..."

# Clean up previous builds
echo "🧹 Cleaning up previous builds..."
rm -rf $LAYER_DIR $PACKAGE_DIR
rm -f lambda_layer.zip lambda_deployment_minimal.zip

# Create directories
mkdir -p $LAYER_DIR/python
mkdir -p $PACKAGE_DIR

echo "📚 Creating Lambda Layer with heavy dependencies..."

# Create layer requirements (heavy dependencies)
cat > layer_requirements.txt << 'EOF'
boto3==1.34.34
botocore==1.34.34
pandas==2.1.4
pyarrow==14.0.2
Pillow==10.2.0
requests==2.31.0
aiofiles==23.2.1
EOF

# Install layer dependencies
pip install -r layer_requirements.txt -t $LAYER_DIR/python --no-deps

# Create layer package
echo "🗜️  Creating Lambda Layer package..."
cd $LAYER_DIR
zip -r ../lambda_layer.zip . -x "*.pyc" "__pycache__/*" "*.git/*"
cd ..

# Check layer size
LAYER_SIZE=$(du -sh lambda_layer.zip | cut -f1)
echo "📏 Layer package size: $LAYER_SIZE"

echo "📦 Creating minimal function package..."

# Create minimal requirements (only TikTokApi and small deps)
cat > minimal_requirements.txt << 'EOF'
TikTokApi==6.1.0
EOF

# Install minimal dependencies
pip install -r minimal_requirements.txt -t $PACKAGE_DIR --no-deps

# Copy optimized source code
cp src/tiktok_data_collect_s3_optimized.py $PACKAGE_DIR/
# Also copy as the original name for the handler
cp src/tiktok_data_collect_s3_optimized.py $PACKAGE_DIR/tiktok_data_collect_s3.py

# Create minimal deployment package
cd $PACKAGE_DIR
zip -r ../lambda_deployment_minimal.zip . -x "*.pyc" "__pycache__/*" "*.git/*"
cd ..

# Check package sizes
PACKAGE_SIZE=$(du -sh lambda_deployment_minimal.zip | cut -f1)
echo "📏 Minimal package size: $PACKAGE_SIZE"

echo "✅ Optimized deployment packages created!"
echo "  - Layer: lambda_layer.zip ($LAYER_SIZE)"
echo "  - Function: lambda_deployment_minimal.zip ($PACKAGE_SIZE)"

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo "❌ AWS CLI not configured. Please run 'aws configure' first."
    exit 1
fi

# Deploy layer first
echo "🎯 Deploying Lambda Layer..."
LAYER_VERSION=$(aws lambda publish-layer-version \
    --layer-name $LAYER_NAME \
    --zip-file fileb://lambda_layer.zip \
    --compatible-runtimes $RUNTIME \
    --region $REGION \
    --query 'Version' --output text)

echo "✅ Layer deployed! Version: $LAYER_VERSION"

# Get layer ARN
LAYER_ARN="arn:aws:lambda:$REGION:$(aws sts get-caller-identity --query Account --output text):layer:$LAYER_NAME:$LAYER_VERSION"
echo "📋 Layer ARN: $LAYER_ARN"

# Offer to deploy function
read -p "Do you want to deploy/update the function now? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 Deploying to AWS Lambda..."
    
    # Check if function exists
    if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION &>/dev/null; then
        echo "🔄 Updating existing function..."
        aws lambda update-function-code \
            --function-name $FUNCTION_NAME \
            --zip-file fileb://lambda_deployment_minimal.zip \
            --region $REGION
        
        echo "🔗 Updating function layers..."
        aws lambda update-function-configuration \
            --function-name $FUNCTION_NAME \
            --layers $LAYER_ARN \
            --region $REGION
    else
        echo "🆕 Creating new function..."
        aws lambda create-function \
            --function-name $FUNCTION_NAME \
            --runtime $RUNTIME \
            --role arn:aws:iam::777022888924:role/lambda-socialmediaanalyzer-collector-role \
            --handler $HANDLER \
            --zip-file fileb://lambda_deployment_minimal.zip \
            --memory-size $MEMORY_SIZE \
            --timeout $TIMEOUT \
            --layers $LAYER_ARN \
            --region $REGION
    fi
    
    echo "✅ Function deployed successfully!"
else
    echo ""
    echo "Manual deployment commands:"
    echo "1. Deploy layer:"
    echo "   aws lambda publish-layer-version --layer-name $LAYER_NAME --zip-file fileb://lambda_layer.zip --compatible-runtimes $RUNTIME --region $REGION"
    echo ""
    echo "2. Create function:"
    echo "   aws lambda create-function \\"
    echo "     --function-name $FUNCTION_NAME \\"
    echo "     --runtime $RUNTIME \\"
    echo "     --role arn:aws:iam::777022888924:role/lambda-socialmediaanalyzer-collector-role \\"
    echo "     --handler $HANDLER \\"
    echo "     --zip-file fileb://lambda_deployment_minimal.zip \\"
    echo "     --memory-size $MEMORY_SIZE \\"
    echo "     --timeout $TIMEOUT \\"
    echo "     --layers $LAYER_ARN \\"
    echo "     --region $REGION"
fi

# Cleanup temporary files
echo "🧹 Cleaning up temporary files..."
rm -f layer_requirements.txt minimal_requirements.txt

echo "✨ Optimized deployment script completed!" 