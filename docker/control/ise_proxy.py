#!/usr/bin/env python3
"""Scoped ISE worker MCP calls and a read-only diagnostic through the broker.

No host shell, caller-supplied host paths, vendor license disclosure, Docker
network mutation or arbitrary Docker action. The worker bearer is read only
inside its own container. The worker's vendor-license Ethernet identity is
provided by a pre-existing, verified Docker-internal network.
"""
import base64
from decimal import Decimal
import hashlib
import json
import re
import time

WORKER="panolab-direct-ise14-worker-1"
LICENSE_NETWORK="panolab-direct-ise14-license-internal"
TOOLS={"toolchain_info", "build_start", "build_status", "build_result", "build_cancel", "diagnose"}
NAME=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
JOB=re.compile(r"^[0-9]{10,25}$")
ARTIFACTS={"xst.log","ngdbuild.log","map.log","par.log","trce.log","bitgen.log","design.bit","design.twr"}
TIMING_ARTIFACT = "design.twr"
CHUNK_BYTES = 8192
MAX_REPORT = 1024 * 1024
MAX_EVIDENCE = 24000
MAX_RPC_OUTPUT = 24000
REQUEST_SECONDS = 110
STATES = {"running", "succeeded", "failed", "cancelled", "interrupted"}
DIGEST = re.compile(r"[a-f0-9]{64}")
LOG_MARKERS = (
    ("error:", "ERROR"), ("warning:", "WARNING"), ("license", "LICENSE_MENTION"),
    ("permission denied", "FILE_PERMISSION"), ("not found", "FILE_NOT_FOUND"),
    ("constraint", "CONSTRAINT"), ("timing", "TIMING"),
    ("placed", "PLACEMENT"), ("route", "ROUTING"),
)
# Python 2.6-compatible: the worker container uses the CentOS 6 runtime.
# Never print bearer, worker environment, raw user input, or raw errors.
RPC_CLIENT=r'''
import json,sys,urllib2
try:
 name=sys.argv[1]
 arguments=json.loads(sys.argv[2])
 token=open("/run/secrets/ise-worker-token","rb").read().strip()
 if not token.startswith(b"Bearer "): token=b"Bearer "+token
 if not isinstance(token,str): token=token.decode("ascii")
 payload=json.dumps({"jsonrpc":"2.0","id":1,"method":"tools/call",
                     "params":{"name":name,"arguments":arguments}})
 req=urllib2.Request("http://127.0.0.1:8765/mcp",data=payload,
    headers={"Authorization":token,"Content-Type":"application/json",
             "Accept":"application/json, text/event-stream",
             "MCP-Protocol-Version":"2025-06-18"})
 raw=urllib2.urlopen(req,timeout=20).read(524289)
 if len(raw)>524288:
  print(json.dumps({"ok":False,"category":"ISE_RPC_RESPONSE_TOO_LARGE"}));sys.exit(4)
 res=json.loads(raw)
 if not isinstance(res,dict) or res.get("jsonrpc")!="2.0" or type(res.get("id"))!=int or res["id"]!=1:
  print(json.dumps({"ok":False,"category":"MALFORMED_RESPONSE"}));sys.exit(4)
 if res.get("error") or res.get("result",{}).get("isError"):
  details=[]
  error=res.get("error",{})
  if isinstance(error,dict): details.append(str(error.get("message","")))
  result=res.get("result",{})
  if isinstance(result,dict):
   for item in result.get("content",[]):
    if isinstance(item,dict) and item.get("type")=="text":
     details.append(str(item.get("text","")))
  msg=" ".join(details).lower()
  categories=(("permission denied","FILE_PERMISSION"),("operation not permitted","CAPABILITY_DENIED"),
   ("read-only file system","READ_ONLY_PATH"),("no such file or directory","MISSING_FILE"),
   ("missing project manifest","MISSING_MANIFEST"),("project path must be a real directory","PROJECT_DIR"),
   ("invalid project","INVALID_PROJECT"),("invalid top, part or source count","INVALID_MANIFEST"),
   ("invalid verilog source filename","INVALID_SOURCE"),("project file must be regular","INVALID_SOURCE"),
   ("worker busy","BUSY"),("unsupported build profile","BAD_PROFILE"),
   ("license unavailable","LICENSE_UNAVAILABLE"),("license path unset","LICENSE_UNAVAILABLE"),
   ("failed to persist job","PERSIST_FAILED"),("invalid arguments","BAD_ARGS"),
   ("unmarshal","BAD_ARGS"),("unknown tool","UNSUPPORTED_TOOL"),
   ("mkdir","MKDIR_FAILED"),("open ","FILE_OPEN_FAILED"))
  category="WORKER_REJECTED"
  for marker,code in categories:
   if marker in msg: category=code;break
  print(json.dumps({"ok":False,"category":category}))
  sys.exit(4)
 result=res.get("result",{})
 data=result.get("structuredContent")
 if data is None:
  text=result.get("content",[])
  if len(text)!=1 or text[0].get("type")!="text":
   print(json.dumps({"ok":False,"category":"MALFORMED_RESPONSE"}));sys.exit(4)
  data=json.loads(text[0]["text"])
 if not isinstance(data,dict):
  print(json.dumps({"ok":False,"category":"MALFORMED_RESPONSE"}));sys.exit(4)
 if name=="build_result":
  tail=data.pop("log_tail","")
  if not isinstance(tail,basestring):
   print(json.dumps({"ok":False,"category":"MALFORMED_RESPONSE"}));sys.exit(4)
  lower=tail.lower()
  data["log_categories"]=[category for word,category in ''' + repr(LOG_MARKERS) + r''' if word in lower]
 output=json.dumps({"ok":True,"data":data},sort_keys=True)
 if len(output)>=24000:
  print(json.dumps({"ok":False,"category":"ISE_RPC_RESPONSE_TOO_LARGE"}));sys.exit(4)
 print(output)
except urllib2.HTTPError as e:
 print(json.dumps({"ok":False,"category":"HTTP_"+str(e.code)}))
 sys.exit(4)
except Exception as e:
 print(json.dumps({"ok":False,"category":type(e).__name__.upper()}))
 sys.exit(4)
'''

# Read-only health signals for troubleshooting a rejected build_start. No
# license contents, tokens, path strings or vendor logs are returned.
WORKER_PROBE=r'''
import os,json,stat
def regular(p):
 try: return stat.S_ISREG(os.stat(p).st_mode)
 except OSError: return False
def directory(p):
 try: return stat.S_ISDIR(os.stat(p).st_mode)
 except OSError: return False
fields={
 "project_directory":directory("/projects/panolab_ise_smoke"),
 "project_manifest_readable":os.access("/projects/panolab_ise_smoke/build.json",os.R_OK) and regular("/projects/panolab_ise_smoke/build.json"),
 "project_verilog_readable":os.access("/projects/panolab_ise_smoke/design.v",os.R_OK) and regular("/projects/panolab_ise_smoke/design.v"),
 "project_constraints_readable":os.access("/projects/panolab_ise_smoke/design.ucf",os.R_OK) and regular("/projects/panolab_ise_smoke/design.ucf"),
 "results_directory":directory("/results/jobs"),
 "results_writable":os.access("/results/jobs",os.W_OK),
 "ise_settings_readable":os.access("/opt/Xilinx/14.7/ISE_DS/settings64.sh",os.R_OK),
 "license_file_readable":os.access("/licenses/Xilinx.lic",os.R_OK)
}
print(json.dumps(fields,sort_keys=True))
'''

def fail(category):
    return {"ok":False,"error":str(category)[:80]}

def validate_tool(request):
    name=request.get("tool")
    if name not in TOOLS:
        raise ValueError("ISE_TOOL_OUTSIDE_ALLOWLIST")
    args=request.get("arguments",{})
    if not isinstance(args,dict):
        raise ValueError("INVALID_ARGUMENT_SHAPE")
    if name in ("toolchain_info","diagnose"):
        if args:
            raise ValueError("UNEXPECTED_INFO_ARGS")
        return name,{}
    if name=="build_start":
        profile=args.get("Profile",args.get("profile"))
        project=args.get("Project",args.get("project"))
        if set(args)-{"Profile","Project","profile","project"} or profile!="ise14-implementation" or not isinstance(project,str) or not NAME.fullmatch(project):
            raise ValueError("INVALID_BUILD_REQUEST")
        return name,{"profile":profile,"project":project}
    jobid=args.get("ID",args.get("job_id"))
    if not isinstance(jobid,str) or not JOB.fullmatch(jobid):
        raise ValueError("INVALID_JOB_ID")
    if name in ("build_status","build_cancel"):
        if set(args)-{"ID","job_id"}:
            raise ValueError("UNEXPECTED_JOB_ARGS")
        return name,{"job_id":jobid}
    if name=="build_result":
        if set(args)-{"ID","job_id","Artifact","artifact"}:
            raise ValueError("UNEXPECTED_RESULT_ARGS")
        if {"ID","job_id"} <= args.keys() or {"Artifact","artifact"} <= args.keys():
            raise ValueError("UNEXPECTED_RESULT_ARGS")
        artifact=args.get("Artifact",args.get("artifact",""))
        if artifact not in ("", TIMING_ARTIFACT):
            raise ValueError("INVALID_RESULT_ARGUMENTS")
        return name,{"job_id":jobid,"artifact":artifact}
    raise ValueError("UNKNOWN_TOOL")

def validate_worker(command):
    show=command(["docker","inspect","--format",
                  '{{.Name}}|{{.State.Running}}|{{index .Config.Labels "panolab.managed"}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.Privileged}}|{{.HostConfig.ReadonlyRootfs}}|{{.Config.User}}',WORKER],15)
    if not show.get("ok"):
        raise ValueError("ISE_WORKER_UNAVAILABLE")
    fields=show.get("stdout","").strip().split("|")
    if (len(fields)!=7 or fields[0]!="/"+WORKER or
            fields[1:3]!=["true","true"] or
            fields[4:]!=["false","true","0:0"] or
            fields[3] not in ("none",LICENSE_NETWORK)):
        raise ValueError("ISE_WORKER_SECURITY_CONTRACT_FAILED")
    if fields[3]==LICENSE_NETWORK:
        # The licensed vendor tool requires an Ethernet hostid; use a
        # named Docker-INTERNAL network, never host/LAN/Internet access.
        net=command(["docker","network","inspect","--format",
                     '{{.Internal}}|{{index .Labels "panolab.managed"}}',
                     LICENSE_NETWORK],15)
        if not net.get("ok") or net.get("stdout","").strip()!="true|true":
            raise ValueError("ISE_LICENSE_NETWORK_NOT_INTERNAL")
        attached=command(["docker","inspect","--format",
                          "{{json .NetworkSettings.Networks}}",WORKER],15)
        if not attached.get("ok"):
            raise ValueError("ISE_WORKER_NETWORK_INSPECT_FAILED")
        try:
            active=json.loads(attached["stdout"])
        except (ValueError,TypeError):
            raise ValueError("ISE_WORKER_NETWORK_INSPECT_INVALID")
        nic=active.get(LICENSE_NETWORK) if isinstance(active,dict) else None
        if (not isinstance(active,dict) or set(active)!={LICENSE_NETWORK} or
                not isinstance(nic,dict) or
                not isinstance(nic.get("MacAddress"),str) or
                len(nic["MacAddress"].split(":"))!=6):
            raise ValueError("ISE_WORKER_NETWORK_IDENTITY_FAILED")
    mounts=command(["docker","inspect","--format","{{json .Mounts}}",WORKER],15)
    if not mounts.get("ok"):
        raise ValueError("ISE_WORKER_MOUNTS_UNAVAILABLE")
    try:
        allmounts=json.loads(mounts["stdout"])
    except (ValueError,TypeError,KeyError):
        raise ValueError("ISE_WORKER_MOUNTS_INVALID")
    binds={m.get("Destination"):(m.get("RW"),m.get("Type"))
           for m in allmounts if m.get("Type")=="bind"}
    needed={"/opt/Xilinx":(False,"bind"),"/licenses/Xilinx.lic":(False,"bind"),
            "/projects":(False,"bind"),"/results":(True,"bind"),
            "/run/secrets/ise-worker-token":(False,"bind")}
    extras={(m.get("Type"),m.get("Destination")) for m in allmounts
            if m.get("Type")!="bind"}
    if binds!=needed or not extras<={("tmpfs","/tmp"),("tmpfs","/home/ise")}:
        raise ValueError("ISE_WORKER_MOUNT_POLICY_FAILED")
    security=command(["docker","inspect","--format",
                      "{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}",WORKER],15)
    if not security.get("ok"):
        raise ValueError("ISE_WORKER_SECURITY_OPTIONS_MISSING")
    try:
        cap,options=security["stdout"].strip().split("|",1)
        cap=json.loads(cap)
        options=json.loads(options)
    except (ValueError,TypeError,KeyError):
        raise ValueError("ISE_WORKER_SECURITY_OPTIONS_INVALID")
    if (not isinstance(cap,list) or
            "all" not in [str(x).lower() for x in cap] or
            not isinstance(options,list) or
            not any(x in ("no-new-privileges:true","no-new-privileges") for x in options)):
        raise ValueError("ISE_WORKER_SECURITY_OPTIONS_FAILED")

def filtered_result(name,data):
    if not isinstance(data,dict):
        return fail("INVALID_WORKER_RESULT")
    if name=="toolchain_info":
        proof = data.get("license_validation_job_id")
        validated = (data.get("license_available") is True and
                     data.get("license_validated") is True and
                     data.get("license_validation_status") == "validated" and
                     isinstance(proof, str) and JOB.fullmatch(proof) is not None)
        available = data.get("license_available") is True
        return {"ok":True,"tool":name,"vendor":str(data.get("vendor",""))[:40],
                "version":str(data.get("toolchain_version",""))[:80],
                "ise_available":data.get("ise_available") is True,
                "license_available":data.get("license_available") is True,
                "license_validated":validated,
                "license_validation_status":("validated" if validated else
                                             "not_yet_validated" if available else "unavailable"),
                **({"license_validation_job_id":proof} if validated else {}),
                "programming_supported":data.get("programming_supported") is True}
    if name=="build_start":
        job=data.get("job_id","")
        if not isinstance(job,str) or not JOB.fullmatch(job):
            return fail("INVALID_NEW_JOB_ID")
        return {"ok":True,"tool":name,"job_id":job,"state":str(data.get("state",""))[:24]}
    if name in ("build_status","build_cancel"):
        return {"ok":True,"tool":name,"job_id":str(data.get("job_id",""))[:32],
                "state":str(data.get("state",""))[:24],"exit_code":data.get("exit_code",-1)}
    # Return only bounded metadata; never return raw vendor logs or bitstream content.
    if not valid_job_result(data):
        return fail("ISE_RESULT_INVALID")
    artifacts = []
    seen = set()
    supplied = data.get("artifacts")
    if not isinstance(supplied, list) or len(supplied) > len(ARTIFACTS):
        return fail("ISE_RESULT_INVALID")
    for artifact in supplied:
        if not isinstance(artifact, dict):
            return fail("ISE_RESULT_INVALID")
        name_value, size, digest = (artifact.get(key) for key in ("name", "bytes", "sha256"))
        if (not isinstance(name_value, str) or name_value not in ARTIFACTS or
                name_value in seen or type(size) != int or size < 0 or
                not isinstance(digest, str) or not DIGEST.fullmatch(digest)):
            return fail("ISE_RESULT_INVALID")
        seen.add(name_value)
        artifacts.append({"name": name_value, "bytes": size, "sha256": digest})
    categories = data.get("log_categories")
    if categories is None:
        # Allow metadata from an older worker response during rolling updates.
        tail = str(data.get("log_tail", "")).lower()
        categories = [category for word, category in LOG_MARKERS if word in tail]
    if not isinstance(categories, list):
        return fail("ISE_RESULT_INVALID")
    return {"ok":True,"tool":name,"job_id":data["job_id"],"state":data["state"],
            "exit_code":data["exit_code"],"artifacts":artifacts,
            "logs_truncated":bool(data.get("logs_truncated",False)),
            "log_categories":[category for _, category in LOG_MARKERS if category in categories]}


def valid_job_result(data):
    return (isinstance(data.get("job_id"), str) and JOB.fullmatch(data["job_id"]) and
            isinstance(data.get("state"), str) and data["state"] in STATES and
            type(data.get("exit_code")) == int and -1 <= data["exit_code"] < 2**31 and
            (data["state"] != "succeeded" or data["exit_code"] == 0))


def timing_result(metadata, identity, command, deadline):
    if (not isinstance(identity.get("project"), str) or not NAME.fullmatch(identity["project"]) or
            identity.get("profile") != "ise14-implementation"):
        return fail("ISE_RESULT_INVALID")
    if metadata["state"] == "running":
        return fail("ISE_TIMING_JOB_NOT_COMPLETE")
    artifact = next((item for item in metadata["artifacts"]
                     if item["name"] == TIMING_ARTIFACT), None)
    if artifact is None:
        return fail("ISE_TIMING_ARTIFACT_MISSING")
    size = artifact["bytes"]
    if not 0 < size <= MAX_REPORT:
        return fail("ISE_TIMING_ARTIFACT_SIZE_INVALID")
    content = bytearray()
    for offset in range(0, size, CHUNK_BYTES):
        reply = worker_rpc("build_result", {"job_id": metadata["job_id"],
                           "artifact": TIMING_ARTIFACT, "offset": offset}, command, deadline)
        if not reply["ok"]:
            return reply
        page = reply["data"]
        end = min(offset + CHUNK_BYTES, size)
        # Go omits the first zero offset and false EOF. The worker does not
        # echo the name. Each correlated request pins it, and the final digest
        # binds all returned bytes to that exact named metadata entry.
        start = page.get("chunk_offset", 0)
        next_offset = page.get("next_offset")
        eof = page.get("chunk_eof", False)
        encoded = page.get("chunk_base64")
        if (not valid_job_result(page) or
                any(page.get(key) != identity.get(key)
                    for key in ("job_id", "state", "exit_code", "project", "profile")) or
                page.get("artifacts") != [] or
                type(start) != int or start != offset or
                type(next_offset) != int or next_offset != end or
                type(eof) != bool or eof != (end == size) or
                not isinstance(encoded, str) or len(encoded) != 4 * ((end - offset + 2) // 3)):
            return fail("ISE_TIMING_CHUNK_INVALID")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except ValueError:
            return fail("ISE_TIMING_CHUNK_INVALID")
        if len(decoded) != end - offset or base64.b64encode(decoded).decode("ascii") != encoded:
            return fail("ISE_TIMING_CHUNK_INVALID")
        content.extend(decoded)
    if len(content) != size or hashlib.sha256(content).hexdigest() != artifact["sha256"]:
        return fail("ISE_TIMING_ARTIFACT_INTEGRITY_FAILED")
    try:
        evidence = parse_timing_report(content)
    except ValueError:
        return fail("ISE_TIMING_REPORT_UNRECOGNIZED")
    answer = dict(metadata, timing={"artifact": artifact, "schema_version": 1, **evidence})
    if len(json.dumps(answer)) > MAX_EVIDENCE:
        return fail("ISE_TIMING_EVIDENCE_TOO_LARGE")
    return answer


# TRACE -v reports contain per-constraint details followed by an overall
# summary. Match fixed labels and bounded numeric values only. Constraint
# ordinals preserve order without disclosing clock/net names or UCF text.
COUNT = r"([0-9]{1,10})"
TIME = r"([+-]?[0-9]{1,9}(?:\.[0-9]{1,9})?)\s*(ns|ps)"
ERRORS = re.compile(
    rf"{COUNT} timing errors? detected\.?(?:\s*\(\s*{COUNT} setup errors?\s*,"
    rf"\s*{COUNT} hold errors?(?:\s*,\s*{COUNT} component switching limit errors?)?\s*\))?\.?$", re.I)
ANALYZED = re.compile(
    rf"{COUNT} paths? analyzed,\s*{COUNT} endpoints? analyzed,\s*{COUNT} failing endpoints?\.?", re.I)
CONSTRAINT = re.compile(
    r"Timing constraint:\s*(?:[^=]{1,256}=\s*)?"
    r"(PERIOD|OFFSET|FROM|MAXDELAY|TIG)\b(.*)", re.I)
CONSTRAINT_TIME = re.compile(rf"(?<![\w.]){TIME}(?=[\s;]|$)", re.I)
SLACK = re.compile(rf"Slack\s*\((setup|hold) path\)\s*:\s*{TIME}(?=\s|$)", re.I)
MAXIMUM_FREQUENCY = re.compile(
    r"\(Maximum frequency:\s*([0-9]{1,9}(?:\.[0-9]{1,9})?)\s*MHz\)", re.I)
MINIMUM_PERIOD = re.compile(rf"Minimum period(?:\s+is\s+|\s*:\s*){TIME}(?=\s|[.(\x7b]|$)", re.I)
COVERAGE = re.compile(
    rf"Constraints cover\s+{COUNT} paths?,\s+{COUNT} nets?,?\s+and\s+{COUNT} connections?\.?", re.I)
TIMING_SCORE = re.compile(rf"Timing (?:errors\s*:\s*{COUNT}\s+)?(?:score\s*:\s*){COUNT}"
                          rf"(?:\s*\(\s*Setup/Max\s*:\s*{COUNT}\s*,\s*Hold\s*:\s*{COUNT}\s*\))?", re.I)
TIMING_CONCLUSIONS = {
    "all constraints were met.": True,
    "not all constraints were met.": False,
    "timing constraints are not met.": False,
}


def ns(value, unit):
    return Decimal(value).scaleb(-3 if unit.lower() == "ps" else 0)


def record_fact(section, key, value):
    if key in section and section[key] != value:
        raise ValueError("conflicting timing facts")
    section[key] = value


def parse_timing_report(content):
    overall = {}
    constraints = []
    current = None
    in_summary = False
    saw_header = False
    saw_no_constraints = False
    preceding_conclusions = set()
    for line in content.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        conclusion = TIMING_CONCLUSIONS.get(line.lower())
        if re.match(r"Release\s+14\.7\s+Trace\b", line, re.I):
            saw_header = True
        if re.fullmatch(r"(?:Timing\s+)?Summary(?:\s+of\s+Timing\s+Analysis)?\s*[:.]*", line, re.I):
            # TRACE 14.7 can place its conclusion immediately before the timing summary.
            if re.fullmatch(r"Timing\s+summary:", line, re.I):
                for preceding_conclusion in preceding_conclusions:
                    record_fact(overall, "all_constraints_met", preceding_conclusion)
            current = None
            in_summary = True
            preceding_conclusions.clear()
            continue
        if conclusion is None:
            preceding_conclusions.clear()
        else:
            preceding_conclusions.add(conclusion)
        if line.lower().startswith("timing constraint:"):
            in_summary = False
            if len(constraints) == 64:
                raise ValueError()
            match = CONSTRAINT.fullmatch(line)
            kind = match[1].lower() if match else "other"
            if re.match(r"Timing constraint:\s*Default period analysis\b", line, re.I):
                kind = "default_period"
            current = {"index": len(constraints) + 1, "type": kind}
            constraints.append(current)
            if kind in ("period", "offset"):
                # Ignore quoted clock/group names when finding the target.
                value = CONSTRAINT_TIME.search(re.sub(r'"[^"]*"', '""', match[2]))
                if value:
                    current["requested_" + kind + "_ns"] = ns(*value.groups())
            continue
        target = current if current is not None else overall
        if (match := ERRORS.fullmatch(line)) and (current is not None or in_summary):
            for key, value in zip(("timing_errors", "setup_errors", "hold_errors",
                                   "component_switching_limit_errors"), match.groups()):
                if value is None:
                    continue
                record_fact(target, key, int(value))
        if (match := ANALYZED.fullmatch(line)) and (current is not None or in_summary):
            for key, value in zip(("paths_analyzed", "endpoints_analyzed", "failing_endpoints"), match.groups()):
                record_fact(target, key, int(value))
        if current is not None:
            if match := SLACK.match(line):
                key = "worst_reported_" + match[1].lower() + "_slack_ns"
                value = ns(*match.groups()[1:])
                current[key] = min(current.get(key, value), value)
        if (match := MINIMUM_PERIOD.match(line)) and (current is not None or in_summary):
            value = ns(*match.groups())
            previous = target.get("minimum_period_ns")
            if previous is None or value >= previous:
                if previous != value:
                    target.pop("maximum_frequency_mhz", None)
                target["minimum_period_ns"] = value
                if frequency := MAXIMUM_FREQUENCY.search(line):
                    target["maximum_frequency_mhz"] = frequency[1]
        if re.fullmatch(r"No timing constraints (?:were |are )?found\.?", line, re.I):
            saw_no_constraints = True
        if in_summary:
            if match := COVERAGE.fullmatch(line):
                for key, value in zip(("covered_paths", "covered_nets", "covered_connections"), match.groups()):
                    record_fact(overall, key, int(value))
            if match := TIMING_SCORE.fullmatch(line):
                errors, score, setup_score, hold_score = match.groups()
                if errors is not None:
                    record_fact(overall, "timing_errors", int(errors))
                record_fact(overall, "timing_score", int(score))
                if setup_score is not None:
                    record_fact(overall, "setup_score", int(setup_score))
                    record_fact(overall, "hold_score", int(hold_score))
            if conclusion is not None:
                record_fact(overall, "all_constraints_met", conclusion)
    if not saw_header or "timing_errors" not in overall or not content.endswith(b"\n"):
        raise ValueError("incomplete TRACE report")
    explicit = [c for c in constraints if c["type"] not in ("default_period", "tig")]
    if not explicit:
        state = ("unconstrained" if saw_no_constraints or constraints or
                 overall.get("covered_paths") == 0 else "unknown")
    elif (not overall.get("covered_paths") or "timing_score" not in overall or
          "all_constraints_met" not in overall or
          any(not c.get("paths_analyzed") or c.get("timing_errors") is None or
              c["type"] == "other" or
              (c["type"] in ("period", "offset") and f'requested_{c["type"]}_ns' not in c)
              for c in explicit)):
        state = "incomplete"
    else:
        state = "constrained"
    conclusion = overall.pop("all_constraints_met", None)
    if state == "constrained":
        observed_violation = any(
            c["timing_errors"] > 0 or c.get("failing_endpoints", 0) > 0 or
            any(c.get(key, 0) < 0 for key in
                ("worst_reported_setup_slack_ns", "worst_reported_hold_slack_ns"))
            for c in explicit
        )
        if conclusion != (overall["timing_errors"] == 0 and overall["timing_score"] == 0) or (
                conclusion and observed_violation):
            raise ValueError("contradictory timing conclusion")
        overall["all_constraints_met"] = conclusion
    # Missing counts are unknown. Timing scores are penalties in the report,
    # and are never used to infer a setup or hold error count.
    for key in ("setup_errors", "hold_errors", "component_switching_limit_errors"):
        overall.setdefault(key, None)
    for section in [overall, *constraints]:
        for key, value in section.items():
            if isinstance(value, Decimal):
                section[key] = format(value, "f")
    return {"constraint_status": state, "overall": overall, "constraints": constraints}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate response key")
        result[key] = value
    return result


def worker_rpc(name, args, command, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return fail("ISE_RPC_DEADLINE")
    docker = ["docker","exec","--user","0:0",WORKER,"python","-c",
              RPC_CLIENT,name,json.dumps(args,sort_keys=True)]
    run = command(docker, min(45, remaining))
    if time.monotonic() >= deadline:
        return fail("ISE_RPC_DEADLINE")
    if run.get("error") == "timeout":
        return fail("ISE_RPC_TIMEOUT")
    raw = run.get("stdout") or ""
    if len(raw) >= MAX_RPC_OUTPUT:
        return fail("ISE_RPC_RESPONSE_TOO_LARGE")
    try:
        reply = json.loads(raw, object_pairs_hook=unique_keys)
    except (ValueError, TypeError):
        return fail("ISE_RPC_UNREADABLE")
    if not isinstance(reply, dict):
        return fail("ISE_RPC_UNREADABLE")
    if reply.get("ok") is False:
        category = reply.get("category")
        if isinstance(category, str) and re.fullmatch(r"[A-Z][A-Z_0-9]{0,63}", category):
            return fail(category)
        return fail("ISE_RPC_ERROR")
    if reply.get("ok") is not True or not run.get("ok") or not isinstance(reply.get("data"), dict):
        return fail("ISE_RPC_ERROR")
    return reply


def call_worker(request,command):
    try:
        name,args=validate_tool(request)
        deadline = time.monotonic() + REQUEST_SECONDS

        def bounded_command(argv, timeout):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("ISE_RPC_DEADLINE")
            return command(argv, min(timeout, remaining))

        validate_worker(bounded_command)
        if name=="diagnose":
            check=bounded_command(["docker","exec","--user","0:0",WORKER,"python","-c",WORKER_PROBE],20)
            try:
                signals=json.loads((check.get("stdout") or "").strip())
            except (ValueError,TypeError):
                return fail("ISE_WORKER_DIAGNOSTIC_UNAVAILABLE")
            approved={"project_directory","project_manifest_readable","project_verilog_readable",
                      "project_constraints_readable","results_directory","results_writable",
                      "ise_settings_readable","license_file_readable"}
            if set(signals)!=approved or any(type(x)!=bool for x in signals.values()):
                return fail("ISE_WORKER_DIAGNOSTIC_INVALID")
            return dict({"ok":True,"tool":"diagnose"},**signals)
        timing = name == "build_result" and args.pop("artifact") == TIMING_ARTIFACT
        reply = worker_rpc(name, args, bounded_command, deadline)
        if not reply["ok"]:
            return reply
        data = reply["data"]
        result = filtered_result(name, data)
        if name == "build_result" and result["ok"]:
            if result["job_id"] != args["job_id"]:
                return fail("ISE_RESULT_JOB_MISMATCH")
            if timing:
                return timing_result(result, data, bounded_command, deadline)
        return result
    except ValueError as exc:
        return fail(str(exc))
    except Exception:
        return fail("ISE_PROXY_INTERNAL_ERROR")
