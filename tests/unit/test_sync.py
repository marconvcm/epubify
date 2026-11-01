import copy
import ssl
from pathlib import Path

import pytest

from epub_reader.domain.models.reading_progress import ReadingLocation, ReadingProgress
from epub_reader.infrastructure.database.engine import create_database
from epub_reader.infrastructure.database.repositories import PreferenceRepository
from epub_reader.infrastructure.sync.crypto import (
    Identity,
    Invitations,
    fingerprint,
    private_host,
    verify_record,
)
from epub_reader.infrastructure.sync.records import (
    SyncError,
)
from epub_reader.infrastructure.sync.store import SyncStore
from epub_reader.services.annotation_service import AnnotationService
from tests.fixtures.epub_factory import make_epub


@pytest.fixture
def stores(tmp_path: Path):
    engines = [create_database(tmp_path / name / "library.sqlite3") for name in ("a", "b")]
    stores = [
        SyncStore(engine, tmp_path / name, Identity(tmp_path / name / "sync/identity"))
        for engine, name in zip(engines, ("a", "b"), strict=True)
    ]
    yield stores
    for engine in engines:
        engine.dispose()


def exchange(first: SyncStore, second: SyncStore) -> None:
    for record in first.records():
        second.merge(record.wire())
    for record in second.records():
        first.merge(record.wire())


def install_fixture(first: SyncStore, second: SyncStore, tmp_path: Path) -> tuple[str, str, str]:
    book = first.importer.import_book(
        make_epub(tmp_path / "book.epub", title="Python Robotics Projects")
    )
    first.books.save_progress(
        book.id, ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 120).encode(), 0.3)
    )
    first.snapshot()
    exchange(first, second)
    identifier = next(record.key for record in first.records() if record.kind == "book")
    archive, _, _ = first.export(identifier)
    remote_id = second.install_book(identifier, archive)
    return book.id, remote_id, identifier


def test_pairing_invitation_is_bound_expiring_and_single_use(tmp_path: Path) -> None:
    identity = Identity(tmp_path / "identity")
    restored = Identity(tmp_path / "identity")
    assert restored.id == identity.id
    invitations = Invitations()
    text = invitations.create("127.0.0.1", 38477, identity.id)
    data = invitations.parse(text)
    assert data["pin"] == identity.id
    assert not invitations.consume("invalid")
    assert invitations.consume(data["token"])
    assert not invitations.consume(data["token"])
    invitations.create("127.0.0.1", 38477, identity.id)
    invitations._expires = 0
    assert not invitations.consume(data["token"])
    with pytest.raises(SyncError):
        Invitations.parse("https://example.org")
    for invalid in ("8.8.8.8", "example.org", "0.0.0.0", "224.0.0.251"):
        with pytest.raises(SyncError):
            private_host(invalid)


def test_signed_records_reject_tampering_and_unsafe_values(stores) -> None:
    first, second = stores
    record = first.identity.record("preference", "dark", {"value": True}, {first.identity.id: 1})
    verify_record(record)
    second.merge(record.wire())
    changed = copy.deepcopy(record.wire())
    changed["value"]["value"] = False
    with pytest.raises(SyncError, match="signature"):
        second.merge(changed)
    changed = copy.deepcopy(record.wire())
    changed["key"] = "data_directory"
    with pytest.raises(SyncError, match="preference"):
        second.merge(changed)
    changed = copy.deepcopy(record.wire())
    changed["updated_ms"] = 10**16
    with pytest.raises(SyncError, match="clocks"):
        second.merge(changed)
    assert PreferenceRepository(second.engine).get("dark", False) is True


def test_book_transfer_identity_and_progress_are_portable_and_do_not_echo(
    stores, tmp_path: Path
) -> None:
    first, second = stores
    local_id, remote_id, identifier = install_fixture(first, second, tmp_path)
    assert second.has_book(identifier)
    remote = second.books.get(remote_id)
    assert remote.title == "Python Robotics Projects"
    assert remote.progress == 0.3
    assert remote.location == first.books.get(local_id).location
    heads = {record.id for record in first.records()}
    second.snapshot()
    assert {record.id for record in second.records()} == heads
    second.books.set_favorite(remote_id, True)
    second.snapshot()
    exchange(first, second)
    assert first.books.get(local_id).favorite
    assert len(first.books.list()) == len(second.books.list()) == 1


def test_concurrent_reading_conflict_converges_and_can_be_resolved(stores, tmp_path: Path) -> None:
    first, second = stores
    local_id, remote_id, identifier = install_fixture(first, second, tmp_path)
    first.books.save_progress(
        local_id, ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 180).encode(), 0.4)
    )
    second.books.save_progress(
        remote_id, ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 360).encode(), 0.6)
    )
    first.snapshot()
    second.snapshot()
    exchange(first, second)
    assert first.books.get(local_id).location == second.books.get(remote_id).location
    conflicts = first.conflicts()
    assert len(conflicts) == 1 and conflicts[0]["kind"] == "progress"
    chosen = next(
        choice for choice in conflicts[0]["choices"] if choice["value"]["fraction"] == 0.4
    )
    first.resolve("progress", identifier, chosen["id"])
    exchange(first, second)
    assert first.books.get(local_id).progress == second.books.get(remote_id).progress == 0.4
    assert not first.conflicts() and not second.conflicts()


def test_preference_keys_merge_independently_and_notes_sync(stores, tmp_path: Path) -> None:
    first, second = stores
    local_id, remote_id, _ = install_fixture(first, second, tmp_path)
    PreferenceRepository(first.engine).set("dark", False)
    PreferenceRepository(second.engine).set("language", "pt")
    notes = AnnotationService(first.engine)
    notes.add(
        local_id, ReadingLocation("EPUB/chapter1.xhtml", 180).encode(), "A note stored locally"
    )
    first.snapshot()
    second.snapshot()
    exchange(first, second)
    assert PreferenceRepository(second.engine).get("dark", True) is False
    assert PreferenceRepository(first.engine).get("language", "en") == "pt"
    copied = AnnotationService(second.engine).notes(remote_id)
    assert copied[0]["text"] == "A note stored locally"
    notes.update(local_id, copied[0]["id"], "A changed note")
    AnnotationService(second.engine).remove(remote_id, copied[0]["id"])
    first.snapshot()
    second.snapshot()
    exchange(first, second)
    assert not notes.notes(local_id)
    assert not AnnotationService(second.engine).notes(remote_id)
    assert any(conflict["kind"] == "annotation" for conflict in first.conflicts())


def test_book_identity_mismatch_cannot_enter_the_library(stores, tmp_path: Path) -> None:
    first, second = stores
    first.importer.import_book(make_epub(tmp_path / "book.epub"))
    first.snapshot()
    identifier = next(record.key for record in first.records() if record.kind == "book")
    archive, _, _ = first.export(identifier)
    with pytest.raises(ValueError, match="identity"):
        second.install_book("a" * 64, archive)
    assert second.books.list() == []


def test_tls13_encrypts_payload_and_certificate_pin_is_checkable_without_network(
    tmp_path: Path,
) -> None:
    identity = Identity(tmp_path / "identity")
    incoming_client, outgoing_client, incoming_server, outgoing_server = [
        ssl.MemoryBIO() for _ in range(4)
    ]
    client = Identity.client_context().wrap_bio(
        incoming_client, outgoing_client, server_hostname="epubify.local"
    )
    server = identity.server_context().wrap_bio(incoming_server, outgoing_server, server_side=True)
    client_ready = server_ready = False
    for _ in range(20):
        if not client_ready:
            try:
                client.do_handshake()
                client_ready = True
            except ssl.SSLWantReadError:
                pass
        if outgoing_client.pending:
            incoming_server.write(outgoing_client.read())
        if not server_ready:
            try:
                server.do_handshake()
                server_ready = True
            except ssl.SSLWantReadError:
                pass
        if outgoing_server.pending:
            incoming_client.write(outgoing_server.read())
        if client_ready and server_ready:
            break
    assert client_ready and server_ready
    assert client.version() == "TLSv1.3"
    assert fingerprint(client.getpeercert(binary_form=True)) == identity.id
    secret = b"A private book title and reading position"
    client.write(secret)
    encrypted = outgoing_client.read()
    assert secret not in encrypted
    incoming_server.write(encrypted)
    assert server.read() == secret


def test_incoming_progress_preserves_unsnapshotted_local_edit(stores, tmp_path: Path) -> None:
    first, second = stores
    local_id, remote_id, _ = install_fixture(first, second, tmp_path)
    first.books.save_progress(
        local_id, ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 230).encode(), 0.5)
    )
    second.books.save_progress(
        remote_id, ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 400).encode(), 0.8)
    )
    second.snapshot()
    for record in second.records():
        first.merge(record.wire())
    conflict = next(item for item in first.conflicts() if item["kind"] == "progress")
    assert {item["value"]["fraction"] for item in conflict["choices"]} == {0.5, 0.8}


def test_revoked_author_cannot_reenter_through_a_relay(stores) -> None:
    first, second = stores
    second.trust(first.identity.id, "First", first.identity.pem, "127.0.0.1", 1234)
    second.revoke(first.identity.id)
    record = first.identity.record("preference", "dark", {"value": False}, {first.identity.id: 1})
    assert second.merge(record.wire()) == {"books": [], "preferences": []}
    assert PreferenceRepository(second.engine).get("dark", True) is True


def test_identity_pin_rejects_an_untrusted_tls_certificate(tmp_path: Path) -> None:
    from epub_reader.infrastructure.sync.crypto import verify_server_pin

    first, second = [Identity(tmp_path / name) for name in ("first", "second")]
    der = ssl.PEM_cert_to_DER_cert(first.pem)
    verify_server_pin(der, first.id)
    with pytest.raises(SyncError, match="certificate"):
        verify_server_pin(der, second.id)
