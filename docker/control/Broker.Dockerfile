# Only the restricted broker has Docker CLI/socket access; rootless socket
# mounting and engine verification are enforced by Compose and broker code.
FROM python:3.12-alpine
RUN apk add --no-cache docker-cli
COPY broker.py /usr/local/bin/panolab-broker.py
ENTRYPOINT ["python3","-u","/usr/local/bin/panolab-broker.py"]
