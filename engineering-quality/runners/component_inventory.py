"""Run from the repository root; --write refreshes the reviewable inventory."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engineering-quality"))
from quality_harness.component_inventory import (
    refresh_control_families,
    scan_button_sites,
)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--write", action="store_true")
args = parser.parse_args()
actual = scan_button_sites(ROOT)
target = ROOT / "engineering-quality/acceptance/UI_COMPONENT_INVENTORY.json"
if args.write:
    target.write_text(json.dumps(actual, indent=2) + "\n")
    families = target.with_name("UI_CONTROL_FAMILIES.json")
    families.write_text(
        json.dumps(
            refresh_control_families(ROOT, json.loads(families.read_text())), indent=2
        )
        + "\n"
    )
expected = json.loads(target.read_text())


# Line movement alone does not imply a new component; changed callers and
# overrides do. Refresh line references when editing the relevant source.
def identities(value):
    return sorted(
        json.dumps({k: v for k, v in site.items() if k != "line"}, sort_keys=True)
        for site in value["sites"]
    )


print(
    json.dumps(
        {
            "counts": actual["counts"],
            "violations": actual["violations"],
            "inventory_matches": identities(actual) == identities(expected),
        },
        indent=2,
    )
)
raise SystemExit(
    bool(actual["violations"]) or identities(actual) != identities(expected)
)
