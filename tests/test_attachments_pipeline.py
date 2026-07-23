"""Increment 4 Group D — pure upload validation + image sanitization."""

from io import BytesIO

import pytest
from PIL import Image

from office_connect.core.attachments import pipeline
from office_connect.core.attachments.errors import RejectedUpload


def _jpeg(color=(255, 0, 0), size=(16, 16), *, with_exif=True) -> bytes:
    img = Image.new("RGB", size, color)
    buf = BytesIO()
    if with_exif:
        exif = img.getexif()
        exif[0x010E] = "SECRET ImageDescription"  # 0x010E = ImageDescription
        img.save(buf, "JPEG", exif=exif.tobytes())
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGBA", (8, 8), (0, 255, 0, 128)).save(buf, "PNG")
    return buf.getvalue()


def _webp() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), (0, 0, 255)).save(buf, "WEBP")
    return buf.getvalue()


def _pdf() -> bytes:
    return b"%PDF-1.4\n%stub pdf bytes for magic sniff\n"


def test_allowlist_accepts_known_types():
    assert pipeline.validate_upload(_jpeg(), max_bytes=10_000_000).media_kind == "image"
    assert pipeline.validate_upload(_png(), max_bytes=10_000_000).media_kind == "image"
    assert pipeline.validate_upload(_webp(), max_bytes=10_000_000).media_kind == "image"
    assert pipeline.validate_upload(_pdf(), max_bytes=10_000_000).media_kind == "pdf"


def test_svg_is_rejected():
    svg = b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'></svg>"
    with pytest.raises(RejectedUpload):
        pipeline.validate_upload(svg, max_bytes=10_000_000)
    with pytest.raises(RejectedUpload):
        pipeline.validate_upload(b"<svg></svg>", max_bytes=10_000_000)


def test_unknown_type_rejected():
    with pytest.raises(RejectedUpload):
        pipeline.validate_upload(b"MZ\x90\x00 not an image", max_bytes=10_000_000)
    with pytest.raises(RejectedUpload):
        pipeline.validate_upload(b"plain text, definitely not allowed", max_bytes=10_000_000)


def test_oversized_rejected():
    with pytest.raises(RejectedUpload):
        pipeline.validate_upload(_jpeg(), max_bytes=10)


def test_empty_rejected():
    with pytest.raises(RejectedUpload):
        pipeline.validate_upload(b"", max_bytes=10_000_000)


def test_reencode_strips_exif():
    original = _jpeg(with_exif=True)
    # Sanity: the ORIGINAL carries our EXIF tag.
    assert 0x010E in Image.open(BytesIO(original)).getexif()

    clean_bytes, mime = pipeline.reencode_image(original, "image/jpeg")
    assert mime == "image/jpeg"
    assert clean_bytes != original
    # The re-encoded copy carries no EXIF at all.
    assert dict(Image.open(BytesIO(clean_bytes)).getexif()) == {}


def test_reencode_preserves_dimensions():
    original = _jpeg(size=(20, 12), with_exif=False)
    clean_bytes, _ = pipeline.reencode_image(original, "image/jpeg")
    assert Image.open(BytesIO(clean_bytes)).size == (20, 12)


def test_decompression_bomb_rejected(monkeypatch):
    monkeypatch.setattr(pipeline, "_MAX_IMAGE_PIXELS", 50)  # 16x16=256 > 2*50
    with pytest.raises(RejectedUpload):
        pipeline.reencode_image(_jpeg(size=(16, 16), with_exif=False), "image/jpeg")


def test_heic_sniffs_and_reencodes_to_jpeg():
    import pillow_heif

    pillow_heif.register_heif_opener()
    buf = BytesIO()
    Image.new("RGB", (16, 16), (10, 20, 30)).save(buf, format="HEIF")
    heic = buf.getvalue()

    assert pipeline.sniff_mime(heic) == "image/heic"
    clean_bytes, mime = pipeline.reencode_image(heic, "image/heic")
    assert mime == "image/jpeg"
    assert pipeline.sniff_mime(clean_bytes) == "image/jpeg"
