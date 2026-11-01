"""Optional DNS-SD discovery; advertisements never contain library data or pairing tokens."""

import asyncio
import importlib
import ipaddress
import socket
from collections.abc import Callable
from typing import Any

from epub_reader.infrastructure.sync.crypto import private_host
from epub_reader.infrastructure.sync.records import valid_id

SERVICE_TYPE = "_epubify._tcp.local."


def addresses() -> list[str]:
    found = []
    for adapter in importlib.import_module("ifaddr").get_adapters():
        for entry in adapter.ips:
            address = entry.ip[0] if isinstance(entry.ip, tuple) else entry.ip
            if (
                isinstance(entry.ip, tuple)
                and entry.ip[2]
                and ipaddress.ip_address(address).is_link_local
            ):
                address += f"%{entry.ip[2]}"
            try:
                private_host(address)
            except ValueError:
                continue
            if not ipaddress.ip_address(address.split("%")[0]).is_loopback:
                found.append(address)
    return sorted(set(found), key=lambda value: (":" in value, value))


class Discovery:
    def __init__(
        self, device_id: str, name: str, port: int, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        self.id, self.name, self.port, self.callback = device_id, name, port, callback
        self.zeroconf: Any = None
        self.browser: Any = None
        self.info: Any = None
        self.tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        module = importlib.import_module("zeroconf")
        aio = importlib.import_module("zeroconf.asyncio")
        ips = [
            socket.inet_pton(socket.AF_INET6 if ":" in ip else socket.AF_INET, ip.split("%")[0])
            for ip in addresses()
        ]
        self.zeroconf = aio.AsyncZeroconf(ip_version=module.IPVersion.All)
        self.info = module.ServiceInfo(
            SERVICE_TYPE,
            f"{self.id[:24]}.{SERVICE_TYPE}",
            addresses=ips,
            port=self.port,
            properties={"id": self.id, "name": self.name[:80], "protocol": "1"},
            server=f"{self.id[:24]}.local.",
        )
        announcements = await self.zeroconf.async_register_service(
            self.info, allow_name_change=True
        )
        await announcements
        self.browser = aio.AsyncServiceBrowser(
            self.zeroconf.zeroconf, SERVICE_TYPE, handlers=[self._event]
        )

    def _event(self, zeroconf: Any, service_type: str, name: str, state_change: Any) -> None:
        if len(self.tasks) >= 32 or state_change.name == "Removed":
            return
        task = asyncio.create_task(self._resolve(service_type, name))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _resolve(self, service_type: str, name: str) -> None:
        try:
            info = await self.zeroconf.async_get_service_info(service_type, name, timeout=2000)
            if info is None:
                return
            properties = info.properties
            identifier = properties.get(b"id", b"").decode("ascii")
            if (
                not valid_id(identifier)
                or identifier == self.id
                or properties.get(b"protocol") != b"1"
            ):
                return
            candidates = info.parsed_scoped_addresses()
            for host in sorted(candidates, key=lambda value: (":" in value, value)):
                try:
                    private_host(host)
                except ValueError:
                    continue
                self.callback(
                    {
                        "id": identifier,
                        "name": properties.get(b"name", b"Device").decode(
                            "utf-8", errors="replace"
                        )[:80],
                        "host": host,
                        "port": info.port,
                    }
                )
                break
        except (ValueError, OSError, UnicodeError):
            return

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.browser is not None:
            await self.browser.async_cancel()
        if self.zeroconf is not None:
            await self.zeroconf.async_unregister_all_services()
            await self.zeroconf.async_close()
