"""TLS identities, certificate pinning and signatures using the cryptography package."""

import base64
import hashlib
import hmac
import importlib
import ipaddress
import json
import os
import secrets
import ssl
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from epub_reader.infrastructure.sync.records import Record, SyncError, canonical, valid_id


def _modules() -> tuple[Any, Any, Any, Any]:
    return (
        importlib.import_module("cryptography.x509"),
        importlib.import_module("cryptography.hazmat.primitives.asymmetric.ec"),
        importlib.import_module("cryptography.hazmat.primitives.hashes"),
        importlib.import_module("cryptography.hazmat.primitives.serialization"),
    )


def fingerprint(certificate: bytes) -> str:
    return hashlib.sha256(certificate).hexdigest()


def private_host(host: str) -> str:
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError as exc:
        raise SyncError("Only local-network IP addresses are accepted.") from exc
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    on_link = False
    if address.is_global:
        # IPv6 LANs can use globally routable prefixes (including Apple test
        # networks). Accept only addresses on a locally attached subnet.
        try:
            adapters = importlib.import_module("ifaddr").get_adapters()
        except OSError as exc:
            raise SyncError("Local network interfaces could not be inspected.") from exc
        for adapter in adapters:
            for entry in adapter.ips:
                ip = entry.ip[0] if isinstance(entry.ip, tuple) else entry.ip
                network = ipaddress.ip_network(f"{ip}/{entry.network_prefix}", strict=False)
                if network.version == address.version and address in network:
                    on_link = True
    if (
        address.is_unspecified
        or address.is_multicast
        or not (address.is_private or address.is_link_local or address.is_loopback or on_link)
    ):
        raise SyncError("Only local-network IP addresses are accepted.")
    if "%" in host and (
        not address.is_link_local
        or not host.split("%", 1)[1].replace("_", "").replace("-", "").isalnum()
    ):
        raise SyncError("Invalid local-network address.")
    return host


class Identity:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            root.chmod(0o700)
        self.key_path, self.cert_path = root / "identity-key.pem", root / "identity-cert.pem"
        x509, ec, hashes, serialization = _modules()
        if self.key_path.exists() != self.cert_path.exists():
            raise SyncError(
                "Device identity is incomplete. Restore its private key and certificate together."
            )
        if not self.key_path.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "Epubify device")])
            now = datetime.now(UTC)
            cert = (
                x509.CertificateBuilder()
                .subject_name(name)
                .issuer_name(name)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5))
                .not_valid_after(now + timedelta(days=3650))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .sign(key, hashes.SHA256())
            )
            # Exclusive creation avoids silently replacing an existing device identity.
            with self.key_path.open("xb") as target:
                if os.name != "nt":
                    os.fchmod(target.fileno(), 0o600)
                target.write(
                    key.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                )
            with self.cert_path.open("xb") as target:
                target.write(cert.public_bytes(serialization.Encoding.PEM))
        self.key = serialization.load_pem_private_key(self.key_path.read_bytes(), password=None)
        self.cert = x509.load_pem_x509_certificate(self.cert_path.read_bytes())
        if self.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ) != self.cert.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        ):
            raise SyncError("Device certificate does not match its private key.")
        self.pem = self.cert_path.read_text()
        self.id = fingerprint(self.cert.public_bytes(serialization.Encoding.DER))

    def sign(self, payload: bytes) -> str:
        _, ec, hashes, _ = _modules()
        return base64.b64encode(self.key.sign(payload, ec.ECDSA(hashes.SHA256()))).decode("ascii")

    def record(self, kind: str, key: str, value: dict[str, Any], vector: dict[str, int]) -> Record:
        unsigned = Record(kind, key, value, vector, self.id, int(time.time() * 1000), self.pem, "")
        return Record(
            kind,
            key,
            value,
            vector,
            self.id,
            unsigned.updated_ms,
            self.pem,
            self.sign(canonical(unsigned.body())),
        )

    def server_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(self.cert_path, self.key_path)
        return context

    @staticmethod
    def client_context() -> ssl.SSLContext:
        # Public CA validation is replaced by mandatory DER SHA-256 pinning before
        # sending authentication, invitation tokens or any application data.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        return context


def verify(
    certificate: str, claimed_id: str, signature: str, payload: bytes, *, at: datetime | None = None
) -> None:
    x509, ec, hashes, serialization = _modules()
    try:
        cert = x509.load_pem_x509_certificate(certificate.encode("ascii"))
        if not valid_id(claimed_id) or not hmac.compare_digest(
            fingerprint(cert.public_bytes(serialization.Encoding.DER)), claimed_id
        ):
            raise SyncError("Device identity verification failed.")
        checked_at = at or datetime.now(UTC)
        if not cert.not_valid_before_utc <= checked_at <= cert.not_valid_after_utc:
            raise SyncError("The device certificate has expired or is not valid yet.")
        public = cert.public_key()
        if not isinstance(public, ec.EllipticCurvePublicKey) or not isinstance(
            public.curve, ec.SECP256R1
        ):
            raise SyncError("Unsupported device key.")
        public.verify(
            base64.b64decode(signature, validate=True), payload, ec.ECDSA(hashes.SHA256())
        )
    except Exception as exc:
        raise SyncError("Device signature verification failed.") from exc


def verify_record(record: Record) -> None:
    verify(
        record.certificate,
        record.author,
        record.signature,
        canonical(record.body()),
        at=datetime.fromtimestamp(record.updated_ms / 1000, UTC),
    )


def verify_server_pin(der: bytes, expected: str) -> None:
    if not hmac.compare_digest(fingerprint(der), expected):
        raise SyncError("The device certificate does not match its trusted identity.")
    x509, _, _, _ = _modules()
    certificate = x509.load_der_x509_certificate(der)
    if not certificate.not_valid_before_utc <= datetime.now(UTC) <= certificate.not_valid_after_utc:
        raise SyncError("The device certificate has expired or is not valid yet.")


class Invitations:
    def __init__(self) -> None:
        self._hash = b""
        self._expires = 0.0

    def create(self, host: str, port: int, pin: str) -> str:
        token = secrets.token_urlsafe(32)
        self._hash = hashlib.sha256(token.encode()).digest()
        self._expires = time.monotonic() + 300
        data = {"v": 1, "host": private_host(host), "port": port, "pin": pin, "token": token}
        return "epubify://pair/" + base64.urlsafe_b64encode(canonical(data)).decode().rstrip("=")

    def consume(self, token: str) -> bool:
        if time.monotonic() > self._expires or not self._hash or not isinstance(token, str):
            return False
        valid = hmac.compare_digest(self._hash, hashlib.sha256(token.encode()).digest())
        if valid:
            self._hash = b""
        return valid

    @staticmethod
    def parse(invitation: str) -> dict[str, Any]:
        try:
            if len(invitation) > 4096 or not invitation.startswith("epubify://pair/"):
                raise ValueError
            encoded = urlsplit(invitation).path.lstrip("/")
            data = json.loads(base64.urlsafe_b64decode(encoded + "=" * ((-len(encoded)) % 4)))
            if (
                set(data) != {"v", "host", "port", "pin", "token"}
                or data["v"] != 1
                or not valid_id(data["pin"])
                or type(data["port"]) is not int
                or not 1 <= data["port"] <= 65535
                or not isinstance(data["token"], str)
                or len(data["token"]) < 40
            ):
                raise ValueError
            private_host(data["host"])
            return dict(data)
        except Exception as exc:
            raise SyncError("Invalid or expired pairing invitation.") from exc
