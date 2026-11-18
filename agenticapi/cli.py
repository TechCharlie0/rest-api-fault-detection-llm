"""Command-line entry points for AgenticAPI."""

from __future__ import annotations

import argparse
import json
import sys
import time

from agenticapi.config import Settings
from agenticapi.evaluation.conditions import CONDITIONS, DEFAULT_CONDITIONS
from agenticapi.evaluation.runner import load_experiment_config, run_experiment
from agenticapi.mock_api.server import MockAPIServer
from agenticapi.models import ExperimentConfig
from agenticapi.spec.graph import build_dependency_graph, graph_metrics
from agenticapi.spec.loader import load_spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agenticapi", description="AgenticAPI local research harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one or more experimental conditions")
    run.add_argument("--config", default=None, help="JSON experiment config")
    run.add_argument("--spec", default=None, help="OpenAPI/Swagger JSON file")
    run.add_argument("--conditions", default=None, help="comma-separated condition IDs")
    run.add_argument("--seeds", default=None, help="comma-separated integer seeds")
    run.add_argument("--no-faults", action="store_true", help="skip fault-injection runs")
    run.add_argument("--label", default="", help="run directory label")

    sub.add_parser("conditions", help="list experimental conditions")
    sub.add_parser("check", help="validate the default specification")
    mock = sub.add_parser("mock", help="serve the local mock API")
    mock.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    if args.command == "conditions":
        for condition in CONDITIONS.values():
            print(f"{condition.condition_id:24} {condition.description}")
        return 0
    if args.command == "check":
        config = ExperimentConfig()
        spec = load_spec(config.spec_path)
        graph = build_dependency_graph(spec)
        print(json.dumps(graph_metrics(spec, graph), indent=2, sort_keys=True))
        return 0
    if args.command == "mock":
        with MockAPIServer(port=args.port) as server:
            print(f"mock API listening on {server.base_url} (Ctrl-C to stop)")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                return 0
    if args.command == "run":
        config = load_experiment_config(args.config)
        if args.spec:
            config.spec_path = args.spec
        conditions = (
            [item.strip() for item in args.conditions.split(",") if item.strip()]
            if args.conditions
            else config.conditions or DEFAULT_CONDITIONS
        )
        seeds = (
            [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
            if args.seeds
            else config.seeds or [1]
        )
        summary = run_experiment(
            settings,
            config,
            condition_ids=conditions,
            seeds=seeds,
            run_faults=not args.no_faults,
            label=args.label,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
