"""Synthetic MCP receipt server. No quota, financial effect or model call."""
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.umask(0o077)
LOG = Path(__file__).with_name("backend.jsonl")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 16384:
            self.send_error(400)
            return
        body = json.loads(self.rfile.read(size))
        record = {"utc": datetime.now(timezone.utc).isoformat(), "request": body}
        with LOG.open("a") as handle:
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        method = body.get("method")
        if "id" not in body:
            self.send_response(204)
            self.end_headers()
            return
        response = {"jsonrpc": "2.0", "id": body["id"]}
        if method == "initialize":
            response["result"] = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "synthetic-refund", "version": "0.1"}}
        elif method == "tools/list":
            response["result"] = {"tools": [{"name": "refund", "description": "Return a receipt without performing a refund", "inputSchema": {"type": "object", "properties": {"amount": {"type": "integer", "minimum": 1, "maximum": 1000}}, "required": ["amount"], "additionalProperties": False}}]}
        elif method == "tools/call" and body.get("params", {}).get("name") == "refund":
            amount = body["params"].get("arguments", {}).get("amount")
            if type(amount) is not int or not 1 <= amount <= 1000:
                response["error"] = {"code": -32602, "message": "Invalid amount"}
            else:
                response["result"] = {"content": [{"type": "text", "text": json.dumps({"receipt": body["id"], "amount": amount, "effect": "none"})}], "isError": False}
        else:
            response["error"] = {"code": -32601, "message": "Method or tool not found"}
        encoded = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
