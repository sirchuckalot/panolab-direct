# Build the authenticated MCP manager. The rootless Compose overlay
# uses owner-mapped namespace UID 0 for access to private 0600 inputs.
FROM golang:1.26-bookworm AS build
WORKDIR /src
COPY ise14/mcp/go.mod ise14/mcp/go.sum ./
RUN go mod download && go mod verify
COPY control/mcp/*.go ./
RUN go test ./... && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o /panolab-manager .
FROM debian:bookworm-slim
COPY --from=build /panolab-manager /usr/local/bin/panolab-manager
USER 1000:1000
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/panolab-manager"]
