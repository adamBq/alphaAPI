# Base image for AWS Lambda Python
FROM public.ecr.aws/lambda/python:3.12

# Set working directory
WORKDIR /var/task

# Copy app code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the Lambda function handler
CMD ["lambda_function.lambda_handler"]