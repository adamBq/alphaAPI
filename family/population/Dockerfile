ARG PLATFORM=linux/amd64

FROM --platform=${PLATFORM} public.ecr.aws/lambda/python:3.12

# Copy requirements.txt first so Docker can cache the layer when dependencies don't change
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the Python code
COPY population.py ${LAMBDA_TASK_ROOT}

# Set the Lambda entry point (the handler function in population.py)
CMD ["population.lambda_handler"]
