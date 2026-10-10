"""Scoped fresh setup. Called only by the frozen one-shot supervisor."""
import base64
import hashlib
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone

from repeat_runner import ROOT as SOURCE, ORIGINAL
from resources import ROOT, AUTH, api, cli
from bundles import bundle, VARIANTS

BASE = "https://apigee.googleapis.com/v1/organizations/your-gcp-project"


def deadline():
    return json.loads((ROOT / "resources.json").read_text())["provision_start_epoch"] + 2 * 3600


def wait_runtime():
    allocation = json.loads((ROOT / "allocation.json").read_text())
    operation = allocation["payload"].get("name")
    if not operation or not operation.startswith("organizations/your-gcp-project/operations/"):
        raise RuntimeError("No recognised provisioning operation")
    while time.time() < deadline():
        status, value = api("GET", "https://apigee.googleapis.com/v1/" + operation)
        if status != 200:
            raise RuntimeError("Provisioning observation failed")
        if value.get("done"):
            if value.get("error"):
                raise RuntimeError("Provisioning failed")
            break
        time.sleep(15)
    else:
        raise RuntimeError("Provisioning time gate")
    status, org = api("GET", BASE)
    if status != 200 or org.get("billingType") != "EVALUATION" or org.get("subscriptionType") != "TRIAL":
        raise RuntimeError("Evaluation billing check failed")
    while time.time() < deadline():
        status, instances = api("GET", BASE + "/instances")
        values = instances.get("instances", [])
        if status != 200 or len(values) > 1:
            raise RuntimeError("Unexpected runtime inventory")
        if values:
            instance = values[0]
            if instance.get("location") != "europe-west2":
                raise RuntimeError("Runtime outside approved region")
            if instance.get("state") == "ACTIVE":
                return org, instance
            if instance.get("state") in ("DELETING", "ERROR"):
                raise RuntimeError("Runtime failed readiness")
        time.sleep(15)
    raise RuntimeError("Runtime readiness time gate")


def common():
    return ["--zone=europe-west2-a", "--tunnel-through-iap", "--ssh-key-file=" + str(ROOT / "ssh_key")]


def create_vm():
    resources = json.loads((ROOT / "resources.json").read_text())
    end = datetime.fromtimestamp(resources["vm_delete_epoch"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name, port, source in [("mcp-lab-allow-iap", 22, "35.235.240.0/20"),
                               ("mcp-lab-allow-backend", 8080, "10.78.0.0/22")]:
        cli(["compute", "firewall-rules", "create", name, "--network=mcp-lab-vpc",
             f"--allow=tcp:{port}", "--source-ranges=" + source, "--target-tags=mcp-lab-client"])
    cli(["compute", "instances", "create", "mcp-lab-client", "--zone=europe-west2-a",
         "--machine-type=e2-small", "--subnet=mcp-lab-subnet", "--private-network-ip=10.77.0.10",
         "--tags=mcp-lab-client", "--no-service-account", "--no-scopes",
         "--image-family=debian-12", "--image-project=debian-cloud", "--boot-disk-size=10GB",
         "--boot-disk-type=pd-standard", "--boot-disk-auto-delete",
         "--termination-time=" + end, "--instance-termination-action=DELETE"])
    # Read-only SSH readiness checks may be repeated. The server is launched once.
    ready = False
    for _ in range(20):
        result = cli(["compute", "ssh", "mcp-lab-client", *common(), "--command=true"], check=False)
        # cli returns stdout for SSH even on failure. Inspect its durable exit record.
        row = json.loads((ROOT / "setup.jsonl").read_text().splitlines()[-1])
        if row["code"] == 0:
            ready = True
            break
        if time.time() >= deadline():
            break
        time.sleep(15)
    if not ready:
        raise RuntimeError("SSH readiness not established")
    cli(["compute", "ssh", "mcp-lab-client", *common(), "--command=install -d -m 700 /tmp/mcp-study"])
    server = ORIGINAL.parent / "gcp_mcp_smoke/server.py"
    client = SOURCE / "remote_call.py"
    cli(["compute", "scp", str(server), str(client), "mcp-lab-client:/tmp/mcp-study/", *common()])
    launch = ("import subprocess; from pathlib import Path; "
              "p=Path('/tmp/mcp-study'); "
              "(p/'backend.jsonl').touch(exist_ok=False); "
              "f=(p/'server.log').open('xb'); "
              "subprocess.Popen(['python3','server.py'],cwd=p,stdin=subprocess.DEVNULL,"
              "stdout=f,stderr=subprocess.STDOUT,start_new_session=True)")
    cli(["compute", "ssh", "mcp-lab-client", *common(),
         "--command=" + shlex.join(["python3", "-c", launch])])
    checked = cli(["compute", "ssh", "mcp-lab-client", *common(),
        "--command=cd /tmp/mcp-study && sha256sum server.py remote_call.py && pgrep -af '^python3 server.py$'"])
    for path in (server, client):
        if hashlib.sha256(path.read_bytes()).hexdigest() not in checked:
            raise RuntimeError("Remote source mismatch")
    (ROOT / "remote_source_check.txt").write_text(checked)


def configure_access(org, instance):
    status, groups = api("GET", BASE + "/envgroups")
    if status != 200 or len(groups.get("environmentGroups", [])) != 1:
        raise RuntimeError("Unexpected environment groups")
    hostname = groups["environmentGroups"][0]["hostnames"][0]
    resources = json.loads((ROOT / "resources.json").read_text())
    from repeat_runner import Management, Journal
    from resources import CREDENTIALS
    journal = Journal(ROOT / "bootstrap_import.jsonl")
    try:
        manager = Management(journal, CREDENTIALS)
        proxies = manager.request("GET", "organizations/your-gcp-project/apis")
        if any(p["name"] != "hello-world" for p in proxies.get("proxies", [])):
            raise RuntimeError("Unexpected proxy inventory")
        imported = manager.request("POST", "organizations/your-gcp-project/apis?action=import&name=mcp-lab-refund",
            bundle("baseline", resources["window_date"]), "application/octet-stream")
        (ROOT / "bootstrap_revision.json").write_text(json.dumps({"revision": imported["revision"], "deployed": False}))
    finally:
        journal.close()
    for path, body in [
        ("apiproducts", {"name": "mcp-lab-product", "displayName": "Synthetic MCP continuation study",
            "approvalType": "auto", "apiResources": ["/**"], "proxies": ["mcp-lab-refund"], "environments": ["eval"]}),
        ("developers", {"email": "smoke@example.invalid", "firstName": "Synthetic", "lastName": "Study", "userName": "mcp-lab-client"}),
        ("developers/smoke%40example.invalid/apps", {"name": "mcp-lab-client", "apiProducts": ["mcp-lab-product"]}),
    ]:
        status, value = api("POST", BASE + "/" + path, body)
        if status >= 400:
            raise RuntimeError("Access setup rejected")
        if path.endswith("/apps"):
            (ROOT / "api.key").write_text(value["credentials"][0]["consumerKey"] + "\n")
    encoded = org.get("caCertificates") or [org["caCertificate"]]
    if isinstance(encoded, str):
        encoded = [encoded]
    certificates = b"\n".join(base64.b64decode(item) for item in encoded)
    if b"BEGIN CERTIFICATE" not in certificates:
        raise RuntimeError("Invalid evaluation certificate")
    (ROOT / "ca.pem").write_bytes(certificates)
    remote = {"url": "https://example.your-gcp-project.apigee.internal/mcp-smoke/mcp", "host": hostname,
        "connect_ip": instance["host"], "expiry": resources["expiry_epoch"], "deadline": resources["vm_delete_epoch"]}
    (ROOT / "remote_config.json").write_text(json.dumps(remote))
    cli(["compute", "scp", str(ROOT / "api.key"), str(ROOT / "ca.pem"), str(ROOT / "remote_config.json"),
         "mcp-lab-client:/tmp/mcp-study/", *common()])
    from integration import install_and_check
    repair_hashes = install_and_check(cli, common())
    return {"repair_hashes": repair_hashes, "billing_type": org["billingType"], "subscription_type": org["subscriptionType"],
            "runtime_version": instance.get("runtimeVersion"),
            "bundle_sha256": {v: hashlib.sha256(bundle(v, resources["window_date"])).hexdigest() for v in VARIANTS}}
