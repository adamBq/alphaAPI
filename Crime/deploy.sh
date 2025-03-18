#!/bin/bash
set -e

# Configuration variables
ACCOUNT_ID="216989131264"
REGION="us-east-1"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
LAMBDA_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/CrimeDataRole"

# Authenticate Docker to ECR
echo "Authenticating Docker to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Process each function in parallel
for dir in */ ; do
    ( # Start a subprocess
        if [ -f "${dir}Dockerfile" ]; then
            FUNCTION_NAME=$(basename $dir | tr '[:upper:]' '[:lower:]')
            echo "_____________________________"
            echo "Processing function: ${FUNCTION_NAME}"

            # Check if ECR repository exists
            if ! aws ecr describe-repositories --repository-names "${FUNCTION_NAME}" --region ${REGION} > /dev/null 2>&1; then

                echo "Creating ECR repository for function: ${FUNCTION_NAME}"
                aws ecr create-repository --repository-name "${FUNCTION_NAME}" --region ${REGION}

            fi

            # Build and push Docker image
            echo "Building Docker image..."
            docker buildx build --platform linux/amd64 \
                --tag ${ECR_URI}/${FUNCTION_NAME}:latest \
                --push --provenance=false "${dir}"

        echo "Pushed image to ECR: ${ECR_URI}/${FUNCTION_NAME}:latest"

            # Deploy Lambda function
            if aws lambda get-function --function-name ${FUNCTION_NAME} --region ${REGION} > /dev/null 2>&1; then
                echo "Updating existing Lambda function..."
                aws lambda update-function-code \
                 --function-name ${FUNCTION_NAME} \
                 --image-uri ${ECR_URI}/${FUNCTION_NAME}:latest \
                 --region ${REGION}
            else
                echo "Creating new Lambda function..."
                aws lambda create-function \
                 --function-name ${FUNCTION_NAME} \
                 --package-type Image \
                 --code ImageUri=${ECR_URI}/${FUNCTION_NAME}:latest \
                 --role ${LAMBDA_ROLE} \
                 --region ${REGION}
            fi

            echo "Deployment completed for ${FUNCTION_NAME}"
            echo "_____________________________"
        else
            echo "Skipping ${dir} as it does not contain a Dockerfile"
        fi
    ) &
done
wait

echo "All functions deployed successfully"