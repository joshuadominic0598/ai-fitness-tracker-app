"""Dedicated creatine records, legacy compatibility and independent scoring."""

import json
import tempfile
import unittest
from datetime import date

from fitness_tracker.consistency import consistency
from fitness_tracker.prompt_budget import chat_topics
from fitness_tracker.store import Store, insights

DAY = "2026-11-15"


class CreatineTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)

    def test_creatine_is_not_a_supplement_option_or_selection(self):
        profile = self.store.save_profile(
            {
                "supplements": ["Creatine", "Magnesium"],
                "consistency_supplements": ["Creatine", "Magnesium"],
            }
        )
        self.assertNotIn("Creatine", profile["supplements"])
        self.assertEqual(profile["consistency_supplements"], ["Magnesium"])
        self.assertIn("creatine", profile["goals"])
        with self.assertRaisesRegex(ValueError, "dedicated Creatine"):
            self.store.add_supplement("creatine")

    def test_new_entries_and_legacy_writes_use_dedicated_kind(self):
        first = self.store.save("creatine", {"date": DAY, "amount": 3})
        second = self.store.save(
            "supplement",
            {
                "date": DAY,
                "name": "Creatine",
                "amount": 2,
                "unit": "g",
            },
        )
        self.assertEqual(first["kind"], "creatine")
        self.assertEqual(second["kind"], "creatine")
        self.assertEqual(first["unit"], "g")
        self.assertNotIn("Creatine", self.store.profile()["supplements"])
        profile = self.store.profile()
        score = consistency(self.store.entries(), profile, date(2026, 11, 16))
        self.assertEqual(score["categories"]["creatine"]["score"], 100)
        self.assertIsNone(score["categories"]["supplements"]["score"])
        self.assertEqual(
            insights(self.store.entries(), profile, date(2026, 11, 16))["daily"][DAY]["creatine"], 5
        )
        with self.assertRaisesRegex(ValueError, "grams"):
            self.store.save("creatine", {"date": DAY, "amount": 1, "unit": "tablet"})

    def test_existing_records_read_as_creatine_without_rewriting_or_duplicate(self):
        legacy = {"date": DAY, "name": "Creatine", "amount": 5, "unit": "g", "notes": "old"}
        encoded = json.dumps(legacy)
        with self.store.connect() as con:
            con.execute("INSERT INTO entries VALUES (?,?,?)", ("legacy-id", "supplement", encoded))
        record = self.store.entries()[0]
        self.assertEqual((record["id"], record["kind"]), ("legacy-id", "creatine"))
        with self.store.connect() as con:
            self.assertEqual(
                con.execute("SELECT kind,data FROM entries").fetchone(), ("supplement", encoded)
            )
        self.store.save(record["kind"], {**record, "amount": 4}, record["id"])
        self.assertEqual(len(self.store.entries()), 1)
        self.assertEqual(self.store.entries()[0]["amount"], 4)

    def test_mixed_and_legacy_drafts_preview_and_approve_independently(self):
        draft = self.store.draft(
            "batch",
            {
                "entries": [
                    {"kind": "creatine", "data": {"date": DAY, "amount": 5}},
                    {
                        "kind": "supplement",
                        "data": {"date": DAY, "name": "Vitamin D", "amount": 1, "unit": "tablet"},
                    },
                ]
            },
        )
        self.assertEqual(
            [e["kind"] for e in self.store.preview(draft["id"])["entries"]],
            ["creatine", "supplement"],
        )
        self.assertEqual(self.store.entries(), [])
        self.store.approve(draft["id"])
        self.assertEqual({e["kind"] for e in self.store.entries()}, {"creatine", "supplement"})
        legacy = self.store.draft(
            "supplement", {"date": DAY, "name": "Creatine", "amount": 2, "unit": "g"}
        )
        self.assertEqual(legacy["kind"], "creatine")
        self.assertEqual(self.store.drafts()[0]["kind"], "creatine")
        self.assertEqual(self.store.approve(legacy["id"])["kind"], "creatine")
        self.assertEqual(chat_topics("Log my creatine: 5 g"), {"creatine"})
