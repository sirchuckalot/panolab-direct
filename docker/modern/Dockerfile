FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git make gcc g++ curl python3 python3-pip python3-venv \
    yosys iverilog verilator ripgrep \
    gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf \
    libevent-dev libjson-c-dev zlib1g-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
# OpenAI Codex CLI: official standalone Linux binary, pinned by version and SHA-256.
# Credentials are deliberately NOT baked into images. CODEX_HOME is a private,
# dedicated host bind mount and never the shared workspace.
ARG CODEX_VERSION=0.171.0
ARG CODEX_ARCHIVE_SHA256=01baa2e47809f8597be5b2f8abd4e4dfe3fb5bcb6e504c2fbaaad97056c15e8d
ARG CODEX_CODE_MODE_HOST_SHA256=d78619030c1b8d0a4d9c9c67667c1bfa23ad9d9edc63d87ffeaa86796f3d868c
RUN set -eux; \
    curl -fLsS --retry 3 \
      "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/codex.tar.gz; \
    echo "${CODEX_ARCHIVE_SHA256}  /tmp/codex.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/codex.tar.gz -C /usr/local/bin codex-x86_64-unknown-linux-musl; \
    mv /usr/local/bin/codex-x86_64-unknown-linux-musl /usr/local/bin/codex; \
    chmod 0755 /usr/local/bin/codex; \
    rm /tmp/codex.tar.gz; \
    curl -fLsS --retry 3 \
      "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-code-mode-host-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/codex-code-mode-host.tar.gz; \
    echo "${CODEX_CODE_MODE_HOST_SHA256}  /tmp/codex-code-mode-host.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/codex-code-mode-host.tar.gz -C /usr/local/bin codex-code-mode-host-x86_64-unknown-linux-musl; \
    mv /usr/local/bin/codex-code-mode-host-x86_64-unknown-linux-musl /usr/local/bin/codex-code-mode-host; \
    chmod 0755 /usr/local/bin/codex-code-mode-host; \
    rm /tmp/codex-code-mode-host.tar.gz; \
    test -x /usr/local/bin/codex-code-mode-host; \
    codex --version
# PanoLab Rescue: immutable source-pinned LiteX development toolchain.
# No old G2 FPGA framework, host package installer, license, JTAG or TAP sudo.
COPY litex-bootstrap.py litex-upstream.lock.json litex-requirements.txt /opt/panolab/recipes/
RUN python3 /opt/panolab/recipes/litex-bootstrap.py \
      --prefix /opt/panolab/litex \
      --lock /opt/panolab/recipes/litex-upstream.lock.json \
      --requirements /opt/panolab/recipes/litex-requirements.txt && \
    python3 /opt/panolab/recipes/litex-bootstrap.py \
      --prefix /opt/panolab/litex \
      --lock /opt/panolab/recipes/litex-upstream.lock.json \
      --requirements /opt/panolab/recipes/litex-requirements.txt \
      --verify-only
ENV PANOLAB_RESCUE_UPSTREAM=/opt/panolab/litex/upstream \
    PANOLAB_RESCUE_PYDEPS=/opt/panolab/litex/venv/lib/python3.12/site-packages \
    PANOLAB_RESCUE_BIN=/opt/panolab/litex/venv/bin \
    VIRTUAL_ENV=/opt/panolab/litex/venv
ENV PATH="/opt/panolab/litex/venv/bin:${PATH}"
ENV PYTHONPATH="/opt/panolab/litex/upstream/pythondata-software-picolibc:/opt/panolab/litex/upstream/migen:/opt/panolab/litex/upstream/litex:/opt/panolab/litex/upstream/litex-boards:/opt/panolab/litex/upstream/liteeth:/opt/panolab/litex/upstream/litespi:/opt/panolab/litex/venv/lib/python3.12/site-packages"
LABEL org.panolab.litex.recipe="rescue-g2b-20261123-v1"
# A deterministic CLI environment is also available at /opt/panolab/litex/env.sh.
# Codex executable is installed; authentication remains separate in a private mount.
WORKDIR /workspace
CMD ["bash"]

# An optional UID 1000 account is retained in the tool image.
# The active rootless dev container runs as namespace UID 0, which maps
# to the ordinary laptop owner and can reach private owner-only binds.
RUN if ! getent group 1000 >/dev/null; then groupadd --gid 1000 dev; fi && \
    if ! getent passwd 1000 >/dev/null; then \
      useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash dev; \
    fi && \
    mkdir -p /workspace /codex-auth && \
    chown 1000:1000 /workspace /codex-auth

