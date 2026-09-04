from __future__ import annotations

import inspect

from yt_downloader import (
    focus_settings,
    library_annotation_ui,
    library_search_ui,
    local_audio_video_ui,
)
from yt_downloader.ui_widgets import ChoiceDropdown, ModernCheckbox


def test_visible_product_surfaces_do_not_construct_native_combo_or_check_controls() -> (
    None
):
    modules = (
        focus_settings,
        library_annotation_ui,
        library_search_ui,
        local_audio_video_ui,
    )

    for module in modules:
        source = inspect.getsource(module)
        assert "ttk.Combobox(" not in source
        assert "ttk.Checkbutton(" not in source


def test_choice_dropdown_owns_one_cohesive_surface_and_local_popover() -> None:
    source = inspect.getsource(ChoiceDropdown)

    assert "class ChoiceDropdown(tk.Frame)" in source
    assert "popup.overrideredirect(True)" in source
    assert '"chevron-down"' in source
    assert 'self.event_generate("<<ComboboxSelected>>"' in source
    assert "self._popover" in source


def test_checkbox_uses_checkmark_asset_and_theme_owned_states() -> None:
    source = inspect.getsource(ModernCheckbox)

    assert '"check"' in source
    assert "size=(12, 12)" in source
    assert 'THEME["accent_dark"]' in source
    assert 'THEME["surface"]' in source
    assert "not bool(self.variable.get())" in source
