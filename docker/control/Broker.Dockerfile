FROM python:3.12-alpine
RUN apk add --no-cache docker-cli
COPY broker.py /usr/local/bin/panolab-broker.py
ENTRYPOINT ["python3","-u","/usr/local/bin/panolab-broker.py"]
