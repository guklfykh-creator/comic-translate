from typing import Any
from .gpt import GPTTranslation


class CustomTranslation(GPTTranslation):
    """Translation engine using custom LLM configurations with OpenAI-compatible API."""
    
    def __init__(self):
        super().__init__()
    
    def initialize(self, settings: Any, source_lang: str, target_lang: str, tr_key: str, **kwargs) -> None:
        super(GPTTranslation, self).initialize(settings, source_lang, target_lang, **kwargs)
        
        credentials = settings.get_credentials(settings.ui.tr(tr_key))
        self.api_key = credentials.get('api_key', '')
        self.model = credentials.get('model', '')
        self.api_base_url = credentials.get('api_url', '').rstrip('/')
        custom_headers = credentials.get('custom_headers', {})
        if isinstance(custom_headers, dict):
            self.custom_headers = custom_headers
        else:
            self.custom_headers = {}
        timeout_val = credentials.get('timeout', 120)
        try:
            self.timeout = int(timeout_val)
        except (ValueError, TypeError):
            self.timeout = 120
