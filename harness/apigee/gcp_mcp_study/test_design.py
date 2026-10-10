import unittest
from collections import Counter
from xml.etree import ElementTree as ET

from bundles import QUOTA, VARIANTS, bundle, contents
from design import manifest, promotions, schedule


class DesignTests(unittest.TestCase):
    def test_allocation_and_calls(self):
        value = manifest()
        self.assertEqual(value["planned_sequences"], 90)
        self.assertEqual(value["planned_core_tool_calls"], 250)
        self.assertEqual(value["planned_focal_updates"], 60)
        self.assertEqual(value["nominal_promotions_including_baselines"], 110)
        self.assertEqual(value["arms"]["tighten700"], 20)
        self.assertTrue(all(count == 10 for arm, count in value["arms"].items() if arm != "tighten700"))

    def test_order_and_keys(self):
        rows = schedule()
        self.assertEqual(rows, schedule())
        self.assertEqual(len({r["accounting_key"] for r in rows}), 90)
        self.assertEqual(Counter(r["block"] for r in rows), {1: 45, 2: 45})
        for block in (1, 2):
            arms = Counter(r["arm"] for r in rows if r["block"] == block)
            self.assertEqual(arms["tighten700"], 10)
            self.assertTrue(all(n == 5 for arm, n in arms.items() if arm != "tighten700"))

    def test_fresh700_is_attached_not_another_transition(self):
        rows = schedule()
        for index, row in enumerate(rows):
            if row["arm"] == "fresh700":
                self.assertEqual(row["uses_parent_deployment"], rows[index - 1]["id"])
                self.assertEqual(rows[index - 1]["arm"], "tighten700")
                self.assertNotEqual(row["accounting_key"], rows[index - 1]["accounting_key"])
        self.assertEqual(sum(w["purpose"] == "focal" for w in promotions(rows)), 60)

    def test_below_spent_does_not_claim_to_undo_past_actions(self):
        row = next(r for r in schedule() if r["arm"] == "tighten500")
        self.assertEqual(row["preload"], [600])
        self.assertEqual(row["probes"], [1, 50])
        self.assertEqual(row["conformance_pattern"], ["refuse", "refuse"])

    def test_name_intervention_has_no_preselected_conformance_pattern(self):
        self.assertTrue(all(r["conformance_pattern"] is None for r in schedule() if r["arm"] == "rename_policy"))


class BundleTests(unittest.TestCase):
    day = "2026-10-09"

    def test_deterministic_and_identical_bytes(self):
        for variant in VARIANTS:
            self.assertEqual(bundle(variant, self.day), bundle(variant, self.day))
        self.assertEqual(bundle("baseline", self.day), bundle("identical", self.day))

    def test_tightening_changes_only_limit(self):
        base = contents("baseline", self.day)
        for variant, limit in (("tighten700", "700"), ("tighten500", "500")):
            candidate = contents(variant, self.day)
            self.assertEqual({k for k in base if base[k] != candidate[k]}, {QUOTA})
            self.assertEqual(base[QUOTA].replace('count="1000"', f'count="{limit}"'), candidate[QUOTA])

    def test_whitespace_preserves_xml_structure(self):
        base = contents("baseline", self.day)
        candidate = contents("whitespace", self.day)
        self.assertEqual({k for k in base if base[k] != candidate[k]}, {QUOTA})
        self.assertEqual(ET.canonicalize(base[QUOTA], strip_text=True), ET.canonicalize(candidate[QUOTA], strip_text=True))

    def test_name_and_references_change_together(self):
        base = contents("baseline", self.day)
        renamed = contents("rename_policy", self.day)
        recovered = {k.replace("RefundQuotaRenamed", "RefundQuota"): v.replace("RefundQuotaRenamed", "RefundQuota") for k, v in renamed.items()}
        self.assertEqual(base, recovered)
        quota = ET.fromstring(renamed[QUOTA.replace("RefundQuota", "RefundQuotaRenamed")])
        self.assertEqual(quota.find("Identifier").get("ref"), "smoke.task")
        self.assertEqual(quota.find("Allow").get("count"), "1000")

    def test_window_and_input_guards(self):
        for variant in VARIANTS:
            files = contents(variant, "2026-10-10")
            quota_name = QUOTA.replace("RefundQuota", "RefundQuotaRenamed") if variant == "rename_policy" else QUOTA
            self.assertEqual(ET.fromstring(files[quota_name]).findtext("StartTime"), "2026-10-10 00:00:00")
        with self.assertRaises(ValueError):
            contents("unknown", self.day)
        with self.assertRaises(ValueError):
            contents("baseline", "bad-date")


if __name__ == "__main__":
    unittest.main()
