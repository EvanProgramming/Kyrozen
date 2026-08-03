"""Local Hardware Bridge for compiling and uploading firmware.

The bridge wraps ``arduino-cli`` and ``platformio`` commands. It validates every
command against a whitelist and runs it in the project's hardware/firmware
directory via ``subprocess``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


class HardwareBridgeError(Exception):
    """Raised when the hardware bridge cannot execute a command safely."""


def classify_upload_error(stderr: str) -> str:
    """Normalize common upload failures for user-facing recovery actions."""
    text = (stderr or "").lower()
    if not text:
        return "unknown"
    if (
        "no such file" in text
        or ("port" in text and "not found" in text)
        or ("serial" in text and "not found" in text)
        or "device disconnected" in text
        or "no device" in text
    ):
        return "not_connected"
    if "permission denied" in text or "access is denied" in text or "operation not permitted" in text:
        return "permission_denied"
    if "busy" in text or "resource temporarily unavailable" in text or "resource busy" in text:
        return "port_occupied"
    if "power" in text or "brownout" in text:
        return "power_failure"
    if "upload speed" in text or "baud" in text or "921600" in text or "460800" in text or "too fast" in text:
        return "upload_speed_too_high"
    if "timeout" in text or "timed out" in text or "stopped responding" in text:
        return "board_error"
    if "upload" in text or "bootloader" in text or "chip" in text:
        return "board_error"
    return "unknown"


class HardwareBridge:
    """Execute whitelisted Arduino CLI / PlatformIO commands locally."""

    ALLOWED_COMMANDS = {
        "arduino-cli",
        "pio",
    }

    def __init__(self, firmware_dir: str | Path | None = None) -> None:
        self.firmware_dir = Path(firmware_dir) if firmware_dir else Path.cwd()

    def _check_tool(self, command: str) -> str:
        # Desktop client may pass pre-resolved tool paths via environment
        # variables so that bundled toolchains can be used.
        tool_path = self._tool_path(command)
        if tool_path is None:
            raise HardwareBridgeError(f"Tool not found: {command}")
        return tool_path

    def _tool_path(self, command: str) -> str | None:
        """Resolve a system or desktop-bundled tool consistently.

        Packaged Electron launches the Python Agent with explicit paths for
        bundled tools.  Those paths are intentionally not added to PATH, so
        every capability check must use the same resolver as command
        execution; checking only ``shutil.which`` makes a packaged tool appear
        installed while discovery reports ``toolchain_unavailable``.
        """
        env_override = os.environ.get(f"KYROZEN_{command.upper().replace('-', '_')}_PATH")
        if env_override and Path(env_override).is_file():
            return env_override
        return shutil.which(command)

    def _validate_args(self, args: list[str]) -> None:
        if not args:
            raise HardwareBridgeError("Empty command")
        if args[0] not in self.ALLOWED_COMMANDS:
            raise HardwareBridgeError(f"Disallowed command: {args[0]}")

        # Only a small set of subcommands are permitted.
        allowed_arduino = {"board", "compile", "upload", "monitor", "version", "core"}
        allowed_pio = {"run", "device", "--version"}
        if args[0] == "arduino-cli" and len(args) > 1 and args[1] not in allowed_arduino:
            raise HardwareBridgeError(f"Disallowed arduino-cli subcommand: {args[1]}")
        if args[0] == "pio" and len(args) > 1 and args[1] not in allowed_pio:
            raise HardwareBridgeError(f"Disallowed pio subcommand: {args[1]}")
        if args[0] == "arduino-cli" and args[1] == "version" and len(args) != 2:
            raise HardwareBridgeError("Only arduino-cli version discovery is allowed")
        if args[0] == "arduino-cli" and args[1] == "core" and args[1:] != ["core", "list"]:
            raise HardwareBridgeError("Only arduino-cli core list discovery is allowed")
        if args[0] == "pio" and args[1] == "--version" and len(args) != 2:
            raise HardwareBridgeError("Only PlatformIO version discovery is allowed")

        # Forbid shell metacharacters and redirection.
        dangerous = {";", "&", "|", "`", "$", "(", ")", ">", "<", "\\", "\n"}
        for arg in args:
            if any(ch in arg for ch in dangerous):
                raise HardwareBridgeError(f"Dangerous character in argument: {arg!r}")

    def run(self, args: list[str], timeout: int = 120) -> dict[str, Any]:
        """Run a whitelisted command and return structured output."""
        self._validate_args(args)
        tool_path = self._check_tool(args[0])
        command_line = [tool_path, *args[1:]]
        command = " ".join(args)

        try:
            result = subprocess.run(
                command_line,
                cwd=self.firmware_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command,
                "error_category": classify_upload_error(result.stderr) if result.returncode != 0 else "",
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "returncode": None,
                "stdout": exc.stdout or "",
                "stderr": f"Command timed out after {timeout}s",
                "command": command,
                "error_category": "board_error",
            }
        except Exception as exc:  # pragma: no cover - safety net
            return {
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": str(exc),
                "command": command,
                "error_category": classify_upload_error(str(exc)),
            }

    def list_ports(
        self,
        board: str | None = None,
        port: str | None = None,
    ) -> dict[str, Any]:
        """List available serial ports using the first available tool."""
        toolchain = self.toolchain_status()
        if self._tool_path("arduino-cli"):
            result = self.run(["arduino-cli", "board", "list"])
            result["toolchain"] = toolchain
            cli_identified = bool(re.search(
                r"\b[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+\b",
                str(result.get("stdout") or ""),
            ))
            # USB-UART bridges (including common CH340 adapters) expose a
            # real port but Arduino CLI cannot identify the MCU until it is
            # placed in the bootloader.  The physical workflow explicitly
            # asks the user to confirm the board and selected port, so that
            # confirmation is sufficient to proceed without pretending the
            # CLI auto-detected an FQBN.
            output = str(result.get("stdout") or "")
            confirmed_port = bool(port and port in output)
            user_confirmed = bool(board and confirmed_port)
            result["board_detected"] = cli_identified or user_confirmed
            result["board_identification"] = (
                "arduino_cli" if cli_identified else "user_confirmed"
                if user_confirmed else "unconfirmed"
            )
            result["confirmed_board"] = board or ""
            result["confirmed_port"] = port or ""
            if result.get("success"):
                result["status"] = "PASSED" if result["board_detected"] else "BLOCKED"
                if not result["board_detected"]:
                    result["block_reason"] = "board_not_connected"
            return result
        if self._tool_path("pio"):
            result = self.run(["pio", "device", "list"])
            result["toolchain"] = toolchain
            # PlatformIO lists ports but cannot identify an ESP32 board without
            # a project-specific probe. Keep physical acceptance conservative.
            result["board_detected"] = False
            if result.get("success"):
                result["status"] = "BLOCKED"
                result["block_reason"] = "board_not_confirmed"
            return result
        return {
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": "No supported hardware tool found (arduino-cli or platformio)",
            "board_detected": False,
            "status": "BLOCKED",
            "block_reason": "toolchain_unavailable",
            "toolchain": toolchain,
        }

    def toolchain_status(self) -> dict[str, Any]:
        """Return read-only tool and board-core discovery for the workbench."""
        status: dict[str, Any] = {}
        if self._tool_path("arduino-cli"):
            version = self.run(["arduino-cli", "version"])
            cores = self.run(["arduino-cli", "core", "list"])
            status["arduino_cli"] = {
                "installed": True,
                "version": (version.get("stdout") or version.get("stderr") or "").strip(),
                "core_list": (cores.get("stdout") or cores.get("stderr") or "").strip(),
                "core_command_success": bool(cores.get("success")),
            }
        else:
            status["arduino_cli"] = {"installed": False}
        if self._tool_path("pio"):
            version = self.run(["pio", "--version"])
            status["platformio"] = {
                "installed": True,
                "version": (version.get("stdout") or version.get("stderr") or "").strip(),
                "command_success": bool(version.get("success")),
            }
        else:
            status["platformio"] = {"installed": False}
        status["serial_driver"] = {
            "status": "probe_with_board_listing",
            "note": "串口驱动只能通过实际端口枚举确认；未枚举到板卡时不会推断驱动正常。",
        }
        return status

    def compile(self, board: str | None = None) -> dict[str, Any]:
        """Compile the firmware project."""
        # Prefer PlatformIO if project uses it, otherwise arduino-cli.
        if (self.firmware_dir / "platformio.ini").exists():
            return self.run(["pio", "run"])

        if board is None:
            return {
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": "Board FQBN is required for arduino-cli compile",
                "command": "arduino-cli compile",
                "error_category": "board_error",
            }
        return self.run(["arduino-cli", "compile", "--fqbn", board, "."])

    def prepare_serial_probe(self) -> dict[str, Any]:
        """Create the approved, GPIO-free ESP32 serial probe sketch."""
        probe_file = self.firmware_dir / "kyrozen_serial_probe.ino"
        # Arduino CLI treats a directory as a sketch only when it contains a
        # main file named after the directory. Keep the descriptive probe
        # filename for evidence and provide the CLI-compatible entrypoint.
        main_file = self.firmware_dir / f"{self.firmware_dir.name}.ino"
        source = "\n".join([
            "// Kyrozen hardware acceptance serial probe; no GPIO or product protocol assumptions.",
            "#include <Arduino.h>",
            "",
            "unsigned long heartbeat = 0;",
            "",
            "void setup() {",
            "  Serial.begin(115200);",
            "  delay(200);",
            "  Serial.println(\"KYROZEN_SERIAL_PROBE ready\");",
            "}",
            "",
            "void loop() {",
            "  Serial.print(\"KYROZEN_SERIAL_PROBE heartbeat \");",
            "  Serial.println(heartbeat++);",
            "  delay(1000);",
            "}",
            "",
        ])
        # Arduino CLI compiles every `.ino` in the directory. Keep the
        # descriptive probe filename as a non-compiling evidence pointer and
        # place the single executable sketch in the directory entrypoint.
        probe_file.write_text(
            "// Kyrozen serial probe source is compiled from firmware.ino.\n"
            "// This file is retained as the named evidence record.\n"
            "// Expected output includes: KYROZEN_SERIAL_PROBE heartbeat N\n",
            encoding="utf-8",
        )
        if main_file != probe_file:
            main_file.write_text(source, encoding="utf-8")
        return {
            "success": True,
            "status": "PASSED",
            "probe_file": str(probe_file),
            "compile_entrypoint": str(main_file),
            "probe_name": "KYROZEN_SERIAL_PROBE",
            "baud": 115200,
            "note": "GPIO-free serial heartbeat probe; it does not define BLE/GATT/OTA or product behavior.",
        }

    def upload(self, board: str | None = None, port: str | None = None) -> dict[str, Any]:
        """Upload compiled firmware to the board."""
        if (self.firmware_dir / "platformio.ini").exists():
            args = ["pio", "run", "--target", "upload"]
            if port:
                args.extend(["--upload-port", port])
            return self.run(args)

        if board is None:
            return {
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": "Board FQBN is required for arduino-cli upload",
                "command": "arduino-cli upload",
                "error_category": "board_error",
            }
        args = ["arduino-cli", "upload", "--fqbn", board]
        if port:
            args.extend(["--port", port])
        args.append(".")
        return self.run(args)

    def monitor(self, port: str, baud: int = 115200) -> dict[str, Any]:
        """Capture a bounded serial sample instead of opening a forever monitor.

        The desktop workflow needs a result it can persist and render.  Both
        Arduino CLI and PlatformIO monitors are interactive processes, so a
        normal ``subprocess.run`` would leave the workbench waiting until its
        global timeout.  Capture a short sample, then terminate the monitor;
        the probe is considered passed only when its real heartbeat is seen.
        """
        if self._tool_path("arduino-cli"):
            args = ["arduino-cli", "monitor", "--port", port, "--config", f"baudrate={baud}"]
        else:
            args = ["pio", "device", "monitor", "--port", port, "--baud", str(baud)]
        self._validate_args(args)
        tool_path = self._check_tool(args[0])
        command_line = [tool_path, *args[1:]]
        command = " ".join(args)
        process = subprocess.Popen(
            command_line,
            cwd=self.firmware_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=8)
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            process.terminate()
            try:
                stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            stdout = (exc.stdout or "") + (stdout or "")
            stderr = (exc.stderr or "") + (stderr or "")
            timed_out = True
        combined = f"{stdout}\n{stderr}"
        probe_seen = "KYROZEN_SERIAL_PROBE" in combined
        return {
            "success": probe_seen,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr if probe_seen else stderr or "Serial probe output was not observed",
            "command": command,
            "error_category": "" if probe_seen else "board_error",
            "sample_seconds": 8,
            "probe_seen": probe_seen,
            "monitor_ended_by_timeout": timed_out,
        }
