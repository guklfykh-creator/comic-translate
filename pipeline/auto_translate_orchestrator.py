from __future__ import annotations

import json
import logging
import time
import traceback
from typing import TYPE_CHECKING, Callable, Optional

import requests
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor

from modules.detection.processor import TextBlockDetector
from modules.translation.processor import Translator
from modules.utils.textblock import sort_blk_list
from modules.utils.pipeline_config import get_config
from modules.utils.image_utils import generate_mask, get_smart_text_color
from modules.utils.language_utils import get_language_code, is_no_space_lang, to_canonical_language_name
from modules.utils.translator_utils import (
    get_raw_translation, get_raw_text, format_translations, is_renderable_translation
)
from modules.rendering.render import get_best_render_area, pyside_word_wrap, is_vertical_block
from modules.utils.device import resolve_device
from modules.utils.exceptions import InsufficientCreditsException
from app.path_materialization import ensure_path_materialized
from app.ui.canvas.text_item import OutlineInfo, OutlineType
from app.ui.canvas.text.text_item_properties import TextItemProperties
from .inpainting import call_inpaint_image
import imkit as imk

if TYPE_CHECKING:
    from controller import ComicTranslate
    from .cache_manager import CacheManager
    from .block_detection import BlockDetectionHandler
    from .inpainting import InpaintingHandler
    from .ocr_handler import OCRHandler

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 1.0


class AutoTranslateProgress:
    __slots__ = ("completed", "total", "current_page", "failed_paths", "start_time")

    def __init__(self, total: int):
        self.completed = 0
        self.total = total
        self.current_page = ""
        self.failed_paths: list[dict] = []
        self.start_time = time.time()


class AutoTranslateOrchestrator:
    def __init__(
        self,
        main_page: ComicTranslate,
        cache_manager,
        block_detection: BlockDetectionHandler,
        inpainting: InpaintingHandler,
        ocr_handler: OCRHandler,
    ):
        self.main_page = main_page
        self.cache_manager = cache_manager
        self.block_detection = block_detection
        self.inpainting = inpainting
        self.ocr_handler = ocr_handler
        self._cancelled = False
        self.progress: Optional[AutoTranslateProgress] = None
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(self, callback: Callable):
        self._progress_callback = callback

    def cancel(self):
        self._cancelled = True

    def run(
        self,
        image_paths: list[str],
        provider_name: str,
        source_lang: str,
        target_lang: str,
        reasoning_enabled: bool,
        system_prompt: str,
    ) -> dict:
        self._cancelled = False
        self.progress = AutoTranslateProgress(len(image_paths))

        settings_page = self.main_page.settings_page

        self._apply_settings_overrides(reasoning_enabled, system_prompt)

        try:
            for index, image_path in enumerate(image_paths):
                if self._cancelled:
                    break

                self._emit_progress(current_page=os.path.basename(image_path))

                state = self.main_page.image_states.get(image_path, {})
                if state.get('skip', False):
                    self.progress.completed += 1
                    self._emit_progress()
                    continue

                success = False
                last_error = ""
                for attempt in range(MAX_RETRIES + 1):
                    if self._cancelled:
                        break
                    try:
                        self._process_single_page(
                            image_path, index, settings_page,
                            source_lang, target_lang, provider_name,
                        )
                        success = True
                        break
                    except InsufficientCreditsException:
                        raise
                    except Exception as e:
                        last_error = str(e)
                        if attempt < MAX_RETRIES:
                            wait_time = BACKOFF_BASE * (2 ** attempt)
                            logger.warning(
                                "Page %s attempt %d failed: %s. Retrying in %.1fs...",
                                os.path.basename(image_path), attempt + 1, last_error, wait_time,
                            )
                            time.sleep(wait_time)

                if not success and not self._cancelled:
                    self.progress.failed_paths.append({
                        "path": image_path,
                        "reason": self._summarize_error(last_error),
                    })
                    self.main_page.image_skipped.emit(image_path, "Translator", last_error)

                self.progress.completed += 1
                self._emit_progress()

        except InsufficientCreditsException:
            raise
        finally:
            self._restore_settings_overrides()

        elapsed = time.time() - self.progress.start_time
        return {
            "total": self.progress.total,
            "succeeded": self.progress.total - len(self.progress.failed_paths),
            "failed": len(self.progress.failed_paths),
            "failed_paths": self.progress.failed_paths,
            "total_time": elapsed,
            "was_cancelled": self._cancelled,
        }

    def _process_single_page(
        self,
        image_path: str,
        index: int,
        settings_page,
        source_lang: str,
        target_lang: str,
        provider_name: str,
    ):
        ensure_path_materialized(image_path)
        image = imk.read_image(image_path)
        if image is None:
            raise RuntimeError(f"Failed to load image: {image_path}")

        file_on_display = self.main_page.image_files[self.main_page.curr_img_idx] if 0 <= self.main_page.curr_img_idx < len(self.main_page.image_files) else None

        # 1. Block Detection
        if self.block_detection.block_detector_cache is None:
            self.block_detection.block_detector_cache = TextBlockDetector(settings_page)
        blk_list = self.block_detection.block_detector_cache.detect(image)

        self.block_detection.annotate_language_if_auto(image, blk_list, source_lang)

        if not blk_list:
            raise RuntimeError("No text blocks detected")

        # 2. OCR
        ocr_model = settings_page.get_tool_selection('ocr')
        device = resolve_device(settings_page.is_gpu_enabled())
        cache_key = self.cache_manager._get_ocr_cache_key(image, source_lang, ocr_model, device)

        self.ocr_handler.ocr.initialize(self.main_page, source_lang)
        try:
            self.ocr_handler.ocr.process(image, blk_list)
            self.cache_manager._cache_ocr_results(cache_key, self.main_page.blk_list)
            rtl = True if source_lang == 'Japanese' else False
            blk_list = sort_blk_list(blk_list, rtl)
        except Exception as e:
            raise RuntimeError(f"OCR failed: {e}") from e

        # 3. Translation
        extra_context = settings_page.get_llm_settings()['extra_context']
        translator_key = settings_page.get_tool_selection('translator')

        source_lang_en = self.main_page.lang_mapping.get(source_lang, source_lang)
        target_lang_en = self.main_page.lang_mapping.get(target_lang, target_lang)

        translator = Translator(self.main_page, source_lang_en, target_lang_en)
        translator.translate(blk_list, image, extra_context)

        # Validate translation output
        entire_raw_text = get_raw_text(blk_list)
        entire_translated_text = get_raw_translation(blk_list)
        try:
            raw_text_obj = json.loads(entire_raw_text)
            translated_text_obj = json.loads(entire_translated_text)
            if (not raw_text_obj) or (not translated_text_obj):
                raise RuntimeError("Translation returned empty result")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Translation produced invalid JSON: {e}") from e

        # 4. Inpainting
        config = get_config(settings_page)
        inpaint_blk_list = [
            blk for blk in blk_list
            if blk.text and blk.text.strip() and blk.translation and blk.translation.strip()
            and is_renderable_translation(blk.translation)
        ]

        mask = generate_mask(image, inpaint_blk_list)
        inpaint_input_img = call_inpaint_image(self.inpainting, image, mask, config, blk_list=inpaint_blk_list)
        inpaint_input_img = imk.convert_scale_abs(inpaint_input_img)

        patches = self.inpainting.get_inpainted_patches(mask, inpaint_input_img)
        self.main_page.patches_processed.emit(patches, image_path)

        # 5. Text Rendering
        render_settings = self.main_page.render_settings()
        upper_case = render_settings.upper_case
        outline = render_settings.outline
        trg_lng_cd = get_language_code(target_lang)
        format_translations(blk_list, trg_lng_cd, upper_case=upper_case)
        get_best_render_area(blk_list, image, inpaint_input_img)

        font = render_settings.font_family
        setting_font_color = QColor(render_settings.color)
        max_font_size = render_settings.max_font_size
        min_font_size = render_settings.min_font_size
        line_spacing = float(render_settings.line_spacing)
        outline_width = float(render_settings.outline_width)
        outline_color = QColor(render_settings.outline_color) if outline else None
        bold = render_settings.bold
        italic = render_settings.italic
        underline = render_settings.underline
        alignment_id = render_settings.alignment_id
        alignment = self.main_page.button_to_alignment[alignment_id]
        direction = render_settings.direction

        text_items_state = []
        for blk in blk_list:
            x1, y1, block_width, block_height = blk.xywh
            translation = blk.translation
            if not is_renderable_translation(translation):
                continue

            vertical = is_vertical_block(blk, trg_lng_cd)

            translation, font_size, rendered_width, rendered_height = pyside_word_wrap(
                translation, font, block_width, block_height,
                line_spacing, outline_width, bold, italic, underline,
                alignment, direction, max_font_size, min_font_size,
                vertical, is_no_space_lang(trg_lng_cd),
                return_metrics=True
            )

            if image_path == file_on_display:
                self.main_page.blk_rendered.emit(translation, font_size, blk, image_path)

            font_color = get_smart_text_color(blk.font_color, setting_font_color)

            text_props = TextItemProperties(
                text=translation, font_family=font, font_size=font_size,
                text_color=font_color, alignment=alignment, line_spacing=line_spacing,
                outline_color=outline_color, outline_width=outline_width,
                bold=bold, italic=italic, underline=underline,
                position=(x1, y1), rotation=blk.angle, scale=1.0,
                transform_origin=blk.tr_origin_point, width=rendered_width,
                height=rendered_height, direction=direction, vertical=vertical,
                selection_outlines=[
                    OutlineInfo(0, len(translation), outline_color, outline_width, OutlineType.Full_Document)
                ] if outline else [],
            )
            text_items_state.append(text_props.to_dict())

        self.main_page.image_states[image_path]['viewer_state'].update({
            'text_items_state': text_items_state,
            'push_to_stack': True,
        })

        self.main_page.image_states[image_path].update({
            'blk_list': blk_list
        })

        self.main_page.render_state_ready.emit(image_path)

        if image_path == file_on_display:
            self.main_page.blk_list = blk_list

    def _apply_settings_overrides(self, reasoning_enabled: bool, system_prompt: str):
        self._saved_llm_settings = self.main_page.settings_page.get_llm_settings().copy()
        if reasoning_enabled:
            self.main_page.settings_page.ui.reasoning_checkbox.setChecked(True)
        if system_prompt.strip():
            self.main_page.settings_page.ui.system_prompt_edit.setPlainText(system_prompt)

    def _restore_settings_overrides(self):
        saved = getattr(self, '_saved_llm_settings', None)
        if saved:
            self.main_page.settings_page.ui.reasoning_checkbox.setChecked(
                saved.get('reasoning_enabled', False)
            )
            self.main_page.settings_page.ui.system_prompt_edit.setPlainText(
                saved.get('system_prompt', '')
            )

    def _emit_progress(self, current_page: str = None):
        if self.progress and self._progress_callback:
            if current_page:
                self.progress.current_page = current_page
            completed = self.progress.completed
            total = self.progress.total
            elapsed = time.time() - self.progress.start_time
            avg_time = elapsed / completed if completed > 0 else 0
            remaining = avg_time * (total - completed)
            self._progress_callback(completed, total, self.progress.current_page, remaining)

    @staticmethod
    def _summarize_error(error: str) -> str:
        if not error:
            return ""
        for line in str(error).splitlines():
            line = line.strip()
            if line:
                return line[:200]
        return ""
