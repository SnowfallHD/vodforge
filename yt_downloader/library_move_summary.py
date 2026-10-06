"""Account for every selected entry in Move previews and terminal results."""

from collections import Counter

from .archive_file_operations import FileOperationPlan


def move_summary(plan: FileOperationPlan, outcomes=None) -> str:
    items = {item.owner: item for item in plan.items}
    entries = (
        outcomes if outcomes is not None else [(i.owner, i.state) for i in plan.items]
    )
    counts = Counter()
    for owner, state in entries:
        item = items.get(owner)
        if state in {"ready", "completed"}:
            counts["structure" if item and item.missing_media else "media"] += 1
        elif state == "already_in_target":
            counts["already"] += 1
        elif state == "conflict":
            counts["conflict"] += 1
        elif state == "ambiguous" or (item and item.reason == "hierarchy_root_unknown"):
            counts["unsupported"] += 1
        elif state in {"unavailable", "missing"}:
            counts["unavailable"] += 1
        elif state == "cancelled":
            counts["cancelled"] += 1
        else:
            counts["review"] += 1
    ready = outcomes is None
    labels = {
        "media": "media ready to move" if ready else "media moved",
        "structure": "missing-media folder structures ready to move"
        if ready
        else "missing-media folder structures moved",
        "already": "already in destination",
        "conflict": "destination conflicts, kept",
        "unsupported": "unsupported or ambiguous source layouts, kept",
        "unavailable": "missing or inaccessible sources, kept",
        "cancelled": "cancelled, kept or awaiting review",
        "review": "need review",
    }
    text = (
        f"{len(entries)} selected: "
        + "; ".join(
            f"{counts[key]} {label}" for key, label in labels.items() if counts[key]
        )
        + "."
    )
    if counts["structure"]:
        text += " Their media will remain missing."
    return text
