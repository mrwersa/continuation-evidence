"""Build the controlled MCP proxy. The only accounting is native Quota."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from xml.etree import ElementTree

parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, choices=(700, 1000), required=True)
parser.add_argument("--backend", default="http://10.77.0.10:8080/mcp")
args = parser.parse_args()
root = Path(__file__).parent
files = {}
files["mcp-lab-refund.xml"] = '<APIProxy name="mcp-lab-refund" revision="1"><DisplayName>MCP refund smoke</DisplayName><Description>Controlled synthetic tool quota</Description><ProxyEndpoints><ProxyEndpoint>default</ProxyEndpoint></ProxyEndpoints><TargetEndpoints><TargetEndpoint>default</TargetEndpoint></TargetEndpoints></APIProxy>'
files["policies/VerifyKey.xml"] = '<VerifyAPIKey name="VerifyKey"><APIKey ref="request.header.x-api-key"/></VerifyAPIKey>'
files["policies/ParseMCP.xml"] = '<ParsePayload name="ParseMCP"><Source>request</Source><PayloadType>JSON-RPC-2.0</PayloadType><Protocol>MCP</Protocol></ParsePayload>'
files["policies/Validate.xml"] = '<Javascript name="Validate" timeLimit="200"><ResourceURL>jsc://validate.js</ResourceURL></Javascript>'
files["resources/jsc/validate.js"] = '''context.setVariable("smoke.valid", false);
var data = JSON.parse(context.getVariable("request.content"));
var key = context.getVariable("request.header.x-task-id");
var amount = data.params && data.params.arguments && data.params.arguments.amount;
if (data.method === "tools/call" && data.params.name === "refund" &&
    typeof amount === "number" && isFinite(amount) && Math.floor(amount) === amount &&
    amount >= 1 && amount <= 1000 && typeof key === "string" && /^[a-zA-Z0-9_-]{1,80}$/.test(key)) {
  context.setVariable("smoke.amount", amount);
  context.setVariable("smoke.task", key);
  context.setVariable("smoke.valid", true);
}
'''
files["policies/BadRequest.xml"] = '<RaiseFault name="BadRequest"><FaultResponse><Set><StatusCode>400</StatusCode><ReasonPhrase>Invalid synthetic tool input</ReasonPhrase><Payload contentType="application/json">{"error":"invalid_input"}</Payload></Set></FaultResponse></RaiseFault>'
files["policies/RefundQuota.xml"] = f'''<Quota name="RefundQuota" type="calendar">
<Allow count="{args.limit}"/><Interval>1</Interval><TimeUnit>day</TimeUnit>
<StartTime>2026-10-09 00:00:00</StartTime><Distributed>true</Distributed><Synchronous>true</Synchronous>
<Identifier ref="smoke.task"/><MessageWeight ref="smoke.amount"/>
</Quota>'''
files["policies/ReturnEvidence.xml"] = '''<AssignMessage name="ReturnEvidence"><AssignTo createNew="false" type="response"/><Set><Headers>
<Header name="x-smoke-revision">{apiproxy.revision}</Header>
<Header name="x-smoke-limit">{ratelimit.RefundQuota.allowed.count}</Header>
<Header name="x-smoke-used">{ratelimit.RefundQuota.used.count}</Header>
<Header name="x-smoke-available">{ratelimit.RefundQuota.available.count}</Header>
<Header name="x-smoke-expiry">{ratelimit.RefundQuota.expiry.time}</Header>
<Header name="x-smoke-operation">{parsepayload.ParseMCP.operation}</Header>
</Headers></Set><IgnoreUnresolvedVariables>true</IgnoreUnresolvedVariables></AssignMessage>'''
files["proxies/default.xml"] = '''<ProxyEndpoint name="default">
<DefaultFaultRule name="EvidenceOnFault"><Step><Name>ReturnEvidence</Name></Step><AlwaysEnforce>true</AlwaysEnforce></DefaultFaultRule>
<PreFlow name="PreFlow"><Request><Step><Name>VerifyKey</Name></Step><Step><Name>ParseMCP</Name></Step></Request><Response/></PreFlow>
<Flows><Flow name="Refund"><Request>
<Step><Name>Validate</Name></Step><Step><Name>BadRequest</Name><Condition>smoke.valid != true</Condition></Step>
<Step><Name>RefundQuota</Name></Step>
</Request><Response/><Condition>parsepayload.ParseMCP.operation = "tools/call/refund"</Condition></Flow></Flows>
<PostFlow name="PostFlow"><Request/><Response><Step><Name>ReturnEvidence</Name></Step></Response></PostFlow>
<HTTPProxyConnection><BasePath>/mcp-smoke</BasePath></HTTPProxyConnection>
<RouteRule name="default"><TargetEndpoint>default</TargetEndpoint></RouteRule></ProxyEndpoint>'''
files["targets/default.xml"] = f'<TargetEndpoint name="default"><HTTPTargetConnection><URL>{args.backend}</URL></HTTPTargetConnection></TargetEndpoint>'
for name, body in files.items():
    if name.endswith(".xml"):
        ElementTree.fromstring(body)
output = root / f"proxy-{args.limit}.zip"
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for name, body in sorted(files.items()):
        archive.writestr("apiproxy/" + name, body)
print(json.dumps({"file": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "limit": args.limit}))
