ARG PLATFORM=linux/amd64

FROM --platform=${PLATFORM} public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}

RUN pip install -r requirements.txt

COPY main.py ${LAMBDA_TASK_ROOT}
COPY helpers.py ${LAMBDA_TASK_ROOT}

CMD [ "main.handler" ]