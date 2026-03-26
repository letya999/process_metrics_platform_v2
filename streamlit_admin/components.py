"""Shared Streamlit components for admin studio."""

import json
from typing import Any

import streamlit as st


def section_title(title: str, subtitle: str | None = None) -> None:
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def json_editor(key: str, value: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = st.text_area(
        "JSON",
        value=(
            "{}" if value is None else json.dumps(value, ensure_ascii=False, indent=2)
        ),
        key=key,
        height=120,
    )
    try:
        return json.loads(raw)
    except Exception:
        st.warning("Invalid JSON; fallback to {}")
        return {}


def save_bar(label: str = "Save") -> bool:
    cols = st.columns([1, 1, 6])
    with cols[0]:
        return st.button(label, type="primary", use_container_width=True)


def show_error(err: Exception) -> None:
    st.error(str(err))


def show_success(message: str) -> None:
    st.success(message)
