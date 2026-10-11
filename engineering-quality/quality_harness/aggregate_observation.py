"""Capture original source-suite observations while they occur."""

import hashlib
import json
import subprocess
import time

from .aggregate_interaction import AGGREGATE_CONTRACTS, SOURCE_SCOPE
from .source_identity import source_manifest


def ref(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")
    return ref(path)


def observe_source(root):
    try:
        return source_manifest(root)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        # Preserve missing authority as evidence, never infer a passing manifest.
        return {"observation_error": type(error).__name__}


class AggregateObservation:
    def __init__(self, sid, root, source_root):
        self.sid, self.root, self.source_root = sid, root, source_root
        self.started = time.monotonic()
        self.before = save(
            root / "aggregate-source-before.json", observe_source(source_root)
        )
        self.trace = [{"phase": "before_suite", "elapsed_seconds": 0.0}]

    def finish(self, scenario, **details):
        self.trace.append(
            {
                "phase": "suite_returned",
                "elapsed_seconds": time.monotonic() - self.started,
            }
        )
        after = save(
            self.root / "aggregate-source-after.json", observe_source(self.source_root)
        )
        self.trace.append(
            {
                "phase": "authority_reobserved",
                "elapsed_seconds": time.monotonic() - self.started,
            }
        )
        raw = {
            "scenario_id": self.sid,
            "contract": AGGREGATE_CONTRACTS[self.sid],
            "scope": SOURCE_SCOPE,
            "source_root": str(self.source_root),
            "source_before": self.before,
            "source_after": after,
            "trace": self.trace,
            **details,
        }
        path = self.root / "aggregate-observation.json"
        save(path, raw)
        scenario.update(raw_result=str(path), raw_result_sha256=ref(path)["sha256"])
        return scenario
