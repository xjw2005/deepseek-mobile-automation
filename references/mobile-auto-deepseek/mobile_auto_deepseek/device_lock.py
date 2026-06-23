import hashlib
import json
import os
import tempfile
from pathlib import Path


class DeviceBusyError(RuntimeError):
    """Raised when another runner already owns the target Android device."""


class DeviceProcessLock:
    """Non-blocking OS file lock keyed by adb device serial."""

    def __init__(self, serial: str):
        self.serial = str(serial or "unknown-device")
        digest = hashlib.sha256(self.serial.encode("utf-8")).hexdigest()[:16]
        self.path = Path(tempfile.gettempdir()) / f"mobile-auto-device-{digest}.lock"
        self._handle = None

    def acquire(self) -> "DeviceProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise DeviceBusyError(
                f"ADB device {self.serial!r} is already controlled by another mobile runner "
                f"(lock: {self.path})."
            ) from exc

        metadata = json.dumps({"pid": os.getpid(), "serial": self.serial}, ensure_ascii=False).encode("utf-8")
        handle.seek(0)
        handle.truncate()
        handle.write(metadata or b"\0")
        handle.flush()
        handle.seek(0)
        self._handle = handle
        return self

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None

    def __enter__(self) -> "DeviceProcessLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()
