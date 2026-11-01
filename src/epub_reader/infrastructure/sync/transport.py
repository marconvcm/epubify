"""Authenticated TLS WebSocket replication and streamed, verified EPUB transfer."""

import asyncio
import hashlib
import hmac
import importlib
import json
import secrets
import shutil
import socket
import ssl
import time
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from epub_reader.infrastructure.epub.extraction import ArchiveLimits
from epub_reader.infrastructure.sync.crypto import (
    Identity,
    Invitations,
    private_host,
    verify,
    verify_server_pin,
)
from epub_reader.infrastructure.sync.discovery import Discovery, addresses
from epub_reader.infrastructure.sync.records import Record, SyncError, canonical, valid_id
from epub_reader.infrastructure.sync.store import SyncStore


class Node:
    def __init__(
        self,
        store: SyncStore,
        name: str,
        notify: Callable[[str, dict[str, Any]], None],
        *,
        port: int = 0,
        discovery: bool = True,
    ) -> None:
        self.store, self.identity, self.name, self.notify = store, store.identity, name[:80], notify
        self.port, self.use_discovery = port, discovery
        self.invitations = Invitations()
        self.stop_event = asyncio.Event()
        self.discovery: Discovery | None = None
        self.connections: dict[str, Any] = {}
        self.connecting: set[str] = set()
        self.tasks: set[asyncio.Task[None]] = set()
        self.rate: dict[str, deque[float]] = defaultdict(deque)
        self.known_addresses: dict[str, dict[str, Any]] = {}
        self.retry: dict[str, tuple[int, float]] = {}
        self.authenticating = 0

    def task(self, coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _discovered(self, peer: dict[str, Any]) -> None:
        if peer["id"] not in self.known_addresses and len(self.known_addresses) >= 256:
            return
        self.known_addresses[peer["id"]] = peer
        known = self.store.peer(peer["id"])
        if known and known["enabled"]:
            self.store.endpoint(peer["id"], peer["host"], peer["port"])
        self.notify("discovered", peer)

    async def run(self) -> None:
        server_api = importlib.import_module("websockets.asyncio.server")
        listener = (
            socket.create_server(("::", self.port), family=socket.AF_INET6, dualstack_ipv6=True)
            if socket.has_dualstack_ipv6()
            else socket.create_server(("0.0.0.0", self.port))
        )
        listener.setblocking(False)
        self.port = listener.getsockname()[1]
        server = await server_api.serve(
            self._accept,
            sock=listener,
            ssl=self.identity.server_context(),
            origins=[None],
            max_size=128 * 1024,
            max_queue=4,
            compression=None,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=3,
            ssl_handshake_timeout=5,
            server_header=None,
        )
        try:
            if self.use_discovery:
                self.discovery = Discovery(self.identity.id, self.name, self.port, self._discovered)
                try:
                    await self.discovery.start()
                except OSError:
                    self.notify(
                        "error",
                        {
                            "message": "Local discovery is unavailable. "
                            "You can still pair with an invitation."
                        },
                    )
            self.notify(
                "ready", {"id": self.identity.id, "port": self.port, "addresses": addresses()}
            )
            self.task(self._reconcile())
            await self.stop_event.wait()
        finally:
            for task in self.tasks:
                task.cancel()
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
            if self.discovery is not None:
                await self.discovery.close()
            server.close()
            await server.wait_closed()

    async def _reconcile(self) -> None:
        while not self.stop_event.is_set():
            try:
                await asyncio.to_thread(self.store.snapshot)
                for peer in self.store.peers():
                    if (
                        self.identity.id < peer["id"]
                        and peer["id"] not in self.connections
                        and peer["id"] not in self.connecting
                        and peer["host"]
                        and time.monotonic() >= self.retry.get(peer["id"], (0, 0))[1]
                    ):
                        self.task(self.connect(peer["host"], peer["port"], peer["id"]))
            except Exception as exc:
                self.notify("error", {"message": str(exc)})
            with suppress(TimeoutError):
                await asyncio.wait_for(self.stop_event.wait(), timeout=5)

    def invitation(self, host: str = "") -> str:
        candidates = addresses()
        chosen = host or (candidates[0] if candidates else "127.0.0.1")
        return self.invitations.create(chosen, self.port, self.identity.id)

    async def pair(self, invitation: str) -> None:
        data = Invitations.parse(invitation)
        await self.connect(data["host"], data["port"], data["pin"], data["token"])

    async def _json(self, ws: Any) -> dict[str, Any]:
        message = await asyncio.wait_for(ws.recv(), timeout=30)
        if not isinstance(message, str) or len(message.encode()) > 128 * 1024:
            raise SyncError("Invalid synchronization message.")
        data = json.loads(message)
        if not isinstance(data, dict):
            raise SyncError("Invalid synchronization message.")
        return data

    async def _accept(self, ws: Any) -> None:
        peer_id = ""
        admitted = False
        try:
            if ws.request.path != "/sync" or len(self.connections) + self.authenticating >= 8:
                raise SyncError("Connection limit reached.")
            self.authenticating += 1
            admitted = True
            host = str(ws.remote_address[0])
            private_host(host)
            if host not in self.rate and len(self.rate) >= 256:
                self.rate.pop(next(iter(self.rate)))
            recent = self.rate[host]
            while recent and recent[0] < time.monotonic() - 60:
                recent.popleft()
            if len(recent) >= 5:
                raise SyncError("Too many pairing attempts.")
            recent.append(time.monotonic())
            nonce = secrets.token_hex(32)
            await ws.send(
                canonical(
                    {"type": "challenge", "nonce": nonce, "server": self.identity.id}
                ).decode()
            )
            auth = await self._json(ws)
            peer_id = auth.get("id", "")
            certificate = auth.get("certificate", "")
            if (
                auth.get("type") != "auth"
                or not valid_id(peer_id)
                or not isinstance(certificate, str)
                or len(certificate) > 8192
            ):
                raise SyncError("Device authentication failed.")
            transcript = canonical(
                {"protocol": 1, "nonce": nonce, "server": self.identity.id, "client": peer_id}
            )
            verify(certificate, peer_id, auth.get("signature", ""), transcript)
            peer = self.store.peer(peer_id)
            if peer is None or not peer["enabled"]:
                if not self.invitations.consume(auth.get("token", "")):
                    raise SyncError("Pairing invitation is invalid or expired.")
                self.store.trust(
                    peer_id,
                    str(auth.get("name", "Device"))[:80],
                    certificate,
                    host,
                    auth["port"]
                    if type(auth.get("port")) is int and 1 <= auth["port"] <= 65535
                    else 0,
                )
                self.notify("paired", {"id": peer_id})
            await ws.send(
                canonical({"type": "ready", "server": self.identity.id, "name": self.name}).decode()
            )
            self.authenticating -= 1
            admitted = False
            await self._session(ws, peer_id)
        except Exception as exc:
            self.notify("error", {"message": str(exc)})
            await ws.close(code=1008, reason="Authentication or protocol error")
        finally:
            if admitted:
                self.authenticating -= 1

    async def connect(self, host: str, port: int, peer_id: str, token: str = "") -> None:
        if peer_id == self.identity.id or peer_id in self.connecting or peer_id in self.connections:
            return
        private_host(host)
        self.connecting.add(peer_id)
        try:
            client_api = importlib.import_module("websockets.asyncio.client")
            endpoint = f"[{host}]" if ":" in host else host
            # Force the dialed IP/port even if an endpoint attempts an HTTP redirect.
            async with client_api.connect(
                f"wss://{endpoint}:{port}/sync",
                host=host,
                port=port,
                ssl=Identity.client_context(),
                proxy=None,
                open_timeout=8,
                max_size=128 * 1024,
                max_queue=4,
                compression=None,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=3,
            ) as ws:
                tls = ws.transport.get_extra_info("ssl_object")
                der = tls.getpeercert(binary_form=True) if tls else None
                if der is None:
                    raise SyncError("The device certificate does not match its trusted identity.")
                verify_server_pin(der, peer_id)
                challenge = await self._json(ws)
                if (
                    challenge.get("type") != "challenge"
                    or challenge.get("server") != peer_id
                    or not valid_id(challenge.get("nonce"))
                ):
                    raise SyncError("Invalid device authentication challenge.")
                transcript = canonical(
                    {
                        "protocol": 1,
                        "nonce": challenge["nonce"],
                        "server": peer_id,
                        "client": self.identity.id,
                    }
                )
                await ws.send(
                    canonical(
                        {
                            "type": "auth",
                            "id": self.identity.id,
                            "name": self.name,
                            "certificate": self.identity.pem,
                            "signature": self.identity.sign(transcript),
                            "token": token,
                            "port": self.port,
                        }
                    ).decode()
                )
                ready = await self._json(ws)
                if ready.get("type") != "ready" or ready.get("server") != peer_id:
                    raise SyncError("Device authentication failed.")
                self.store.trust(
                    peer_id,
                    str(ready.get("name", "Device"))[:80],
                    ssl.DER_cert_to_PEM_cert(der),
                    host,
                    port,
                )
                self.notify("paired", {"id": peer_id})
                await self._session(ws, peer_id)
        except Exception as exc:
            self.notify("error", {"message": str(exc)})
        finally:
            self.connecting.discard(peer_id)
            failures = min(self.retry.get(peer_id, (0, 0))[0] + 1, 6)
            self.retry[peer_id] = (
                failures,
                time.monotonic()
                + min(300, 5 * 2 ** (failures - 1))
                + secrets.randbelow(1000) / 1000,
            )

    async def revoke(self, peer_id: str) -> None:
        self.store.revoke(peer_id)
        if peer_id in self.connections:
            await self.connections[peer_id].close(code=1000, reason="Device revoked")
        self.notify("paired", {"id": peer_id})

    async def _session(self, ws: Any, peer_id: str) -> None:
        if peer_id in self.connections:
            await ws.close(code=1000, reason="Already connected")
            return
        self.connections[peer_id] = ws
        self.retry.pop(peer_id, None)
        self.notify("connected", {"id": peer_id})
        known: set[str] = set()
        requested: set[str] = set()
        pending_books: set[str] = set()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=8)
        send_lock = asyncio.Lock()
        incoming: dict[str, Any] | None = None
        received = 0
        inventory = asyncio.Event()

        async def request_books() -> None:
            while pending_books and len(requested) < 8:
                identifier = min(pending_books)
                pending_books.remove(identifier)
                requested.add(identifier)
                await send({"type": "want_book", "book": identifier})

        async def send(data: dict[str, Any]) -> None:
            async with send_lock:
                await ws.send(canonical(data).decode())

        async def publish() -> None:
            initial = await asyncio.to_thread(self.store.records)
            pending_books.update(await asyncio.to_thread(self.store.missing_books))
            identifiers = [record.id for record in initial]
            for offset in range(0, len(identifiers), 256):
                await send({"type": "inventory", "ids": identifiers[offset : offset + 256]})
            await send({"type": "inventory_end"})
            await asyncio.wait_for(inventory.wait(), timeout=30)
            while True:
                records = await asyncio.to_thread(self.store.records)
                for record in records:
                    if record.id not in known:
                        await send({"type": "record", "record": record.wire()})
                await send({"type": "records_end"})
                await asyncio.sleep(2)

        async def transfer() -> None:
            while True:
                identifier = await queue.get()
                path, size, checksum = await asyncio.to_thread(self.store.export, identifier)
                async with send_lock:
                    await ws.send(
                        canonical(
                            {
                                "type": "book_begin",
                                "book": identifier,
                                "size": size,
                                "sha256": checksum,
                            }
                        ).decode()
                    )
                    with path.open("rb") as stream:
                        while chunk := stream.read(65536):
                            await ws.send(chunk)
                    await ws.send(canonical({"type": "book_end", "book": identifier}).decode())

        async def guarded(coroutine: Any) -> None:
            try:
                await coroutine
            except Exception:
                # Wake the receiver when a producer fails, so reconnect can
                # retry instead of leaving a half-alive session indefinitely.
                await ws.close(code=1011, reason="Synchronization interrupted")
                raise

        sender = asyncio.create_task(guarded(publish()))
        uploader = asyncio.create_task(guarded(transfer()))
        try:
            while True:
                if not (peer := self.store.peer(peer_id)) or not peer["enabled"]:
                    raise SyncError("Device access has been revoked.")
                packet = await asyncio.wait_for(ws.recv(), timeout=60)
                if isinstance(packet, bytes):
                    if (
                        incoming is None
                        or not packet
                        or len(packet) > 65536
                        or incoming["written"] + len(packet) > incoming["size"]
                    ):
                        raise SyncError("Invalid book transfer size.")
                    incoming["stream"].write(packet)
                    incoming["digest"].update(packet)
                    incoming["written"] += len(packet)
                    continue
                if not isinstance(packet, str) or len(packet.encode()) > 128 * 1024:
                    raise SyncError("Invalid synchronization message.")
                data = json.loads(packet)
                if not isinstance(data, dict):
                    raise SyncError("Invalid synchronization message.")
                kind = data.get("type")
                if kind == "inventory":
                    identifiers = data.get("ids")
                    if (
                        not isinstance(identifiers, list)
                        or len(identifiers) > 256
                        or not all(valid_id(item) for item in identifiers)
                        or len(known) + len(identifiers) > 100000
                    ):
                        raise SyncError("Invalid synchronization inventory.")
                    known.update(identifiers)
                elif kind == "inventory_end":
                    inventory.set()
                elif kind == "record":
                    received += 1
                    if received > 10000:
                        raise SyncError("Synchronization session limit reached.")
                    record = Record.parse(data["record"])
                    changes = await asyncio.to_thread(self.store.merge, data["record"])
                    known.add(record.id)
                    self.notify("changed", changes)
                    await send({"type": "ack", "id": record.id})
                    if (
                        record.kind == "book"
                        and not (
                            (author := self.store.peer(record.author)) and not author["enabled"]
                        )
                        and not self.store.has_book(record.key)
                        and record.key not in requested
                        and len(pending_books) + len(requested) < 10000
                    ):
                        pending_books.add(record.key)
                elif kind == "records_end":
                    await request_books()
                elif kind == "ack":
                    if valid_id(data.get("id")):
                        known.add(data["id"])
                elif kind == "want_book":
                    if not valid_id(data.get("book")) or queue.full():
                        raise SyncError("Too many book transfer requests.")
                    await queue.put(data["book"])
                elif kind == "book_begin":
                    if (
                        incoming is not None
                        or data.get("book") not in requested
                        or type(data.get("size")) is not int
                        or not 0 < data["size"] <= ArchiveLimits().compressed_bytes
                        or not valid_id(data.get("sha256"))
                    ):
                        raise SyncError("Invalid book transfer request.")
                    folder = self.store.root / "sync/incoming"
                    folder.mkdir(parents=True, exist_ok=True)
                    if (
                        shutil.disk_usage(folder).free
                        < data["size"] + ArchiveLimits().expanded_bytes
                    ):
                        raise SyncError("Insufficient free space for the incoming book.")
                    path = folder / f"{secrets.token_hex(16)}.epub"
                    incoming = {
                        "book": data["book"],
                        "path": path,
                        "stream": path.open("xb"),
                        "size": data["size"],
                        "written": 0,
                        "digest": hashlib.sha256(),
                        "sha256": data["sha256"],
                    }
                elif kind == "book_end":
                    if (
                        incoming is None
                        or data.get("book") != incoming["book"]
                        or incoming["written"] != incoming["size"]
                        or not hmac.compare_digest(
                            incoming["digest"].hexdigest(), incoming["sha256"]
                        )
                    ):
                        raise SyncError("The transferred book failed its integrity check.")
                    incoming["stream"].close()
                    book_id = await asyncio.to_thread(
                        self.store.install_book, incoming["book"], incoming["path"]
                    )
                    incoming["path"].unlink(missing_ok=True)
                    requested.discard(incoming["book"])
                    incoming = None
                    self.notify("changed", {"books": [book_id], "preferences": []})
                    await request_books()
                else:
                    raise SyncError("Unknown synchronization message.")
        finally:
            sender.cancel()
            uploader.cancel()
            await asyncio.gather(sender, uploader, return_exceptions=True)
            if incoming is not None:
                incoming["stream"].close()
                incoming["path"].unlink(missing_ok=True)
            self.connections.pop(peer_id, None)
            self.notify("disconnected", {"id": peer_id})
