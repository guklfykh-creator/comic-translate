from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Optional

from PySide6 import QtWidgets, QtCore

from ..dayu_widgets.label import MLabel
from ..dayu_widgets.text_edit import MTextEdit
from ..dayu_widgets.check_box import MCheckBox
from ..dayu_widgets.push_button import MPushButton
from ..dayu_widgets.combo_box import MComboBox
from ..dayu_widgets.progress_bar import MProgressBar
from ..dayu_widgets.divider import MDivider
from ..dayu_widgets import dayu_theme
from ..main_window.constants import supported_source_languages, supported_target_languages
from ..settings.llms_page import BUILT_IN_SYSTEM_PROMPT

if TYPE_CHECKING:
    from app.ai_providers.manager import AIProviderManager


class AutoTranslatePage(QtWidgets.QWidget):
    start_requested = QtCore.Signal()
    cancel_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager: Optional[AIProviderManager] = None
        self._setup_ui()

    def set_manager(self, manager: AIProviderManager):
        self._manager = manager
        self._refresh_providers()

    def _setup_ui(self):
        outer = QtWidgets.QVBoxLayout(self)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)

        title = MLabel(self.tr("Auto Multi-Page Translation")).h3()
        layout.addWidget(title)
        layout.addSpacing(5)

        desc = MLabel(self.tr(
            "Automatically translate multiple pages using a configured AI provider. "
            "Select pages, choose your provider and model, then start translation."
        )).secondary()
        desc.setWordWrap(True)
        layout.addWidget(desc)
        layout.addSpacing(10)

        # ---- Page Selection ----
        layout.addWidget(MDivider(self.tr("Page Selection")))

        sel_layout = QtWidgets.QHBoxLayout()
        self.select_all_btn = MPushButton(self.tr("Select All")).small()
        self.deselect_all_btn = MPushButton(self.tr("Deselect All")).small()
        sel_layout.addWidget(self.select_all_btn)
        sel_layout.addWidget(self.deselect_all_btn)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        range_layout = QtWidgets.QHBoxLayout()
        range_layout.addWidget(MLabel(self.tr("From:")))
        self.range_from_spin = QtWidgets.QSpinBox()
        self.range_from_spin.setMinimum(1)
        self.range_from_spin.setPrefix("#")
        range_layout.addWidget(self.range_from_spin)
        range_layout.addWidget(MLabel(self.tr("To:")))
        self.range_to_spin = QtWidgets.QSpinBox()
        self.range_to_spin.setMinimum(1)
        self.range_to_spin.setPrefix("#")
        range_layout.addWidget(self.range_to_spin)
        self.range_select_btn = MPushButton(self.tr("Select Range")).small()
        range_layout.addWidget(self.range_select_btn)
        range_layout.addStretch()
        layout.addLayout(range_layout)

        self.page_list = QtWidgets.QListWidget()
        self.page_list.setMinimumHeight(160)
        layout.addWidget(self.page_list)

        layout.addSpacing(10)

        # ---- Provider & Model ----
        layout.addWidget(MDivider(self.tr("Provider & Model")))

        provider_layout = QtWidgets.QHBoxLayout()
        provider_layout.addWidget(MLabel(self.tr("Provider:")))
        self.provider_combo = MComboBox().small()
        self.provider_combo.setMinimumWidth(200)
        provider_layout.addWidget(self.provider_combo, 1)
        provider_layout.addWidget(MLabel(self.tr("Model:")))
        self.model_label = MLabel("").strong()
        self.model_label.setMinimumWidth(120)
        provider_layout.addWidget(self.model_label)
        layout.addLayout(provider_layout)
        layout.addSpacing(5)

        # ---- Language Selection ----
        layout.addWidget(MDivider(self.tr("Languages")))

        lang_layout = QtWidgets.QHBoxLayout()
        lang_layout.addWidget(MLabel(self.tr("Source:")))
        self.source_combo = MComboBox().small()
        for lang in supported_source_languages:
            self.source_combo.addItem(self.tr(lang))
        lang_layout.addWidget(self.source_combo)
        lang_layout.addWidget(MLabel(self.tr("Target:")))
        self.target_combo = MComboBox().small()
        for lang in supported_target_languages:
            self.target_combo.addItem(self.tr(lang))
        lang_layout.addWidget(self.target_combo)
        lang_layout.addStretch()
        layout.addLayout(lang_layout)
        layout.addSpacing(10)

        # ---- Reasoning & System Prompt ----
        layout.addWidget(MDivider(self.tr("Translation Settings")))

        self.reasoning_checkbox = MCheckBox(self.tr("Enable Reasoning/Thinking Mode"))
        self.reasoning_checkbox.setToolTip(
            self.tr("Enable extended reasoning. May increase token usage and cost.")
        )
        layout.addWidget(self.reasoning_checkbox)

        prompt_header = QtWidgets.QHBoxLayout()
        prompt_header.addWidget(MLabel(self.tr("System Prompt:")))
        prompt_header.addStretch()
        self.restore_prompt_btn = MPushButton(self.tr("Restore Default")).small()
        self.restore_prompt_btn.set_dayu_type(MPushButton.DefaultType)
        prompt_header.addWidget(self.restore_prompt_btn)
        layout.addLayout(prompt_header)

        self.system_prompt_edit = MTextEdit()
        self.system_prompt_edit.setMinimumHeight(140)
        self.system_prompt_edit.setPlaceholderText(
            self.tr("Leave empty to use the built-in default. "
                    "Use {source_lang} and {target_lang} as placeholders.")
        )
        layout.addWidget(self.system_prompt_edit)

        layout.addSpacing(10)

        # ---- Start / Cancel ----
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_btn = MPushButton(self.tr("Start Translation"))
        self.start_btn.set_dayu_type(MPushButton.PrimaryType)
        self.start_btn.setMinimumHeight(36)
        self.cancel_btn = MPushButton(self.tr("Cancel"))
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setMinimumHeight(36)
        btn_layout.addWidget(self.start_btn, 1)
        btn_layout.addWidget(self.cancel_btn, 1)
        layout.addLayout(btn_layout)

        layout.addSpacing(10)

        # ---- Progress Panel ----
        self.progress_group = QtWidgets.QGroupBox(self.tr("Progress"))
        progress_layout = QtWidgets.QVBoxLayout(self.progress_group)
        self.progress_group.setVisible(False)

        self.progress_bar = MProgressBar().auto_color()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        info_grid = QtWidgets.QGridLayout()
        self.status_label = MLabel(self.tr("Idle")).strong()
        self.current_page_label = MLabel("")
        self.completed_label = MLabel(self.tr("Completed: 0 / 0"))
        self.remaining_label = MLabel(self.tr("Remaining: 0"))
        self.eta_label = MLabel(self.tr("ETA: --"))

        info_grid.addWidget(MLabel(self.tr("Status:")), 0, 0)
        info_grid.addWidget(self.status_label, 0, 1)
        info_grid.addWidget(MLabel(self.tr("Current:")), 1, 0)
        info_grid.addWidget(self.current_page_label, 1, 1)
        info_grid.addWidget(MLabel(self.tr("Progress:")), 2, 0)
        info_grid.addWidget(self.completed_label, 2, 1)
        info_grid.addWidget(MLabel(self.tr("Remaining:")), 3, 0)
        info_grid.addWidget(self.remaining_label, 3, 1)
        info_grid.addWidget(MLabel(self.tr("ETA:")), 4, 0)
        info_grid.addWidget(self.eta_label, 4, 1)
        progress_layout.addLayout(info_grid)

        layout.addWidget(self.progress_group)

        # ---- Summary Panel ----
        self.summary_group = QtWidgets.QGroupBox(self.tr("Summary"))
        summary_layout = QtWidgets.QVBoxLayout(self.summary_group)
        self.summary_group.setVisible(False)

        self.summary_total_label = MLabel("")
        self.summary_success_label = MLabel("")
        self.summary_failed_label = MLabel("")
        self.summary_time_label = MLabel("")

        summary_layout.addWidget(self.summary_total_label)
        summary_layout.addWidget(self.summary_success_label)
        summary_layout.addWidget(self.summary_failed_label)
        summary_layout.addWidget(self.summary_time_label)

        self.summary_failed_list = QtWidgets.QListWidget()
        self.summary_failed_list.setMaximumHeight(120)
        self.summary_failed_list.setVisible(False)
        summary_layout.addWidget(self.summary_failed_list)

        summary_btn_layout = QtWidgets.QHBoxLayout()
        self.summary_close_btn = MPushButton(self.tr("Close")).small()
        self.retry_failed_btn = MPushButton(self.tr("Retry Failed")).small()
        self.retry_failed_btn.set_dayu_type(MPushButton.PrimaryType)
        self.retry_failed_btn.setVisible(False)
        summary_btn_layout.addWidget(self.retry_failed_btn)
        summary_btn_layout.addStretch()
        summary_btn_layout.addWidget(self.summary_close_btn)
        summary_layout.addLayout(summary_btn_layout)

        layout.addWidget(self.summary_group)
        layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Connections
        self.select_all_btn.clicked.connect(self._select_all)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        self.range_select_btn.clicked.connect(self._select_range)
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self.start_btn.clicked.connect(self._on_start)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.restore_prompt_btn.clicked.connect(self._restore_default_prompt)
        self.summary_close_btn.clicked.connect(self._close_summary)
        self.retry_failed_btn.clicked.connect(self._on_retry_failed)

    # ---- Page Management ----

    def refresh_pages(self, image_files: list[str]):
        self.page_list.clear()
        self.range_from_spin.setMaximum(max(len(image_files), 1))
        self.range_to_spin.setMaximum(max(len(image_files), 1))
        if image_files:
            self.range_to_spin.setValue(len(image_files))
        for idx, path in enumerate(image_files):
            item = QtWidgets.QListWidgetItem(os.path.basename(path))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, idx)
            item.setCheckState(QtCore.Qt.CheckState.Checked)
            self.page_list.addItem(item)

    def get_selected_paths(self) -> list[str]:
        paths = []
        for i in range(self.page_list.count()):
            item = self.page_list.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                paths.append(item.data(QtCore.Qt.ItemDataRole.UserRole))
        return paths

    def _select_all(self):
        for i in range(self.page_list.count()):
            self.page_list.item(i).setCheckState(QtCore.Qt.CheckState.Checked)

    def _deselect_all(self):
        for i in range(self.page_list.count()):
            self.page_list.item(i).setCheckState(QtCore.Qt.CheckState.Unchecked)

    def _select_range(self):
        from_idx = self.range_from_spin.value() - 1
        to_idx = self.range_to_spin.value() - 1
        for i in range(self.page_list.count()):
            state = QtCore.Qt.CheckState.Checked if from_idx <= i <= to_idx else QtCore.Qt.CheckState.Unchecked
            self.page_list.item(i).setCheckState(state)

    # ---- Provider Management ----

    def _refresh_providers(self):
        if self._manager is None:
            return
        providers = self._manager.list_providers()
        active = self._manager.active_provider_name()

        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()
        for p in providers:
            self.provider_combo.addItem(p.name)
        idx = self.provider_combo.findText(active)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        elif providers:
            self.provider_combo.setCurrentIndex(0)
        self.provider_combo.blockSignals(False)
        self._on_provider_changed(self.provider_combo.currentText())

    def _on_provider_changed(self, name: str):
        if self._manager is None:
            self.model_label.setText("")
            return
        p = self._manager.get_provider(name)
        if p:
            self.model_label.setText(p.model)
        else:
            self.model_label.setText("")

    def get_selected_provider_name(self) -> str:
        return self.provider_combo.currentText()

    # ---- System Prompt ----

    def _restore_default_prompt(self):
        self.system_prompt_edit.setPlainText(BUILT_IN_SYSTEM_PROMPT)

    # ---- Controls ----

    def _on_start(self):
        self.start_requested.emit()

    def _on_cancel(self):
        self.cancel_requested.emit()

    def _on_retry_failed(self):
        self.start_requested.emit()

    def _close_summary(self):
        self.summary_group.setVisible(False)

    # ---- Progress Updates (called from controller via signals) ----

    def show_progress(self):
        self.progress_group.setVisible(True)
        self.summary_group.setVisible(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr("Running..."))
        self.current_page_label.setText("")
        self.completed_label.setText(self.tr("Completed: 0 / 0"))
        self.remaining_label.setText(self.tr("Remaining: 0"))
        self.eta_label.setText(self.tr("ETA: --"))
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

    def update_progress(self, completed: int, total: int, current_page: str, eta_seconds: float):
        if total > 0:
            pct = int((completed / total) * 100)
            self.progress_bar.setValue(pct)
        self.current_page_label.setText(current_page)
        self.completed_label.setText(self.tr("Completed: {0} / {1}").format(completed, total))
        self.remaining_label.setText(self.tr("Remaining: {0}").format(max(0, total - completed)))
        if eta_seconds > 0:
            mins = int(eta_seconds) // 60
            secs = int(eta_seconds) % 60
            self.eta_label.setText(self.tr("ETA: {0}m {1}s").format(mins, secs))
        else:
            self.eta_label.setText(self.tr("ETA: --"))

    def show_summary(self, summary: dict):
        self.progress_group.setVisible(False)
        self.summary_group.setVisible(True)

        total = summary.get("total", 0)
        succeeded = summary.get("succeeded", 0)
        failed = summary.get("failed", 0)
        total_time = summary.get("total_time", 0)
        failed_paths = summary.get("failed_paths", [])

        self.summary_total_label.setText(self.tr("Total pages processed: {0}").format(total))
        self.summary_success_label.setText(self.tr("Successfully translated: {0}").format(succeeded))
        self.summary_failed_label.setText(self.tr("Failed: {0}").format(failed))

        mins = int(total_time) // 60
        secs = int(total_time) % 60
        self.summary_time_label.setText(self.tr("Total time: {0}m {1}s").format(mins, secs))

        self.summary_failed_list.clear()
        self.summary_failed_list.setVisible(bool(failed_paths))
        self.retry_failed_btn.setVisible(bool(failed_paths))
        for entry in failed_paths:
            path = entry.get("path", "")
            reason = entry.get("reason", "")
            text = os.path.basename(path) if path else self.tr("Unknown")
            if reason:
                text += f"  —  {reason}"
            self.summary_failed_list.addItem(text)

        self.status_label.setText(self.tr("Complete"))
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def set_cancelled(self):
        self.status_label.setText(self.tr("Cancelled"))
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
