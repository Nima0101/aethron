# C09 offline appliance qualification review — V3, partial

Decision for this pass: **CLARIFY diagnostic authority, storage and termination
claims; add fault-disclosure controls.** The worker's executable behavior is
unchanged. The existing dirty provisioning file is read-only for this pass.
This is a qualification review, not a runtime KEEP/MIGRATE decision or completed
V3 technology reassessment. The full audit cursor remains C01.

The worker publishes diagnostics with `data=None`, not semantic observations.
Its processing availability and host deadline do not grant live sensor authority.
The duration measures provider processing including initial binding, excluding
file hashing, validation, pacing, IPC and downstream delivery. It therefore
cannot support an exposure-to-output latency or real-time claim.

The new synthetic controls inject a manifest-load failure with private details.
The worker emits exactly the fixed fault fields, zero batches/expiry and no raw
payload or exception text. A second control makes that fault-message sink fail;
the exception propagates, so final diagnostic delivery is not guaranteed. Both
controls pass before documentation changes. They do not simulate a physical
sensor, measure scheduling or certify a supervisor's process termination.

The stop event is cooperative. The worker cannot check it while blocked inside
hashing, validation, file I/O, provider code or a send callback. Scheduled waits
of at most 100 ms do not establish a 100 ms shutdown guarantee. Supervisor
termination is a separate boundary, owned outside this component; its code is
not changed here. No five-nines availability, failover, hard-real-time or
platform qualification is established.

The manifest and source digest checks do not authenticate runtime caller objects
or replace the signed-installation trust boundary. One descriptor prevents path
reopening substitution but is not an immutable content snapshot: administrator
storage must remain trusted and unchanged throughout validation and playback.
Signature and hash checks do not certify physical calibration or content truth.
These limits are now explicit in the appliance contract. Obsolete future ROS
integration language is replaced with ownership and independent-evidence limits.

Historical appliance results refer to their recorded source/wheel revisions;
previous startup, EOF, RGB and optional rectification timing failures remain in
that evidence. This pass runs only two mocked worker disclosure tests. No spawned
supervisor, signed service, installed wheel, boot soak or physical device was
requalified. See [review evidence](evidence/phase2/appliance-claims-review-v3.json).
Hashes identify reviewed bytes, not authenticated execution. Insufficient
information for tactical deployment.
