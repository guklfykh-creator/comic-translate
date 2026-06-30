from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AIProvider:
    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    custom_headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 120

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "custom_headers": dict(self.custom_headers),
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AIProvider:
        return cls(
            name=data.get("name", ""),
            base_url=data.get("base_url", ""),
            api_key=data.get("api_key", ""),
            model=data.get("model", ""),
            custom_headers=data.get("custom_headers", {}),
            timeout=data.get("timeout", 120),
        )

    def validate_fields(self) -> tuple[bool, str]:
        if not self.name.strip():
            return False, "Provider name is required."
        if not self.base_url.strip():
            return False, "Base URL is required."
        if not self.api_key.strip():
            return False, "API Key is required."
        if not self.model.strip():
            return False, "Model is required."
        return True, ""

    @property
    def api_base_url(self) -> str:
        url = self.base_url.strip()
        if url.endswith("/"):
            url = url[:-1]
        return url
