ARG PLATFORM=linux/amd64

FROM --platform=${PLATFORM} public.ecr.aws/lambda/python:3.12

# Copy function code
COPY collector.py ./
COPY requirements.txt ./

# Install dependencies into the container
RUN pip install --no-cache-dir -r requirements.txt --target .

# Set the command to your Lambda handler's function
CMD ["collector.lambda_handler"]