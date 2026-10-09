"""Local tooling; explicit operations only, fixed errors without input echo."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path

from . import __version__
from ._startup_trace import mark


def main():
    mark("cli_ready")
    parser = argparse.ArgumentParser(prog="aethron-edge")
    parser.add_argument(
        "command",
        choices=[
            "doctor",
            "replay",
            "export-openapi",
            "run",
            "serve",
            "bind-telemetry-policy",
            "initialize-telemetry",
        ],
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--update-store", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--replay-floor", type=int)
    args = parser.parse_args()
    provisioning = args.command in ("bind-telemetry-policy", "initialize-telemetry")
    if args.replay_floor is not None and args.command != "initialize-telemetry":
        parser.error("--replay-floor requires initialize-telemetry")
    if args.name is not None and not provisioning:
        parser.error("--name requires a telemetry provisioning command")
    if args.command == "export-openapi":
        from .openapi import document

        if args.out is None:
            parser.error("--out required")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document(), sort_keys=True, indent=2) + "\n")
        return
    if args.config is None:
        parser.error("--config required")
    if provisioning:
        from .config import load_config
        from .telemetry.boot_authority import initialize_boot_authority, provision_boot_authority
        from .telemetry.provisioning import load_boot_policy

        try:
            if not args.name or args.update_store is not None or args.out is not None:
                raise ValueError("invalid_binding_arguments")
            config = load_config(args.config)
            if config.runtime_mode == "appliance":
                from .runtime.updates import verify_configuration

                verify_configuration(config, args.config)
            selected = [item for item in config.telemetry if item.name == args.name]
            if len(selected) != 1 or selected[0].clock_policy_file is None:
                raise ValueError("clock_policy_required")
            item = selected[0]
            policy = load_boot_policy(
                item.clock_policy_file, system=item.system_id, component=item.component_id
            )
            if args.command == "initialize-telemetry":
                initialize_boot_authority(
                    item.replay_file, policy, timestamp_floor=args.replay_floor
                )
            else:
                provision_boot_authority(item.replay_file, policy)
        except (ValueError, OSError):
            error = (
                "initial_telemetry_provisioning_failed"
                if args.command == "initialize-telemetry"
                else "telemetry_policy_binding_failed"
            )
            parser.exit(2, error + "\n")
        result = {"policy_bound": True, "authority_issued": False}
        if args.command == "initialize-telemetry":
            result["journal_created"] = True
        print(json.dumps(result, separators=(",", ":")))
        return
    if args.command in ("run", "serve"):
        mark("config_import_start")
        from .config import load_config

        mark("config_import_done")

        try:
            config = load_config(args.config)
            mark("config_load_done")
            if config.runtime_mode == "appliance":
                mark("verification_start")
                from .runtime.updates import verify_configuration

                verify_configuration(config, args.config)
                mark("verification_done")
                if args.update_store:
                    from .runtime.updates import selected_runtime

                    selected = selected_runtime(args.update_store, Path(config.trust_root))
                    if selected:
                        python, active_config = selected
                        os.execv(
                            str(python),
                            [
                                str(python),
                                "-I",
                                "-m",
                                "aethron_edge",
                                "run",
                                "--config",
                                str(active_config),
                            ],
                        )
            elif args.update_store:
                raise ValueError("appliance_mode_required")
            mark("runtime_import_start")
            from .runtime.entrypoint import run

            mark("runtime_import_done")

            run(config)
        except (ValueError, OSError):
            parser.exit(2, "startup_failed\n")
        return
    try:
        config = json.loads(args.config.read_text())
        if config.get("version") != 1:
            raise ValueError("invalid_request")
        if args.command == "doctor":
            result = {
                "edge_version": __version__,
                "core_version": importlib.metadata.version("aethron"),
                "hardware_probed": False,
                "qualified": False,
                "model": "not_loaded",
                "provider": "not_selected",
            }
        else:
            from .protocol import replay_stream

            path = (args.config.parent / config["replay"]).resolve()
            with path.open("rb") as stream:
                result = replay_stream(stream).model_dump(by_alias=True)
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    except (ValueError, OSError, KeyError):
        parser.exit(2, "invalid_request\n")
