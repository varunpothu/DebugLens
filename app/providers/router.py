"""Explicit provider registry; never silently switch to an unapproved model."""

from app.providers.base import VisionProvider


class ProviderUnavailableError(RuntimeError):
    """Raised when a requested provider is not registered or enabled."""


class ProviderRouter:
    def __init__(self, providers: list[VisionProvider] | None = None) -> None:
        self._providers = {provider.name: provider for provider in providers or []}

    def register(self, provider: VisionProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered.")
        self._providers[provider.name] = provider

    def get(self, name: str) -> VisionProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderUnavailableError(
                f"Provider '{name}' is not configured. No automatic provider fallback is allowed."
            ) from exc

    @property
    def available(self) -> list[str]:
        return sorted(self._providers)
