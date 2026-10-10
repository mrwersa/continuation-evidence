"""One non-retried MCP request with a persisted 50-tool-call budget."""
import argparse
import fcntl
import json
import os
import ssl
import socket
import urllib.error
import urllib.request
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.umask(0o077)
parser = argparse.ArgumentParser()
parser.add_argument("--url", required=True)
parser.add_argument("--key", required=True)
parser.add_argument("--task", required=True)
parser.add_argument("--amount", type=int)
parser.add_argument("--method", default="tools/call", choices=["tools/call", "tools/list", "initialize"])
parser.add_argument("--ca")
parser.add_argument("--host", help="Apigee environment-group HTTP host")
parser.add_argument("--connect-ip", help="Private ingress IP, preserving URL hostname for TLS")
args = parser.parse_args()
root = Path(__file__).parent
budget = root / "tool_count.txt"
with budget.open("a+") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    handle.seek(0)
    count = int(handle.read() or "0")
    if args.method == "tools/call":
        if args.amount is None or not 1 <= args.amount <= 1000 or count >= 50:
            raise SystemExit("Invalid amount or tool-call budget exhausted")
        count += 1
        handle.seek(0)
        handle.truncate()
        handle.write(str(count))
        handle.flush()
        os.fsync(handle.fileno())
body = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": args.method}
if args.method == "tools/call":
    body["params"] = {"name": "refund", "arguments": {"amount": args.amount}}
elif args.method == "initialize":
    body["params"] = {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "controlled-smoke", "version": "0.1"}}
record = {"utc_start": datetime.now(timezone.utc).isoformat(), "task": args.task, "request": body, "tool_calls_reserved": count}
with (root / "attempts.jsonl").open("a") as handle:
    handle.write(json.dumps(record) + "\n")
request = urllib.request.Request(args.url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "x-api-key": Path(args.key).read_text().strip(), "x-task-id": args.task})
if args.host:
    request.add_header("Host", args.host)
if args.connect_ip:
    original_getaddrinfo = socket.getaddrinfo
    tls_host = urllib.parse.urlparse(args.url).hostname
    def resolve(host, port, *rest, **kwargs):
        return original_getaddrinfo(args.connect_ip if host == tls_host else host, port, *rest, **kwargs)
    socket.getaddrinfo = resolve
context = ssl.create_default_context(cafile=args.ca)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
try:
    response = opener.open(request, timeout=30)
except urllib.error.HTTPError as exc:
    response = exc
    record["delivery"] = "response_received"
except Exception as exc:
    record["delivery"] = "uncertain"
    record["error"] = type(exc).__name__ + ": " + str(exc)
else:
    record["delivery"] = "response_received"
if "error" not in record:
    with response:
        record["status"] = response.code
        record["headers"] = {k: v for k, v in response.headers.items() if k.lower().startswith("x-smoke-") or k.lower() == "content-type"}
        record["body"] = response.read(65536).decode(errors="replace")
record["utc_end"] = datetime.now(timezone.utc).isoformat()
with (root / "client.jsonl").open("a") as handle:
    handle.write(json.dumps(record) + "\n")
print(json.dumps(record))
