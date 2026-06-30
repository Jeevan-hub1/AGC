"""Command-line runner for GEOS - run a scenario from the terminal.

Usage:
    python -m geos.cli hormuz_partial
    python -m geos.cli --black-swan hormuz_partial russia_secondary_sanctions
    python -m geos.cli --list
"""

from __future__ import annotations

import argparse
import json
import sys

from geos.agents import SupervisorOrchestrator
from geos.data.events import list_events


def _print_brief(result: dict) -> None:
    print("\n" + "=" * 70)
    print(f" EVENT: {result['event']['title']}")
    print("=" * 70)
    nb, na = result["neri_before"], result["neri_after"]
    print(f" NERI: {nb['score']} -> {na['score']}  ({na['band']})  "
          f"Δ {result['neri_delta']}")
    c = result["causal"]
    print(f" Brent: ${c['brent_usd']} (+{c['brent_change_pct']}%)  "
          f"CPI +{c['inflation_delta_pp']}pp  GDP {c['gdp_drag_pp']}pp")
    print(f" Decision brief: {result['decision_brief']['summary']}")
    print("\n AGENT FEED:")
    for a in result["agent_reports"]:
        print(f"  [{a['confidence']*100:.0f}%] {a['agent']}: {a['headline']}")
    print(f"\n Full national response in {result['total_elapsed_ms']} ms.\n")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="GEOS scenario runner")
    p.add_argument("event", nargs="*", help="event id(s)")
    p.add_argument("--black-swan", action="store_true", help="compound events")
    p.add_argument("--list", action="store_true", help="list available events")
    p.add_argument("--json", action="store_true", help="emit full JSON")
    p.add_argument("--runs", type=int, default=3000, help="Monte Carlo runs")
    args = p.parse_args(argv)

    if args.list:
        for e in list_events():
            print(f"  {e['id']:30s} {e['title']}")
        return 0

    if not args.event:
        p.error("provide an event id (or --list)")

    orch = SupervisorOrchestrator()
    if args.black_swan:
        result = orch.respond_black_swan(args.event, sim_runs=args.runs)
    else:
        result = orch.respond_to_id(args.event[0], sim_runs=args.runs)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_brief(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
