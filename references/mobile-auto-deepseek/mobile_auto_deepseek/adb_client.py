import base64
import os
import subprocess
import time
import uuid
from pathlib import Path

from .constants import DEFAULT_ADB, DEFAULT_SERIAL

ADB_COMMAND_TIMEOUT_SECONDS = 15.0
ADB_COMMAND_RETRIES = 1


class AdbError(RuntimeError):
    pass


class AdbClient:
    def __init__(self, adb: str = DEFAULT_ADB, serial: str | None = DEFAULT_SERIAL):
        self.adb = adb
        self.serial = serial
        self.remote_tag = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def command(
        self,
        args: list[str],
        check: bool = True,
        text: bool = True,
        timeout: float = ADB_COMMAND_TIMEOUT_SECONDS,
        retries: int = ADB_COMMAND_RETRIES,
    ) -> subprocess.CompletedProcess:
        command = [self.adb]
        if self.serial:
            command.extend(["-s", self.serial])
        command.extend(args)
        attempts = max(1, int(retries) + 1)
        last_error = ""
        for attempt in range(attempts):
            try:
                kwargs = {"capture_output": True, "text": text, "timeout": timeout}
                if text:
                    kwargs.update({"encoding": "utf-8", "errors": "replace"})
                result = subprocess.run(command, **kwargs)
            except subprocess.TimeoutExpired:
                last_error = f"adb command timed out after {timeout:g}s: {' '.join(command)}"
            else:
                if not check or result.returncode == 0:
                    return result
                stderr = result.stderr if isinstance(result.stderr, str) else ""
                stdout = result.stdout if isinstance(result.stdout, str) else ""
                last_error = stderr.strip() or stdout.strip() or f"adb failed: {command}"
            if attempt + 1 < attempts:
                time.sleep(0.4)
        raise AdbError(last_error or f"adb failed: {command}")

    def devices(self) -> list[str]:
        serial = self.serial
        self.serial = None
        try:
            result = self.command(["devices"])
        finally:
            self.serial = serial
        devices = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def resolve_serial(self) -> str:
        if self.serial:
            return self.serial
        devices = self.devices()
        if not devices:
            raise AdbError("No connected adb device found.")
        self.serial = devices[0]
        return self.serial

    def tap(self, x: int, y: int) -> None:
        self.command(["shell", "input", "tap", str(x), str(y)], retries=0)

    def keyevent(self, code: int) -> None:
        self.command(["shell", "input", "keyevent", str(code)], retries=0)

    def text(self, value: str) -> None:
        escaped = value.replace("%", "%s").replace(" ", "%s")
        self.command(["shell", "input", "text", escaped], retries=0)

    def broadcast_text(self, value: str) -> None:
        self.command(["shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", value], retries=0)

    def broadcast_base64_text(self, value: str) -> None:
        encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
        self.command(["shell", "am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", encoded], retries=0)

    def broadcast_clear_text(self) -> None:
        self.command(["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"], retries=0)

    def list_imes(self) -> list[str]:
        result = self.command(["shell", "ime", "list", "-s"])
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def current_ime(self) -> str:
        return self.command(["shell", "settings", "get", "secure", "default_input_method"], check=False).stdout.strip()

    def set_ime(self, ime: str) -> None:
        self.command(["shell", "ime", "set", ime], retries=0)

    def dump_xml(self) -> str:
        remote = f"/sdcard/mobile-auto-deepseek-window-{self.remote_tag}.xml"
        last_error: Exception | None = None
        for _ in range(3):
            try:
                # dump_xml already owns the bounded three-attempt retry loop.
                self.command(["shell", "uiautomator", "dump", remote], retries=0)
                xml = self.command(["shell", "cat", remote]).stdout
                if xml and "<hierarchy" in xml:
                    return xml
                last_error = AdbError("uiautomator dump did not produce valid hierarchy xml")
            except Exception as exc:
                last_error = exc
                cat_result = self.command(["shell", "cat", remote], check=False)
                xml = cat_result.stdout or ""
                if "<hierarchy" in xml:
                    return xml
            time.sleep(0.8)
        raise AdbError(str(last_error) if last_error else "uiautomator dump failed")

    def screenshot(self, path: str | Path) -> bool:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        remote = f"/sdcard/mobile-auto-deepseek-screen-{self.remote_tag}.png"
        shot = self.command(["shell", "screencap", "-p", remote], check=False)
        if shot.returncode != 0:
            return False
        pull = self.command(["pull", remote, str(target)], check=False)
        return pull.returncode == 0 and target.exists() and target.stat().st_size > 0

    def current_focus(self) -> str:
        result = self.command(["shell", "dumpsys", "window"], check=False)
        lines = [line.strip() for line in result.stdout.splitlines() if "mCurrentFocus" in line or "mFocusedApp" in line]
        return "\n".join(lines)

    def current_focus_package(self) -> str:
        """Return the package name of the currently focused window."""
        result = self.command(["shell", "dumpsys", "window"], check=False)
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if "mCurrentFocus" in stripped:
                # e.g. mCurrentFocus=Window{... com.deepseek.chat/.MainActivity}
                parts = stripped.split()
                for part in parts:
                    if "/" in part and "." in part.split("/")[0]:
                        return part.split("/")[0]
        return ""

    def start_app(self, package: str) -> None:
        self.command(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"], retries=0)

    def start_activity(self, component: str) -> None:
        """Start an activity by component name (e.g. com.deepseek.chat/.MainActivity)."""
        self.command(["shell", "am", "start", "-n", component], retries=0)

    def force_stop(self, package: str) -> None:
        self.command(["shell", "am", "force-stop", package], retries=0)
