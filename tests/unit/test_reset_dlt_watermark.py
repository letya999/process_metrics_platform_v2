"""Unit tests for the dlt watermark reset utility.

Verifies encode/decode round-trip and that the reset produces a valid
state blob with the expected last_value.
"""

import base64
import json
import zlib

from scripts.reset_dlt_watermark import _decode_state, _encode_state


def _make_state(pipeline_name: str, last_value: str, version: int = 1) -> dict:
    return {
        "_state_version": version,
        "_state_engine_version": 4,
        "pipeline_name": pipeline_name,
        "dataset_name": "raw_jira",
        "schema_names": ["jira"],
        "default_schema_name": "jira",
        "destination_type": "dlt.destinations.postgres",
        "destination_name": None,
        "_version_hash": "test-hash",
        "sources": {
            "jira": {
                "resources": {
                    "issues": {
                        "incremental": {
                            "fields.updated": {
                                "initial_value": "1970-01-01T00:00:00.000+0000",
                                "last_value": last_value,
                                "unique_hashes": ["abc123"],
                            }
                        }
                    }
                }
            }
        },
    }


class TestEncodeDecodeRoundTrip:
    def test_decode_then_encode_is_stable(self):
        original = _make_state("jira_raw_TWAD", "2026-03-27T17:56:15.157+0300")
        blob = _encode_state(original)
        decoded = _decode_state(blob)
        assert decoded == original

    def test_encoded_blob_is_valid_zlib_base64(self):
        """dlt decompresses with plain zlib.decompress() — must be zlib format, not gzip."""
        state = _make_state("jira_raw_TWAD", "2026-03-18T00:00:00.000+0300")
        blob = _encode_state(state)
        raw = base64.b64decode(blob)
        # Must decompress with plain zlib (no wbits) — exactly how dlt does it
        decompressed = zlib.decompress(raw)
        parsed = json.loads(decompressed)
        assert parsed["pipeline_name"] == "jira_raw_TWAD"

    def test_decode_real_state_blob(self):
        """Decode the actual TWAD v7 blob captured from production DB."""
        real_blob = (
            "eNpVUGFPwjAQ/S/9CsxuA5Yt8YMBJZjwAYJRMaY5WdmKXTd6LQaI/92Ogc7mmrbv7t271xNh"
            "aMBwtucaRalIEnWvEFeZUK1Mv0tSvgErDcN1zgtgCgpOErIVGkiXVKLisma0YKbhiy2f78Yun4"
            "IB5OaarjMXZqsdkuStafhey6ERCoyTZ+ZQ1axUGq8Fo1eVaDLteP/LGxFlpXR+LhZYDpi7Hk+b"
            "3Kz0bvH4cIinL5Px681sqMvJHrOP+UjPzSqcFZBtj2X4eVtPV1q9rgc7NYO50+n9gQLRXm5qr"
            "XnBlQFZPzeCyxQ9WznnPG0KhBEg2R6krd34cUR71HexpDQ5h0cp7bhNnbIENL+1AQ2GPRr2gmj"
            "pR8lgmPgDzx9EHRqea60SO8vPFptP7Ic+3sfHPJ7aeYDgj0eLgLx/N+sHVDaqTg=="
        )
        state = _decode_state(real_blob)
        lv = state["sources"]["jira"]["resources"]["issues"]["incremental"][
            "fields.updated"
        ]["last_value"]
        assert lv == "2026-03-27T17:56:15.157+0300"
        assert state["pipeline_name"] == "jira_raw_TWAD"


class TestResetWatermarkLogic:
    def test_reset_changes_last_value_and_clears_hashes(self):
        original = _make_state("jira_raw_TWAD", "2026-03-27T17:56:15.157+0300")
        blob = _encode_state(original)

        # Simulate the reset operation
        state = _decode_state(blob)
        state["sources"]["jira"]["resources"]["issues"]["incremental"][
            "fields.updated"
        ]["last_value"] = "2026-03-18T00:00:00.000+0000"
        state["sources"]["jira"]["resources"]["issues"]["incremental"][
            "fields.updated"
        ]["unique_hashes"] = []

        new_blob = _encode_state(state)
        result = _decode_state(new_blob)

        lv = result["sources"]["jira"]["resources"]["issues"]["incremental"][
            "fields.updated"
        ]["last_value"]
        hashes = result["sources"]["jira"]["resources"]["issues"]["incremental"][
            "fields.updated"
        ]["unique_hashes"]

        assert lv == "2026-03-18T00:00:00.000+0000"
        assert hashes == []
