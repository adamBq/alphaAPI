ARG PLATFORM=linux/amd64

FROM --platform=${PLATFORM} public.ecr.aws/lambda/python:3.12
# Copy requirements and install them into /opt/python (so they're visible to Lambda)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target /opt/python

# Copy our function code
COPY collector.py ./

# The Lambda runtime looks for the function "collector.lambda_handler" by default
CMD [ "collector.lambda_handler" ]
