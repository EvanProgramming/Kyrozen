"""Transport-neutral, versioned application messages for hardware projects.

This module intentionally does not define BLE UUIDs, GATT characteristics,
MTU rules, OTA formats, or acknowledgements. Those require a user-provided
device protocol. Serial and a deterministic fake are enough for Phase 2's
first ESP32 workflow and integration tests.
"""

from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


CONNECTION_LAYERS = (
    "device",
    "firmware",
    "serial_transport",
    "application_service",
    "api",
    "database",
)


def build_connection_model(
    protocol: dict[str, Any],
    *,
    affected_files: list[str] | None = None,
    affected_tasks: list[str] | None = None,
) -> dict[str, Any]:
    """Build the durable six-layer contract without inventing device details."""
    return {
        "layers": [{"name": layer, "status": "declared"} for layer in CONNECTION_LAYERS],
        "protocol_version": str(protocol.get("protocol_version") or ""),
        "message_type": str(protocol.get("message_type") or ""),
        "fields": dict(protocol.get("fields") or {}),
        "units": dict(protocol.get("units") or {}),
        "direction": str(protocol.get("direction") or "device_to_app"),
        "frequency_hz": protocol.get("frequency_hz"),
        "error_code": str(protocol.get("error_code") or ""),
        "affected_files": list(affected_files or []),
        "affected_tasks": list(affected_tasks or []),
        "protocol_confirmed": True,
    }


@dataclass
class VersionedMessage:
    protocol_version: str
    message_type: str
    fields: dict[str, Any] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    direction: str = "device_to_app"
    frequency_hz: float | None = None
    correlation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "message_type": self.message_type,
            "fields": dict(self.fields),
            "units": dict(self.units),
            "direction": self.direction,
            "frequency_hz": self.frequency_hz,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "error_code": self.error_code,
        }

    def encode_line(self) -> bytes:
        return (json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VersionedMessage":
        return cls(
            protocol_version=str(data.get("protocol_version", "")),
            message_type=str(data.get("message_type", "")),
            fields=dict(data.get("fields") or {}),
            units=dict(data.get("units") or {}),
            direction=str(data.get("direction", "device_to_app")),
            frequency_hz=data.get("frequency_hz"),
            correlation_id=str(data.get("correlation_id") or uuid.uuid4().hex),
            timestamp=float(data.get("timestamp", time.time())),
            error_code=str(data.get("error_code", "")),
        )


class SerialTransport(ABC):
    """Minimal transport contract injected into application/integration code."""

    @abstractmethod
    def connect(self, port: str, baud: int = 115200) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def send(self, message: VersionedMessage) -> None: ...

    @abstractmethod
    def receive(self, timeout: float = 1.0) -> VersionedMessage | None: ...

    @property
    @abstractmethod
    def connected(self) -> bool: ...


class SerialPortTransport(SerialTransport):
    """Real line-oriented serial transport for the declared application protocol.

    ``pyserial`` is imported only when a real connection is requested. Tests and
    desktop discovery can inject a small serial factory, while deployments that
    want physical ESP32 communication install the optional runtime dependency.
    No BLE, OTA, framing, or device-specific assumptions are made here.
    """

    def __init__(self, serial_factory: Any | None = None) -> None:
        self._serial_factory = serial_factory
        self._serial: Any | None = None

    @property
    def connected(self) -> bool:
        return bool(self._serial is not None and getattr(self._serial, "is_open", True))

    def connect(self, port: str, baud: int = 115200) -> None:
        if not port:
            raise ValueError("serial port is required")
        factory = self._serial_factory
        if factory is None:
            try:
                import serial
            except ImportError as exc:  # pragma: no cover - depends on deployment
                raise RuntimeError("pyserial is required for real serial transport") from exc
            factory = lambda name, speed, timeout: serial.Serial(
                port=name, baudrate=speed, timeout=timeout
            )
        self._serial = factory(port, baud, 0)

    def disconnect(self) -> None:
        if self._serial is not None:
            self._serial.close()
        self._serial = None

    def send(self, message: VersionedMessage) -> None:
        if not self.connected:
            raise ConnectionError("serial transport is offline")
        self._serial.write(message.encode_line())

    def receive(self, timeout: float = 1.0) -> VersionedMessage | None:
        if not self.connected:
            raise ConnectionError("serial transport is offline")
        previous_timeout = getattr(self._serial, "timeout", None)
        try:
            if hasattr(self._serial, "timeout"):
                self._serial.timeout = timeout
            raw = self._serial.readline()
        finally:
            if hasattr(self._serial, "timeout"):
                self._serial.timeout = previous_timeout
        if not raw:
            return None
        try:
            payload = json.loads(raw.decode("utf-8").strip() if isinstance(raw, bytes) else str(raw).strip())
            if not isinstance(payload, dict):
                raise ValueError("message must be a JSON object")
            return VersionedMessage.from_dict(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return VersionedMessage(
                protocol_version="",
                message_type="error",
                direction="device_to_app",
                error_code="invalid_message",
                fields={"detail": str(exc)},
            )


def create_transport(kind: str = "serial", *, protocol_version: str = "1.0") -> SerialTransport:
    """Select the real or deterministic transport without changing callers."""
    if kind == "fake":
        return FakeSerialTransport(protocol_version=protocol_version)
    if kind == "serial":
        return SerialPortTransport()
    raise ValueError(f"Unsupported transport kind '{kind}'")


class FakeSerialTransport(SerialTransport):
    """Deterministic fake supporting offline/reconnect/duplicate/error tests."""

    def __init__(self, *, protocol_version: str = "1.0") -> None:
        self.protocol_version = protocol_version
        self._connected = False
        self._queue: list[VersionedMessage] = []
        self.sent: list[VersionedMessage] = []
        self.duplicate_next = False
        self.force_error = ""

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, port: str, baud: int = 115200) -> None:
        if not port:
            raise ValueError("serial port is required")
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def send(self, message: VersionedMessage) -> None:
        if not self._connected:
            raise ConnectionError("serial transport is offline")
        self.sent.append(message)
        incompatible = message.protocol_version != self.protocol_version
        response = VersionedMessage(
            protocol_version=self.protocol_version,
            message_type="error" if self.force_error or incompatible else f"ack:{message.message_type}",
            fields={},
            direction="device_to_app",
            correlation_id=message.correlation_id,
            error_code=self.force_error or ("protocol_version_incompatible" if incompatible else ""),
        )
        self._queue.append(response)
        if self.duplicate_next:
            self._queue.append(response)
            self.duplicate_next = False

    def receive(self, timeout: float = 1.0) -> VersionedMessage | None:
        if not self._connected:
            raise ConnectionError("serial transport is offline")
        return self._queue.pop(0) if self._queue else None


PROTOCOL_SCENARIOS = (
    "normal",
    "offline",
    "reconnect",
    "duplicate",
    "error",
    "version_incompatible",
)


def run_fake_protocol_scenarios() -> dict[str, Any]:
    """Run the six transport scenarios without pretending to test hardware.

    The returned records are suitable for an Artifact or local hardware run.
    They prove application/transport behavior only; a physical board remains a
    separate acceptance requirement.
    """
    records: list[dict[str, Any]] = []

    def record(name: str, passed: bool, expected: str, observed: str, **extra: Any) -> None:
        records.append({
            "scenario": name,
            "status": "PASSED" if passed else "FAILED",
            "expected": expected,
            "observed": observed,
            **extra,
        })

    message = VersionedMessage(protocol_version="1.0", message_type="telemetry", fields={"value": 1})

    transport = FakeSerialTransport()
    transport.connect("fake")
    transport.send(message)
    response = transport.receive()
    record("normal", bool(response and response.error_code == ""), "ack:telemetry", response.message_type if response else "no_response")
    transport.disconnect()

    transport = FakeSerialTransport()
    try:
        transport.send(message)
    except ConnectionError as exc:
        record("offline", True, "offline_error", type(exc).__name__)
    else:
        record("offline", False, "offline_error", "send_succeeded")

    transport.connect("fake")
    transport.disconnect()
    transport.connect("fake")
    transport.send(message)
    response = transport.receive()
    record("reconnect", bool(response and response.error_code == ""), "ack_after_reconnect", response.message_type if response else "no_response")
    transport.disconnect()

    transport = FakeSerialTransport()
    transport.duplicate_next = True
    transport.connect("fake")
    transport.send(message)
    first, second = transport.receive(), transport.receive()
    duplicate = bool(first and second and first.correlation_id == second.correlation_id)
    record("duplicate", duplicate, "duplicate_detected_by_correlation_id", f"responses={int(first is not None) + int(second is not None)}", correlation_id=first.correlation_id if first else "")
    transport.disconnect()

    transport = FakeSerialTransport()
    transport.force_error = "device_error"
    transport.connect("fake")
    transport.send(message)
    response = transport.receive()
    record("error", bool(response and response.error_code == "device_error"), "device_error", response.error_code if response else "no_response")
    transport.disconnect()

    transport = FakeSerialTransport(protocol_version="2.0")
    transport.connect("fake")
    transport.send(message)
    response = transport.receive()
    record("version_incompatible", bool(response and response.error_code == "protocol_version_incompatible"), "protocol_version_incompatible", response.error_code if response else "no_response")
    transport.disconnect()

    return {
        "transport": "fake",
        "protocol_version": "1.0",
        "scenarios": records,
        "success": all(item["status"] == "PASSED" for item in records),
        "status": "PASSED" if all(item["status"] == "PASSED" for item in records) else "FAILED",
    }
