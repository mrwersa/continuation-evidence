"""Offline-tested integration functions for a future separately frozen package.

No command-line entry point, provisioning or automatic retries.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPORTS = ("backend.jsonl", "remote_attempts.jsonl", "remote_transport.jsonl",
           "remote_responses.jsonl", "readiness.jsonl", "server.log")


def redact(text, secrets):
    for value in secrets:
        if value:
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?i)(Bearer\s+)\S+", r"\1[REDACTED]", text)
    text = re.sub(r'(?i)((?:access_token|refresh_token|consumerKey|x-api-key)[\s\"\x27:=]+)[^\s\"\x27,}]+',
                  r'\1[REDACTED]', text)
    return text[-12000:]


def dispatch(command, envelope, diagnostic, secrets, run=subprocess.run):
    """One remote call. Retain redacted failure details, never replay."""
    try:
        result = run(command, input=json.dumps(envelope), text=True,
                     capture_output=True, timeout=90)
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        diagnostic({"kind": "remote_failure", "error": "TimeoutExpired",
                    "stderr": redact(stderr, secrets)})
        raise RuntimeError("Remote dispatch uncertain, no replay") from None
    if result.returncode:
        diagnostic({"kind": "remote_failure", "code": result.returncode,
                    "stderr": redact(result.stderr, secrets),
                    "stdout": redact(result.stdout, secrets)})
        raise RuntimeError("Remote client failed, no replay")
    try:
        row = json.loads(result.stdout)
    except (ValueError, TypeError):
        diagnostic({"kind": "remote_failure", "error": "MalformedResponse",
                    "stdout": redact(result.stdout, secrets)})
        raise RuntimeError("Remote response malformed, no replay") from None
    try:
        validate_response(row, envelope["request"]["id"])
    except RuntimeError:
        diagnostic({"kind": "remote_response_rejected", "request_id": row.get("request_id"),
            "delivery": row.get("delivery"), "status": row.get("status"),
            "backend_log_status": row.get("backend_log_status"),
            "body": redact(str(row.get("body", "")), secrets)})
        raise
    return row


def validate_response(row, identity):
    if not isinstance(row, dict) or row.get("request_id") != identity:
        raise RuntimeError("Response identity mismatch")
    if row.get("delivery") != "response_received":
        raise RuntimeError("Transport outcome uncertain")
    if row.get("backend_log_status") != "read":
        raise RuntimeError("Backend evidence missing or unreadable")
    if not isinstance(row.get("backend_matches"), list):
        raise RuntimeError("Backend evidence malformed")


def install_and_check(cli, ssh_options):
    """Called only after a future setup has started the unchanged backend."""
    paths = [HERE / name for name in ("remote_call.py", "readiness.py")]
    cli(["compute", "scp", *(str(p) for p in paths),
         "mcp-lab-client:/tmp/mcp-study/", *ssh_options])
    output = cli(["compute", "ssh", "mcp-lab-client", *ssh_options,
        "--command=cd /tmp/mcp-study && sha256sum remote_call.py readiness.py"])
    expected = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    actual = dict((line.split()[1], line.split()[0]) for line in output.splitlines()
                  if len(line.split()) == 2)
    if actual != expected:
        raise RuntimeError("Remote repair source mismatch")
    output = cli(["compute", "ssh", "mcp-lab-client", *ssh_options,
        "--command=cd /tmp/mcp-study && python3 readiness.py"])
    if json.loads(output).get("ready") is not True:
        raise RuntimeError("Non-mutating readiness check failed")
    return expected


def export_then_cleanup(export, cleanup, record):
    """Try every expected export and retain failures, always invoke cleanup."""
    outcomes = {}
    try:
        for name in EXPORTS:
            try:
                export(name)
                outcomes[name] = "exported"
            except Exception as exc:
                outcomes[name] = "missing_or_failed"
                record({"kind": "export_failed", "file": name, "error": type(exc).__name__})
    finally:
        cleanup()
    return outcomes


def audit_transport(responses, transport):
    """Additional strict gate before the original scientific evidence audit."""
    ids = [r["request_id"] for r in responses]
    tids = [r["request_id"] for r in transport]
    if len(set(ids)) != len(ids) or len(set(tids)) != len(tids) or set(ids) != set(tids):
        raise RuntimeError("Transport records missing or duplicated")
    indexed = {r["request_id"]: r for r in transport}
    for row in responses:
        validate_response(row, row["request_id"])
        if any(row.get(k) != v for k, v in indexed[row["request_id"]].items()):
            raise RuntimeError("Transport evidence differs from response")
