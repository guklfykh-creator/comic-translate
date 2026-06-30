from PySide6 import QtWidgets, QtCore
from ..dayu_widgets.label import MLabel
from ..dayu_widgets.text_edit import MTextEdit
from ..dayu_widgets.check_box import MCheckBox
from ..dayu_widgets.push_button import MPushButton
from ..dayu_widgets.collapse import MCollapse
from ..dayu_widgets.divider import MDivider

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


class LlmsPage(QtWidgets.QWidget):
    DEFAULT_EXTRA_CONTEXT_LIMIT = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._extra_context_limit: int | None = self.DEFAULT_EXTRA_CONTEXT_LIMIT

        v = QtWidgets.QVBoxLayout(self)
        main_layout = QtWidgets.QHBoxLayout()

        self.image_checkbox = MCheckBox(self.tr("Provide Image as Input to AI"))
        self.image_checkbox.setChecked(False)

        # Left column: Extra Context
        left_layout = QtWidgets.QVBoxLayout()
        prompt_label = MLabel(self.tr("Extra Context:"))
        self.extra_context = MTextEdit()
        self.extra_context.setMinimumHeight(200)
        left_layout.addWidget(prompt_label)
        left_layout.addWidget(self.extra_context)
        left_layout.addWidget(self.image_checkbox)
        left_layout.addStretch(1)

        # Right column: Reasoning + System Prompt
        right_layout = QtWidgets.QVBoxLayout()

        # Reasoning / Thinking mode
        self.reasoning_checkbox = MCheckBox(self.tr("Enable Reasoning/Thinking Mode"))
        self.reasoning_checkbox.setChecked(False)
        self.reasoning_checkbox.setToolTip(
            self.tr(
                "Enable the model's extended reasoning/thinking capability. "
                "This may increase token usage and cost."
            )
        )
        reasoning_warn = MLabel(
            self.tr("Note: Increases token usage and cost for some providers.")
        ).secondary()
        right_layout.addWidget(self.reasoning_checkbox)
        right_layout.addWidget(reasoning_warn)
        right_layout.addSpacing(15)

        # System Prompt
        sys_prompt_label = MLabel(self.tr("System Prompt:"))
        self.system_prompt_edit = MTextEdit()
        self.system_prompt_edit.setMinimumHeight(280)
        self.system_prompt_edit.setPlaceholderText(
            self.tr("Leave empty to use the built-in default prompt. "
                    "Use {source_lang} and {target_lang} as placeholders.")
        )
        right_layout.addWidget(sys_prompt_label)
        right_layout.addWidget(self.system_prompt_edit)

        self.restore_prompt_btn = MPushButton(self.tr("Restore Default Prompt")).small()
        self.restore_prompt_btn.set_dayu_type(MPushButton.DefaultType)
        self.restore_prompt_btn.clicked.connect(self._restore_default_prompt)
        right_layout.addWidget(self.restore_prompt_btn)

        right_layout.addStretch(1)

        main_layout.addLayout(left_layout, 3)
        main_layout.addLayout(right_layout, 1)

        v.addLayout(main_layout)
        v.addStretch(1)

        self.extra_context.textChanged.connect(self._limit_extra_context)

    def set_extra_context_unlimited(self, enabled: bool) -> None:
        self._extra_context_limit = None if enabled else self.DEFAULT_EXTRA_CONTEXT_LIMIT
        self._limit_extra_context()

    def _limit_extra_context(self):
        max_length = self._extra_context_limit
        if max_length is None:
            return
        text = self.extra_context.toPlainText()
        if len(text) > max_length:
            cursor = self.extra_context.textCursor()
            position = cursor.position()
            self.extra_context.setPlainText(text[:max_length])
            new_position = min(position, max_length)
            cursor.setPosition(new_position)
            self.extra_context.setTextCursor(cursor)

    def _restore_default_prompt(self):
        self.system_prompt_edit.setPlainText(BUILT_IN_SYSTEM_PROMPT)

    @staticmethod
    def get_built_in_system_prompt() -> str:
        return BUILT_IN_SYSTEM_PROMPT
