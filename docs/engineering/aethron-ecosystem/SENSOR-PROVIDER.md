# Calibrated raw geometry provider — implemented software boundary

`aethron_edge.sensors.provider` connects decoded recorded depth/cloud packets and ROS ingress to [registration and sparse rectification](SENSOR-REGISTRATION.md). This is partial P2.1/P3.1. It returns measured point geometry, never a semantic detection, track, free-space statement or qualified live observation. No model or supervisor admission gate has been relaxed.

## Contracts and lifetime

`ProviderCalibration` is a frozen, closed Pydantic model containing source ID, modality (`depth`, `radar`, `lidar`), rigid calibration, optional source intrinsics/lens, declared measurement error in metres, and expected format SHA-256. Depth requires source intrinsics. Cloud inputs forbid camera/lens fields. A canonical digest binds all these fields, including target intrinsics, mount and declared errors. Hashes identify configuration; they do not authenticate calibration or measure its accuracy.

`layout_digest(ImageLayout)` includes dimensions, encoding, stride, byte order and depth scale. For `CloudLayout` it binds fields, offsets, types, point stride and byte order; validated packet counts and row padding may vary. Existing binary `read_frames` retains its stricter fixed-layout stream contract; changing cloud counts inside that recording format still requires a future version. ROS can vary cloud counts now.

`GeometryProvider(calibration, mode=..., clock_id=..., valid_for_ns=..., clock=...)` owns an expiring binding (maximum 600 seconds) and one executor/thread. ROS defaults to `time.monotonic_ns`; recorded mode needs an explicit logical clock in the recording's domain. There is no automatic conversion of replay timestamps into live evidence. Invalid/rewound clocks or changed mount permanently close the binding; explicit recreation/rebinding is required. Source loss withdraws availability and marks the next accepted batch as a scene break.

- `recorded(frame, indices, mount_id=...)`: accepts decoded `RecordedFrame`, checking source/frame/modality, format, bundle digest, increasing sequence/acquisition and freshness. Depth indices are unique `(column,row)` integers; cloud indices are unique indices into the decoder's valid-point tuple. At most 64 selected samples per call. No full-image inference or automatic point selection is supplied.
- `ros(ingress, indices, mount_id=...)`: consumes the configured `RosIngress` exactly once. It binds the ingress instance and checks mapped acquisition time, format and current CameraInfo intrinsics. A different ingress requires a new provider. Depth output expires at the earliest rig, CameraInfo, clock-mapping or 100 ms measurement deadline. ROS CameraInfo remains the zero-distortion contract; distorted recorded depth may use the optional lens path. No silent interpretation of distorted ROS images is introduced.
- `RosSubscriber.poll_geometry(provider, indices, mount_id=..., timeout_sec=...)`: spins the actual SDK executor, then admits the pending packet through the provider. Use this instead of raw `poll()` followed by provider consumption, which would consume twice. Closing the subscriber withdraws provider availability on the next geometry poll; direct status also observes its cleared mapping/calibration.
- `source_lost()` and `close()` clear availability. `status()` rechecks the trusted clock, expiry and ROS calibration/mapping changes. Its semantic `state` is always `UNKNOWN`; `geometry_available` is only a diagnostic and `qualified` is always false.

A `GeometryBatch` contains at most 64 `RegisteredPoint`s, selected invalid-sample count, recorded/external-unverified provenance, bundle digest, capture/expiry time and scene-break flag. Individual points retain rig digest, target frame, transformed coordinates, projected pixel/error footprint and range. Their expiry is clipped to the batch's authority deadline. Missing depth or out-of-view/unsupported projections are counted as invalid selected samples, not absence of obstacles. Cloud decoder discards invalid raw points before selection; its separate `invalid_points` count remains at that adapter boundary.

Sparse depth is corrected through the source lens **before** deprojection and rigid transformation. The declared 3D measurement bound must cover the installation's depth, pixel localization and lens uncertainty; software does not estimate that bound from arbitrary counts. A final clock check prevents slow processing from returning expired geometry. There is no hard-real-time execution claim.

## Installed ROS consumer shape

The following function uses implemented APIs. It requires an installed ROS SDK, an existing context, a validated calibration and an explicit clock mapping from the installation. Creating an offset is not proof of physical exposure synchronization. This consumer returns one unqualified geometry batch or fixed source fault; a caller supplies lifecycle supervision.

```python
from uuid import uuid4
from aethron_edge.sensors.provider import GeometryProvider
from aethron_edge.sensors.ros2 import RosIngress
from aethron_edge.sensors.ros2_node import RosSubscriber


def read_radar(context, calibration, mapping, indices):
    bridge = RosIngress(modality="radar", frame_id=calibration.rig.source_frame)
    bridge.bind_clock(mapping)
    provider = GeometryProvider(
        calibration, mode="ros", clock_id=uuid4().hex,
        valid_for_ns=30_000_000_000,
    )
    subscriber = RosSubscriber(
        bridge, topic="/installation/radar", context=context,
    )
    try:
        return subscriber.poll_geometry(
            provider, indices, mount_id=calibration.rig.mount_id,
        )
    finally:
        subscriber.close()
        provider.close()
```

A returned batch is a historical measurement with finite expiry; closing its provider does not turn it into retained live support. A continuous consumer must poll/status/watchdog within the existing freshness contract. Do not use this single-read example as an unattended appliance supervisor.

## Verification and remaining work

Portable tests exercise actual binary depth replay and ROS message admission, translated geometry, mount/source/calibration/format loss, cloud count changes, duplicate/future/stale timestamps, processing expiry, malformed raster bytes and 2,000 invalid pixel selections. Optional OpenCV verification uses an analytically derived distorted depth ray through the provider. The installed ROS test publishes real DDS PointCloud2 through `poll_geometry`, verifies the target-plane projection and withdrawal on close; it runs offline with no actuation interface.

[Recorded provider provisioning and appliance supervision](SENSOR-APPLIANCE.md) are now implemented. Remaining: ROS per-boot authority, middleware isolation and supervisor subscriber wiring; independently evaluated modality-specific models; LWIR/NIR image-to-semantic and depth association; licensed recorded nonvisible evidence; full-raster/stereo/fisheye processing; hardware clock/calibration, power/thermal, field safety and independent certification. Raw geometry tests do not close any of these gates. See [NEXT](NEXT.md) and [test evidence](TEST-EVIDENCE.md).
