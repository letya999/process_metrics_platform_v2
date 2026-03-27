from __future__ import annotations

from bi.providers.metabase.provider import MetabaseProvider


def get_provider(provider_name: str):
    normalized = provider_name.strip().lower()
    if normalized == "metabase":
        return MetabaseProvider()

    available = "metabase"
    raise ValueError(
        f"Unsupported BI provider '{provider_name}'. Available providers: {available}"
    )
