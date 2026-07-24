"""Local Hardware Bridge for compiling and uploading firmware.

The bridge wraps ``arduino-cli`` and ``platformio`` commands. It validates every
command against a whitelist and runs it in the project's hardware/firmware
directory via ``subprocess``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class HardwareBridgeError(Exception):
    """Raised when the hardware bridge cannot execute a command safely."""


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
        env_override = os.environ.get(f"KYROZEN_{command.upper().replace('-', '_')}_PATH")
        if env_override and Path(env_override).is_file():
            return env_override
        tool_path = shutil.which(command)
        if tool_path is None:
            raise HardwareBridgeError(f"Tool not found: {command}")
        return tool_path

    def _validate_args(self, args: list[str]) -> None:
        if not args:
            raise HardwareBridgeError("Empty command")
        if args[0] not in self.ALLOWED_COMMANDS:
            raise HardwareBridgeError(f"Disallowed command: {args[0]}")

        # Only a small set of subcommands are permitted.
        allowed_arduino = {"board", "compile", "upload", "monitor"}
        allowed_pio = {"run", "device"}
        if args[0] == "arduino-cli" and len(args) > 1 and args[1] not in allowed_arduino:
            raise HardwareBridgeError(f"Disallowed arduino-cli subcommand: {args[1]}")
        if args[0] == "pio" and len(args) > 1 and args[1] not in allowed_pio:
            raise HardwareBridgeError(f"Disallowed pio subcommand: {args[1]}")

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
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "success": False,
                "returncode": None,
                "stdout": exc.stdout or "",
                "stderr": f"Command timed out after {timeout}s",
            }
        except Exception as exc:  # pragma: no cover - safety net
            return {
                "success": False,
                "returncode": None,
                "stdout": "",
                "stderr": str(exc),
            }

    def list_ports(self) -> dict[str, Any]:
        """List available serial ports using the first available tool."""
        if shutil.which("arduino-cli"):
            result = self.run(["arduino-cli", "board", "list"])
            return result
        if shutil.which("pio"):
            result = self.run(["pio", "device", "list"])
            return result
        return {
            "success": False,
            "returncode": None,
            "stdout": "",
            "stderr": "No supported hardware tool found (arduino-cli or platformio)",
        }

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
            }
        return self.run(["arduino-cli", "compile", "--fqbn", board, "."])

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
            }
        args = ["arduino-cli", "upload", "--fqbn", board]
        if port:
            args.extend(["--port", port])
        args.append(".")
        return self.run(args)

    def monitor(self, port: str, baud: int = 115200) -> dict[str, Any]:
        """Open serial monitor."""
        if shutil.which("arduino-cli"):
            return self.run(["arduino-cli", "monitor", "--port", port, "--config", f"baudrate={baud}"])
        return self.run(["pio", "device", "monitor", "--port", port, "--baud", str(baud)])
