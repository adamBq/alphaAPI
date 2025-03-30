ARG PLATFORM=linux/amd64

FROM --platform=${PLATFORM} public.ecr.aws/lambda/python:3.12

COPY main.py ${LAMBDA_TASK_ROOT}

CMD [ "main.handler" ]