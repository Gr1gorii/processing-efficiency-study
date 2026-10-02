"""Hand-calculated answers and deterministic input invariants."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from backends import BACKENDS
from collect import make_schedule
from dataset import digest_result, generate, reference


class CorrectnessTests(unittest.TestCase):
    def check_case(self, fact, customers, expected):
        fact = np.asarray(fact, dtype=np.int64).reshape(-1, 5)
        customers = np.asarray(customers, dtype=np.int64).reshape(-1, 2)
        for name, backend_class in BACKENDS.items():
            backend = backend_class(fact, customers)
            try:
                for operation, answer in expected.items():
                    with self.subTest(backend=name, operation=operation):
                        actual = backend.execute(operation)
                        self.assertEqual(actual, answer)
                        self.assertEqual(reference(fact, customers, operation), answer)
                        width = 2 if operation == "filter" else 3
                        self.assertEqual(digest_result(actual, width), digest_result(answer, width))
            finally:
                backend.close()

    def test_thresholds_negative_values_and_unmatched_join(self):
        self.check_case(
            [[4, 99, 2, 8000, 1], [0, 10, 2, 4999, 1], [3, 12, 9, -1000, 1],
             [1, 11, 2, 5000, 1], [2, 10, 9, 6000, 0]],
            [[10, 3], [11, 3], [12, 7]],
            {"filter": [(1, 5000), (4, 8000)],
             "group": [(2, 3, 17999), (9, 2, 5000)],
             "join": [(3, 3, 15999), (7, 1, -1000)]},
        )

    def test_empty_filter_and_missing_categories(self):
        self.check_case([[0, 1, 42, 4999, 1], [1, 1, 42, -999, 0]], [[1, 7]],
                        {"filter": [], "group": [(42, 2, 4000)], "join": [(7, 2, 4000)]})

    def test_empty_fact(self):
        self.check_case([], [[1, 7]], {"filter": [], "group": [], "join": []})

    def test_empty_dimension(self):
        self.check_case([[0, 1, 42, 5000, 1]], [],
                        {"filter": [(0, 5000)], "group": [(42, 1, 5000)], "join": []})

    def test_generator_and_conservation(self):
        fact, customers = generate(1000, 73, 20)
        other_fact, other_customers = generate(1000, 73, 20)
        np.testing.assert_array_equal(fact, other_fact)
        np.testing.assert_array_equal(customers, other_customers)
        self.assertEqual(len(np.unique(fact[:, 0])), len(fact))
        self.assertEqual(len(np.unique(customers[:, 0])), len(customers))
        self.assertTrue(np.isin(fact[:, 1], customers[:, 0]).all())
        for operation in ["group", "join"]:
            answer = reference(fact, customers, operation)
            self.assertEqual(sum(row[1] for row in answer), len(fact))
            self.assertEqual(sum(row[2] for row in answer), int(fact[:, 3].sum()))

    def test_schedule_is_complete_and_reproducible(self):
        schedule = make_schedule([100, 200], 3, 99)
        self.assertEqual(schedule, make_schedule([100, 200], 3, 99))
        self.assertNotEqual(schedule, make_schedule([100, 200], 3, 100))
        keys = {(j["rows"], j["repeat"], j["backend"], j["operation"], j["mode"]) for j in schedule}
        self.assertEqual(len(keys), 2 * 3 * 3 * 3 * 2)


if __name__ == "__main__":
    unittest.main()
