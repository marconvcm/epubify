import asyncio
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from epub_reader.domain.models.reading_progress import ReadingLocation, ReadingProgress
from epub_reader.infrastructure.database.engine import create_database
from epub_reader.infrastructure.sync.crypto import Identity, Invitations
from epub_reader.infrastructure.sync.records import canonical
from epub_reader.infrastructure.sync.store import SyncStore
from epub_reader.infrastructure.sync.transport import Node
from epub_reader.services.annotation_service import AnnotationService
from tests.fixtures.epub_factory import make_epub

CLOSED = object()


class MemorySocket:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.other = None
        self.request = SimpleNamespace(path="/sync")
        self.remote_address = ("127.0.0.1", 1234)
        self.closed = False

    async def send(self, packet):
        if self.closed:
            raise ConnectionError("closed")
        await self.other.incoming.put(packet)

    async def recv(self):
        packet = await self.incoming.get()
        if packet is CLOSED:
            raise ConnectionError("closed")
        return packet

    async def close(self, **kwargs):
        self.closed = True
        await self.other.incoming.put(CLOSED)
        await self.incoming.put(CLOSED)


@pytest.mark.parametrize("metadata_already_received", [False, True])
def test_authenticated_protocol_transfers_books_over_bounded_message_channels(
    tmp_path: Path,
    monkeypatch,
    metadata_already_received: bool,
) -> None:
    """Exercise the complete application protocol; TLS is independently tested with MemoryBIO."""

    async def inline(function, *args, **kwargs):
        # This transport test runs without OS sockets, including asyncio's
        # cross-thread wakeup socket, which is denied by restricted runners.
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline)

    async def scenario():
        roots = [tmp_path / name for name in ("a", "b")]
        engines = [create_database(root / "library.sqlite3") for root in roots]
        stores = [
            SyncStore(engine, root, Identity(root / "identity"))
            for engine, root in zip(engines, roots, strict=True)
        ]
        first, second = stores
        book = first.importer.import_book(make_epub(tmp_path / "source.epub", title="A peer book"))
        first.books.save_progress(
            book.id, ReadingProgress(ReadingLocation("EPUB/chapter1.xhtml", 120).encode(), 0.3)
        )
        AnnotationService(first.engine).add(
            book.id, ReadingLocation("EPUB/chapter1.xhtml", 120).encode(), "A transferred note"
        )
        for index in range(10):
            first.importer.import_book(
                make_epub(tmp_path / f"extra-{index}.epub", title=f"Book {index}")
            )
        first.snapshot()
        if metadata_already_received:
            for record in first.records():
                second.merge(record.wire())
        events = []
        server = Node(
            first, "First", lambda kind, data: events.append((kind, data)), discovery=False
        )
        client = Node(
            second, "Second", lambda kind, data: events.append((kind, data)), discovery=False
        )
        server_ws, client_ws = MemorySocket(), MemorySocket()
        server_ws.other = client_ws
        client_ws.other = server_ws
        invitation = Invitations.parse(
            server.invitations.create("127.0.0.1", 38477, first.identity.id)
        )
        handler = asyncio.create_task(server._accept(server_ws))
        session = None
        try:
            import json

            challenge = json.loads(await client_ws.recv())
            transcript = canonical(
                {
                    "protocol": 1,
                    "nonce": challenge["nonce"],
                    "server": first.identity.id,
                    "client": second.identity.id,
                }
            )
            await client_ws.send(
                canonical(
                    {
                        "type": "auth",
                        "id": second.identity.id,
                        "name": "Second",
                        "certificate": second.identity.pem,
                        "signature": second.identity.sign(transcript),
                        "token": invitation["token"],
                        "port": 38478,
                    }
                ).decode()
            )
            ready = json.loads(await client_ws.recv())
            assert ready["type"] == "ready"
            second.trust(first.identity.id, "First", first.identity.pem, "127.0.0.1", 38477)
            session = asyncio.create_task(client._session(client_ws, first.identity.id))

            async def wait_for_book():
                while len(second.books.list()) != 11:
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait_for_book(), timeout=5)
            assert book.title in {item.title for item in second.books.list()}
            remote = next(item for item in second.books.list() if item.title == book.title)
            assert remote.progress == 0.3
            assert (
                AnnotationService(second.engine).notes(remote.id)[0]["text"] == "A transferred note"
            )
            assert first.peer(second.identity.id)["enabled"]
            assert second.peer(first.identity.id)["enabled"]
            assert any(kind == "changed" and data.get("books") for kind, data in events)
        finally:
            await client_ws.close()
            if session:
                session.cancel()
            handler.cancel()
            await asyncio.gather(*([session] if session else []), handler, return_exceptions=True)
            for engine in engines:
                engine.dispose()

    asyncio.run(scenario())


def test_two_nodes_pair_and_transfer_over_real_tls_websockets(tmp_path: Path) -> None:
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
    except PermissionError:
        pytest.skip("This runner denies local socket binding; run this test outside the sandbox.")

    async def scenario():
        events = []
        engines, stores, nodes = [], [], []
        for name in ("server", "client"):
            root = tmp_path / name
            engine = create_database(root / "library.sqlite3")
            engines.append(engine)
            store = SyncStore(engine, root, Identity(root / "identity"))
            stores.append(store)
            nodes.append(
                Node(store, name, lambda kind, data: events.append((kind, data)), discovery=False)
            )
        stores[0].importer.import_book(make_epub(tmp_path / "source.epub", title="TLS book"))
        stores[0].snapshot()
        tasks = [asyncio.create_task(node.run()) for node in nodes]
        try:
            async with asyncio.timeout(20):
                while sum(kind == "ready" for kind, _ in events) < 2:
                    for task in tasks:
                        if task.done():
                            task.result()
                    await asyncio.sleep(0.01)
                pairing = asyncio.create_task(nodes[1].pair(nodes[0].invitation("127.0.0.1")))
                tasks.append(pairing)
                while not stores[1].books.list():
                    if pairing.done():
                        pairing.result()
                        pytest.fail(f"Pairing stopped before transfer: {events}")
                    await asyncio.sleep(0.01)
                assert stores[1].books.list()[0].title == "TLS book"
        finally:
            for node in nodes:
                node.stop_event.set()
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=15)
            for engine in engines:
                engine.dispose()

    asyncio.run(scenario())
