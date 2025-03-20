FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target /opt/python

COPY retriever.py ./

CMD [ "retriever.lambda_handler" ]
