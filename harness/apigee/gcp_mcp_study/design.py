"""Offline, deterministic trial order and explicit deployment accounting."""
import argparse
import json
import random
from collections import Counter

SEED = 20261009
ARMS = {
    "no_update": (10, [600], [300, 200], None, ["admit", "refuse"]),
    "identical": (10, [600], [300, 200], "baseline", ["admit", "refuse"]),
    "whitespace": (10, [600], [300, 200], "whitespace", ["admit", "refuse"]),
    "tighten700": (20, [600], [50, 100], "tighten700", ["admit", "refuse"]),
    "tighten500": (10, [600], [1, 50], "tighten500", ["refuse", "refuse"]),
    "rename_policy": (10, [600], [300, 200], "rename_policy", None),
    "fresh1000": (10, [], [300, 200], None, ["admit", "admit"]),
    "fresh700": (10, [], [50, 100], None, ["admit", "admit"]),
}


def schedule():
    rng = random.Random(SEED)
    result = []
    for block in (1, 2):
        parents = []
        for arm, (count, before, after, variant, expected) in ARMS.items():
            if arm == "fresh700":
                continue
            for repeat in range(1, count // 2 + 1):
                parents.append({
                    "id": f"b{block}-{arm}-{repeat:02d}", "block": block,
                    "arm": arm, "repeat": repeat, "preload": before,
                    "probes": after, "focal_variant": variant,
                    "conformance_pattern": expected,
                    "accounting_key": f"b{block}-{arm}-{repeat:02d}",
                    "uses_parent_deployment": None,
                })
        rng.shuffle(parents)
        for parent in parents:
            result.append(parent)
            if parent["arm"] == "tighten700" and parent["repeat"] <= 5:
                identity = f"b{block}-fresh700-{parent['repeat']:02d}"
                result.append({
                    "id": identity, "block": block, "arm": "fresh700",
                    "repeat": parent["repeat"], "preload": [], "probes": [50, 100],
                    "focal_variant": None, "conformance_pattern": ["admit", "admit"],
                    "accounting_key": identity, "uses_parent_deployment": parent["id"],
                })
    return result


def promotions(trials):
    """Nominal writes, assuming each attempted import/promotion succeeds once."""
    current = None
    writes = []
    for trial in trials:
        if trial["uses_parent_deployment"]:
            if current != "tighten700":
                raise ValueError("Attached fresh-key control requires its parent's 700 revision")
            continue
        if current != "baseline":
            writes.append({"before_trial": trial["id"], "purpose": "baseline", "variant": "baseline"})
            current = "baseline"
        if trial["focal_variant"] is not None:
            # Identical bytes still receive their specified import/promotion attempt.
            writes.append({"before_trial": trial["id"], "purpose": "focal", "variant": trial["focal_variant"]})
            current = trial["focal_variant"]
    return writes


def manifest():
    trials = schedule()
    writes = promotions(trials)
    return {
        "schema": 1, "seed": SEED, "status": "offline_preparation_no_live_data",
        "planned_sequences": len(trials),
        "planned_core_tool_calls": sum(len(t["preload"]) + len(t["probes"]) for t in trials),
        "planned_focal_updates": sum(t["focal_variant"] is not None for t in trials),
        "nominal_promotions_including_baselines": len(writes),
        "arms": dict(Counter(t["arm"] for t in trials)),
        "conditional_zero_failure_one_sided_95_upper": {str(n): 1 - 0.05 ** (1 / n) for n in (10, 20)},
        "trials": trials, "nominal_promotions": writes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    value = manifest()
    if args.summary:
        value = {k: v for k, v in value.items() if k not in ("trials", "nominal_promotions")}
    print(json.dumps(value, indent=2))
