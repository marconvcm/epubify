"""Qt ownership boundary around an optional asyncio LAN replication worker."""

import asyncio
import importlib.util
import logging
import socket
from threading import Event
from typing import Any

from PySide6.QtCore import Property, QObject, QSysInfo, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from epub_reader.core.localization import tr
from epub_reader.core.paths import AppPaths
from epub_reader.infrastructure.database.repositories import PreferenceRepository

logger = logging.getLogger(__name__)


class SyncThread(QThread):
    notification = Signal(str, object)

    def __init__(self, engine: Any, paths: AppPaths, name: str) -> None:
        super().__init__()
        self.engine, self.paths, self.name = engine, paths, name
        self.loop: asyncio.AbstractEventLoop | None = None
        self.node: Any = None
        self._stop_requested = Event()

    def run(self) -> None:
        from epub_reader.infrastructure.sync.crypto import Identity
        from epub_reader.infrastructure.sync.store import SyncStore
        from epub_reader.infrastructure.sync.transport import Node
        from epub_reader.platforms.network import NetworkLease

        lease = NetworkLease()
        try:
            lease.acquire()

            async def main() -> None:
                self.loop = asyncio.get_running_loop()
                identity = await asyncio.to_thread(Identity, self.paths.root / "sync/identity")
                store = SyncStore(self.engine, self.paths.root, identity)
                self.node = Node(
                    store, self.name, lambda kind, data: self.notification.emit(kind, data)
                )
                if not self._stop_requested.is_set():
                    await self.node.run()

            asyncio.run(main())
        except Exception:
            logger.exception("Local synchronization could not start")
            self.notification.emit(
                "error",
                {
                    "message": "Local synchronization could not start. "
                    "Check network permissions and the application log."
                },
            )
        finally:
            lease.release()
            self.notification.emit("stopped", {})

    def command(self, action: str, value: Any = None) -> None:
        if action == "stop":
            self._stop_requested.set()
        if self.loop is None or self.loop.is_closed() or self.node is None:
            return

        async def execute() -> None:
            try:
                if action == "invite":
                    self.notification.emit("invitation", {"value": self.node.invitation()})
                elif action == "pair":
                    await self.node.pair(value)
                elif action == "revoke":
                    await self.node.revoke(value)
                elif action == "resolve":
                    await asyncio.to_thread(self.node.store.resolve, *value)
                    self.notification.emit("changed", {"books": [], "preferences": [], "all": True})
                elif action == "refresh":
                    self.notification.emit(
                        "refresh",
                        {
                            "peers": self.node.store.peers(),
                            "conflicts": self.node.store.conflicts(),
                        },
                    )
                elif action == "stop":
                    self.node.stop_event.set()
            except Exception:
                logger.exception("Synchronization command failed")
                self.notification.emit(
                    "error",
                    {"message": "The synchronization operation failed. Check the application log."},
                )

        asyncio.run_coroutine_threadsafe(execute(), self.loop)


class SyncController(QObject):
    changed = Signal()
    dataChanged = Signal(object)

    def __init__(self, engine: Any, paths: AppPaths, preferences: PreferenceRepository) -> None:
        super().__init__()
        self.engine, self.paths, self.preferences = engine, paths, preferences
        self._thread: SyncThread | None = None
        self._ready = False
        self._enabled = bool(preferences.get("sync_enabled", False))
        self._error = ""
        self._invitation = ""
        self._peers: dict[str, dict[str, Any]] = {}
        self._conflicts: list[dict[str, Any]] = []
        self._connected: set[str] = set()
        self._device_id = ""
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            app.applicationStateChanged.connect(self._application_state)

    @Property(bool, constant=True)
    def available(self) -> bool:
        return all(
            importlib.util.find_spec(name) is not None
            for name in ("cryptography", "websockets", "zeroconf")
        )

    @Property(bool, notify=changed)
    def enabled(self) -> bool:
        return self._enabled

    @Property(bool, notify=changed)
    def ready(self) -> bool:
        return self._ready

    @Property(str, notify=changed)
    def status(self) -> str:
        return (
            tr(self._error)
            if self._error
            else tr("Connected devices: {count}", count=len(self._connected))
            if self._ready
            else tr("Local sync is stopped.")
        )

    @Property(str, notify=changed)
    def invitation(self) -> str:
        return self._invitation

    @Property(str, notify=changed)
    def deviceId(self) -> str:
        return self._device_id

    @Property(list, notify=changed)
    def peers(self) -> list[dict[str, Any]]:
        return [
            {**peer, "connected": identifier in self._connected}
            for identifier, peer in sorted(self._peers.items())
        ]

    @Property(list, notify=changed)
    def conflicts(self) -> list[dict[str, Any]]:
        return self._conflicts

    @Slot()
    def startSaved(self) -> None:
        if self._enabled:
            self._start()

    def _start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        if not self.available:
            self._error = "Local sync is unavailable in this build."
            self.changed.emit()
            return
        self._error = ""
        thread = SyncThread(
            self.engine,
            self.paths,
            str(self.preferences.get("sync_device_name", socket.gethostname())),
        )
        thread.setParent(self)
        thread.notification.connect(self._event)
        self._thread = thread
        thread.start()
        self.timer.start()

    @Slot(bool)
    def setEnabled(self, value: bool) -> None:
        self._enabled = value
        self.preferences.set("sync_enabled", value)
        if value:
            self._start()
        else:
            self.shutdown()
        self.changed.emit()

    @Slot()
    def createInvitation(self) -> None:
        if self._thread and self._ready:
            self._thread.command("invite")

    @Slot()
    def copyInvitation(self) -> None:
        if self._invitation:
            QGuiApplication.clipboard().setText(self._invitation)

    @Slot(str)
    def pair(self, invitation: str) -> None:
        if self._thread and self._ready:
            self._thread.command("pair", invitation.strip())

    @Slot(str)
    def revoke(self, identifier: str) -> None:
        if self._thread:
            self._thread.command("revoke", identifier)

    @Slot(str, str, str)
    def resolve(self, kind: str, key: str, choice: str) -> None:
        if self._thread:
            self._thread.command("resolve", (kind, key, choice))

    @Slot()
    def refresh(self) -> None:
        if self._thread and self._ready:
            self._thread.command("refresh")

    @Slot(str, object)
    def _event(self, kind: str, data: dict[str, Any]) -> None:
        if self.sender() is not None and self.sender() is not self._thread:
            return
        if kind == "ready":
            self._ready = True
            self._device_id = data["id"]
        elif kind == "stopped":
            self._ready = False
            self._connected.clear()
        elif kind == "error":
            self._error = data["message"]
        elif kind == "discovered":
            self._peers[data["id"]] = {
                **data,
                "paired": self._peers.get(data["id"], {}).get("paired", False),
            }
        elif kind == "connected":
            self._connected.add(data["id"])
            self._error = ""
        elif kind == "disconnected":
            self._connected.discard(data["id"])
        elif kind == "invitation":
            self._invitation = data["value"]
        elif kind == "changed":
            self.dataChanged.emit(data)
            self.refresh()
        elif kind == "refresh":
            for peer in self._peers.values():
                peer["paired"] = False
            for peer in data["peers"]:
                self._peers[peer["id"]] = {**peer, "paired": True}
            self._conflicts = data["conflicts"]
        elif kind == "paired":
            self.refresh()
        self.changed.emit()

    @Slot(Qt.ApplicationState)
    def _application_state(self, state: Qt.ApplicationState) -> None:
        import sys

        if sys.platform != "ios" and QSysInfo.productType() != "android":
            return
        if state == Qt.ApplicationState.ApplicationActive and self._enabled:
            self._start()
        elif state != Qt.ApplicationState.ApplicationActive:
            self.shutdown()

    def shutdown(self) -> None:
        self.timer.stop()
        if self._thread is not None:
            self._thread.command("stop")
            self._thread.wait(15000)
            if self._thread.isRunning():
                logger.error("Synchronization worker did not finish within the shutdown interval")
                self._thread.wait()
            self._thread.deleteLater()
            self._thread = None
        self._ready = False
        self._invitation = ""
        self._connected.clear()
