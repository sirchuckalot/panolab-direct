"""Owner-authorized rootless external-storage transaction."""
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

from cutover_copy import (copy_external, entries, lexists, manifest, remove_entry,
                          restore_legacy, sync_filesystem, verify_link_relocation)
from storage_paths import check_path


LABEL = "panolab.cutover"
PROJECT = "panolab-direct-external"
INGRESS = "panolab-direct-connect-tunnel-1"
COMPOSE = {
    "setup": "panolab-direct-connect-setup-1",
    "docker-broker": "panolab-direct-connect-docker-broker-1",
    "repo-git": "panolab-direct-connect-repo-git-1",
    "manager": "panolab-direct-connect-manager-1",
    "trusted-maintenance": "panolab-direct-trusted-maintenance",
    "tunnel": INGRESS,
}


def load_script(directory, name):
    spec = importlib.util.spec_from_file_location(name, directory / "host" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def restart_value(record):
    name = record["Name"]
    count = record["MaximumRetryCount"]
    if name not in {"no", "unless-stopped", "on-failure", "always"} or (
        type(count) is not int or count < 0 or (count and name != "on-failure")
    ):
        raise ValueError("Invalid restart policy")
    return f"{name}:{count}" if count else name


class Cutover:
    def __init__(self, api, args, records, migration, worker):
        self.api = api
        self.args = args
        self.records = records
        self.migration = migration
        self.worker = worker
        self.repo = args.checkout
        self.journal = args.journal / "transaction.json"
        self.stage = self.repo / "docker" / (".cutover-restore-" + args.transaction)
        self.config, self.data = args.config, args.data
        self.legacy = self.repo / "docker/private"
        self.plan = [
            (self.repo / "docker/.env" if name == ".env" else self.legacy / name, root / name)
            for root, names in ((self.config, migration.CONFIG), (self.data, migration.DATA))
            for name in names
        ]
        self.names = set(COMPOSE.values()) | {api.DEV, api.WORKER}
        self.start_order = [COMPOSE[role] for role in ("docker-broker", "repo-git")] + [
            api.WORKER, api.DEV, COMPOSE["manager"], api.MAINTENANCE, INGRESS,
        ]
        self.stop_order = [
            INGRESS, COMPOSE["manager"], COMPOSE["docker-broker"], COMPOSE["repo-git"],
            api.WORKER, api.DEV, api.MAINTENANCE,
        ]
        self.labels = f"{LABEL}={args.transaction}"
        self.probe_name = "panolab-cutover-probe-" + args.transaction
        self.baseline_branch = "panolab-cutover-baseline-" + args.transaction
        self.target_branch = "panolab-cutover-target-" + args.transaction
        self.git_push = any(
            mount["target"] == "/run/panolab-git-auth"
            for mount in records[COMPOSE["repo-git"]]["mounts"]
        )
        self.override = args.journal / "compose-override.json"
        self.identity = dict(
            version=1, transaction=args.transaction, repo=str(self.repo),
            source=str(api.SOURCE), config=str(self.config), data=str(self.data),
            socket=str(args.socket), target=args.target, baseline=args.baseline,
            inventory=args.inventory_sha256,
            candidate_images=[args.broker_image, args.repo_git_image],
        )
        self.env = dict(os.environ, PANOLAB_REPO_HOST=str(self.repo),
                        PANOLAB_ROOTLESS_SOCKET=str(args.socket),
                        PANOLAB_CONFIG_DIR=str(self.config), PANOLAB_DATA_DIR=str(self.data),
                        PANOLAB_WORKSPACE_HOST=str(self.data / "agent-workspace"),
                        PANOLAB_CODEX_AUTH_HOST=str(self.config / "codex-auth"),
                        PANOLAB_ISE_TARBALL=str(self.data / migration.ARCHIVE))
        self.env.pop("DOCKER_CONTEXT", None)
        self.env.pop("DOCKER_HOST", None)
        self.state = {}

    def docker(self, *args):
        return self.api.query("docker", "-H", f"unix://{self.args.socket}", *args)

    def git(self, *args):
        return self.api.git(self.api.query, self.repo, *args)

    def save(self, phase, **details):
        self.state.update(details, phase=phase)
        self.migration.write_journal(self.journal, self.state)

    def renamed(self, name):
        return f"{name}-pre-external-{self.args.transaction}"

    def containers(self):
        raw = self.docker("ps", "-a", "--no-trunc", "--format", "{{json .}}")
        result = {}
        for line in raw.splitlines():
            row = json.loads(line)
            name, oid = row["Names"], row["ID"]
            if name in result or not re.fullmatch(self.api.DIGEST, oid):
                raise ValueError("Malformed container inventory result")
            result[name] = oid
        return result

    def owned(self):
        present = self.containers()
        result = {}
        for name, oid in present.items():
            if name not in self.names:
                continue
            if oid == self.records[name]["id"]:
                continue
            installed = self.docker("inspect", "--format",
                                    '{{index .Config.Labels "panolab.cutover"}}', oid)
            if installed != self.args.transaction:
                raise ValueError("A foreign container occupies a canonical name")
            result[name] = oid
        return result

    def quiescent(self):
        for oid in self.docker("ps", "-q", "--no-trunc").splitlines():
            if oid == self.state["supervisor"]:
                continue
            mounts = json.loads(self.docker("inspect", "--format", "{{json .Mounts}}", oid))
            for mount in mounts:
                source = Path(mount["Source"])
                if mount["Type"] == "bind" and any(
                    source.is_relative_to(root) or root.is_relative_to(source)
                    for root in (self.repo, self.config, self.data, self.args.journal, self.api.SOURCE)
                ):
                    raise ValueError("A running container still binds a transaction root")

    def admit(self, supervisor):
        api, args = self.api, self.args
        api.require(self.repo.stat().st_uid == os.getuid(), "Canonical checkout owner differs")
        api.require_checkout(api.query, self.repo, args.baseline)
        api.require_checkout(api.query, api.SOURCE, args.target)
        api.require(self.git("symbolic-ref", "--short", "HEAD") == "development",
                    "Canonical checkout must be on development")
        api.require(args.baseline != args.target, "Target must advance development")
        api.require(not self.branch_revision(self.baseline_branch) and
                    not self.branch_revision(self.target_branch), "A Git backup branch already exists")
        api.query("git", "-C", str(api.SOURCE), "merge-base", "--is-ancestor",
                  args.baseline, args.target)
        api.query("python3", "-B", str(api.SOURCE / "docker/control/dev_source.py"), str(api.SOURCE))
        api.require("GNU coreutils" in api.query("cp", "--version"), "GNU cp unavailable in supervisor")
        api.require((api.SOURCE / "host/probe-management.py").is_file(),
                    "Reviewed local MCP health probe unavailable")
        api.verify_engine(api.query, self.repo, args.socket, self.records,
                          {"broker": args.broker_image, "repo-git": args.repo_git_image},
                          extra_ids={supervisor})
        api.require(not any(self.config.iterdir()) and not any(self.data.iterdir()),
                    "External roots must be empty")
        api.require(not lexists(self.stage), "Recovery staging path already exists")
        check_path(self.legacy, 0o700, True)
        expected = {old.name for old, _ in self.plan if old.parent == self.legacy}
        api.require({path.name for path in self.legacy.iterdir()} == expected,
                    "Legacy inventory differs")
        for old, new in self.plan:
            mode = (0o664 if new.name == self.migration.ARCHIVE else
                    0o600 if new.name in self.migration.FILES else 0o700)
            check_path(old, mode, new.name not in self.migration.FILES)
        try:
            self.migration.require_terminal_ise_jobs(self.legacy / "ise-work")
        except self.migration.ISEAdmissionError as error:
            raise ValueError(f"phase=ise-admission {error}") from None
        api.require(restart_value(self.records[api.SETUP]["restart"]) == "no",
                    "On-demand setup must have restart disabled")
        api.require(not set(self.containers()).intersection(map(self.renamed, self.names)),
                    "A backup name is occupied")
        for record in self.records.values():
            restart_value(record["restart"])
        if self.legacy.stat().st_dev != self.stage.parent.stat().st_dev:
            raise ValueError("Legacy restore staging requires a non-replacing local rename")

    def stop_if_running(self, oid):
        status = self.docker("inspect", "--format", "{{.State.Status}}", oid)
        if status in {"running", "restarting"}:
            self.docker("stop", "--time", "20", oid)
        elif status not in {"exited", "created"}:
            raise ValueError("Unexpected preserved container state")

    def storage_identity(self, forward):
        result = {}
        for path, name, _ in entries(self.plan, forward):
            info = path.lstat()
            result[name] = [info.st_dev, info.st_ino]
        return result

    def stop_old(self):
        for record in self.records.values():
            self.docker("update", "--restart=no", record["id"])
        for name in self.stop_order:
            self.docker("stop", "--time", "20", self.records[name]["id"])
        for record in self.records.values():
            if self.docker("inspect", "--format", "{{.State.Status}}", record["id"]) != "exited":
                raise ValueError("An original container did not quiesce")
        self.quiescent()
        self.migration.require_terminal_ise_jobs(self.legacy / "ise-work")
        for name in sorted(self.names):
            self.docker("rename", self.records[name]["id"], self.renamed(name))

    def compose_create(self):
        services = {}
        for role, name in COMPOSE.items():
            image = self.api.SERVICE_TAGS[name]
            services[role] = {"labels": {LABEL: self.args.transaction},
                              "image": image, "restart": "no"}
        self.migration.write_journal(self.override, {"services": services})
        compose = ["docker", "-H", f"unix://{self.args.socket}", "compose",
                   "--project-name", PROJECT, "--env-file", str(self.config / ".env")]
        paths = [self.repo / name for name in (
            "docker/compose.setup.yaml", "docker/compose.manage.yaml", "host/compose.rootless-laptop.yaml",
        )]
        if self.git_push:
            paths.append(self.repo / "docker/compose.git-push.yaml")
        for path in [*paths, self.override]:
            compose.extend(("-f", str(path)))
        subprocess.run([*compose, "--profile", "ise-setup", "--profile", "trusted-maintenance",
                        "create", "--no-build", "--no-recreate", "--pull", "never", *COMPOSE],
                       check=True, timeout=90, env=self.env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def set_service_tags(self, forward):
        for role, pair in (("docker-broker", self.args.broker_image),
                           ("repo-git", self.args.repo_git_image)):
            name = COMPOSE[role]
            tag = self.api.SERVICE_TAGS[name]
            previous = self.records[name]["image_id"]
            candidate = pair[1]
            current = self.docker("image", "inspect", "--format", "{{.Id}}", tag)
            if current not in (previous, candidate):
                raise ValueError("Service tag was changed outside the transaction")
            image = candidate if forward else previous
            if image != current:
                self.docker("image", "tag", image, tag)

    def create_replacements(self):
        self.set_service_tags(forward=True)
        self.compose_create()
        api = self.api
        self.docker("create", "--name", api.DEV, "--restart", "no", "--label", self.labels,
                    "--label", "panolab.managed=true", "--user", "0:0", "--workdir", "/workspace",
                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                    "--memory", "4g", "--cpus", "2", "--pids-limit", "256",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
                    "--tmpfs", "/home:rw,nosuid,nodev,size=64m",
                    "--mount", f"type=bind,src={self.data / 'agent-workspace'},dst=/workspace",
                    "--mount", f"type=bind,src={self.config / 'codex-auth'},dst=/codex-auth",
                    "--mount", f"type=bind,src={self.repo},dst=/repo,readonly",
                    "--tmpfs", "/repo/.git:ro,nosuid,nodev,noexec,size=64k",
                    "--env", "CODEX_HOME=/codex-auth", self.records[api.DEV]["image_id"],
                    "sleep", "infinity")
        worker = self.worker
        worker.ROOT = self.repo
        worker.DOCKER_SOCK = self.args.socket
        folder = self.data / "ise-work/worker"
        license_copy = folder / "license/Xilinx.lic"
        paths = (folder / "projects", folder / "results", license_copy, folder / "worker-token")
        for index, path in enumerate(paths):
            if path.resolve() != path or not (path.is_dir() if index < 2 else path.is_file()):
                raise ValueError("Preserved ISE worker inputs unavailable")
        if license_copy.read_bytes() != (self.config / "Xilinx.lic").read_bytes():
            raise ValueError("Preserved ISE license differs")
        worker.ensure_worker(*paths, image=self.records[api.WORKER]["image_id"],
                             restart="no", transaction=self.args.transaction)

    def probe(self, ids, old=False):
        if old:
            network = "panolab-direct-connect_lab-backend"
            secret = self.legacy / "mcp-bearer"
            image = self.records[COMPOSE["docker-broker"]]["image_id"]
        else:
            network = PROJECT + "_lab-backend"
            secret = self.config / "mcp-bearer"
            image = self.args.broker_image[1]
            src = self.repo / "docker/control/dev_source.py"
            script = self.api.query("python3", "-B", str(src), "--probe")
            dev = ids[self.api.DEV]
            mounts = self.docker("inspect", "--format",
                                 "{{json .Mounts}} {{json .HostConfig.Tmpfs}}", dev)
            subprocess.run(["python3", "-B", str(src), "--mounts", str(self.repo),
                            str(self.data / "agent-workspace"), str(self.config / "codex-auth")],
                           input=mounts, text=True, check=True, timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.docker("exec", dev, "/bin/sh", "-ec", script)
            self.docker("exec", dev, "/usr/local/bin/codex", "login", "status")
        owner = self.docker("network", "inspect", "--format",
                            '{{index .Labels "com.docker.compose.project"}}/'
                            '{{index .Labels "com.docker.compose.network"}}', network)
        if owner != network.removesuffix("_lab-backend") + "/lab-backend":
            raise ValueError("Local MCP probe network identity differs")
        probe = (self.api.SOURCE / "host/probe-management.py").read_text()
        expected = "PASS: private authenticated MCP, anonymous request rejected, status and repo tools"
        response = self.docker(
            "run", "--rm", "--name", self.probe_name, "--label", self.labels, "--network", network,
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
            "--mount", f"type=bind,src={secret},dst=/run/secrets/mcp-bearer,readonly",
            "--entrypoint", "python3", image, "-c", probe,
            self.args.baseline if old else self.args.target,
        )
        if response != expected:
            raise ValueError("Local MCP verification did not return its required result")
        self.worker.DOCKER_SOCK = self.args.socket
        result = self.worker.read_rpc(ids[self.api.WORKER], 8765,
                                      "/run/secrets/ise-worker-token", "toolchain_info")
        if (not isinstance(result, dict) or result.get("name") != "panolab-ise14"
                or result.get("ise_available") is not True or result.get("license_available") is not True
                or "ise14-implementation" not in result.get("profiles", [])):
            raise ValueError("Licensed worker did not report toolchain health")

    def apply(self):
        self.save("quiescing")
        self.stop_old()
        self.git("-c", "core.hooksPath=/dev/null", "fetch", "--no-tags",
                 "--no-write-fetch-head", str(self.api.SOURCE), self.args.target)
        self.save("advancing-source")
        self.git("branch", "--copy", "development", self.baseline_branch)
        self.git("-c", "core.hooksPath=/dev/null", "merge", "--ff-only", self.args.target)
        self.api.require_checkout(self.api.query, self.repo, self.args.target)
        originals = self.storage_identity(False)
        self.save("copying", originals=originals)
        digest = copy_external(self.plan)
        if originals != self.storage_identity(False):
            raise ValueError("Legacy storage identity changed during transfer")
        self.save("deleting", digest=digest, external=self.storage_identity(True))
        for old, new in self.plan:
            info = old.lstat()
            if originals[new.name] != [info.st_dev, info.st_ino]:
                raise ValueError("Legacy entry identity changed before removal")
            remove_entry(old)
        self.legacy.rmdir()
        sync_filesystem(self.legacy.parent)
        if any(lexists(path) for path in (self.legacy, self.repo / "docker/.env")):
            raise ValueError("Legacy data remains visible in the canonical checkout")
        self.api.query("python3", "-B", str(self.repo / "docker/control/dev_source.py"),
                       str(self.repo))
        self.save("creating")
        self.create_replacements()
        ids = self.owned()
        if set(ids) != self.names:
            raise ValueError("Replacement creation is incomplete")
        for name, oid in ids.items():
            expected = {COMPOSE["docker-broker"]: self.args.broker_image[1],
                        COMPOSE["repo-git"]: self.args.repo_git_image[1]}.get(
                            name, self.records[name]["image_id"])
            if self.docker("inspect", "--format", "{{.Image}}", oid) != expected:
                raise ValueError("Replacement image differs from its approved ID")
        self.save("starting", replacements=ids)
        for name in self.start_order[:-1]:
            self.docker("start", ids[name])
        self.probe(ids)
        for name, record in self.records.items():
            actual = self.docker("inspect", "--format",
                                 "{{.Image}}|{{.Name}}|{{.State.Status}}|{{.HostConfig.RestartPolicy.Name}}",
                                 record["id"])
            original_name = self.renamed(name) if name in self.names else name
            if actual != f"{record['image_id']}|/{original_name}|exited|no":
                raise ValueError("A preserved original differs after cutover")
        self.save("opening-ingress")
        self.docker("start", ids[INGRESS])
        if self.docker("inspect", "--format", "{{.State.Status}}", ids[INGRESS]) != "running":
            raise ValueError("Replacement tunnel is not running")
        for name, oid in ids.items():
            self.docker("update", "--restart", restart_value(self.records[name]["restart"]), oid)
        self.save("completed")

    def branch_revision(self, name):
        return self.git("for-each-ref", "--format=%(objectname)", "refs/heads/" + name)

    def restore_source(self):
        baseline, target = self.args.baseline, self.args.target
        head = self.git("rev-parse", "HEAD")
        if head not in (baseline, target):
            raise ValueError("Unexpected canonical source revision during rollback")
        self.api.require_checkout(self.api.query, self.repo, head)

        branch = self.branch_revision("development")
        if branch == target:
            if self.branch_revision(self.baseline_branch) != baseline or self.branch_revision(self.target_branch):
                raise ValueError("Git rollback branch identity differs")
            self.git("-c", "core.hooksPath=/dev/null", "switch", "--detach", baseline)
            self.git("branch", "--move", "development", self.target_branch)
            branch = ""
        if not branch:
            if (self.branch_revision(self.target_branch) != target or
                    self.branch_revision(self.baseline_branch) != baseline):
                raise ValueError("Interrupted Git rollback branch identity differs")
            self.git("branch", "--move", self.baseline_branch, "development")
        elif branch != baseline:
            raise ValueError("Unexpected development ref during rollback")
        self.git("-c", "core.hooksPath=/dev/null", "switch", "development")
        self.api.require_checkout(self.api.query, self.repo, baseline)

    def rollback(self):
        phase = self.state["phase"]
        self.save("stopping-replacements",
                  rollback_from=self.state.get("rollback_from", phase))
        for name, oid in self.owned().items():
            self.docker("update", "--restart=no", oid)
        new = self.owned()
        probe = self.containers().get(self.probe_name)
        if probe:
            label = self.docker("inspect", "--format", '{{index .Config.Labels "panolab.cutover"}}', probe)
            if label != self.args.transaction:
                raise ValueError("Probe name belongs to a foreign container")
            self.docker("rm", "-f", probe)
        for name in [*self.stop_order, self.api.SETUP]:
            if name in new:
                self.stop_if_running(new[name])
                self.docker("rm", new[name])
        self.stop_if_running(self.records[INGRESS]["id"])
        if self.state.get("rollback_storage_done") is not True:
            prior = self.state["rollback_from"]
            if prior not in {"admitted", "quiescing"}:
                self.quiescent()
            if prior in {"starting", "opening-ingress", "completed"} and not self.state.get("restore_digest"):
                verify_link_relocation([(new, old) for old, new in self.plan])
                self.save("stopping-replacements", restore_digest=manifest(entries(self.plan, True)),
                          restore_external=self.storage_identity(True))
            digest = self.state.get("restore_digest", self.state.get("digest"))
            if prior == "copying" and self.storage_identity(False) != self.state["originals"]:
                raise ValueError("Original entries changed during the failed copy")
            if digest:
                expected = self.state.get("restore_external", self.state["external"])
                if self.storage_identity(True) != expected:
                    raise ValueError("External entry identity differs during recovery")
                if not self.state.get("restore_staged"):
                    for old, new in self.plan:
                        if lexists(old):
                            info = old.lstat()
                            if self.state["originals"][new.name] != [info.st_dev, info.st_ino]:
                                raise ValueError("Original entry identity differs during recovery")
                    self.save("restoring")
                    restore_legacy(self.plan, self.stage, digest, self.migration.rename_without_replacement,
                                   self.legacy, "restoring")
                    self.save("installing-restore", restore_staged=True)
                restore_legacy(self.plan, self.stage, digest, self.migration.rename_without_replacement,
                               self.legacy, "installing-restore")
            self.save("restoring-services", rollback_storage_done=True)
        self.restore_source()
        if self.state["rollback_from"] in {"creating", "starting", "opening-ingress", "completed"}:
            self.set_service_tags(forward=False)
        if self.state["rollback_from"] in {"copying", "deleting", "creating", "starting",
                                           "opening-ingress", "completed"}:
            for _, new in self.plan:
                remove_entry(new)
            for root in (self.config, self.data):
                sync_filesystem(root)
        # Reconcile original names by full ID.
        present = self.containers()
        for name in sorted(self.names):
            oid = self.records[name]["id"]
            if present.get(name) == oid:
                continue
            if name in present or present.get(self.renamed(name)) != oid:
                raise ValueError("Original container identity cannot be reconciled")
            self.docker("rename", oid, name)
        for record in self.records.values():
            self.docker("update", "--restart", restart_value(record["restart"]), record["id"])
        ids = {name: record["id"] for name, record in self.records.items()}
        for name in self.start_order[:-1]:
            self.docker("start", ids[name])
        self.probe(ids, old=True)
        self.docker("start", ids[INGRESS])
        if self.docker("inspect", "--format", "{{.State.Status}}", ids[INGRESS]) != "running":
            raise ValueError("Original tunnel is not running")
        self.save("rolled-back")


def validate_paths(api, args):
    roots = [args.checkout, args.reviewed, args.journal, args.config, args.data]
    for path in [*roots, args.socket, args.inventory]:
        api.require(path is not None and path.is_absolute() and ".." not in path.parts
                    and not any(char in str(path) for char in "\n\r,:"),
                    "Expected an exact absolute bind or inventory path")
    api.require(all(not a.is_relative_to(b) and not b.is_relative_to(a)
                    for i, a in enumerate([*roots, args.socket])
                    for b in [*roots, args.socket][i + 1:]), "Supervisor binds overlap")
    api.require(args.inventory.parent == args.journal, "Stage the pinned inventory in the journal bind")
    api.require(re.fullmatch(api.IMAGE, args.supervisor_image or ""), "Expected full supervisor image ID")
    api.require(re.fullmatch(r"[a-f0-9]{32}", args.transaction or ""), "Expected exact transaction ID")


def supervisor_name(args):
    return "panolab-cutover-" + args.transaction


def launch(api, args):
    validate_paths(api, args)
    if not args.client_socket.is_socket():
        raise ValueError("Launching maintenance rootless socket unavailable")

    def docker(*command):
        return api.query("docker", "-H", f"unix://{args.client_socket}", *command)

    api.require('"name=rootless"' in docker("info", "--format", "{{json .SecurityOptions}}"),
                "Supervisor requires the owner rootless Engine")
    name = supervisor_name(args)
    existing = docker("ps", "-aq", "--no-trunc", "--filter", f"name=^/{name}$")
    if existing:
        metadata = docker("inspect", "--format",
                          '{{.Id}}|{{.Name}}|{{.Image}}|{{index .Config.Labels "panolab.supervisor"}}|{{.State.Running}}',
                          existing)
        api.require(metadata == f"{existing}|/{name}|{args.supervisor_image}|{args.transaction}|false",
                    "Supervisor name is occupied or the transaction is already running")
        # Keep the stopped supervisor and its logs as execution evidence.
        if not args.rollback:
            raise ValueError("Read the existing supervisor result before explicitly launching recovery")
        docker("rename", existing, name + "-previous-" + existing[:12])
    mounts = []
    bindings = [
        (args.checkout, False), (args.reviewed, True), (args.journal, False),
        (args.config, False), (args.data, False), (args.socket, False),
    ]
    for path, read_only in bindings:
        mounts.extend(("--mount", f"type=bind,src={path},dst={path}" + (",readonly" if read_only else "")))
    forwarded = []
    for key in ("checkout", "reviewed", "journal", "config", "data", "socket", "supervisor_image",
                "baseline", "target", "transaction", "inventory", "inventory_sha256"):
        forwarded.extend(("--" + key.replace("_", "-"), str(getattr(args, key))))
    forwarded.extend(("--broker-image", *args.broker_image, "--repo-git-image", *args.repo_git_image))
    if args.rollback:
        forwarded.append("--rollback")
    oid = docker("create", "--name", name, "--label", f"panolab.supervisor={args.transaction}",
                 "--restart", "unless-stopped", "--network", "none", "--read-only",
                 "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
                 "--user", "0:0", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                 "--env", "GIT_CONFIG_NOSYSTEM=1", "--env", "GIT_TERMINAL_PROMPT=0",
                 "--entrypoint", "python3", *mounts, args.supervisor_image, "-B",
                 str(args.reviewed / "host/cutover-external-storage.py"),
                 "--supervise", "--jobs-drained", *forwarded)
    api.require(re.fullmatch(api.DIGEST, oid), "Malformed supervisor container ID")
    docker("start", oid)
    print("PANOLAB_CUTOVER_SUPERVISOR=" + oid, flush=True)
    return 0


def verify_supervisor(transaction):
    args = transaction.args
    raw = transaction.docker("inspect", "--format",
                             '{{json .Id}}\n{{json .Image}}\n{{json .Mounts}}\n'
                             '{{json .HostConfig}}\n{{json .Config.User}}\n'
                             '{{json (index .Config.Labels "panolab.supervisor")}}',
                             supervisor_name(args))
    identity, image, mounts, host, user, label = map(json.loads, raw.splitlines())
    paths = [args.checkout, args.reviewed, args.journal, args.config, args.data, args.socket]
    expected = {str(path): (str(path), path != args.reviewed, "bind") for path in paths}
    actual = {m["Destination"]: (m["Source"], m["RW"], m["Type"]) for m in mounts}
    if (image != args.supervisor_image or actual != expected or host["NetworkMode"] != "none"
            or not host["ReadonlyRootfs"] or host["Privileged"] or user != "0:0"
            or os.getuid() != 0 or os.getgid() != 0 or label != args.transaction
            or host["CapDrop"] != ["ALL"] or host.get("CapAdd")
            or "no-new-privileges:true" not in host.get("SecurityOpt", [])):
        raise ValueError("Supervisor does not match its isolated launch contract")
    # Docker sets HOSTNAME from the container ID by default.
    if os.environ.get("HOSTNAME") != identity[:12]:
        raise ValueError("Supervisor identity does not match the executing container")
    return identity


def supervise(api, args):
    import fcntl

    validate_paths(api, args)
    for path in (args.config, args.data, args.journal):
        check_path(path, 0o700, True)
    api.require(api.SOURCE == args.reviewed and args.socket.is_socket(),
                "Reviewed code or rootless socket unavailable inside supervisor")
    records = api.inventory(args.inventory, args.inventory_sha256,
                            (args.checkout, args.reviewed, args.config, args.data))
    api.require(args.supervisor_image == records[api.MAINTENANCE]["image_id"],
                "Supervisor image differs from the authorized maintenance image")
    migration = load_script(api.SOURCE, "migrate-external-storage")
    worker = load_script(api.SOURCE, "ise14-bringup")
    transaction = Cutover(api, args, records, migration, worker)
    supervisor = verify_supervisor(transaction)
    api.require('"name=rootless"' in transaction.docker("info", "--format",
                                                        "{{json .SecurityOptions}}"),
                "Expected owner rootless Engine")
    os.environ.update(transaction.env)
    # The journal has its own exact bind. A supervisor restart always chooses
    # recovery for an interrupted transaction, even without a tunnel.
    fd = os.open(args.journal / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if lexists(transaction.journal):
            check_path(transaction.journal, 0o600)
            transaction.state = json.loads(transaction.journal.read_text())
            api.require(transaction.state["identity"] == transaction.identity, "Journal identity differs")
            phase = transaction.state["phase"]
            if (phase == "completed" and not args.rollback) or phase == "rolled-back":
                transaction.docker("update", "--restart=no", supervisor)
                print("PANOLAB_CUTOVER=" + phase, flush=True)
                return 0 if phase == "completed" else 9
            transaction.state["supervisor"] = supervisor
            recover = True
        else:
            api.require(not args.rollback, "Recovery journal unavailable")
            transaction.docker("update", "--restart=no", supervisor)
            transaction.admit(supervisor)
            transaction.save("admitted", identity=transaction.identity, supervisor=supervisor)
            transaction.docker("update", "--restart=unless-stopped", supervisor)
            recover = False

        errors = (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError)
        try:
            if recover:
                transaction.rollback()
            else:
                try:
                    transaction.apply()
                except errors as error:
                    transaction.save(transaction.state["phase"], apply_error=type(error).__name__)
                    transaction.rollback()
        except errors as error:
            transaction.save(transaction.state["phase"], recovery_error=type(error).__name__)
            transaction.docker("update", "--restart=no", supervisor)
            print("PANOLAB_CUTOVER=blocked phase=" + transaction.state["phase"] +
                  " error=" + type(error).__name__, flush=True)
            return 9
        transaction.docker("update", "--restart=no", supervisor)
        phase = transaction.state["phase"]
        print("PANOLAB_CUTOVER=" + phase, flush=True)
        return 0 if phase == "completed" else 9
