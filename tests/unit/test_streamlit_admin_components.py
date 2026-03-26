from contextlib import nullcontext
from unittest.mock import MagicMock

from streamlit_admin import components


def test_section_title_with_subtitle(monkeypatch):
    subheader = MagicMock()
    caption = MagicMock()
    monkeypatch.setattr(components.st, "subheader", subheader)
    monkeypatch.setattr(components.st, "caption", caption)

    components.section_title("Title", "Sub")

    subheader.assert_called_once_with("Title")
    caption.assert_called_once_with("Sub")


def test_section_title_without_subtitle(monkeypatch):
    subheader = MagicMock()
    caption = MagicMock()
    monkeypatch.setattr(components.st, "subheader", subheader)
    monkeypatch.setattr(components.st, "caption", caption)

    components.section_title("Title")

    subheader.assert_called_once_with("Title")
    caption.assert_not_called()


def test_json_editor_valid_json(monkeypatch):
    # Verify apostrophes are handled correctly (not broken by .replace("'", '"'))
    input_val = {"text": "it's working"}
    text_area = MagicMock(return_value='{"text": "it\'s working"}')
    monkeypatch.setattr(components.st, "text_area", text_area)

    result = components.json_editor("k", value=input_val)

    assert result == {"text": "it's working"}
    # Check that it was called with correctly escaped JSON
    call_args = text_area.call_args
    assert '"it\'s working"' in call_args.kwargs["value"]


def test_json_editor_invalid_json_returns_empty(monkeypatch):
    warning = MagicMock()
    monkeypatch.setattr(components.st, "text_area", lambda *_args, **_kwargs: "{")
    monkeypatch.setattr(components.st, "warning", warning)

    assert components.json_editor("k") == {}
    warning.assert_called_once()


def test_save_bar_returns_button_result(monkeypatch):
    monkeypatch.setattr(
        components.st,
        "columns",
        lambda _spec: [nullcontext(), nullcontext(), nullcontext()],
    )
    monkeypatch.setattr(components.st, "button", lambda *_args, **_kwargs: True)

    assert components.save_bar("Save") is True


def test_show_error_and_success(monkeypatch):
    error = MagicMock()
    success = MagicMock()
    monkeypatch.setattr(components.st, "error", error)
    monkeypatch.setattr(components.st, "success", success)

    components.show_error(RuntimeError("boom"))
    components.show_success("ok")

    error.assert_called_once_with("boom")
    success.assert_called_once_with("ok")
