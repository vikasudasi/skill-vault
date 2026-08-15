#!/usr/bin/env python3
"""Generate a systemd unit file from a simple config.

Usage: python generate_unit.py --name my-app --exec /opt/app/venv/bin/app --user svc
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

UNIT_TEMPLATE = """[Unit]
Description={description}
After=network.target
{after_extra}
[Service]
Type={svc_type}
User={user}
Group={group}
WorkingDirectory={workdir}
ExecStart={exec_start}
Restart={restart}
RestartSec={restart_sec}
{env_file_line}
{extra_service}
[Install]
WantedBy=multi-user.target
"""


def generate(args: argparse.Namespace) -> str:
    env_file_line = ""
    if args.env_file:
        env_file_line = f"EnvironmentFile={args.env_file}"

    after_extra = ""
    if args.after_db:
        after_extra = "After=postgresql.service"

    extra_service = ""
    if args.svc_type == "notify":
        extra_service = "NotifyAccess=all\n"
    if args.limit_nofile:
        extra_service += f"LimitNOFILE={args.limit_nofile}\n"
    if args.timeout_sec:
        extra_service += f"TimeoutStopSec={args.timeout_sec}\n"

    return UNIT_TEMPLATE.format(
        description=args.description or args.name,
        after_extra=after_extra,
        svc_type=args.svc_type,
        user=args.user,
        group=args.group or args.user,
        workdir=args.workdir,
        exec_start=args.exec_start,
        restart=args.restart,
        restart_sec=args.restart_sec,
        env_file_line=env_file_line,
        extra_service=extra_service,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a systemd unit file")
    parser.add_argument("--name", required=True, help="Service name")
    parser.add_argument("--description", help="Service description")
    parser.add_argument("--exec-start", required=True, help="Full path to binary + args")
    parser.add_argument("--user", required=True, help="Unprivileged user to run as")
    parser.add_argument("--group", help="Group (defaults to --user)")
    parser.add_argument("--workdir", default="/opt/app", help="WorkingDirectory")
    parser.add_argument("--env-file", help="Path to EnvironmentFile")
    parser.add_argument(
        "--svc-type",
        default="simple",
        choices=["simple", "notify", "forking", "oneshot"],
    )
    parser.add_argument(
        "--restart",
        default="on-failure",
        choices=["no", "on-failure", "always", "on-abnormal"],
    )
    parser.add_argument("--restart-sec", type=int, default=3)
    parser.add_argument("--after-db", action="store_true", help="Add After=postgresql")
    parser.add_argument("--limit-nofile", type=int, help="File descriptor limit")
    parser.add_argument("--timeout-sec", type=int, help="TimeoutStopSec")
    parser.add_argument("--output", help="Write to file instead of stdout")

    args = parser.parse_args()
    unit = generate(args)

    if args.output:
        Path(args.output).write_text(unit)
        print(f"Unit written to {args.output}")
    else:
        print(unit)

    # Reminders
    install_name = args.output.rsplit("/", 1)[-1] if args.output else args.name
    print("\n# After deploying, run:")
    print(f"#   sudo cp {args.output or '<file>'} /etc/systemd/system/{install_name}.service")
    print(f"#   sudo systemctl daemon-reload")
    print(f"#   sudo systemctl enable --now {install_name}")


if __name__ == "__main__":
    main()
