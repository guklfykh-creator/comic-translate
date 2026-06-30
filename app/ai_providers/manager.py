from __future__ import annotations

import json
import logging
from typing import Optional

import requests
from PySide6.QtCore import QSettings

from .provider import AIProvider

logger = logging.getLogger(__name__)

_SETTINGS_ORG = "ComicLabs"
SETTINGS_APP = "ComicTranslate"
_PROVIDERS_GROUP = "ai_providers"
_ACTIVE_KEY = "active_provider_name"
_PROVIDER_NAMES_KEY = "provider_names"


class AIProviderManager:
    def __init__(self):
        self._settings = QSettings(_SETTINGS_ORG, SETTINGS_APP)

    def list_providers(self) -> list[AIProvider]:
        names = self._get_provider_names()
        providers = []
        for name in names:
            p = self._load_provider(name)
            if p is not None:
                providers.append(p)
        return providers

    def get_provider(self, name: str) -> Optional[AIProvider]:
        return self._load_provider(name)

    def add_provider(self, provider: AIProvider) -> None:
        names = self._get_provider_names()
        if provider.name in names:
            self.update_provider(provider.name, provider)
            return
        names.append(provider.name)
        self._save_provider_names(names)
        self._save_provider(provider)

    def update_provider(self, name: str, provider: AIProvider) -> None:
        names = self._get_provider_names()
        old_idx = names.index(name) if name in names else -1
        if old_idx == -1:
            return
        if provider.name != name:
            if provider.name in names:
                return
            names[old_idx] = provider.name
            self._save_provider_names(names)
            self._remove_provider_group(name)
        self._save_provider(provider)
        if self.active_provider_name() == name and provider.name != name:
            self.set_active_provider(provider.name)

    def delete_provider(self, name: str) -> None:
        names = self._get_provider_names()
        if name not in names:
            return
        names.remove(name)
        self._save_provider_names(names)
        self._remove_provider_group(name)
        if self.active_provider_name() == name:
            if names:
                self.set_active_provider(names[0])
            else:
                self.set_active_provider("")

    def active_provider_name(self) -> str:
        self._settings.beginGroup(_PROVIDERS_GROUP)
        name = self._settings.value(_ACTIVE_KEY, "", type=str)
        self._settings.endGroup()
        return name

    def set_active_provider(self, name: str) -> None:
        self._settings.beginGroup(_PROVIDERS_GROUP)
        self._settings.setValue(_ACTIVE_KEY, name)
        self._settings.endGroup()
        self._settings.sync()

    def get_active_provider(self) -> Optional[AIProvider]:
        name = self.active_provider_name()
        if not name:
            return None
        return self.get_provider(name)

    def validate_provider(self, provider: AIProvider) -> tuple[bool, str]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key}",
        }
        headers.update(provider.custom_headers)
        base = provider.api_base_url
        try:
            resp = requests.get(
                f"{base}/models",
                headers=headers,
                timeout=min(provider.timeout, 15),
            )
            if resp.status_code == 200:
                return True, "Connection successful."
            if resp.status_code == 401 or resp.status_code == 403:
                return False, f"Authentication failed (HTTP {resp.status_code}). Check your API key."
            if resp.status_code == 404:
                try:
                    resp2 = requests.post(
                        f"{base}/chat/completions",
                        headers=headers,
                        json={
                            "model": provider.model,
                            "messages": [{"role": "user", "content": "hi"}],
                            "max_tokens": 1,
                        },
                        timeout=min(provider.timeout, 15),
                    )
                    if resp2.status_code in (200, 201):
                        return True, "Connection successful."
                    if resp2.status_code in (401, 403):
                        return False, f"Authentication failed (HTTP {resp2.status_code})."
                    try:
                        detail = resp2.json().get("error", {}).get("message", resp2.text[:200])
                    except Exception:
                        detail = resp2.text[:200]
                    return False, f"HTTP {resp2.status_code}: {detail}"
                except requests.exceptions.ConnectTimeout:
                    return False, "Connection timed out."
                except requests.exceptions.ConnectionError:
                    return False, "Could not connect to the server."
            try:
                detail = resp.json().get("error", {}).get("message", resp.text[:200])
            except Exception:
                detail = resp.text[:200]
            return False, f"HTTP {resp.status_code}: {detail}"
        except requests.exceptions.ConnectTimeout:
            return False, "Connection timed out."
        except requests.exceptions.ConnectionError:
            return False, "Could not connect to the server. Check the Base URL."
        except Exception as e:
            return False, f"Connection test failed: {e}"

    def _get_provider_names(self) -> list[str]:
        self._settings.beginGroup(_PROVIDERS_GROUP)
        raw = self._settings.value(_PROVIDER_NAMES_KEY, "")
        self._settings.endGroup()
        if not raw:
            return []
        try:
            names = json.loads(raw)
            if isinstance(names, list):
                return [n for n in names if isinstance(n, str)]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def _save_provider_names(self, names: list[str]) -> None:
        self._settings.beginGroup(_PROVIDERS_GROUP)
        self._settings.setValue(_PROVIDER_NAMES_KEY, json.dumps(names))
        self._settings.endGroup()
        self._settings.sync()

    def _save_provider(self, provider: AIProvider) -> None:
        self._settings.beginGroup(_PROVIDERS_GROUP)
        self._settings.beginGroup(provider.name)
        self._settings.setValue("base_url", provider.base_url)
        self._settings.setValue("api_key", provider.api_key)
        self._settings.setValue("model", provider.model)
        self._settings.setValue("custom_headers", json.dumps(provider.custom_headers))
        self._settings.setValue("timeout", provider.timeout)
        self._settings.endGroup()
        self._settings.endGroup()
        self._settings.sync()

    def _load_provider(self, name: str) -> Optional[AIProvider]:
        self._settings.beginGroup(_PROVIDERS_GROUP)
        self._settings.beginGroup(name)
        base_url = self._settings.value("base_url", "", type=str)
        api_key = self._settings.value("api_key", "", type=str)
        model = self._settings.value("model", "", type=str)
        raw_headers = self._settings.value("custom_headers", "{}", type=str)
        timeout = self._settings.value("timeout", 120, type=int)
        self._settings.endGroup()
        self._settings.endGroup()
        try:
            custom_headers = json.loads(raw_headers) if raw_headers else {}
            if not isinstance(custom_headers, dict):
                custom_headers = {}
        except (json.JSONDecodeError, TypeError):
            custom_headers = {}
        return AIProvider(
            name=name,
            base_url=base_url,
            api_key=api_key,
            model=model,
            custom_headers=custom_headers,
            timeout=timeout,
        )

    def _remove_provider_group(self, name: str) -> None:
        self._settings.beginGroup(_PROVIDERS_GROUP)
        self._settings.beginGroup(name)
        self._settings.remove("")
        self._settings.endGroup()
        self._settings.endGroup()
        self._settings.sync()

    def set_provider_credentials_for_translator(self, provider: AIProvider) -> dict:
        return {
            "save_key": True,
            "api_key": provider.api_key,
            "api_url": provider.base_url,
            "model": provider.model,
            "custom_headers": provider.custom_headers,
            "timeout": provider.timeout,
        }
