import concurrent.futures
import json
import subprocess
import sys
import unittest

from test_core import claim, evaluate, observation, request
from test_v2 import person, scene


class AdversarialTests(unittest.TestCase):
    def test_invalid_enums_and_rectangles_never_escape_validation(self):
        for rect in [
            [0, 0, 0, 4],
            [99, 0, 2, 1],
            [True, 0, 1, 1],
            [1.5, 0, 2, 2],
            [],
            [0, 0, 101, 2],
            "secret",
        ]:
            with self.assertRaises(ValueError):
                evaluate(scene(dict(person(), rect=rect)))
        for field, value in [
            ("zone", []),
            ("sensor", {}),
            ("at_ms", True),
            ("calibration_until_ms", 2**60),
            ("nonhuman", 1),
            ("inference_ms", -1),
            ("quality", "secret"),
        ]:
            with self.assertRaises(ValueError):
                evaluate(scene(dict(person(), **{field: value})))

    def test_person_geometry_conflict_keeps_coarse_presence(self):
        out = evaluate(scene(person(), dict(person("thermal_person"), rect=[10, 10, 40, 60])))
        c = claim(out, "human_presence")
        self.assertEqual(c["state"], "PRESENT")
        self.assertIsNone(c["rect"])
        self.assertIn("localization_uncertain", c["reasons"])
        self.assertEqual(c["confidence"], "medium")

    def test_valid_cue_disagreement_cannot_localize_person(self):
        out = evaluate(scene(person(), dict(person("thermal_person"), values=[0.05])))
        c = claim(out, "human_presence")
        self.assertEqual(c["state"], "UNKNOWN")
        self.assertEqual(c["sources"], [])
        self.assertIsNone(c["rect"])
        self.assertEqual(out["recommendation"]["action"], "STOP")

    def test_zero_probability_is_absence_not_invalid_depth_person(self):
        self.assertEqual(
            claim(evaluate(scene(dict(person("depth_person"), values=[0]))), "human_presence")[
                "state"
            ],
            "ABSENT",
        )

    def test_missing_values_and_deep_duplicate_json(self):
        self.assertEqual(claim(evaluate(request(observation(values=[]))))["state"], "UNKNOWN")
        from rescuesense import evaluate as run

        data = (
            json.dumps(scene(person()))
            .replace('"sensor": "rgb"', '"sensor": "rgb", "sensor": "thermal_person"')
            .encode()
        )
        with self.assertRaises(ValueError):
            run(data)
        with self.assertRaises(ValueError):
            run(b'{"x":' + b"[" * 9 + b"0" + b"]" * 9 + b"}")
        with self.assertRaises(ValueError):
            run(b'{"x":"\\"[[[[[[[[[["}')

    def test_all_modes_absence_does_not_say_safe(self):
        for light in ["daylight", "low_light", "near_dark", "zero_visible"]:
            out = evaluate(scene(dict(person("thermal_person"), values=[0]), lighting=light))
            self.assertNotIn("SAFE", json.dumps(out))
            self.assertEqual(out["recommendation"]["action"], "STOP")

    def test_optimized_python_still_rejects_invalid_input(self):
        p = subprocess.run(
            [sys.executable, "-O", "-m", "rescuesense", "evaluate", "-"],
            input=b'{"identity":"secret"}',
            capture_output=True,
            check=False,
        )
        self.assertEqual(p.returncode, 2)
        self.assertNotIn(b"secret", p.stdout + p.stderr)

    def test_concurrent_evaluations_do_not_share_observations(self):
        docs = [scene(person("thermal_person")), scene(), request(observation(values=[180]))] * 40
        expected = [evaluate(d) for d in docs]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            actual = list(pool.map(evaluate, docs))
        self.assertEqual(actual, expected)

    def test_reentry_at_later_time_is_unlinked(self):
        evaluate(scene(person("thermal_person")))
        evaluate(scene(now_ms=2000))
        reentry = scene(
            person("thermal_person", at_ms=2500, calibration_until_ms=3000), now_ms=2500
        )
        out = evaluate(reentry)
        c = claim(out, "human_presence")
        self.assertEqual(c["state"], "PRESENT")
        self.assertEqual(c["valid_until_ms"], 2700)
        self.assertEqual(
            set(c),
            {
                "capability",
                "zone",
                "state",
                "kind",
                "confidence",
                "confidence_semantics",
                "reasons",
                "sources",
                "rect",
                "valid_until_ms",
            },
        )

    def test_legacy_protocol_never_attributes_blind_sensor_as_support(self):
        out = evaluate(request(observation("rgb", [0.95]), lighting="zero_visible"))
        self.assertEqual(claim(out, "human_presence")["sources"], [])
        out = evaluate(request(observation(), observation("thermal_aux", [80], quality="dropped")))
        self.assertEqual(claim(out)["sources"], ["thermal"])
        self.assertEqual(claim(out)["confidence"], "medium")

    def test_v2_adapter_round_trip(self):
        from rescuesense import evaluate as run
        from rescuesense.adapters import envelope, person_cue

        obs = person_cue(
            "thermal_person", 0.95, at_ms=1000, calibration_until_ms=2000, rect=[10, 10, 20, 30]
        )
        result = run(envelope([obs], now_ms=1000, version=2, lighting="zero_visible"))
        self.assertEqual(claim(result, "human_presence")["rect"], [10, 10, 20, 30])
        with self.assertRaises(ValueError):
            person_cue("radar", 0.95, at_ms=1000, calibration_until_ms=2000)


if __name__ == "__main__":
    unittest.main()
