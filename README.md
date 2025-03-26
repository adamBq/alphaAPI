## Repository Structure

microservice/\
├── functions1/\
│&nbsp;&nbsp;├── main.py\
│&nbsp;&nbsp;├── Dockerfile\
│&nbsp;&nbsp;└── tests/\
│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── test_main.py\
│\
├── functions2/\
│&nbsp;&nbsp;├── main.py\
│&nbsp;&nbsp;├── Dockerfile\
│&nbsp;&nbsp;└── tests/\
│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── test_main.py\
│\
└── deploy.sh\

## Prerequisites

- **Docker:** [Get Docker](https://docs.docker.com/get-docker/)
- **AWS CLI:** [AWS CLI Installation](https://aws.amazon.com/cli/) (ensure it’s configured with proper credentials)
- **AWS SAM CLI (Optional):** [AWS SAM CLI](https://aws.amazon.com/serverless/sam/) for local testing and debugging

## Deployment Instructions

The `deploy.sh` script automates the following steps:

1. **Dockerize each function:** Builds Docker images for every function directory.
2. **Upload to AWS ECR:** Pushes the Docker images to your AWS Elastic Container Registry.
3. **Deploy to AWS Lambda:** Deploys the images as AWS Lambda functions.

### How to Run the Deployment Script
   ```bash
   ./deploy.sh
```

## Local Development and Testing
To build a Docker image for a specific function:
```bash
# Navigate to the function directory
cd functions1

# Build the Docker image
docker build -t function1-image .

# Run the Docker container locally
docker run -p 8080:8080 function1-image
```

