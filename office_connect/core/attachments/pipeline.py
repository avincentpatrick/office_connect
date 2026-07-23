"""Pure upload validation + image sanitization — no DB, no storage, no network.

- ``validate_upload`` enforces the stream/byte cap and the **magic-byte
  allowlist** (JPEG/PNG/WebP/PDF/HEIC). Type is decided by sniffed bytes, never
  the client ``Content-Type`` or extension. SVG/XML is explicitly rejected (script
  XSS vector); anything unrecognized is default-denied.
- ``reencode_image`` re-encodes an image through Pillow, reconstructing the pixel
  data into a fresh object so **all EXIF/XMP/ICC metadata is dropped** (GPS never
  leaves via the app), converting HEIC→JPEG, and guarding against decompression
  bombs.

Kept import-safe: Pillow / pillow-heif are imported lazily inside the functions
that use them, so importing this module needs neither installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from office_connect.core.attachments.errors import RejectedUpload

# HEIF "ftyp" brands we accept (still-image HEIC/HEIF).
_HEIF_BRANDS = frozenset(
    {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"heim", b"heis"}
)

# sniffed MIME → media_kind. The whole allowlist lives here (default-deny).
_ALLOWED: dict[str, str] = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/heic": "image",
    "application/pdf": "pdf",
}

# sniffed image MIME → (Pillow save format, served MIME). HEIC normalizes to JPEG.
_REENCODE: dict[str, tuple[str, str]] = {
    "image/jpeg": ("JPEG", "image/jpeg"),
    "image/png": ("PNG", "image/png"),
    "image/webp": ("WEBP", "image/webp"),
    "image/heic": ("JPEG", "image/jpeg"),
}

# Ceiling for Pillow's decompression-bomb guard (~40 MP).
_MAX_IMAGE_PIXELS = 40_000_000


@dataclass(frozen=True)
class ValidatedUpload:
    sniffed_mime: str
    media_kind: str  # 'image' | 'pdf'


def sniff_mime(data: bytes) -> str | None:
    """Return the allowlisted MIME from magic bytes, or None if unrecognized."""
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "image/heic"
    return None


def _looks_like_xml(data: bytes) -> bool:
    head = data.lstrip()[:6].lower()
    return head.startswith(b"<?xml") or head.startswith(b"<svg")


def validate_upload(
    data: bytes, *, max_bytes: int, declared_mime: str | None = None
) -> ValidatedUpload:
    """Enforce size cap + magic-byte allowlist. Raise ``RejectedUpload`` on fail."""
    if not data:
        raise RejectedUpload("empty upload")
    if len(data) > max_bytes:
        raise RejectedUpload(
            f"upload is {len(data)} bytes; limit is {max_bytes}"
        )
    if _looks_like_xml(data):
        raise RejectedUpload("SVG/XML uploads are not allowed")
    sniffed = sniff_mime(data)
    if sniffed is None or sniffed not in _ALLOWED:
        raise RejectedUpload(
            f"disallowed or unrecognized file type (declared={declared_mime!r})"
        )
    return ValidatedUpload(sniffed_mime=sniffed, media_kind=_ALLOWED[sniffed])


def reencode_image(data: bytes, sniffed_mime: str) -> tuple[bytes, str]:
    """Re-encode an image, stripping all metadata. Returns ``(bytes, served_mime)``.

    HEIC→JPEG. Raises ``RejectedUpload`` on a decompression bomb or undecodable
    image.
    """
    if sniffed_mime not in _REENCODE:
        raise RejectedUpload(f"cannot re-encode {sniffed_mime!r}")

    from PIL import Image, ImageOps, UnidentifiedImageError

    # Register the HEIF opener so Image.open handles HEIC input.
    if sniffed_mime == "image/heic":
        import pillow_heif

        pillow_heif.register_heif_opener()

    Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS
    save_format, served_mime = _REENCODE[sniffed_mime]

    try:
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img) or img  # bake orientation, then drop it
            if save_format == "JPEG":
                img = img.convert("RGB")
            elif img.mode == "P":
                img = img.convert("RGBA")
            # Reconstruct pixels into a fresh object → no EXIF/XMP/ICC survives.
            clean = Image.new(img.mode, img.size)
            clean.putdata(list(img.getdata()))
            out = BytesIO()
            clean.save(out, format=save_format)
    except Image.DecompressionBombError as exc:
        raise RejectedUpload(f"image too large (decompression bomb): {exc}") from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise RejectedUpload(f"undecodable image: {exc}") from exc

    return out.getvalue(), served_mime
