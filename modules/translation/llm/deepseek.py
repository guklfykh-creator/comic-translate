from typing import Any

from .gpt import GPTTranslation
from ...utils.translator_utils import MODEL_MAP


class DeepseekTranslation(GPTTranslation):
    """Translation engine using Deepseek models with OpenAI-compatible API.
    
    Reasoning mode: Deepseek-R1 models have reasoning built in and do not
    require explicit parameters to enable it. For non-R1 models, reasoning
    mode has no additional effect beyond what the base GPT-compatible
    payload already includes (reasoning_effort is sent via GPTTranslation).
    """
    
    def __init__(self):
        super().__init__()
        self.supports_images = False
        self.api_base_url = "https://api.deepseek.com/v1"
    
    def initialize(self, settings: Any, source_lang: str, target_lang: str, model_name: str, **kwargs) -> None:
        super(GPTTranslation, self).initialize(settings, source_lang, target_lang, **kwargs)
        
        self.model_name = model_name
        credentials = settings.get_credentials(settings.ui.tr('Deepseek'))
        self.api_key = credentials.get('api_key', '')
        self.model = MODEL_MAP.get(self.model_name)
