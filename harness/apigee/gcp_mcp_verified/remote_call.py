"""Candidate replacement client. Not wired into an authorised live execution.

Preserve a transport result even when the backend log does not yet exist.
Missing backend evidence is explicit and is never treated as a verified refusal.
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


def persist(path, row):
    with path.open("a") as handle:
        handle.write(json.dumps(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def execute(root, envelope):
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
    original = socket.getaddrinfo
    row = {"utc_start_epoch": time.time(), "request_id": identity}
    try:
        url = config["url"]
        tls_host = urllib.parse.urlsplit(url).hostname
        if urllib.parse.urlsplit(url).scheme != "https" or not tls_host:
            raise ValueError("HTTPS required")
        def resolve(host, port, *args, **kwargs):
            return original(config["connect_ip"] if host == tls_host else host, port, *args, **kwargs)
        socket.getaddrinfo = resolve
        context = ssl.create_default_context(cafile=str(root / "ca.pem"))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                            urllib.request.HTTPSHandler(context=context))
        request = urllib.request.Request(url, data=json.dumps(request_body).encode(), headers={
            "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
            "x-api-key": (root / "api.key").read_text().strip(),
            "x-task-id": envelope["task"], "Host": config["host"]})
        try:
            response = opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            row.update(delivery="response_received", status=response.code,
                headers={k.lower(): v for k, v in response.headers.items()
                         if k.lower().startswith("x-smoke-") or k.lower() == "content-type"},
                body=response.read(65536).decode())
    except Exception as exc:
        row.update(delivery="uncertain", error=type(exc).__name__)
        # Classify nested TLS/socket errors without persisting secret-bearing messages.
        reason = getattr(exc, "reason", None)
        if isinstance(reason, BaseException):
            row["cause_type"] = type(reason).__name__
    finally:
        socket.getaddrinfo = original
    row["utc_end_epoch"] = time.time()
    # First preserve the request outcome independently of backend reconciliation.
    persist(root / "remote_transport.jsonl", row)
    row["backend_matches"] = []
    try:
        backend = [json.loads(line) for line in (root / "backend.jsonl").read_text().splitlines()]
        row["backend_matches"] = [r for r in backend if r.get("request", {}).get("id") == identity]
        row["backend_log_status"] = "read"
    except FileNotFoundError:
        row["backend_log_status"] = "missing"
    except Exception as exc:
        row.update(backend_log_status="unreadable", backend_error=type(exc).__name__)
    persist(root / "remote_responses.jsonl", row)
    return row


if __name__ == "__main__":
    os.umask(0o077)
    print(json.dumps(execute(Path(__file__).resolve().parent, json.load(sys.stdin))))
