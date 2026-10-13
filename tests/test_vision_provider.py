"""Provider failure admission using the real ORT Python fallback mechanism.

Native execution is replaced with a deterministic fault, not an accelerator claim.
"""

import hashlib
import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

from aethron.vision import yolox

AVAILABLE = all(importlib.util.find_spec(name) for name in ("numpy", "cv2", "onnxruntime"))


@unittest.skipUnless(AVAILABLE, "optional pinned vision/Core ML dependencies required")
class VisionProvider(unittest.TestCase):
    def setUp(self):
        import numpy as np
        from onnxruntime.capi.onnxruntime_inference_collection import Session

        self.np = np
        self.session = Session()
        self.session._providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
        self.session._fallback_providers = ["CPUExecutionProvider"]
        self.session._inputs_meta = [
            SimpleNamespace(name="images", shape=[1, 3, 640, 640], type="tensor(float)")
        ]
        self.session._outputs_meta = [
            SimpleNamespace(name="output", shape=[1, 8400, 85], type="tensor(float)")
        ]
        self.pixels = np.zeros((8, 8, 3), dtype=np.uint8)

    def detector(self, available=None, session_factory=None, **kwargs):
        # Keep file length/digest verification real; only native model loading is
        # substituted so no downloaded model or hardware is needed for this fault.
        blob = b"synthetic provider boundary fixture"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.onnx"
            path.write_bytes(blob)
            with (
                patch.object(yolox, "MODEL_BYTES", len(blob)),
                patch.object(yolox, "MODEL_SHA256", hashlib.sha256(blob).hexdigest()),
                patch(
                    "onnxruntime.get_available_providers",
                    return_value=available or ["CoreMLExecutionProvider", "CPUExecutionProvider"],
                ),
                patch(
                    "onnxruntime.InferenceSession",
                    return_value=self.session,
                    side_effect=session_factory,
                ),
            ):
                return yolox.RGBDetector(path, backend="coreml", **kwargs)

    def test_construction_failure_cannot_retry_or_print_native_details(self):
        from onnxruntime.capi.onnxruntime_inference_collection import InferenceSession

        for error_type in (ValueError, RuntimeError):
            with self.subTest(error_type=error_type.__name__):
                attempts = []
                original = error_type("synthetic private native detail")

                def fail(session, providers, *args, attempts=attempts, original=original):
                    attempts.append(tuple(providers))
                    session._fallback_providers = ["CPUExecutionProvider"]
                    raise original

                output = io.StringIO()
                with (
                    patch.object(InferenceSession, "_create_inference_session", fail),
                    redirect_stdout(output),
                    self.assertRaises(error_type) as caught,
                ):
                    self.detector(session_factory=InferenceSession)
                self.assertIs(caught.exception, original)
                self.assertEqual(attempts, [("CoreMLExecutionProvider", "CPUExecutionProvider")])
                self.assertEqual(output.getvalue(), "")

    def test_reenabled_fallback_is_disabled_before_each_execution(self):
        from onnxruntime.capi import _pybind_state as native

        original = native.EPFail("synthetic private provider detail")
        run = Mock(side_effect=original)
        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        detector = self.detector()
        for attempt in range(2):
            with self.subTest(attempt=attempt):
                run.reset_mock()
                self.session.enable_fallback()
                output = io.StringIO()
                with (
                    patch.object(self.session, "set_providers") as retry,
                    redirect_stdout(output),
                    self.assertRaises(native.EPFail) as caught,
                ):
                    detector.infer(self.pixels, lighting="daylight")
                self.assertIs(caught.exception, original)
                self.assertEqual(output.getvalue(), "")
                run.assert_called_once()
                retry.assert_not_called()

    def test_execution_failure_cannot_retry_on_cpu(self):
        from onnxruntime.capi import _pybind_state as native

        def fail(*args):
            raise native.EPFail("synthetic provider failure")

        def cpu_retry(*args):
            self.session._providers = ["CPUExecutionProvider"]
            self.session._sess = SimpleNamespace(
                is_webgpu_graph_capture_enabled=lambda: False,
                run=lambda *args: [self.np.zeros((1, 8400, 85), dtype=self.np.float32)],
            )

        self.session._sess = SimpleNamespace(
            run=fail, is_webgpu_graph_capture_enabled=lambda: False
        )
        detector = self.detector()
        with patch.object(self.session, "set_providers", side_effect=cpu_retry):
            with self.assertRaises(native.EPFail):
                detector.infer(self.pixels, lighting="daylight")
        self.assertEqual(self.session.get_providers()[0], "CoreMLExecutionProvider")

    def test_session_that_lost_coreml_during_construction_is_rejected(self):
        self.session._providers = ["CPUExecutionProvider"]
        with self.assertRaises(ValueError):
            self.detector()

    def test_construction_requires_exact_provider_precedence(self):
        for providers in (
            ["CPUExecutionProvider", "CoreMLExecutionProvider"],
            ["CoreMLExecutionProvider"],
            ["CoreMLExecutionProvider", "CPUExecutionProvider", "UnexpectedProvider"],
            ("CoreMLExecutionProvider", "CPUExecutionProvider"),
            None,
        ):
            with self.subTest(providers=providers):
                self.session._providers = providers
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    self.detector()

    def test_provider_drift_before_execution_prevents_native_run(self):
        detector = self.detector()
        run = Mock(return_value=[self.np.zeros((1, 8400, 85), dtype=self.np.float32)])
        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        for providers in (
            ["CPUExecutionProvider"],
            ["CPUExecutionProvider", "CoreMLExecutionProvider"],
            ["CoreMLExecutionProvider", "CPUExecutionProvider", "UnexpectedProvider"],
        ):
            with self.subTest(providers=providers):
                self.session._providers = providers
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    detector.infer(self.pixels, lighting="daylight")
        run.assert_not_called()

    def test_provider_drift_during_execution_withdraws_output(self):
        detector = self.detector()

        def drift(*args):
            self.session._providers = ["CPUExecutionProvider"]
            return [self.np.zeros((1, 8400, 85), dtype=self.np.float32)]

        run = Mock(side_effect=drift)
        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        with patch.object(yolox, "_validated_output") as validate:
            with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                detector.infer(self.pixels, lighting="daylight")
        run.assert_called_once()
        validate.assert_not_called()

    def test_provider_drift_does_not_mask_execution_failure_or_retry(self):
        from onnxruntime.capi import _pybind_state as native

        detector = self.detector()
        original = native.EPFail("synthetic execution failure")

        def drift_and_fail(*args):
            self.session._providers = ["CPUExecutionProvider"]
            raise original

        run = Mock(side_effect=drift_and_fail)
        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        with patch.object(self.session, "set_providers") as retry:
            with self.assertRaises(native.EPFail) as caught:
                detector.infer(self.pixels, lighting="daylight")
        self.assertIs(caught.exception, original)
        run.assert_called_once()
        retry.assert_not_called()

    def test_missing_coreml_is_rejected(self):
        with self.assertRaises(ValueError):
            self.detector(available=["CPUExecutionProvider"])

    def test_successful_inference_keeps_declared_provider(self):
        self.session._sess = SimpleNamespace(
            is_webgpu_graph_capture_enabled=lambda: False,
            run=lambda *args: [self.np.zeros((1, 8400, 85), dtype=self.np.float32)],
        )
        detector = self.detector()
        self.assertEqual(detector.infer(self.pixels, lighting="daylight"), [])
        self.assertEqual(self.session.get_providers()[0], "CoreMLExecutionProvider")

    def test_coreml_request_preserves_explicit_execution_policy(self):
        factory = Mock(return_value=self.session)
        detector = self.detector(session_factory=factory)
        self.assertIs(detector.ort_session, self.session)
        factory.assert_called_once_with(
            b"synthetic provider boundary fixture",
            sess_options=ANY,
            enable_fallback=False,
            providers=["CoreMLExecutionProvider", "CPUExecutionProvider"],
            provider_options=[
                {
                    "ModelFormat": "MLProgram",
                    "MLComputeUnits": "ALL",
                    "RequireStaticInputShapes": "1",
                },
                {},
            ],
        )

    def test_requested_thread_policy_runs_native_cpu_graph(self):
        import onnxruntime as ort

        # Use the actual production options on a tiny authored CPU Identity graph.
        model = bytes.fromhex(
            "08083a420a100a017812017922084964656e74697479120c7032335f6964656e74697479"
            "5a0f0a0178120a0a08080112040a020801620f0a0179120a0a08080112040a0208014202100d"
        )
        factory = Mock(return_value=self.session)
        self.detector(session_factory=factory)
        options = factory.call_args.kwargs.get("sess_options")
        self.assertIsInstance(options, ort.SessionOptions)
        self.assertEqual(options.intra_op_num_threads, 1)
        self.assertEqual(options.inter_op_num_threads, 1)
        self.assertEqual(options.execution_mode, ort.ExecutionMode.ORT_SEQUENTIAL)
        for pool in ("intra_op", "inter_op"):
            self.assertEqual(
                options.get_session_config_entry(f"session.{pool}.allow_spinning"), "0"
            )
        session = ort.InferenceSession(
            model, sess_options=options, providers=["CPUExecutionProvider"], enable_fallback=False
        )
        actual = session.get_session_options()
        self.assertEqual(actual.intra_op_num_threads, 1)
        self.assertEqual(actual.inter_op_num_threads, 1)
        self.assertEqual(actual.execution_mode, ort.ExecutionMode.ORT_SEQUENTIAL)
        for pool in ("intra_op", "inter_op"):
            self.assertEqual(actual.get_session_config_entry(f"session.{pool}.allow_spinning"), "0")
        value = self.np.array([3.25], dtype=self.np.float32)
        self.np.testing.assert_array_equal(session.run(None, {"x": value})[0], value)

    def test_metadata_dimension_types_are_strict(self):
        for field, shape in (("_inputs_meta", [1, 3, 640, 640]), ("_outputs_meta", [1, 8400, 85])):
            for first in (True, 1.0):
                with self.subTest(field=field, first=first):
                    node = SimpleNamespace(
                        name="tensor", type="tensor(float)", shape=[first, *shape[1:]]
                    )
                    with patch.object(self.session, field, [node]):
                        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                            self.detector()

    def test_metadata_tensor_type_is_float32(self):
        for field, shape in (("_inputs_meta", [1, 3, 640, 640]), ("_outputs_meta", [1, 8400, 85])):
            for tensor_type in (None, "tensor(double)", "tensor(uint8)", "seq(tensor(float))"):
                with self.subTest(field=field, tensor_type=tensor_type):
                    node = SimpleNamespace(name="tensor", type=tensor_type, shape=shape)
                    with patch.object(self.session, field, [node]):
                        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                            self.detector()

    def test_metadata_missing_or_invalid_fields_are_rejected(self):
        for field, shape in (("_inputs_meta", [1, 3, 640, 640]), ("_outputs_meta", [1, 8400, 85])):
            for values in ({"name": None}, {"name": ""}, {"name": 7}, {"shape": None}):
                with self.subTest(field=field, values=values):
                    node = SimpleNamespace(
                        **({"name": "tensor", "type": "tensor(float)", "shape": shape} | values)
                    )
                    with patch.object(self.session, field, [node]):
                        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                            self.detector()
            for missing in ("shape", "type", "name"):
                with self.subTest(field=field, missing=missing):
                    node = SimpleNamespace(name="tensor", type="tensor(float)", shape=shape)
                    delattr(node, missing)
                    with patch.object(self.session, field, [node]):
                        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                            self.detector()

    def test_execution_requires_exactly_one_output(self):
        raw = self.np.zeros((1, 8400, 85), dtype=self.np.float32)
        for outputs in ([], [raw, raw], (raw,), None):
            with self.subTest(
                container=type(outputs).__name__, count=None if outputs is None else len(outputs)
            ):
                run = Mock(return_value=outputs)
                self.session._sess = SimpleNamespace(
                    run=run, is_webgpu_graph_capture_enabled=lambda: False
                )
                detector = self.detector()
                with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                    detector.infer(self.pixels, lighting="daylight")
                run.assert_called_once()

    def test_metadata_accepts_native_cpu_nodeargs(self):
        import onnxruntime as ort

        # Authored IR8/opset13 Identity graph; validates native metadata only.
        model = bytes.fromhex(
            "08083a420a100a017812017922084964656e74697479120c7032335f6964656e74697479"
            "5a0f0a0178120a0a08080112040a020801620f0a0179120a0a08080112040a0208014202100d"
        )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            model, sess_options=options, providers=["CPUExecutionProvider"], enable_fallback=False
        )
        self.assertEqual(yolox._ort_tensor_name(session.get_inputs(), [1]), "x")
        self.assertEqual(yolox._ort_tensor_name(session.get_outputs(), [1]), "y")
        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
            yolox._ort_tensor_name(session.get_inputs(), [1, 3, 640, 640])

    def test_precancelled_load_never_opens_model(self):
        cancellation = yolox.InferenceCancellation()
        cancellation.cancel()
        with patch.object(Path, "open") as opened:
            with self.assertRaises(yolox.InferenceCancelled):
                yolox.RGBDetector("unused", backend="coreml", cancellation=cancellation)
        opened.assert_not_called()

    def test_load_cancellation_reaches_native_options_and_rejects_late_success(self):
        import onnxruntime as ort
        from onnxruntime.capi import onnxruntime_pybind11_state as native

        cancellation = yolox.InferenceCancellation()
        entered, resume = Event(), Event()
        options_seen, outcomes = [], []
        create_session = ort.InferenceSession
        model = bytes.fromhex(
            "08083a420a100a017812017922084964656e74697479120c7032335f6964656e74697479"
            "5a0f0a0178120a0a08080112040a020801620f0a0179120a0a08080112040a0208014202100d"
        )

        def delayed_load(blob, **kwargs):
            options_seen.append(kwargs["sess_options"])
            entered.set()
            if not resume.wait(5):
                raise AssertionError("test release missing")
            return self.session

        def load():
            try:
                outcomes.append(
                    self.detector(session_factory=delayed_load, cancellation=cancellation)
                )
            except Exception as error:
                outcomes.append(error)

        thread = Thread(target=load)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            cancellation.cancel()
            # Exercise the exact forwarded options with a real CPU graph. This
            # witnesses the flag, not interruption of a running native load.
            with self.assertRaises(native.ModelLoadCanceled):
                create_session(
                    model,
                    sess_options=options_seen[0],
                    providers=["CPUExecutionProvider"],
                    enable_fallback=False,
                )
        finally:
            resume.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], yolox.InferenceCancelled)
        self.assertEqual(len(options_seen), 1)

    def test_load_failure_propagates_and_completed_token_detaches(self):
        cancellation = yolox.InferenceCancellation()
        original = RuntimeError("private load details")

        def fail(*args, **kwargs):
            cancellation.cancel()
            raise original

        factory = Mock(side_effect=fail)
        with self.assertRaises(RuntimeError) as caught:
            self.detector(session_factory=factory, cancellation=cancellation)
        self.assertIs(caught.exception, original)
        factory.assert_called_once()
        with self.assertRaises(ValueError):
            self.detector(cancellation=cancellation)

        # A completed load token cannot cancel a later load sharing its options.
        import onnxruntime as ort

        next_token = yolox.InferenceCancellation()
        factory = Mock(return_value=self.session)
        self.detector(session_factory=factory, cancellation=next_token)
        next_token.cancel()
        options = factory.call_args.kwargs["sess_options"]
        model = bytes.fromhex(
            "08083a420a100a017812017922084964656e74697479120c7032335f6964656e74697479"
            "5a0f0a0178120a0a08080112040a020801620f0a0179120a0a08080112040a0208014202100d"
        )
        loaded = ort.InferenceSession(
            model, sess_options=options, providers=["CPUExecutionProvider"], enable_fallback=False
        )
        value = self.np.array([3.25], dtype=self.np.float32)
        self.np.testing.assert_array_equal(loaded.run(None, {"x": value})[0], value)

    def test_load_cancellation_rejects_opencv(self):
        with self.assertRaisesRegex(ValueError, "^invalid_input$"):
            yolox.RGBDetector("unused", cancellation=yolox.InferenceCancellation())

    def test_precancelled_inference_never_submits_pixels(self):
        detector = self.detector()
        cancellation = yolox.InferenceCancellation()
        cancellation.cancel()
        with patch.object(self.session, "run") as run:
            with self.assertRaisesRegex(yolox.InferenceCancelled, "^inference_cancelled$"):
                detector.infer(self.pixels, lighting="daylight", cancellation=cancellation)
        run.assert_not_called()

    def test_cancellation_during_preprocessing_never_submits_pixels(self):
        detector = self.detector()
        cancellation = yolox.InferenceCancellation()
        pack = self.np.ascontiguousarray

        def cancel_after_packing(canvas, **kwargs):
            tensor = pack(canvas, **kwargs)
            cancellation.cancel()
            return tensor

        with (
            patch.object(self.np, "ascontiguousarray", side_effect=cancel_after_packing),
            patch.object(self.session, "run", return_value=[]) as run,
        ):
            with self.assertRaisesRegex(yolox.InferenceCancelled, "^inference_cancelled$"):
                detector.infer(self.pixels, lighting="daylight", cancellation=cancellation)
        self.assertEqual(run.call_count, 0)

    def test_active_cancellation_sets_native_option_and_rejects_late_success(self):
        import onnxruntime as ort

        detector = self.detector()
        cancellation = yolox.InferenceCancellation()
        entered, resume = Event(), Event()
        options_seen, outcomes = [], []

        def delayed_run(names, feeds, options):
            options_seen.append(options)
            entered.set()
            if not resume.wait(5):
                raise AssertionError("test release missing")
            return [self.np.zeros((1, 8400, 85), dtype=self.np.float32)]

        def infer():
            try:
                outcomes.append(
                    detector.infer(self.pixels, lighting="daylight", cancellation=cancellation)
                )
            except Exception as error:
                outcomes.append(error)

        run = Mock(side_effect=delayed_run)
        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        with patch.object(yolox, "_validated_output") as validate:
            thread = Thread(target=infer)
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertIsInstance(options_seen[0], ort.RunOptions)
                self.assertFalse(options_seen[0].terminate)
                cancellation.cancel()
                cancellation.cancel()
                self.assertTrue(options_seen[0].terminate)
            finally:
                resume.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], yolox.InferenceCancelled)
        validate.assert_not_called()
        run.assert_called_once()

    def test_cancellation_failure_propagates_once_and_next_call_is_independent(self):
        from onnxruntime.capi import _pybind_state as native

        detector = self.detector()
        cancellation = yolox.InferenceCancellation()
        original = native.EPFail("synthetic termination failure")
        options_seen = []

        def fail(names, feeds, options):
            options_seen.append(options)
            cancellation.cancel()
            raise original

        run = Mock(side_effect=fail)
        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        self.session.enable_fallback()
        with patch.object(self.session, "set_providers") as retry:
            with self.assertRaises(native.EPFail) as caught:
                detector.infer(self.pixels, lighting="daylight", cancellation=cancellation)
        self.assertIs(caught.exception, original)
        run.assert_called_once()
        retry.assert_not_called()

        def succeed(names, feeds, options):
            options_seen.append(options)
            self.assertFalse(options.terminate)
            return [self.np.zeros((1, 8400, 85), dtype=self.np.float32)]

        run.side_effect = succeed
        next_call = yolox.InferenceCancellation()
        self.assertEqual(
            detector.infer(self.pixels, lighting="daylight", cancellation=next_call), []
        )
        self.assertIsNot(options_seen[0], options_seen[1])
        # Completed tokens detach options and cannot be reused for another call.
        next_call.cancel()
        self.assertFalse(options_seen[1].terminate)
        with self.assertRaises(ValueError):
            detector.infer(self.pixels, lighting="daylight", cancellation=next_call)
        self.assertEqual(run.call_count, 2)

    def test_cancellation_during_postprocessing_withdraws_result(self):
        detector = self.detector()
        cancellation = yolox.InferenceCancellation()
        self.session._sess = SimpleNamespace(
            is_webgpu_graph_capture_enabled=lambda: False,
            run=lambda *args: [self.np.zeros((1, 8400, 85), dtype=self.np.float32)],
        )
        original = yolox._validated_output

        def cancel_during_scores(raw):
            cancellation.cancel()
            return original(raw)

        with patch.object(yolox, "_validated_output", side_effect=cancel_during_scores):
            with self.assertRaises(yolox.InferenceCancelled):
                detector.infer(self.pixels, lighting="daylight", cancellation=cancellation)

    def test_cancellation_rejects_unsupported_backend_and_concurrent_token_reuse(self):
        detector = self.detector()
        cancellation = yolox.InferenceCancellation()
        with patch.object(detector, "backend", "opencv"):
            with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                detector.infer(self.pixels, lighting="daylight", cancellation=cancellation)

        def run(names, feeds, options):
            with self.assertRaisesRegex(ValueError, "^invalid_input$"):
                detector.infer(self.pixels, lighting="daylight", cancellation=cancellation)
            self.assertFalse(options.terminate)
            return [self.np.zeros((1, 8400, 85), dtype=self.np.float32)]

        self.session._sess = SimpleNamespace(run=run, is_webgpu_graph_capture_enabled=lambda: False)
        self.assertEqual(
            detector.infer(self.pixels, lighting="daylight", cancellation=cancellation), []
        )
