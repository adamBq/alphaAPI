# Use AWS Lambda's Python 3.9 base image
FROM public.ecr.aws/lambda/python:3.12

# Copy requirements.txt first so Docker can cache the layer when dependencies don't change
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the Python code
COPY api_population.py ${LAMBDA_TASK_ROOT}

# Set the Lambda entry point (the handler function in api_population.py)
CMD ["api_population.lambda_handler"]
