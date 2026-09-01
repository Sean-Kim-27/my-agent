"""Secret storage abstraction backed by the operating-system credential store."""

from __future__ import annotations

from typing import Protocol


class SecretStoreError(RuntimeError):
    pass


class SecretStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...

    def delete(self, key: str) -> bool: ...


class KeyringSecretStore:
    def __init__(self, service_name: str = "myagen") -> None:
        self.service_name = service_name

    def get(self, key: str) -> str | None:
        try:
            import keyring

            return keyring.get_password(self.service_name, key)
        except Exception as exc:
            raise SecretStoreError(
                "Secure credential backend is unavailable; configure an OS keyring"
            ) from exc

    def set(self, key: str, value: str) -> None:
        if not value:
            raise ValueError("Secret value cannot be empty")
        try:
            import keyring

            keyring.set_password(self.service_name, key, value)
        except Exception as exc:
            raise SecretStoreError(
                "Secure credential backend is unavailable; secret was not stored"
            ) from exc

    def delete(self, key: str) -> bool:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError

            try:
                keyring.delete_password(self.service_name, key)
            except PasswordDeleteError:
                return False
            return True
        except Exception as exc:
            raise SecretStoreError(
                "Secure credential backend is unavailable; secret was not removed"
            ) from exc


class MemorySecretStore:
    """In-memory implementation for tests and explicitly ephemeral callers."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value

    def delete(self, key: str) -> bool:
        return self.values.pop(key, None) is not None


__all__ = [
    "KeyringSecretStore",
    "MemorySecretStore",
    "SecretStore",
    "SecretStoreError",
]
