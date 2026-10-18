"""Private immutable file storage; no host path or caller filename becomes a URL."""

import os
import re
import stat
from pathlib import Path
from typing import Protocol

from app.config import get_settings


class StorageError(Exception):
    pass


class StorageCollisionError(StorageError):
    """An existing object was not created by this upload."""


class StorageProvider(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorageProvider:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", key):
            raise StorageError("Invalid storage key")
        return self.root / key

    def put(self, key: str, data: bytes) -> None:
        path = self.path(key)
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Exclusive create: never overwrite, follow symlinks, or trust a filename.
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            self.sync_directory()
        except FileExistsError:
            raise StorageCollisionError("Storage key already exists") from None
        except OSError:
            # A durable cleanup intent already exists before put() is called.
            raise StorageError("Storage write failed") from None

    def read(self, key: str) -> bytes:
        try:
            descriptor = os.open(self.path(key), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise StorageError("Stored object is not a regular file")
                # Reducing future upload limits must not hide existing valid images.
                data = source.read(8 * 1024 * 1024 + 1)
                if len(data) > 8 * 1024 * 1024:
                    raise StorageError("Stored object exceeds configured size")
                return data
        except FileNotFoundError:
            raise
        except OSError:
            raise StorageError("Storage read failed") from None

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink(missing_ok=True)
            if self.root.exists():
                self.sync_directory()
        except OSError:
            raise StorageError("Storage delete failed") from None

    def sync_directory(self) -> None:
        descriptor = os.open(self.root, os.O_DIRECTORY | os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def get_storage() -> StorageProvider:
    return LocalStorageProvider(get_settings().image_storage_root)
