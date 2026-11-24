# TEMPORARY trusted rootless-Docker maintenance client.
# Activated by the opt-in trusted-maintenance Compose profile only.
# Has no runtime network; it receives only owner rootless Docker socket.
FROM python:3.12-alpine
RUN apk add --no-cache bash coreutils docker-cli docker-cli-buildx docker-cli-compose git
WORKDIR /workspace
ENTRYPOINT ["sleep","infinity"]
