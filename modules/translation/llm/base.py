from typing import Any
import numpy as np
from abc import abstractmethod
import base64
import imkit as imk

from ..base import LLMTranslation
from ...utils.textblock import TextBlock
from ...utils.translator_utils import get_raw_text, set_texts_from_json

BUILT_IN_SYSTEM_PROMPT = (
    "You are an expert translator who translates {source_lang} to {target_lang}. "
    "You pay attention to style, formality, idioms, slang etc and try to convey it "
    "in the way a {target_lang} speaker would understand.\n"
    "BE MORE NATURAL. NEVER USE 당신, 그녀, 그 or its Japanese equivalents.\n"
    "Specifically, you will be translating text OCR'd from a comic. The OCR is not "
    "perfect and as such you may receive text with typos or other mistakes.\n"
    "To aid you and provide context, You may be given the image of the page and/or "
    "extra context about the comic. You will be given a json string of the detected "
    "text blocks and the text to translate. Return the json string with the texts "
    "translated. DO NOT translate the keys of the json. For each block:\n"
    "- If it's already in {target_lang} or looks like gibberish, OUTPUT IT AS IT IS instead\n"
    "- DO NOT give explanations\n"
    "Do Your Best! I'm really counting on you."
)


class BaseLLMTranslation(LLMTranslation):
    """Base class for LLM-based translation engines with shared functionality."""
    
    def __init__(self):
        self.source_lang = None
        self.target_lang = None
        self.api_key = None
        self.api_url = None
        self.model = None
        self.img_as_llm_input = False
        self.temperature = None
        self.top_p = None
        self.max_tokens = None
        self.timeout = 30
        self.reasoning_enabled = False
        self.system_prompt = None
    
    def initialize(self, settings: Any, source_lang: str, target_lang: str, **kwargs) -> None:
        llm_settings = settings.get_llm_settings()
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.img_as_llm_input = llm_settings.get('image_input_enabled', True)
        self.reasoning_enabled = llm_settings.get('reasoning_enabled', False)
        self.system_prompt = llm_settings.get('system_prompt', '')
        self.temperature = 1.0
        self.top_p = 0.95
        self.max_tokens = 5000

    def _resolve_system_prompt(self) -> str:
        if self.system_prompt and self.system_prompt.strip():
            prompt = self.system_prompt
            prompt = prompt.replace("{source_lang}", self.source_lang or "")
            prompt = prompt.replace("{target_lang}", self.target_lang or "")
            return prompt
        return self.get_system_prompt(self.source_lang, self.target_lang)
    
    def translate(self, blk_list: list[TextBlock], image: np.ndarray, extra_context: str) -> list[TextBlock]:
        entire_raw_text = get_raw_text(blk_list)
        system_prompt = self._resolve_system_prompt()
        user_prompt = f"{extra_context}\nMake the translation sound as natural as possible.\nTranslate this:\n{entire_raw_text}"
        
        entire_translated_text = self._perform_translation(user_prompt, system_prompt, image)
        set_texts_from_json(blk_list, entire_translated_text)
            
        return blk_list
    
    @abstractmethod
    def _perform_translation(self, user_prompt: str, system_prompt: str, image: np.ndarray) -> str:
        pass

    def encode_image(self, image: np.ndarray, ext=".jpg"):
        buffer = imk.encode_image(image, ext.lstrip('.'))
        img_str = base64.b64encode(buffer).decode('utf-8')
        mime_types = {
            ".jpg": "image/jpeg", 
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp"
        }
        mime_type = mime_types.get(ext.lower(), f"image/{ext[1:].lower()}")
        return img_str, mime_type
