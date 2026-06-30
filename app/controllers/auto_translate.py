from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore

from app.ui.dayu_widgets.message import MMessage
from app.ui.messages import Messages
from modules.utils.exceptions import InsufficientCreditsException
from pipeline.auto_translate_orchestrator import AutoTranslateOrchestrator

if TYPE_CHECKING:
    from controller import ComicTranslate

logger = logging.getLogger(__name__)


class AutoTranslateController(QtCore.QObject):
    progress_updated = QtCore.Signal(int, int, str, float)
    translation_finished = QtCore.Signal(dict)

    def __init__(self, main: ComicTranslate, parent=None):
        super().__init__(parent)
        self.main = main
        self._orchestrator: Optional[AutoTranslateOrchestrator] = None
        self._is_running = False
        self._failed_paths: list[dict] = []

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start_translation(self):
        if self._is_running:
            return

        page = self.main.auto_translate_page
        provider_name = page.get_selected_provider_name()

        if not provider_name:
            MMessage.error(
                self.main.tr("No AI provider configured. Add a provider in Settings > AI Providers."),
                parent=self.main, duration=5, closable=True
            )
            return

        provider = self.main.ai_provider_mgr.get_provider(provider_name)
        if provider is None:
            MMessage.error(
                self.main.tr("Selected provider not found. Check Settings > AI Providers."),
                parent=self.main, duration=5, closable=True
            )
            return

        selected_paths = page.get_selected_paths()
        if not selected_paths:
            MMessage.error(
                self.main.tr("No pages selected for translation."),
                parent=self.main, duration=3, closable=True
            )
            return

        source_lang = page.source_combo.currentText()
        target_lang = page.target_combo.currentText()

        if not source_lang or not target_lang:
            MMessage.error(
                self.main.tr("Please select source and target languages."),
                parent=self.main, duration=3, closable=True
            )
            return

        if not self.main.render_settings().font_family:
            Messages.select_font_error(self.main)
            return

        self._apply_provider_credentials(provider)

        reasoning_enabled = page.reasoning_checkbox.isChecked()
        system_prompt = page.system_prompt_edit.toPlainText()

        self._orchestrator = AutoTranslateOrchestrator(
            self.main,
            self.main.pipeline.cache_manager,
            self.main.pipeline.block_detection,
            self.main.pipeline.inpainting,
            self.main.pipeline.ocr_handler,
        )
        self._orchestrator.set_progress_callback(self._on_progress)

        page.show_progress()
        page.set_running(True)
        self._is_running = True
        self._failed_paths = []

        source_lang_en = self.main.lang_mapping.get(source_lang, source_lang)
        target_lang_en = self.main.lang_mapping.get(target_lang, target_lang)

        self.main.run_threaded(
            lambda: self._orchestrator.run(
                image_paths=selected_paths,
                provider_name=provider_name,
                source_lang=source_lang_en,
                target_lang=target_lang_en,
                reasoning_enabled=reasoning_enabled,
                system_prompt=system_prompt,
            ),
            self._on_result,
            self._on_error,
            self._on_finished,
        )

    def cancel_translation(self):
        if self._orchestrator:
            self._orchestrator.cancel()
        self.main.auto_translate_page.set_cancelled()

    def _apply_provider_credentials(self, provider):
        settings_page = self.main.settings_page
        creds = self.main.ai_provider_mgr.set_provider_credentials_for_translator(provider)

        translated_custom = settings_page.ui.tr("Custom")

        settings_page.ui.credential_widgets[f"Custom_api_key"].setText(provider.api_key)
        settings_page.ui.credential_widgets[f"Custom_api_url"].setText(provider.api_url)
        settings_page.ui.credential_widgets[f"Custom_model"].setText(provider.model)

        current_translator = settings_page.get_tool_selection('translator')
        translated_custom_key = settings_page.ui.value_mappings.get("Custom", "Custom")
        if current_translator != translated_custom_key:
            idx = settings_page.ui.translator_combo.findText(translated_custom)
            if idx >= 0:
                settings_page.ui.translator_combo.setCurrentIndex(idx)

        from modules.translation.factory import TranslationFactory
        TranslationFactory._engines.clear()

    def _on_progress(self, completed: int, total: int, current_page: str, eta_seconds: float):
        QtCore.QMetaObject.invokeMethod(
            self, "_emit_progress_signal",
            QtCore.Qt.ConnectionType.QueuedConnection,
            QtCore.Q_ARG(int, completed),
            QtCore.Q_ARG(int, total),
            QtCore.Q_ARG(str, current_page),
            QtCore.Q_ARG(float, eta_seconds),
        )

    @QtCore.Slot(int, int, str, float)
    def _emit_progress_signal(self, completed: int, total: int, current_page: str, eta_seconds: float):
        page = self.main.auto_translate_page
        page.update_progress(completed, total, current_page, eta_seconds)

    def _on_result(self, summary: dict):
        if summary is not None:
            self._failed_paths = summary.get("failed_paths", [])
            QtCore.QMetaObject.invokeMethod(
                self, "_show_summary",
                QtCore.Qt.ConnectionType.QueuedConnection,
                QtCore.Q_ARG(dict, summary),
            )

    @QtCore.Slot(dict)
    def _show_summary(self, summary: dict):
        self.main.auto_translate_page.show_summary(summary)

    def _on_error(self, error_tuple):
        exctype, value, traceback_str = error_tuple
        logger.error(f"Auto-translate error: {exctype}: {value}")
        if exctype is InsufficientCreditsException:
            Messages.show_insufficient_credits_error(self.main, details=str(value))
        else:
            Messages.show_error_with_copy(
                self.main,
                self.main.tr("Auto Translate Error"),
                f"An error occurred:\n{exctype.__name__}: {value}",
                traceback_str,
            )
        self.main.auto_translate_page.set_running(False)
        self._is_running = False

    def _on_finished(self):
        self._is_running = False
        self._orchestrator = None
        self.main.auto_translate_page.set_running(False)

        try:
            self.main.pipeline.release_model_caches()
        except Exception:
            pass

    def retry_failed(self):
        if not self._failed_paths:
            return
        retry_paths = [
            entry["path"]
            for entry in self._failed_paths
            if entry.get("path") in self.main.image_files
        ]
        if retry_paths:
            page = self.main.auto_translate_page
            for i in range(page.page_list.count()):
                item = page.page_list.item(i)
                path = item.data(QtCore.Qt.ItemDataRole.UserRole)
                item.setCheckState(
                    QtCore.Qt.CheckState.Checked if path in retry_paths
                    else QtCore.Qt.CheckState.Unchecked
                )
            self.start_translation()
