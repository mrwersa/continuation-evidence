"""Canonicalise only same-project Compute global-operation read URLs."""
import re
from urllib.parse import urlsplit


def operation_poll_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc not in
            {"www.googleapis.com", "compute.googleapis.com"}
            or parsed.query or parsed.fragment
            or not re.fullmatch(
                r"/compute/v1/projects/your-gcp-project/global/operations/[A-Za-z0-9_-]+",
                parsed.path)):
        raise ValueError("Out-of-scope operation URL")
    return "https://compute.googleapis.com" + parsed.path
