"""Remove only this manifest's experiment resources, preserving project/default."""
import json
import time
from operation_url import operation_poll_url
from resources import ROOT, api, cli


def remove_study_key():
    project = cli(["compute", "project-info", "describe"])
    metadata = project.get("commonInstanceMetadata", {})
    if not (ROOT / "ssh_key.pub").exists():
        return
    key = (ROOT / "ssh_key.pub").read_text().split()[1]
    changed = 0
    items = []
    for item in metadata.get("items", []):
        if item["key"] != "ssh-keys":
            items.append(item)
            continue
        lines = item["value"].splitlines()
        kept = [line for line in lines if not (len(line.split()) > 1 and line.split()[1] == key)]
        changed += len(lines)-len(kept)
        if kept:
            items.append({"key": "ssh-keys", "value": "\n".join(kept)})
    if changed:
        status, operation = api("POST", "https://compute.googleapis.com/compute/v1/projects/your-gcp-project/setCommonInstanceMetadata",
                                {"fingerprint": metadata["fingerprint"], "items": items})
        assert status == 200
        deadline = time.time()+600
        while operation.get("status") != "DONE":
            assert time.time() < deadline
            time.sleep(15)
            status, operation = api("GET", operation_poll_url(operation["selfLink"]))
            assert status == 200
        assert not operation.get("error")
    verify = cli(["compute", "project-info", "describe"])
    assert not any(key in item.get("value", "") for item in verify.get("commonInstanceMetadata", {}).get("items", []) if item["key"] == "ssh-keys")
    (ROOT / "ssh_key_removed.json").write_text(json.dumps({"removed_study_entries": changed, "verified_absent": True})+"\n")


def cleanup():
    assert json.loads((ROOT / "resources.json").read_text())["project"] == "your-gcp-project"
    if not (ROOT / "resources_owned.json").exists():
        print("No repeat resource creation was attempted. No resources removed.", flush=True)
        return
    ownership = json.loads((ROOT / "resources_owned.json").read_text())
    assert ownership["project"] == "your-gcp-project" and ownership["initial_inventory_empty"]
    instances = cli(["compute", "instances", "list"])
    targets = [r for r in instances if r["name"] == "mcp-lab-client"]
    if targets:
        assert len(targets) == 1 and targets[0]["zone"].endswith("/europe-west2-a")
        assert targets[0]["networkInterfaces"][0]["network"].endswith("/mcp-lab-vpc")
        cli(["compute", "instances", "delete", "mcp-lab-client", "--zone=europe-west2-a"])
    status, org = api("GET", "https://apigee.googleapis.com/v1/organizations/your-gcp-project")
    if status == 200:
        assert org["billingType"] == "EVALUATION" and org["subscriptionType"] == "TRIAL"
        # A durable marker prevents accidental repetition of the deletion write.
        marker = ROOT / "organisation_delete.json"
        if marker.exists():
            operation = json.loads(marker.read_text())["name"]
        else:
            status, value = api("DELETE", "https://apigee.googleapis.com/v1/organizations/your-gcp-project")
            assert status == 200 and value.get("name")
            marker.write_text(json.dumps(value, indent=2)+"\n")
            operation = value["name"]
        deadline = time.time() + 1800
        while True:
            status, value = api("GET", "https://apigee.googleapis.com/v1/"+operation)
            assert status == 200
            if value.get("done"):
                assert not value.get("error"), value.get("error")
                (ROOT / "organisation_deleted.json").write_text(json.dumps(value, indent=2)+"\n")
                break
            if time.time() >= deadline:
                raise RuntimeError("Deletion not confirmed. Keep observing, do not remove dependent network.")
            time.sleep(15)
    else:
        # Only proceed after a positively verified deletion, not an ambiguous 403.
        refused = ROOT / "allocation.json"
        refusal = json.loads(refused.read_text()) if refused.exists() else {}
        # A definitively rejected allocation creates no new organisation.
        # Otherwise require positive deletion evidence before removing its network.
        assert ((ROOT / "organisation_deleted.json").exists()
                or 400 <= refusal.get("status", 0) < 500
                or not (ROOT / "evaluation_request.started").exists()), "Organisation absence unverified"
    network = [r for r in cli(["compute", "networks", "list"]) if r["name"] == "mcp-lab-vpc"]
    if network:
        peerings = cli(["services", "vpc-peerings", "list", "--network=mcp-lab-vpc", "--service=servicenetworking.googleapis.com"])
        if peerings:
            cli(["services", "vpc-peerings", "delete", "--network=mcp-lab-vpc", "--service=servicenetworking.googleapis.com"])
        for r in cli(["compute", "addresses", "list"]):
            if r["name"] in ("mcp-lab-peering", "google-managed-services-support-1"):
                assert r["network"].endswith("/mcp-lab-vpc") and r["purpose"] == "VPC_PEERING"
                cli(["compute", "addresses", "delete", r["name"], "--global"])
        for r in cli(["compute", "firewall-rules", "list"]):
            if r["name"] in ("mcp-lab-allow-iap", "mcp-lab-allow-backend"):
                assert r["network"].endswith("/mcp-lab-vpc")
                cli(["compute", "firewall-rules", "delete", r["name"]])
        subnet = [r for r in cli(["compute", "networks", "subnets", "list"]) if r["name"] == "mcp-lab-subnet"]
        if subnet:
            assert len(subnet) == 1 and subnet[0]["network"].endswith("/mcp-lab-vpc")
            cli(["compute", "networks", "subnets", "delete", "mcp-lab-subnet", "--region=europe-west2"])
        cli(["compute", "networks", "delete", "mcp-lab-vpc"])
    inventory = {key: cli(command) for key, command in {
        "instances": ["compute", "instances", "list"], "disks": ["compute", "disks", "list"],
        "addresses": ["compute", "addresses", "list"], "networks": ["compute", "networks", "list"],
        "firewalls": ["compute", "firewall-rules", "list"], "subnets": ["compute", "networks", "subnets", "list"]}.items()}
    assert not inventory["instances"] and not inventory["disks"] and not inventory["addresses"]
    assert [r["name"] for r in inventory["networks"]] == ["default"]
    assert not any(r["name"].startswith("mcp-lab-") for key in ("firewalls", "subnets") for r in inventory[key])
    (ROOT / "teardown.json").write_text(json.dumps(inventory, indent=2)+"\n")
    remove_study_key()
    print("Verified deletion of the evaluation, VM, disk and test network. Default network and project retained.", flush=True)


if __name__ == "__main__":
    cleanup()
