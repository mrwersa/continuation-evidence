"""Task-key contract shared by preflight, the runner and the evidence audit."""
import re

EXECUTION = re.compile(r"repeat-[0-9]{8}-[a-z0-9]{8}\Z")
KEY = re.compile(r"[a-zA-Z0-9_-]{1,80}\Z")


def namespaced(execution, key):
    if not isinstance(execution, str) or not EXECUTION.fullmatch(execution):
        raise ValueError("Invalid execution identifier")
    if not isinstance(key, str) or not KEY.fullmatch(key):
        raise ValueError("Invalid unprefixed task key")
    result = execution + "-" + key
    if not KEY.fullmatch(result):
        raise ValueError("Namespaced key violates deployed validator")
    return result
