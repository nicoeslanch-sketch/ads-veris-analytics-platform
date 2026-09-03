"""Signed, non-executable artifacts for reusing an already-cleaned dataframe."""

from __future__ import annotations

import gzip
import hashlib
import hmac
import io
import json
from typing import Any

import pandas as pd


ARTIFACT_VERSION = 1
_MAGIC = b"ADSVERIS-CLEAN-V1\n"
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024


class InvalidCleanArtifact(ValueError):
    """The artifact is stale, malformed, too large, or not server-signed."""


def pack_clean_artifact(
    frame: pd.DataFrame,
    metadata: dict[str, Any],
    *,
    signing_key: str,
) -> bytes:
    """Serialize a dataframe without pickle and authenticate the exact payload."""

    if not signing_key:
        raise InvalidCleanArtifact("A signing key is required.")
    header = json.dumps(
        {
            "version": ARTIFACT_VERSION,
            "metadata": metadata,
            "attrs": frame.attrs,
            "rows": len(frame),
            "columns": [str(column) for column in frame.columns],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    table = frame.to_json(
        orient="table",
        date_format="iso",
        date_unit="ns",
        double_precision=15,
        force_ascii=False,
        index=True,
    ).encode("utf-8")
    raw = header + b"\n" + table
    if len(raw) > MAX_UNCOMPRESSED_BYTES:
        raise InvalidCleanArtifact("The clean artifact exceeds the safe size limit.")
    compressed = gzip.compress(raw, compresslevel=3)
    signature = hmac.new(
        signing_key.encode("utf-8"), compressed, hashlib.sha256
    ).hexdigest().encode("ascii")
    return _MAGIC + signature + b"\n" + compressed


def unpack_clean_artifact(
    payload: bytes,
    *,
    signing_key: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Verify before decompressing and validate the reconstructed frame shape."""

    if not signing_key or not payload.startswith(_MAGIC):
        raise InvalidCleanArtifact("Invalid clean artifact header.")
    remainder = payload[len(_MAGIC) :]
    try:
        supplied_signature, compressed = remainder.split(b"\n", 1)
    except ValueError as exc:
        raise InvalidCleanArtifact("Invalid clean artifact envelope.") from exc
    expected_signature = hmac.new(
        signing_key.encode("utf-8"), compressed, hashlib.sha256
    ).hexdigest().encode("ascii")
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise InvalidCleanArtifact("Invalid clean artifact signature.")
    try:
        raw = gzip.decompress(compressed)
    except (EOFError, OSError) as exc:
        raise InvalidCleanArtifact("Invalid clean artifact compression.") from exc
    if len(raw) > MAX_UNCOMPRESSED_BYTES:
        raise InvalidCleanArtifact("The clean artifact exceeds the safe size limit.")
    try:
        header_bytes, table_bytes = raw.split(b"\n", 1)
        header = json.loads(header_bytes.decode("utf-8"))
        frame = pd.read_json(io.StringIO(table_bytes.decode("utf-8")), orient="table")
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise InvalidCleanArtifact("Invalid clean artifact contents.") from exc
    if (
        not isinstance(header, dict)
        or header.get("version") != ARTIFACT_VERSION
        or int(header.get("rows", -1)) != len(frame)
        or header.get("columns") != [str(column) for column in frame.columns]
        or not isinstance(header.get("metadata"), dict)
        or not isinstance(header.get("attrs"), dict)
    ):
        raise InvalidCleanArtifact("The clean artifact schema does not match.")
    frame.attrs = header["attrs"]
    return frame, header["metadata"]
