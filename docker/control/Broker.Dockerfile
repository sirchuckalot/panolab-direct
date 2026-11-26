# Only the restricted broker has Docker CLI/socket access; rootless socket
# mounting and engine verification are enforced by Compose and broker code.
FROM python:3.12-alpine
RUN apk add --no-cache docker-cli
COPY dev_source.py /usr/local/bin/dev_source.py
COPY broker.py /usr/local/bin/panolab-broker.py
COPY ise_proxy.py /usr/local/bin/ise_proxy.py
COPY ise_staging.py /usr/local/bin/ise_staging.py
COPY ise_setup.py /usr/local/bin/ise_setup.py
COPY ise_acceptance.py /usr/local/bin/ise_acceptance.py
COPY test_ise_setup.py /tmp/test_ise_setup.py
COPY test_ise_acceptance.py /tmp/test_ise_acceptance.py
COPY test_ise_proxy.py /tmp/test_ise_proxy.py
COPY test_ise_staging.py /tmp/test_ise_staging.py
COPY test_trusted_maintenance.py /tmp/test_trusted_maintenance.py
RUN PYTHONPATH=/usr/local/bin python3 /tmp/test_ise_acceptance.py \
 && PYTHONPATH=/usr/local/bin python3 /tmp/test_ise_setup.py \
 && PYTHONPATH=/usr/local/bin python3 /tmp/test_ise_proxy.py \
 && PYTHONPATH=/usr/local/bin python3 /tmp/test_ise_staging.py \
 && PYTHONPATH=/usr/local/bin python3 /tmp/test_trusted_maintenance.py \
 && rm /tmp/test_ise_acceptance.py /tmp/test_ise_setup.py /tmp/test_ise_proxy.py /tmp/test_ise_staging.py /tmp/test_trusted_maintenance.py
ENTRYPOINT ["python3","-u","/usr/local/bin/panolab-broker.py"]
