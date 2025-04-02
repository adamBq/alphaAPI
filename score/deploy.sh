#!/bin/bash
set -e

if [ -z "$1" ]; then
    echo "Usage ./deploy.sh [test|dev|prod]"
    exit 1
fi

ENV=$1

# Validate env input
if [[ ${ENV} != "test" && ${ENV} != "dev" && ${ENV} != "prod" ]]; then
    echo "Invalid environment: '${ENV}'"
    echo "Usage ./deploy.sh [test|dev|prod]"
    exit 1
fi

# Configuration variables
ACCOUNT_ID="522814692697"
REGION="ap-southeast-2"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
LAMBDA_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/LambdaExecutionRole"

# Authenticate Docker to ECR
echo "Authenticating Docker to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Loop through each subdirectory (each representing a Lambda function)
for dir in */ ; do
    if [ -f "${dir}/Dockerfile" ]; then
        SERVICE_NAME=$(basename "$dir")
        FUNCTION_NAME="${ENV}_${SERVICE_NAME}"
        echo "----------------------------------------"
        echo "Processing function: ${FUNCTION_NAME}"
        
        # Check if the ECR repository exists; if not, create it.
        echo "Checking if ECR repository for ${FUNCTION_NAME} exists..."
        if ! aws ecr describe-repositories --repository-names "${FUNCTION_NAME}" --region ${REGION} > /dev/null 2>&1; then
            echo "ECR repository does not exist. Creating repository ${FUNCTION_NAME}..."
            aws ecr create-repository --repository-name "${FUNCTION_NAME}" --region ${REGION}
        else
            echo "ECR repository ${FUNCTION_NAME} already exists."
        fi

        # Build the Docker image
        echo "Building Docker image for ${FUNCTION_NAME}..."
        docker build -t ${FUNCTION_NAME} "${dir}"
        
        # Tag the image for ECR
        echo "Tagging Docker image for ECR..."
        docker tag ${FUNCTION_NAME}:latest ${ECR_URI}/${FUNCTION_NAME}:latest
        
        # Push the image to ECR
        echo "Pushing Docker image to ECR..."
        docker push ${ECR_URI}/${FUNCTION_NAME}:latest
        
        # Check if the Lambda function already exists and update or create accordingly.
        echo "Checking if Lambda function ${FUNCTION_NAME} exists..."
        if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} --no-cli-pager > /dev/null 2>&1; then
            echo "Lambda function exists. Updating function code..."
            aws lambda update-function-code \
              --function-name ${FUNCTION_NAME} \
              --image-uri ${ECR_URI}/${FUNCTION_NAME}:latest \
              --region ${REGION} \
              --no-cli-pager
        else
            echo "Lambda function does not exist. Creating new Lambda function..."
            aws lambda create-function \
              --function-name ${FUNCTION_NAME} \
              --package-type Image \
              --code ImageUri=${ECR_URI}/${FUNCTION_NAME}:latest \
              --role ${LAMBDA_ROLE} \
              --region ${REGION} \
              --no-cli-pager
        fi
        
        echo "Deployment for ${FUNCTION_NAME} completed."
        echo "----------------------------------------"
    else
        echo "Skipping ${dir}: No Dockerfile found."
    fi
done

echo "All functions processed."
