from typing import Any, Dict
import requests
import numpy as np
import json

from .base import BaseLLMTranslation
from ...utils.translator_utils import MODEL_MAP


class ClaudeTranslation(BaseLLMTranslation):
    """Translation engine using Anthropic Claude models via direct REST API calls."""
    
    def __init__(self):
        super().__init__()
        self.model_name = None
        self.api_key = None
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.headers = None
    
    def initialize(self, settings: Any, source_lang: str, target_lang: str, model_name: str, **kwargs) -> None:
        super().initialize(settings, source_lang, target_lang, **kwargs)
        
        self.temperature = self.temperature/2
        self.model_name = model_name
        credentials = settings.get_credentials(settings.ui.tr('Anthropic Claude'))
        self.api_key = credentials.get('api_key', '')
        
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        self.model = MODEL_MAP.get(self.model_name)
    
    def _perform_translation(self, user_prompt: str, system_prompt: str, image: np.ndarray) -> str:
        payload: Dict[str, Any] = {
            "model": self.model,
            "system": system_prompt,
            "max_tokens": self.max_tokens
        }

        if self.reasoning_enabled:
            payload["thinking"] = {
                "type": "enabled",
                "budget_tokens": min(8000, self.max_tokens)
            }
            payload["temperature"] = 1
        else:
            payload["temperature"] = self.temperature
        
        if self.img_as_llm_input and image is not None:
            encoded_image, media_type = self.encode_image(image)
            
            payload["messages"] = [
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": user_prompt}, 
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": encoded_image}}
                    ]
                }
            ]
        else:
            payload["messages"] = [
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": user_prompt}
                    ]
                }
            ]

        response = requests.post(
            self.api_url,
            headers=self.headers,
            data=json.dumps(payload),
            timeout=self.timeout
        )
        
        if response.status_code == 200:
            response_data = response.json()
            content_blocks = response_data.get('content', [])
            text_parts = []
            for block in content_blocks:
                if block.get('type') == 'text':
                    text_parts.append(block.get('text', ''))
            return ''.join(text_parts) if text_parts else response_data['content'][0]['text']
        else:
            error_msg = f"Error {response.status_code}: {response.text}"
            raise Exception(f"Claude API request failed: {error_msg}")
