# Mandatory v2 verification — frozen before v2 implementation
V2-1 Same current direct person envelope survives RGB blackout when a valid thermal_person or depth_person cue remains; current supporting sensor supplies geometry.
V2-2 Support provenance removes blind RGB and identifies only valid remaining contributors.
V2-3 Invalidated support caps confidence at medium and makes degradation/uncertainty explicit; no calibrated probability claim.
V2-4 No internal association state or identifier is created; evaluating after the <=200ms result deadline requires fresh evaluation. Stale input cannot renew a box past 500ms/calibration deadline.
V2-5 After loss/disappearance and re-entry, output is unlinked to prior presence; no identity/state reuse, including across process instances.
V2-6 All support lost produces explicit human_presence UNKNOWN and STOP/HOVER per contract, no permissive clearance or silent object removal.
V2-7 Through-obstruction rejects person sensors, any human box and any geometry; valid authorized radar produces only coarse zone presence.
All seven are mandatory publication and production gate additions. v1 no-human-box tests continue exercising version 1. D06/D07 are superseded ONLY for authorized protocol-2 direct human geometry. Through-obstruction/privacy restrictions remain unchanged. Field accuracy and physical support remain H02/H03 blockers.
