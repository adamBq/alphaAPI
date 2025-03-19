# --------------------------------------------------------
#  Dockerfile for retrieving & returning data (Python 3.12)
# --------------------------------------------------------
    FROM public.ecr.aws/lambda/python:3.12

    WORKDIR /var/task
    
    # 1) Copy requirements and install
    COPY requirements.txt .
    RUN pip install -r requirements.txt
    
    # 2) Copy app.py
    COPY app.py .
    
    # 3) For AWS Lambda, define CMD as module.function
    CMD ["app.lambda_handler"]
    