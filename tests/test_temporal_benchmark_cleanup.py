"""Benchmark lifecycle checks with inert sessions; no performance evidence."""

import tracemalloc
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

from scripts import temporal_evaluate as temporal


class TemporalBenchmarkCleanup(unittest.TestCase):
    def setUp(self):
        if tracemalloc.is_tracing():
            raise RuntimeError("test requires a process without preexisting tracing")

    def tearDown(self):
        if tracemalloc.is_tracing():
            tracemalloc.stop()

    def test_caller_tracing_and_existing_trace_are_preserved(self):
        tracemalloc.start()
        sentinel = bytearray(1024)
        before = tracemalloc.get_object_traceback(sentinel)
        self.assertIsNotNone(before)
        models = [Mock(), Mock()]
        for model in models:
            model.step.return_value = {"tracks": [None] * 32}
        with patch.object(temporal, "Session", side_effect=models) as factory:
            caught = None
            try:
                temporal.benchmark()
            except ValueError as error:
                caught = error
            self.assertTrue(tracemalloc.is_tracing(), "benchmark stopped caller tracing")
            self.assertEqual(tracemalloc.get_object_traceback(sentinel), before)
            self.assertIsNotNone(caught)
            self.assertEqual(str(caught), "tracing_already_active")
            factory.assert_not_called()

    def test_failure_cleanup_preserves_exception_identity(self):
        for stage in ("timed_step", "start", "factory", "memory_step", "peak", "stop"):
            for error_type in (RuntimeError, KeyboardInterrupt):
                with self.subTest(stage=stage, error=error_type.__name__):
                    error = error_type("injected_benchmark_failure")
                    models = [Mock(), Mock()]
                    for model in models:
                        model.step.return_value = {"tracks": [None] * 32}
                    if stage == "timed_step":
                        models[0].step.side_effect = error
                    if stage == "memory_step":
                        models[1].step.side_effect = error
                    try:
                        with ExitStack() as stack:
                            factory = stack.enter_context(
                                patch.object(
                                    temporal,
                                    "Session",
                                    side_effect=[
                                        models[0],
                                        error if stage == "factory" else models[1],
                                    ],
                                )
                            )
                            if stage in ("start", "stop", "peak"):
                                name = "get_traced_memory" if stage == "peak" else stage
                                stack.enter_context(
                                    patch.object(tracemalloc, name, side_effect=error)
                                )
                            with self.assertRaises(error_type) as caught:
                                temporal.benchmark()
                            self.assertIs(caught.exception, error)
                            models[0].close.assert_called_once_with()
                            if stage in ("timed_step", "start", "factory"):
                                models[1].close.assert_not_called()
                            else:
                                models[1].close.assert_called_once_with()
                            self.assertEqual(
                                factory.call_count, 1 if stage in ("timed_step", "start") else 2
                            )
                            if stage != "stop":
                                self.assertFalse(tracemalloc.is_tracing())
                    finally:
                        if tracemalloc.is_tracing():
                            tracemalloc.stop()

    def test_constructor_and_step_tracing_scopes_are_preserved(self):
        models = [Mock(), Mock()]
        constructors, steps = [], []

        def factory():
            model = models[len(constructors)]
            constructors.append(tracemalloc.is_tracing())
            return model

        def step(*args, **kwargs):
            steps.append(tracemalloc.is_tracing())
            return {"tracks": [None] * 32}

        for model in models:
            model.step.side_effect = step
        with patch.object(temporal, "Session", side_effect=factory):
            temporal.benchmark()  # Discard inert timings; never write a report.
        self.assertEqual(constructors, [False, True])
        self.assertEqual(steps, [False] * 100 + [True] * 100)
        for model in models:
            model.close.assert_called_once_with()
        self.assertFalse(tracemalloc.is_tracing())


if __name__ == "__main__":
    unittest.main()
