from typing import Any
import numpy as np
import requests

from .base import BaseLLMTranslation
from ...utils.translator_utils import MODEL_MAP


class GeminiTranslation(BaseLLMTranslation):
    """Translation engine using Google Gemini models via REST API."""
    
    def __init__(self):
        super().__init__()
        self.model_name = None
        self.api_key = None
        self.api_base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    
    def initialize(self, settings: Any, source_lang: str, target_lang: str, model_name: str, **kwargs) -> None:
        super().initialize(settings, source_lang, target_lang, **kwargs)
        
        self.model_name = model_name
        credentials = settings.get_credentials(settings.ui.tr('Google Gemini'))
        self.api_key = credentials.get('api_key', '')
        
        self.model_api_name = MODEL_MAP.get(self.model_name)
    
    def _perform_translation(self, user_prompt: str, system_prompt: str, image: np.ndarray) -> str:
        url = f"{self.api_base_url}/{self.model_api_name}:generateContent?key={self.api_key}"
        
        if self.reasoning_enabled:
            thinking_level = "medium"
        elif self.model_name in ["Gemini-3.1-Flash-Lite"]:
            thinking_level = "minimal"
        else:
            thinking_level = "low"

        generation_config = {
            "temperature": self.temperature,
            "maxOutputTokens": self.max_tokens,
            "thinkingConfig": {
                "thinkingLevel": thinking_level
            },
        }
        
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        parts = []
        
        if self.img_as_llm_input:
            img_b64, mime_type = self.encode_image(image)
            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": img_b64
                }
            })
        
        parts.append({"text": user_prompt})
        
        payload = {
            "contents": [{
                "parts": parts
            }],
            "generationConfig": generation_config,
            "safetySettings": safety_settings
        }
        
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            url, 
            headers=headers, 
            json=payload,
            timeout=self.timeout
        )
        
        if response.status_code != 200:
            error_msg = f"API request failed with status code {response.status_code}: {response.text}"
            raise Exception(error_msg)
        
        response_data = response.json()
        
        candidates = response_data.get("candidates", [])
        if not candidates:
            return "No response generated"
        
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        
        result = ""
        for part in parts:
            if "text" in part:
                result += part["text"]
        
        return result
