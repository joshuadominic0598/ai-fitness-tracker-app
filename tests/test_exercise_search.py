import tempfile
import unittest
from unittest.mock import patch

from fitness_tracker.semantic_index import EMBED_MODEL, SemanticIndex
from fitness_tracker.store import Store


class ExerciseSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.index = SemanticIndex(self.store)

    def test_fuzzy_queries_rank_the_correct_exercise_first(self):
        for query, expected in [
            ("hamer curls", "Hammer_Curls"),
            ("seeted cabel row", "Seated_Cable_Rows"),
            ("dumbell bicep curll", "Dumbbell_Bicep_Curl"),
            ("pec deck", "Butterfly"),
        ]:
            with self.subTest(query=query):
                results = self.index.search_exercises(query)
                self.assertEqual(results[0]["id"], expected)
                self.assertEqual(
                    [r["score"] for r in results],
                    sorted((r["score"] for r in results), reverse=True),
                )
        self.assertEqual(len(self.index.search_exercises("pec deck")), 1)
        self.assertEqual(self.store.entries(), [])

    def test_tracked_and_body_part_filters_limit_ranked_candidates(self):
        self.store.save(
            "workout",
            {
                "date": "2026-11-17",
                "exercises": [{"exercise_id": "Hammer_Curls", "sets": [{"weight": 10, "reps": 8}]}],
            },
        )
        self.assertEqual(
            [r["id"] for r in self.index.search_exercises("hamer curls", tracked=True)],
            ["Hammer_Curls"],
        )
        self.assertEqual(
            self.index.search_exercises("hamer curls", tracked=True, body_part="Chest"), []
        )

    def test_dense_vectors_and_fuzzy_keywords_both_contribute(self):
        self.index.enabled = True
        with self.store.connect() as con:
            con.execute(
                "UPDATE coach_chunks SET vector='[1,0]',model=? WHERE category='exercise'",
                (EMBED_MODEL,),
            )
        with patch.object(self.index, "embed", return_value=[[1, 0]]):
            results = self.index.search_exercises("hamer curl", limit=5)
        self.assertEqual(results[0]["id"], "Hammer_Curls")
        self.assertTrue(all(r["retrieval"] == "semantic + fuzzy keyword" for r in results))

    def test_embeddings_unavailable_keeps_ranked_typo_matches(self):
        self.index.enabled = True
        with self.store.connect() as con:
            con.execute(
                "UPDATE coach_chunks SET vector='[1,0]',model=? WHERE category='exercise'",
                (EMBED_MODEL,),
            )
        with patch.object(
            self.index, "embed", side_effect=ValueError("Local embeddings unavailable")
        ):
            results = self.index.search_exercises("seeted cabel row")
        self.assertEqual(results[0]["id"], "Seated_Cable_Rows")
        self.assertEqual(results[0]["retrieval"], "fuzzy keyword")
