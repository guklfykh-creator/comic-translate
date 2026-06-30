from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Optional

from PySide6 import QtWidgets, QtCore

from ..dayu_widgets.label import MLabel
from ..dayu_widgets.line_edit import MLineEdit
from ..dayu_widgets.spin_box import MSpinBox
from ..dayu_widgets.check_box import MCheckBox
from ..dayu_widgets.push_button import MPushButton
from ..dayu_widgets.combo_box import MComboBox
from ..dayu_widgets.message import MMessage
from .utils import set_label_width
from app.ai_providers.provider import AIProvider

if TYPE_CHECKING:
    from app.ai_providers.manager import AIProviderManager


class ProviderDialog(QtWidgets.QDialog):
    def __init__(self, manager: AIProviderManager, provider: Optional[AIProvider] = None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.provider = provider
        self._editing = provider is not None
        self._result_provider: Optional[AIProvider] = None

        title = self.tr("Edit Provider") if self._editing else self.tr("Add Provider")
        self.setWindowTitle(title)
        self.setMinimumWidth(500)

        layout = QtWidgets.QFormLayout(self)

        self.name_edit = MLineEdit()
        self.name_edit.setPlaceholderText(self.tr("e.g. My Local LLM"))
        if self._editing:
            self.name_edit.setText(provider.name)
            self.name_edit.setEnabled(False)
        layout.addRow(self.tr("Name:"), self.name_edit)

        self.url_edit = MLineEdit()
        self.url_edit.setPlaceholderText(self.tr("e.g. http://localhost:11434/v1"))
        if self._editing:
            self.url_edit.setText(provider.base_url)
        layout.addRow(self.tr("Base URL:"), self.url_edit)

        self.key_edit = MLineEdit()
        self.key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.key_edit.setPlaceholderText(self.tr("API Key"))
        if self._editing:
            self.key_edit.setText(provider.api_key)
        layout.addRow(self.tr("API Key:"), self.key_edit)

        self.model_edit = MLineEdit()
        self.model_edit.setPlaceholderText(self.tr("e.g. llama3"))
        if self._editing:
            self.model_edit.setText(provider.model)
        layout.addRow(self.tr("Model:"), self.model_edit)

        self.headers_edit = QtWidgets.QPlainTextEdit()
        self.headers_edit.setPlaceholderText(self.tr("key1: value1\nkey2: value2"))
        self.headers_edit.setMaximumHeight(80)
        if self._editing and provider.custom_headers:
            lines = [f"{k}: {v}" for k, v in provider.custom_headers.items()]
            self.headers_edit.setPlainText("\n".join(lines))
        layout.addRow(self.tr("Custom Headers:"), self.headers_edit)

        self.timeout_spin = MSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.timeout_spin.setValue(provider.timeout if self._editing else 120)
        self.timeout_spin.setSuffix("s")
        layout.addRow(self.tr("Timeout:"), self.timeout_spin)

        btn_layout = QtWidgets.QHBoxLayout()
        self.test_btn = MPushButton(self.tr("Test Connection")).small()
        self.test_btn.set_dayu_type(MPushButton.DefaultType)
        self.save_btn = MPushButton(self.tr("Save")).small()
        self.save_btn.set_dayu_type(MPushButton.PrimaryType)
        self.cancel_btn = MPushButton(self.tr("Cancel")).small()
        btn_layout.addWidget(self.test_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow(btn_layout)

        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn.clicked.connect(self.reject)
        self.test_btn.clicked.connect(self._on_test)

    def _build_provider(self) -> Optional[AIProvider]:
        name = self.name_edit.text().strip()
        base_url = self.url_edit.text().strip()
        api_key = self.key_edit.text().strip()
        model = self.model_edit.text().strip()
        custom_headers = self._parse_headers()
        timeout = self.timeout_spin.value()

        p = AIProvider(
            name=name,
            base_url=base_url,
            api_key=api_key,
            model=model,
            custom_headers=custom_headers,
            timeout=timeout,
        )
        ok, msg = p.validate_fields()
        if not ok:
            MMessage.error(msg, parent=self, duration=3, closable=True)
            return None
        return p

    def _parse_headers(self) -> dict[str, str]:
        headers = {}
        text = self.headers_edit.toPlainText().strip()
        if not text:
            return headers
        for line in text.splitlines():
            line = line.strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key:
                headers[key] = value
        return headers

    def _on_save(self):
        p = self._build_provider()
        if p is None:
            return
        if not self._editing:
            existing = self.manager.get_provider(p.name)
            if existing is not None:
                MMessage.error(self.tr("A provider with this name already exists."), parent=self, duration=3, closable=True)
                return
        self._result_provider = p
        self.accept()

    def _on_test(self):
        p = self._build_provider()
        if p is None:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText(self.tr("Testing..."))

        def _run_test():
            ok, msg = self.manager.validate_provider(p)
            QtCore.QMetaObject.invokeMethod(self, "_handle_test_result", QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(bool, ok), QtCore.Q_ARG(str, msg))

        t = threading.Thread(target=_run_test, daemon=True)
        t.start()

    def _handle_test_result(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        self.test_btn.setText(self.tr("Test Connection"))
        if ok:
            MMessage.success(msg, parent=self, duration=3, closable=True)
        else:
            MMessage.error(msg, parent=self, duration=5, closable=True)


class AIProvidersPage(QtWidgets.QWidget):
    provider_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager: Optional[AIProviderManager] = None
        self._setup_ui()

    def set_manager(self, manager: AIProviderManager):
        self._manager = manager
        self._refresh_list()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        info_label = MLabel(self.tr(
            "Configure OpenAI-compatible AI providers for translation. "
            "Add, edit, or remove providers and select the active one used for Auto Translate."
        )).secondary()
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        layout.addSpacing(10)

        active_layout = QtWidgets.QHBoxLayout()
        active_label = MLabel(self.tr("Active Provider:")).strong()
        self.active_combo = MComboBox().small()
        self.active_combo.setMinimumWidth(200)
        active_layout.addWidget(active_label)
        active_layout.addWidget(self.active_combo)
        active_layout.addStretch()
        layout.addLayout(active_layout)
        layout.addSpacing(10)

        self.provider_list = QtWidgets.QListWidget()
        self.provider_list.setMinimumHeight(150)
        layout.addWidget(self.provider_list)

        btn_layout = QtWidgets.QHBoxLayout()
        self.add_btn = MPushButton(self.tr("Add Provider")).small()
        self.add_btn.set_dayu_type(MPushButton.PrimaryType)
        self.edit_btn = MPushButton(self.tr("Edit")).small()
        self.delete_btn = MPushButton(self.tr("Delete")).small()
        self.test_btn = MPushButton(self.tr("Test Connection")).small()
        self.test_btn.set_dayu_type(MPushButton.DefaultType)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.edit_btn)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.test_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch(1)

        self.add_btn.clicked.connect(self._on_add)
        self.edit_btn.clicked.connect(self._on_edit)
        self.delete_btn.clicked.connect(self._on_delete)
        self.test_btn.clicked.connect(self._on_test)
        self.active_combo.currentTextChanged.connect(self._on_active_changed)

    def _refresh_list(self):
        if self._manager is None:
            return
        providers = self._manager.list_providers()
        current_active = self._manager.active_provider_name()

        self.provider_list.clear()
        for p in providers:
            item = QtWidgets.QListWidgetItem(f"{p.name}  ({p.model})")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, p.name)
            self.provider_list.addItem(item)

        self.active_combo.blockSignals(True)
        self.active_combo.clear()
        for p in providers:
            self.active_combo.addItem(p.name)
        idx = self.active_combo.findText(current_active)
        if idx >= 0:
            self.active_combo.setCurrentIndex(idx)
        elif providers:
            self.active_combo.setCurrentIndex(0)
        self.active_combo.blockSignals(False)

    def _selected_provider_name(self) -> Optional[str]:
        items = self.provider_list.selectedItems()
        if not items:
            return None
        return items[0].data(QtCore.Qt.ItemDataRole.UserRole)

    def _on_add(self):
        if self._manager is None:
            return
        dlg = ProviderDialog(self._manager, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg._result_provider:
            self._manager.add_provider(dlg._result_provider)
            if not self._manager.active_provider_name():
                self._manager.set_active_provider(dlg._result_provider.name)
            self._refresh_list()
            self.provider_changed.emit()

    def _on_edit(self):
        if self._manager is None:
            return
        name = self._selected_provider_name()
        if not name:
            return
        p = self._manager.get_provider(name)
        if p is None:
            return
        dlg = ProviderDialog(self._manager, provider=p, parent=self)
        if dlg.exec() == QtWidgets.QDialog.Accepted and dlg._result_provider:
            self._manager.update_provider(name, dlg._result_provider)
            self._refresh_list()
            self.provider_changed.emit()

    def _on_delete(self):
        if self._manager is None:
            return
        name = self._selected_provider_name()
        if not name:
            return
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Question)
        msg_box.setWindowTitle(self.tr("Delete Provider"))
        msg_box.setText(self.tr("Are you sure you want to delete the provider '{name}'?").format(name=name))
        yes_btn = msg_box.addButton(self.tr("Delete"), QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        no_btn = msg_box.addButton(self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(no_btn)
        msg_box.exec()
        if msg_box.clickedButton() == yes_btn:
            self._manager.delete_provider(name)
            self._refresh_list()
            self.provider_changed.emit()

    def _on_test(self):
        if self._manager is None:
            return
        name = self._selected_provider_name()
        if not name:
            return
        p = self._manager.get_provider(name)
        if p is None:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText(self.tr("Testing..."))

        def _run():
            ok, msg = self._manager.validate_provider(p)
            QtCore.QMetaObject.invokeMethod(self, "_handle_test_result", QtCore.Qt.ConnectionType.QueuedConnection, QtCore.Q_ARG(bool, ok), QtCore.Q_ARG(str, msg))

        threading.Thread(target=_run, daemon=True).start()

    def _handle_test_result(self, ok: bool, msg: str):
        self.test_btn.setEnabled(True)
        self.test_btn.setText(self.tr("Test Connection"))
        if ok:
            MMessage.success(msg, parent=self, duration=3, closable=True)
        else:
            MMessage.error(msg, parent=self, duration=5, closable=True)

    def _on_active_changed(self, name: str):
        if self._manager and name:
            self._manager.set_active_provider(name)
            self.provider_changed.emit()
