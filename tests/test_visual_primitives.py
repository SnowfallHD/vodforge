from __future__ import annotations

import inspect
from types import SimpleNamespace

from yt_downloader import (
    focus_settings,
    library_annotation_ui,
    library_search_ui,
    local_audio_video_ui,
)
from yt_downloader.ui_widgets import (
    ActionDialogSurface,
    ChoiceDropdown,
    ModernCheckbox,
    ProductEntry,
)


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


def test_visible_product_surfaces_do_not_construct_native_entry_controls() -> None:
    modules = (
        focus_settings,
        library_annotation_ui,
        local_audio_video_ui,
    )

    for module in modules:
        assert "ttk.Entry(" not in inspect.getsource(module)


def test_product_entry_owns_flat_surface_and_focus_ring() -> None:
    source = inspect.getsource(ProductEntry)

    assert "class ProductEntry(ttk.Entry)" in source
    assert "style=prototype_entry_style(parent)" in source
    from yt_downloader.ui_chrome import ProductChromeOwner, prototype_entry_style

    chrome = inspect.getsource(ProductChromeOwner)
    assert '"field_focus"' in chrome
    assert '"Entry.textarea"' in chrome
    # Default application windows retain the canonical shared style. The
    # density-specific resolver remains the one interpreter-owned exception.
    assert (
        prototype_entry_style(SimpleNamespace(winfo_toplevel=lambda: SimpleNamespace()))
        == "Product.TEntry"
    )
    resolver = inspect.getsource(prototype_entry_style)
    assert 'name = f"Dpi{metrics.scale}.Product.TEntry"' in resolver
    assert "owner.entry_variants" in resolver
    assert "def apply_theme" in source


def test_scrollable_action_dialogs_use_shared_sleek_scrollbar() -> None:
    source = inspect.getsource(ActionDialogSurface)

    assert "SleekScrollbar(" in source
    assert "ttk.Scrollbar(" not in source


def test_choice_dropdown_owns_one_cohesive_surface_and_local_popover() -> None:
    source = inspect.getsource(ChoiceDropdown)

    assert "class ChoiceDropdown(tk.Frame)" in source
    assert "ChoicePopover(" in source
    assert "overrideredirect" not in source
    assert '"chevron-down"' in source
    assert 'self.event_generate("<<ComboboxSelected>>"' in source
    assert "self._popover" in source


def test_checkbox_uses_checkmark_asset_and_theme_owned_states() -> None:
    source = inspect.getsource(ModernCheckbox)

    assert '"check"' in source
    assert "size=(self._metrics.px(12), self._metrics.px(12))" in source
    assert "widget=self" in source
    assert 'THEME["accent_dark"]' in source
    assert 'THEME["surface"]' in source
    assert "not bool(self.variable.get())" in source
