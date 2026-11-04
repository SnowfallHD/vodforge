"""UI-independent VODForge URL-list parsing."""

from __future__ import annotations


def parse_url_list_text(text: str) -> list[str]:
    urls: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("<") and line.endswith(">") and "|" in line:
            line = line[1:-1].split("|", 1)[0].strip()
        else:
            parts = line.split(maxsplit=1)
            if parts:
                line = parts[0].strip()
        if line.startswith(("http://", "https://")):
            urls.append(line)
    return urls
