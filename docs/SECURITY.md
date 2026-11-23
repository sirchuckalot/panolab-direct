# Security boundaries

**Allowed:** source checkout, narrow approved private inputs, user-scoped
rootless Docker Engine, local restricted PanoLab MCP broker.

**Forbidden by default:** sudo, host package installation, rootful Docker
management, privileged containers, broad `$HOME` binds, host network,
Docker socket inside a development/agent container, unchecked outbound
services, exposing Etherbone or vendor services publicly, and automatic
FPGA programming.

## Trust map

- `manager` and `repo-git` communicate using private RPC paths.
- Only `docker-broker` sees the **user rootless Docker socket**,
  bound as `/var/run/docker.sock` *inside the broker*. The broker
  must reject non-rootless Engines; its allowlist is a security boundary.
- Rootless container UID 0 maps to the ordinary laptop owner's
  host UID, **not host root**. It can still read/write that owner's
  accessible files if a mount is granted.
- `dev` has a 2-CPU, 4-GiB, 256-PID quota and approved source/workspace
  mounts; its auth mount belongs to the owner's private directory.
- `tunnel` connects out to the platform and uses private on-disk
  credentials. The internal MCP endpoint is bearer-protected; a
  request without a bearer must be rejected.
- The Git gateway masks `docker/private/` and `docker/.env`;
  no credentials, media, license or bitstreams go to GitHub.

Factory SPI flash, JTAG, volatile FPGA programming and physical network
access require separate exact owner authorization, trusted recovery
provisions and evidence. A remote MCP tool is not blanket consent.

The ISE legacy userspace is EOL. Isolate it and confirm licensing/
HOSTID behavior before running a real vendor build.
