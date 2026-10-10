"""One request on the private VM, with a second persistent call budget.

Reads a JSON envelope on stdin. Credentials stay in private VM files. No retry.
This file is copied beside the unchanged smoke server.py and its backend log.
"""
import fcntl
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    envelope = json.load(sys.stdin)
    config = json.loads((root / "remote_config.json").read_text())
    request_body = envelope["request"]
    identity = request_body["id"]
    with (root / "remote_attempts.jsonl").open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        prior = [json.loads(line) for line in handle]
        if any(r["request"]["id"] == identity for r in prior):
            raise RuntimeError("Duplicate request identity")
        if time.time() >= min(config["deadline"], config["expiry"]):
            raise RuntimeError("Remote deadline")
        tools = sum(r["request"]["method"] == "tools/call" for r in prior)
        if request_body["method"] == "tools/call" and tools >= 500:
            raise RuntimeError("Remote call limit")
        handle.write(json.dumps({"reserved_at": time.time(), **envelope}) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    url = config["url"]
    original = socket.getaddrinfo
    tls_host = urllib.parse.urlparse(url).hostname
    def resolve(host, port, *args, **kwargs):
        return original(config["connect_ip"] if host == tls_host else host, port, *args, **kwargs)
    socket.getaddrinfo = resolve
    context = ssl.create_default_context(cafile=str(root / "ca.pem"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    req = urllib.request.Request(url, data=json.dumps(request_body).encode(), headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "x-api-key": (root / "api.key").read_text().strip(), "x-task-id": envelope["task"], "Host": config["host"]})
    row = {"utc_start_epoch": time.time(), "request_id": identity}
    try:
        try:
            response = opener.open(req, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            row.update(delivery="response_received", status=response.code,
                       headers={k.lower(): v for k, v in response.headers.items() if k.lower().startswith("x-smoke-") or k.lower() == "content-type"},
                       body=response.read(65536).decode())
    except Exception as exc:
        row.update(delivery="uncertain", error=type(exc).__name__)
    row["utc_end_epoch"] = time.time()
    # The synchronous backend fsyncs before it replies. Export the full log too.
    backend = [json.loads(line) for line in (root / "backend.jsonl").read_text().splitlines()]
    row["backend_matches"] = [r for r in backend if r.get("request", {}).get("id") == identity]
    with (root / "remote_responses.jsonl").open("a") as handle:
        handle.write(json.dumps(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    print(json.dumps(row))


if __name__ == "__main__":
    main()
