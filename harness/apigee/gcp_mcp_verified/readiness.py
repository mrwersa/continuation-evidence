"""Non-mutating TCP and verified TLS checks. No HTTP or MCP requests."""
import json
import os
import socket
import ssl
import time
from pathlib import Path
from urllib.parse import urlsplit


def check(root):
    config = json.loads((root / "remote_config.json").read_text())
    row = {"utc": time.time(), "ready": False, "http_requests": 0, "tool_calls": 0}
    try:
        if time.time() >= min(config["deadline"], config["expiry"]):
            raise RuntimeError("Readiness deadline")
        row["stage"] = "backend_tcp"
        with socket.create_connection(("127.0.0.1", 8080), timeout=10):
            pass
        row["backend_listening"] = True
        row["stage"] = "runtime_tls"
        parsed = urlsplit(config["url"])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid TLS endpoint")
        context = ssl.create_default_context(cafile=str(root / "ca.pem"))
        with socket.create_connection((config["connect_ip"], parsed.port or 443), timeout=10) as connection:
            with context.wrap_socket(connection, server_hostname=parsed.hostname) as channel:
                row["tls_version"] = channel.version()
        row.update(ready=True, stage="complete")
    except Exception as exc:
        row["error"] = type(exc).__name__
    # This record contains no credential or raw exception message.
    with (root / "readiness.jsonl").open("a") as handle:
        handle.write(json.dumps(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row


if __name__ == "__main__":
    os.umask(0o077)
    result = check(Path(__file__).resolve().parent)
    print(json.dumps(result))
    raise SystemExit(0 if result["ready"] else 2)
