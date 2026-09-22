"""Bound work to visible text while preserving the full-line counting API."""

import pytest

from yt_downloader.ui_layout import ellipsize_wrapped_text, measured_wrapped_line_count


@pytest.mark.parametrize("lines", [1, 2, 3])
def test_long_title_fit_does_not_measure_every_invisible_line(lines):
    calls = []

    def measure(text):
        calls.append(text)
        return len(text)

    value = "x" * 2000
    fitted = ellipsize_wrapped_text(
        value, maximum_width=20, maximum_lines=lines, measure_width=measure
    )
    assert fitted == "x" * (20 * lines - 1) + "…"
    # A 2000-character title needs at most 12 outer prefix decisions.
    # Each visible line needs at most 12 width probes, plus overflow checks.
    # This structural budget is independent of machine speed.
    assert len(calls) <= 12 * (lines * 12 + 3)


@pytest.mark.parametrize("length", [0, 1, 19, 20, 21, 39, 40, 41, 2000])
@pytest.mark.parametrize("lines", [1, 2, 3])
def test_fitted_monospaced_title_preserves_exact_visible_capacity(length, lines):
    value = "x" * length
    fitted = ellipsize_wrapped_text(
        value, maximum_width=20, maximum_lines=lines, measure_width=len
    )
    expected = value if length <= lines * 20 else "x" * (lines * 20 - 1) + "…"
    assert fitted == expected


def test_full_line_count_remains_exact_for_long_documents():
    assert (
        measured_wrapped_line_count("x" * 2000, maximum_width=20, measure_width=len)
        == 100
    )
    assert (
        measured_wrapped_line_count(
            "\n".join(["row"] * 100), maximum_width=20, measure_width=len
        )
        == 100
    )


def test_each_prefix_is_measured_once_within_a_fit_but_not_across_fonts():
    value = "mountains and forests " * 90
    calls = []

    def measure(text):
        calls.append(text)
        return len(text)

    fitted = ellipsize_wrapped_text(
        value, maximum_width=25, maximum_lines=2, measure_width=measure
    )
    assert fitted.endswith("…")
    assert len(calls) == len(set(calls)), (
        "Repeated prefixes must reuse local measurements"
    )
    narrow = ellipsize_wrapped_text(
        value,
        maximum_width=25,
        maximum_lines=2,
        measure_width=lambda text: len(text) * 2,
    )
    assert len(narrow) < len(fitted), "Font measurements must not leak into another fit"
