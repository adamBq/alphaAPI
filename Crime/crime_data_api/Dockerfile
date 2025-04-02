ARG PLATFORM=linux/amd64

FROM --platform=${PLATFORM} public.ecr.aws/lambda/python:3.12

# Set working directory
WORKDIR /var/task

# Copy app code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the Lambda function handler
CMD ["crime_data_api.lambda_handler"]