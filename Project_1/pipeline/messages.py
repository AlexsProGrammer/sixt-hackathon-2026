"""Chat message builders for text, native PDF and rendered page images. Pure functions, no network.

Each builder returns (messages, input_kind, attachment_sha256) for the reply-cache key:
  input_kind in {"text", "pdf", "png"}; attachment_sha256 is None for text.
Use key_messages(messages) for hashing: attachment data URIs are replaced by a placeholder, so the cache key never
contains base64 bytes and depends on the attachment only through attachment_sha256.
"""
from __future__ import annotations

import base64
import copy
import hashlib
from pathlib import Path

ATTACHMENT_PLACEHOLDER = "<attachment>"
PDF_MODES = ("file", "image_url")


def _data_uri(mime: str, data: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def text_messages(prompt: str, text: str) -> tuple[list[dict], str, None]:
    content = f"{prompt}\n--- DOCUMENT TEXT (data) ---\n{text}\n--- END OF DOCUMENT TEXT ---"
    return [{"role": "user", "content": content}], "text", None


def pdf_messages(prompt: str, pdf_bytes: bytes, mode: str = "file") -> tuple[list[dict], str, str]:
    """mode 'file': {"type":"file","file":{"file_data": data-uri}}; mode 'image_url': {"type":"image_url", ...}."""
    if mode not in PDF_MODES:
        raise ValueError(f"unknown pdf mode: {mode}")
    uri = _data_uri("application/pdf", pdf_bytes)
    if mode == "file":
        part = {"type": "file", "file": {"file_data": uri}}
    else:
        part = {"type": "image_url", "image_url": {"url": uri}}
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}, part]}]
    return messages, "pdf", hashlib.sha256(pdf_bytes).hexdigest()


def png_messages(prompt: str, pngs: list[Path | bytes]) -> tuple[list[dict], str, str]:
    """One image_url part per page, in page order. pngs are paths or raw PNG bytes."""
    if not pngs:
        raise ValueError("png_messages needs at least one image")
    parts: list[dict] = [{"type": "text", "text": prompt}]
    digests = []
    for item in pngs:
        data = item if isinstance(item, (bytes, bytearray)) else Path(item).read_bytes()
        digests.append(hashlib.sha256(data).hexdigest())
        parts.append({"type": "image_url", "image_url": {"url": _data_uri("image/png", bytes(data))}})
    sha = digests[0] if len(digests) == 1 else hashlib.sha256("".join(digests).encode("ascii")).hexdigest()
    return [{"role": "user", "content": parts}], "png", sha


def key_messages(messages: list[dict]) -> list[dict]:
    """Copy of messages with every base64 data URI replaced by a placeholder (structure and mime type are kept)."""
    def scrub(url: str) -> str:
        if url.startswith("data:") and ";base64," in url:
            return url.split(";base64,", 1)[0] + ";base64," + ATTACHMENT_PLACEHOLDER
        return url

    out = copy.deepcopy(messages)
    for m in out:
        content = m.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if isinstance(part.get("image_url"), dict) and isinstance(part["image_url"].get("url"), str):
                part["image_url"]["url"] = scrub(part["image_url"]["url"])
            if isinstance(part.get("file"), dict) and isinstance(part["file"].get("file_data"), str):
                part["file"]["file_data"] = scrub(part["file"]["file_data"])
    return out
