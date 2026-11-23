# Constrained source gateway, with private inputs masked by Compose.
# The rootless overlay selects owner-mapped namespace UID 0 at runtime.
FROM python:3.12-alpine
RUN apk add --no-cache git ca-certificates
COPY repo_gateway.py /usr/local/bin/panolab-repo-gateway.py
USER 1000:1000
ENTRYPOINT ["python3","-u","/usr/local/bin/panolab-repo-gateway.py"]
