"""Private, scoped setup record. Never retries a mutation or creates paid Apigee."""
import argparse
import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from credentials import Credentials
from gcloud_command import command as build_command

os.umask(0o077)
ROOT = Path(os.environ["MCP_REPEAT_SCRATCH"]).resolve()
if ROOT.parent != Path("/tmp") or not ROOT.name.startswith("gcp-mcp-retry."):
    raise RuntimeError("Use a fresh repeat scratch directory")
PROJECT = "your-gcp-project"
AUTH = json.loads((ROOT / "authorisation.json").read_text())
CREDENTIALS = Credentials(AUTH["account"])


def record(name, value):
    with (ROOT / name).open("a") as handle:
        handle.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(), **value}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def cli(args, check=True):
    command = build_command(args, AUTH["account"])
    record("setup.jsonl", {"kind": "reserved", "command": command})
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    record("setup.jsonl", {"kind": "result", "command": command, "code": result.returncode,
                            "stdout": result.stdout, "stderr": result.stderr})
    if check and result.returncode:
        print(result.stderr[-3500:])
        raise RuntimeError("Scoped gcloud command failed, no retry: " + " ".join(args[:3]))
    if args[:2] in (["compute", "ssh"], ["compute", "scp"]):
        return result.stdout
    return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None


def api(method, url, body=None):
    if not url.startswith(("https://apigee.googleapis.com/v1/", "https://cloudbilling.googleapis.com/v1/",
                           "https://compute.googleapis.com/compute/v1/projects/your-gcp-project/")):
        raise RuntimeError("Out-of-scope API endpoint")
    token = CREDENTIALS.token()
    record("setup.jsonl", {"kind": "api_reserved", "method": method, "url": url, "body": body})
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method,
                                 headers={"Authorization": "Bearer "+token, "Content-Type": "application/json", "x-goog-user-project": PROJECT})
    try:
        response = urllib.request.urlopen(req, timeout=90)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        value = json.load(response)
        record("setup.jsonl", {"kind": "api_response", "method": method, "url": url, "status": response.status, "payload": value})
        return response.status, value


def prices():
    token = ""
    matches = []
    for page in range(30):
        query = urllib.parse.urlencode({"currencyCode": "GBP", "pageSize": 5000, "pageToken": token})
        status, value = api("GET", "https://cloudbilling.googleapis.com/v1/services/6F81-5844-456A/skus?"+query)
        if status != 200:
            raise RuntimeError("Pricing lookup failed")
        for sku in value.get("skus", []):
            desc = sku.get("description", "").lower()
            if sku.get("category", {}).get("usageType") == "OnDemand" and "europe-west2" in sku.get("serviceRegions", []) and any(x in desc for x in ("e2", "storage pd capacity", "external ip", "ip address")):
                matches.append(sku)
        token = value.get("nextPageToken", "")
        if not token:
            break
    else:
        raise RuntimeError("Pricing pagination incomplete")
    (ROOT / "gbp_prices.json").write_text(json.dumps(matches, indent=2)+"\n")
    for sku in matches:
        if "Custom" not in sku["description"]:
            print(json.dumps({"description": sku["description"], "pricing": sku["pricingInfo"]}))


def allocate():
    from freeze_repeat import check_freeze
    check_freeze()
    now = datetime.now(timezone.utc)
    expiry = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if (expiry-now).total_seconds() < 28800:
        raise RuntimeError("Launch cutoff passed")
    if not (ROOT / "gbp_prices.json").exists() or not (ROOT / "cost_gate.json").exists():
        raise RuntimeError("Price and cost gate missing")
    cost = json.loads((ROOT / "cost_gate.json").read_text())
    projected = cost["fixed_cost_bound_gbp"] + 12*cost["hourly_cost_bound_gbp"]
    if (not all(math.isfinite(cost[k]) and cost[k] >= 0 for k in
                ("prior_total_cost_bound_gbp", "fixed_cost_bound_gbp", "hourly_cost_bound_gbp"))
            or cost["hourly_cost_bound_gbp"] == 0):
        raise RuntimeError("Invalid cost estimate")
    if projected >= 5 or cost["prior_total_cost_bound_gbp"] + projected >= 20:
        raise RuntimeError("Cost gate failed")
    # Check the concrete service environment before any cloud request.
    if not os.path.isabs(shutil.which("gcloud") or ""):
        raise RuntimeError("gcloud is absent from the supervisor environment")
    from contract_check import verify_contract
    record("supervisor.jsonl", {"kind": "input_contract_verified",
        **verify_contract(AUTH["execution_id"], now.date().isoformat())})
    with (ROOT / "allocation.started").open("x") as handle:
        handle.write(now.isoformat())
    manifest = {"project": PROJECT, "provision_start_epoch": now.timestamp(), "expiry_epoch": expiry.timestamp(),
                "window_date": now.date().isoformat(), "vm_delete_epoch": now.timestamp()+28800, **cost}
    (ROOT / "resources.json").write_text(json.dumps(manifest, indent=2)+"\n")
    if cli(["compute", "instances", "list"]):
        raise RuntimeError("Unexpected VM inventory")
    networks = cli(["compute", "networks", "list"])
    if any(n["name"] != "default" for n in networks):
        raise RuntimeError("Unexpected network inventory")
    if cli(["compute", "addresses", "list"]):
        raise RuntimeError("Unexpected address inventory")
    status, org = api("GET", "https://apigee.googleapis.com/v1/organizations/your-gcp-project")
    if status == 200 or not AUTH.get("prior_deletion_reconfirmed"):
        raise RuntimeError("Prior organisation absence not established")
    if status not in (403, 404):
        raise RuntimeError("Unresolved organisation inventory")
    with (ROOT / "resources_owned.json").open("x") as handle:
        json.dump({"project": PROJECT, "network": "mcp-lab-vpc", "vm": "mcp-lab-client",
                   "execution_id": AUTH["execution_id"], "initial_inventory_empty": True}, handle)
    cli(["compute", "networks", "create", "mcp-lab-vpc", "--subnet-mode=custom", "--bgp-routing-mode=global"])
    cli(["compute", "networks", "subnets", "create", "mcp-lab-subnet", "--network=mcp-lab-vpc", "--region=europe-west2", "--range=10.77.0.0/24"])
    cli(["compute", "addresses", "create", "mcp-lab-peering", "--global", "--purpose=VPC_PEERING", "--prefix-length=22", "--addresses=10.78.0.0", "--network=mcp-lab-vpc"])
    cli(["compute", "addresses", "create", "google-managed-services-support-1", "--global", "--purpose=VPC_PEERING", "--prefix-length=28", "--addresses=10.79.0.0", "--network=mcp-lab-vpc"])
    cli(["services", "vpc-peerings", "connect", "--service=servicenetworking.googleapis.com", "--network=mcp-lab-vpc", "--ranges=mcp-lab-peering,google-managed-services-support-1"])
    # One explicit evaluation-only call. The endpoint provisions trial orgs.
    with (ROOT / "evaluation_request.started").open("x") as handle:
        handle.write(now.isoformat())
    status, value = api("POST", "https://apigee.googleapis.com/v1/projects/your-gcp-project:provisionOrganization",
                        {"authorizedNetwork": "projects/your-gcp-project/global/networks/mcp-lab-vpc", "analyticsRegion": "europe-west2", "runtimeLocation": "europe-west2"})
    (ROOT / "allocation.json").write_text(json.dumps({"status": status, "payload": value}, indent=2)+"\n")
    print(json.dumps({"status": status, "operation": value.get("name"), "error": value.get("error"), "start_utc": now.isoformat()}))
    if status >= 400:
        raise RuntimeError("Free allocation refused. Stop and clean up, no retry or paid fallback")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prices", "allocate"])
    args = parser.parse_args()
    {"prices": prices, "allocate": allocate}[args.action]()
