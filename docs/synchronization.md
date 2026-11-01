# Local device synchronization

The shared Python engine implements opt-in LAN replication with no account,
cloud, telemetry, relay server or external discovery service. Reading, imports,
notes and preferences continue to work with sync disabled or the network absent.

## Pair and use

Open **Settings → Devices & sync** on both devices and enable **Local network
sync**. Create an invitation on one device, share it privately, paste it into the
other and select **Pair device**. The invitation grants access to the shared
library; it contains a random 256-bit secret, expires after five minutes and
works once. It is deliberately not a short PIN. Do not publish invitations.

mDNS/DNS-SD advertises `_epubify._tcp.local.` with device identity/name/protocol
and the ephemeral TCP port. Discovery never grants trust or includes book names
or invitation secrets. Paired devices reconnect after restart; unpaired devices
require a fresh invitation. **Revoke** disconnects a device and blocks future
records bearing its identity, including relayed records. Revocation cannot erase
copies already received, and a new invitation can intentionally pair it again.

All paired devices share all books, progress, favorites, page notes and the
allowlisted appearance/language preferences. Device enablement, paths and keys
never synchronize. Book deletion and per-book sharing rules are not implemented.

## Protocol and trust boundary

`infrastructure/sync` contains discovery, TLS identities, bounded message transport
and durable signed registers. `SyncController` owns an asyncio worker in a Qt
thread. The worker commits SQLite before emitting a queued QML refresh. No
networking or database code runs in QML. Sync is off by default.

TLS 1.3 encrypts WebSockets. The invitation pins the server certificate's DER
SHA-256 fingerprint **before** any authentication token or library data is sent.
Subsequent connections use the stored pin. A nonce challenge binds client/server
IDs and protocol version; the client proves possession of its P-256 private key
with ECDSA/SHA-256. Self-signed certificates are intentional; ordinary public CA
validation is replaced by mandatory pinning, not silently bypassed.

Each record carries its author's certificate, signature, timestamp and bounded
version vector. Paired peers may relay signed records; pairing authorizes access
to the whole replication group, not only data originally authored by that peer.
An authorized compromised device can change shared data. This implementation
has automated tests, but has not received an independent security audit.

Private keys live under platform application data in `sync/identity/`, with
0700/0600 permissions on POSIX and inherited user-directory ACLs on Windows.
Keys are not hardware-backed. SQLite/books are not encrypted at rest; use OS
disk encryption. Back up a device's key and certificate together, privately.

## Persistence and convergence

SQLite schema 5 adds peers, immutable signed versions, entity heads, projections,
book identity mappings and notes without removing existing books/preferences.
Content identity hashes sanitized publication paths and bytes, so locally
different ZIP containers can map to the same shared publication. Transfers are
64 KiB binary chunks, never large JSON/base64 payloads. SHA-256, expected content
identity and the normal ZIP/XML/path/decompression validation run before import.

Progress uses this native reader's versioned chapter/text-offset locations.
Concurrent branches are retained. All devices select the same timestamp/author/
record-ID winner; concurrent note deletion wins over an edit. **Conflicts** lets
the user choose a branch, producing a new version that causally dominates the
alternatives. Independent preference keys merge separately. Local edits are
captured before incoming projections; remote projections do not echo as new edits.

The worker snapshots local state every five seconds. Reconnection backs off
from approximately 5 to 160 seconds with jitter. Partial transfers are deleted
and retried in full; byte-range resume is not implemented. Queues, connections,
message sizes, version vectors, records, archive sizes and disk space are bounded.
History stops accepting new versions at 100,000 entries; compaction is a future
migration. Keep device clocks within five minutes. Certificates last ten years;
automatic key/certificate rotation is not implemented.

## Platforms and validation

Desktop uses ordinary sockets, local IP addresses and optional firewall
permission for inbound TCP/mDNS. No UPnP port forwarding, NAT traversal or
internet relay is attempted. IPv6 link-local scopes and on-link global prefixes
are supported. Networks with client isolation or blocked multicast may require
manual invitations; blocked peer-to-peer TCP still prevents transfer.

Android/iOS share the replication code and stop networking when the app leaves
the foreground, reopening it on activation. They do not promise background sync.
See [mobile deployment](mobile.md) for permissions, native dependencies and the
remaining release gates. No Android/iOS build or real-device test is claimed.

Run `uv run pytest tests/unit/test_sync.py tests/integration/test_sync_protocol.py
tests/integration/test_notes_sync_ui.py -q -rs`. Tests cover signatures, pinning,
single-use/expired invitations, tampering, book identity, offline conflicts,
unsnapshotted edits, note deletion, revocation, QML updates and a transfer of 11
books through the complete authenticated application protocol. TLS is separately
exercised using real SSL MemoryBIO. The real two-node TLS/WebSocket test skips
only when the runner forbids socket binding; run it outside that sandbox before
release. mDNS across physical devices remains an additional manual gate.
