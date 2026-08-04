"""Core-service #3 — frozen snapshots: freeze, supersede, void, re-flag.

The service is polymorphic over ``(subject_kind, subject_id)`` and knows nothing
about claims, so these tests use a synthetic subject kind. What they pin down is
the state machine, because that is what an auditor reads: a routine reissue and
an invalidate-after-edit must never be the same recorded fact.
"""

from __future__ import annotations

from office_connect.core.attachments import upload_attachment
from office_connect.core.config import Settings
from office_connect.core.documents import (
    ACTIVE,
    SUPERSEDED,
    VOIDED,
    active_snapshots,
    find_active,
    freeze_snapshot,
    stale_snapshots,
    void_snapshots,
)
from office_connect.core.storage.local import LocalVolumeStorageDriver

SUBJECT = "test_subject"
PDF = b"%PDF-1.7\n% minimal\n"


def _settings(tmp_path) -> Settings:
    return Settings(storage_dir=str(tmp_path), app_env="local")


async def _attachment(session, tmp_path, *, payload: bytes = PDF) -> int:
    settings = _settings(tmp_path)
    result = await upload_attachment(
        session,
        payload,
        filename="doc.pdf",
        declared_mime="application/pdf",
        origin="generated",
        settings=settings,
        storage=LocalVolumeStorageDriver(settings),
    )
    return result.attachment_id


async def test_freeze_records_identity_hashes_and_timestamp(app_session, tmp_path):
    attachment_id = await _attachment(app_session, tmp_path)
    row = await freeze_snapshot(
        app_session,
        subject_kind=SUBJECT,
        subject_id=1,
        document_key="test.form",
        attachment_id=attachment_id,
        content_sha256="a" * 64,
        source_fingerprint="b" * 64,
        revision_no=1,
        actor_id=None,
    )

    assert row.status == ACTIVE
    assert row.content_sha256 == "a" * 64
    assert row.source_fingerprint == "b" * 64
    assert row.generated_at is not None
    assert row.is_draft is False


async def test_a_reissue_supersedes_rather_than_voiding(app_session, tmp_path):
    """The ordinary path. `superseded` is not `voided`, and the difference is the
    whole point: one is a routine reprint, the other says the data moved."""
    first_att = await _attachment(app_session, tmp_path)
    first = await freeze_snapshot(
        app_session,
        subject_kind=SUBJECT,
        subject_id=2,
        document_key="test.form",
        attachment_id=first_att,
        content_sha256="1" * 64,
        source_fingerprint="f1" + "0" * 62,
        is_draft=True,
    )
    second_att = await _attachment(app_session, tmp_path, payload=PDF + b"v2")
    second = await freeze_snapshot(
        app_session,
        subject_kind=SUBJECT,
        subject_id=2,
        document_key="test.form",
        attachment_id=second_att,
        content_sha256="2" * 64,
        source_fingerprint="f2" + "0" * 62,
        is_draft=False,
    )

    await app_session.refresh(first)
    assert first.status == SUPERSEDED
    assert first.voided_at is None  # a reissue is not an invalidation
    assert second.status == ACTIVE

    live = await find_active(
        app_session, subject_kind=SUBJECT, subject_id=2, document_key="test.form"
    )
    assert live is not None and live.id == second.id
    # The draft was retired by the official copy — exactly the submit-time flow.
    assert live.is_draft is False


async def test_void_records_why_and_who(app_session, tmp_path):
    attachment_id = await _attachment(app_session, tmp_path)
    await freeze_snapshot(
        app_session,
        subject_kind=SUBJECT,
        subject_id=3,
        document_key="test.form",
        attachment_id=attachment_id,
        content_sha256="3" * 64,
        source_fingerprint="c" * 64,
    )

    voided = await void_snapshots(
        app_session,
        subject_kind=SUBJECT,
        subject_id=3,
        reason="claim inputs changed",
    )

    assert len(voided) == 1
    assert voided[0].status == VOIDED
    assert voided[0].void_reason == "claim inputs changed"
    assert voided[0].voided_at is not None
    # Nothing is deleted — standing rule 6. The row stays, readable forever.
    assert await find_active(
        app_session, subject_kind=SUBJECT, subject_id=3, document_key="test.form"
    ) is None


async def test_voiding_is_quiet_when_there_is_nothing_to_void(app_session):
    """The common case on a first draft edit — it must not raise."""
    assert (
        await void_snapshots(
            app_session, subject_kind=SUBJECT, subject_id=999, reason="nothing"
        )
        == []
    )


async def test_stale_snapshots_is_the_modified_after_signature_re_flag(
    app_session, tmp_path
):
    a_id = await _attachment(app_session, tmp_path)
    b_id = await _attachment(app_session, tmp_path, payload=PDF + b"b")
    await freeze_snapshot(
        app_session,
        subject_kind=SUBJECT,
        subject_id=4,
        document_key="test.a",
        attachment_id=a_id,
        content_sha256="a" * 64,
        source_fingerprint="fingerprint-a",
    )
    await freeze_snapshot(
        app_session,
        subject_kind=SUBJECT,
        subject_id=4,
        document_key="test.b",
        attachment_id=b_id,
        content_sha256="b" * 64,
        source_fingerprint="fingerprint-b",
    )

    stale = await stale_snapshots(
        app_session,
        subject_kind=SUBJECT,
        subject_id=4,
        fingerprints={"test.a": "fingerprint-a", "test.b": "CHANGED"},
    )
    assert [row.document_key for row in stale] == ["test.b"]

    # It REPORTS; it does not void. Whether a divergence should invalidate a
    # signature is a workflow decision, not core's.
    assert len(await active_snapshots(
        app_session, subject_kind=SUBJECT, subject_id=4
    )) == 2

    # A key the caller did not ask about is skipped, not assumed stale.
    assert await stale_snapshots(
        app_session,
        subject_kind=SUBJECT,
        subject_id=4,
        fingerprints={"test.a": "fingerprint-a"},
    ) == []


async def test_snapshots_are_scoped_to_their_subject(app_session, tmp_path):
    a_id = await _attachment(app_session, tmp_path)
    await freeze_snapshot(
        app_session,
        subject_kind=SUBJECT,
        subject_id=5,
        document_key="test.form",
        attachment_id=a_id,
        content_sha256="5" * 64,
        source_fingerprint="x",
    )
    b_id = await _attachment(app_session, tmp_path, payload=PDF + b"other")
    await freeze_snapshot(
        app_session,
        subject_kind="other_kind",
        subject_id=5,
        document_key="test.form",
        attachment_id=b_id,
        content_sha256="6" * 64,
        source_fingerprint="y",
    )

    # Same id, different kind — the polymorphic key is the PAIR.
    mine = await active_snapshots(app_session, subject_kind=SUBJECT, subject_id=5)
    assert [row.content_sha256 for row in mine] == ["5" * 64]
