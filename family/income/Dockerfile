ARG PLATFORM=linux/amd64

FROM --platform=${PLATFORM} public.ecr.aws/lambda/python:3.12

# Copy requirements first to cache dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the Python script
COPY income.py ${LAMBDA_TASK_ROOT}

# Set the Lambda handler
CMD ["income.lambda_handler"]