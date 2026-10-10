"""Construct controlled offline variants from the exact successful smoke bundle."""
import argparse
import base64
import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).parent
SOURCE_HASH = "e93bf08a3a386522a21e87dcc44e1e85873f89934643d12017228986ccd30430"
VARIANTS = ("baseline", "identical", "whitespace", "tighten700", "tighten500", "rename_policy")
QUOTA = "apiproxy/policies/RefundQuota.xml"


def contents(variant, window_date):
    if variant not in VARIANTS:
        raise ValueError("Unknown variant")
    if date.fromisoformat(window_date).isoformat() != window_date:
        raise ValueError("Use canonical YYYY-MM-DD")
    encoded = json.loads((ROOT.parent / "gcp_mcp_smoke/deployed_bundles.json").read_text())["1000"]
    source = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(source).hexdigest() != SOURCE_HASH:
        raise ValueError("Changed smoke source")
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        files = {name: archive.read(name).decode() for name in archive.namelist()}
    files[QUOTA] = files[QUOTA].replace("2026-10-09 00:00:00", window_date + " 00:00:00")
    if variant in ("tighten700", "tighten500"):
        limit = "700" if variant == "tighten700" else "500"
        files[QUOTA] = files[QUOTA].replace('count="1000"', f'count="{limit}"')
    elif variant == "whitespace":
        files[QUOTA] = files[QUOTA].replace("/><Interval>", "/>\n    <Interval>")
    elif variant == "rename_policy":
        # All references must follow the name, including diagnostic flow variables.
        files = {name.replace("RefundQuota", "RefundQuotaRenamed"): text.replace("RefundQuota", "RefundQuotaRenamed") for name, text in files.items()}
    for name, text in files.items():
        if name.endswith(".xml"):
            ET.fromstring(text)
    return files


def bundle(variant, window_date):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, text in sorted(contents(variant, window_date).items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, text.encode())
    return output.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=VARIANTS)
    parser.add_argument("--window-date", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = bundle(args.variant, args.window_date)
    with args.output.open("xb") as handle:
        handle.write(data)
    print(json.dumps({"variant": args.variant, "window_date": args.window_date, "sha256": hashlib.sha256(data).hexdigest()}))
