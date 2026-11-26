# PanoLab Direct ISE 14.7 runtime worker and authenticated setup service.
# CentOS 6.10 compatibility; vendor binaries and license stay private.
# The vendor MCP server and toolchain run in one runtime container.
# Compile the embedded MCP binary in a local Docker build stage.
FROM golang:1.26-bookworm AS mcp-builder
ARG TARGETOS
ARG TARGETARCH
RUN test "$TARGETOS/$TARGETARCH" = linux/amd64 || \
    { echo "ISE 14.7 images require --platform linux/amd64" >&2; exit 1; }
WORKDIR /src
COPY mcp/go.mod mcp/go.sum ./
RUN go mod download && go mod verify
COPY mcp/*.go ./
COPY mcp/setup/ ./setup/
# Compile and test only against the committed checksum-locked module graph.
RUN go test ./... && \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /panolab-ise-mcp . && \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /panolab-setup-mcp ./setup

FROM centos:6.10 AS runtime
ARG TARGETOS
ARG TARGETARCH
RUN test "$TARGETOS/$TARGETARCH" = linux/amd64 || \
    { echo "ISE 14.7 images require --platform linux/amd64" >&2; exit 1; }
RUN sed -i \
      -e 's/^mirrorlist=/#mirrorlist=/' \
      -e 's|^#baseurl=http://mirror.centos.org/centos/$releasever|baseurl=http://vault.centos.org/6.10|' \
      /etc/yum.repos.d/CentOS-Base.repo && \
    yum -y install \
      ca-certificates compat-libstdc++-33 libX11 openmotif22 patch \
      tigervnc-server xterm xorg-x11-twm xorg-x11-fonts-misc \
      xorg-x11-fonts-75dpi libXext libXrender libXrandr libXtst libXi \
      fontconfig freetype dejavu-sans-fonts liberation-sans-fonts \
      shadow-utils util-linux-ng && yum clean all

RUN printf '%s\n' 'ise soft nproc 16384' > /etc/security/limits.d/99-pano-ise-nproc.conf
COPY --from=mcp-builder /panolab-ise-mcp /usr/local/bin/panolab-ise-mcp
COPY entrypoint.sh /usr/local/bin/panolab-ise-entrypoint
RUN chmod 0755 /usr/local/bin/panolab-ise-mcp /usr/local/bin/panolab-ise-entrypoint && \
    mkdir -p /opt/Xilinx /home/ise /results/jobs /projects

ENV XILINXD_LICENSE_FILE=/licenses/Xilinx.lic
WORKDIR /results
EXPOSE 8765
ENTRYPOINT ["/usr/local/bin/panolab-ise-entrypoint"]
CMD ["mcp"]

FROM runtime AS setup-runtime
COPY --from=mcp-builder /panolab-setup-mcp /usr/local/bin/panolab-setup-mcp
RUN chmod 0755 /usr/local/bin/panolab-setup-mcp
EXPOSE 8766
ENTRYPOINT ["/usr/local/bin/panolab-setup-mcp"]
CMD []

# Default output: ISE 14.7 runtime worker with embedded MCP.
FROM runtime AS final
