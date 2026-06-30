# AI Translation Provider System & Auto Multi-Page Translation

## Summary

Add a complete AI provider management system (multiple OpenAI-compatible providers, reasoning toggle, custom system prompt) and a new auto-multi-page translation section with its own nav tab, separate orchestrator sharing existing pipeline handlers, exponential-backoff retries, and real-time progress UI.

---

## Key Design Decisions

1. **Provider storage**: QSettings `credentials/ai_providers` group. Existing `save_keys` checkbox gates persistence. Each provider is a named sub-group with fields: base_url, api_key, model, custom_headers, timeout.
2. **Reasoning mode**: Per-protocol adaptation. UI exposes a single on/off toggle. The engine layer translates this to provider-specific params (OpenAI: `reasoning_effort`, Deepseek: enable reasoning content, Claude: extended thinking with `budget_tokens`).
3. **System prompt**: Editable default prompt stored in QSettings `llm/system_prompt`. A "Restore Default" button resets it to the built-in from `LLMTranslation.get_system_prompt()`.
4. **Auto-translate UI**: New nav-rail tab ("Auto Translate") with its own page selector, provider/model picker, system prompt, reasoning toggle, start/cancel, and progress/summary panel.
5. **Pipeline relationship**: New `AutoTranslateOrchestrator` reuses existing handlers (`BlockDetectionHandler`, `OCRHandler`, `InpaintingHandler`) but has its own entry point, retry logic, and progress signals. The existing `BatchProcessor` remains untouched.

---

## Task List

### Phase 1: AI Provider Data Model & Persistence

**1.1 Create provider data class**
- File: `app/ai_providers/provider.py`
- Create `AIProvider` dataclass: `name: str`, `base_url: str`, `api_key: str`, `model: str`, `custom_headers: dict[str, str]`, `timeout: int` (default 120).

**1.2 Create provider manager**
- File: `app/ai_providers/manager.py`
- Create `AIProviderManager` class:
  - `list_providers() -> list[AIProvider]`
  - `get_provider(name: str) -> AIProvider`
  - `add_provider(provider: AIProvider) -> None`
  - `update_provider(name: str, provider: AIProvider) -> None`
  - `delete_provider(name: str) -> None`
  - `active_provider_name() -> str` / `set_active_provider(name: str) -> None`
  - Internally reads/writes QSettings under `credentials/ai_providers/<name>/` keys.
  - Validate connectivity: `validate_provider(provider: AIProvider) -> tuple[bool, str]` — sends a lightweight `GET /models` (or `POST /chat/completions` with tiny payload) to confirm base_url + api_key work.
  - `__init__.py` in `app/ai_providers/` to expose `AIProviderManager`.

**1.3 Wire provider manager into controller**
- File: `controller.py`
- Instantiate `AIProviderManager` in `ComicTranslate.__init__`, store as `self.ai_provider_mgr`.

---

### Phase 2: Custom Provider UI (Settings)

**2.1 Create provider management page**
- File: `app/ui/settings/ai_providers_page.py`
- QWidget with:
  - List of saved providers (QListWidget or QTableWidget) showing name + model.
  - "Add Provider" button → dialog/modal with fields: name, base URL, API key (password echo), model, custom headers (key=value text editor), timeout (spinbox, default 120).
  - "Edit" / "Delete" buttons for selected provider.
  - "Test Connection" button — calls `manager.validate_provider()`; shows success/failure toast.
  - "Active Provider" combo at the top — dropdown of all saved provider names; selecting one calls `set_active_provider()`.
  - Validation before save: base_url non-empty, api_key non-empty, model non-empty.

**2.2 Add AI Providers as a settings sub-page**
- Files: `app/ui/settings/settings_ui.py`, `app/ui/settings/settings_page.py`
- Add `AIProvidersPage` to the stacked widget after Credentials.
- Add nav card "AI Providers" to the navbar.
- Load/save providers through `AIProviderManager` in `SettingsPage.load_settings()` / `save_settings()`.

---

### Phase 3: Translation Settings (Reasoning + System Prompt)

**3.1 Add reasoning toggle and system prompt to LLMs page**
- File: `app/ui/settings/llms_page.py`
- Add `MCheckBox(self.tr("Enable Reasoning/Thinking Mode"))` — `self.reasoning_checkbox`.
- Add `MLabel(self.tr("System Prompt"))` + `MTextEdit` — `self.system_prompt_edit` (minimum height ~150px).
- Add `MPushButton(self.tr("Restore Default Prompt"))` — connects to a slot that resets `system_prompt_edit` to the built-in default from `LLMTranslation.get_system_prompt("{source}", "{target}")` template.
- Store both values via QSettings in `llm/reasoning_enabled` (bool) and `llm/system_prompt` (string).

**3.2 Expose new settings in SettingsPage**
- File: `app/ui/settings/settings_page.py`
- Extend `get_llm_settings()` to return `reasoning_enabled` and `system_prompt`.
- Extend `save_settings()` and `load_settings()` to persist these.

---

### Phase 4: Engine-Layer Reasoning Support

**4.1 Add reasoning param to BaseLLMTranslation**
- File: `modules/translation/llm/base.py`
- Add `self.reasoning_enabled = False` attribute.
- In `initialize()`, read `reasoning_enabled` from `settings.get_llm_settings()`.
- Override `get_system_prompt()` to return custom system prompt from settings if provided, else built-in default.

**4.2 Update GPTTranslation for reasoning**
- File: `modules/translation/llm/gpt.py`
- If `self.reasoning_enabled`, add `reasoning_effort: "low"` to payload (or `"medium"` depending on model). For o-series models, adjust `max_completion_tokens` accordingly.

**4.3 Update DeepseekTranslation for reasoning**
- File: `modules/translation/llm/deepseek.py`
- If `self.reasoning_enabled`, no special request params needed for Deepseek-R1 (reasoning is built in). For non-R1, pass nothing extra. Add a comment documenting the behavior.

**4.4 Update ClaudeTranslation for extended thinking**
- File: `modules/translation/llm/claude.py`
- If `self.reasoning_enabled`, add `thinking: {type: "enabled", budget_tokens: 8000}` to payload. Note: when thinking is enabled, temperature must be set to 1 and system must be in `system` top-level (already the case).

**4.5 Update GeminiTranslation for reasoning**
- File: `modules/translation/llm/gemini.py`
- If `self.reasoning_enabled`, set `thinkingConfig.thinkingLevel` to `"medium"` (was "low"/"minimal"). This gives deeper reasoning.

**4.6 Update CustomTranslation to pass reasoning + custom headers + timeout**
- File: `modules/translation/llm/custom.py`
- Read custom_headers and timeout from the active `AIProvider` stored via provider manager credentials.
- Merge custom_headers into request headers.
- Use provider's timeout value.
- Pass `reasoning_enabled` down to GPTTranslation's payload-building logic.

**4.7 Update TranslationFactory cache key**
- File: `modules/translation/factory.py`
- Include `reasoning_enabled` and `system_prompt` in the LLM extras hash so a change in these settings invalidates cached engines.

---

### Phase 5: Auto-Translate Nav Tab & Page

**5.1 Create AutoTranslatePage widget**
- File: `app/ui/auto_translate/page.py`
- QWidget containing:
  - **Page selector**: QListWidget showing all loaded pages (mirrors `main_page.image_files`). Checkbox per item for multi-select. "Select All" / "Deselect All" buttons. Range selector (from page X to page Y).
  - **Provider & model selector**: Combo boxes listing all saved AI providers and their models. Auto-refreshes when providers change.
  - **Language selectors**: Source and target language combos (reuse `supported_source_languages` / `supported_target_languages` from constants).
  - **Reasoning toggle**: MCheckBox "Enable Reasoning/Thinking Mode".
  - **System prompt**: MTextEdit with editable default prompt + "Restore Default" button (mirrors LLMs page behavior).
  - **Start Translation** button (MPushButton, primary style).
  - **Cancel** button.
  - **Progress panel** (see 5.3).
  - **Summary panel** (see 5.4).

**5.2 Add nav rail tab**
- Files: `app/ui/main_window/builders/nav.py`, `app/ui/main_window/window.py`, `controller.py`
- Add a new nav button (SVG: `auto_translate.svg` or similar) between Home and Settings in the rail.
- Add `AutoTranslatePage` instance to `_center_stack`.
- Add `show_auto_translate_page()` method.
- Wire the nav button.

---

### Phase 6: AutoTranslate Orchestrator & Controller

**6.1 Create AutoTranslateOrchestrator**
- File: `pipeline/auto_translate_orchestrator.py`
- New class that owns the end-to-end flow:
  - `__init__(self, main_page, cache_manager, block_detection, inpainting, ocr_handler)`
  - `run(self, image_paths, provider_config, source_lang, target_lang, reasoning_enabled, system_prompt) -> dict` (summary dict)
  - For each page in `image_paths`:
    1. Load image.
    2. Detect blocks (reuse `BlockDetectionHandler`).
    3. OCR (reuse `OCRHandler`).
    4. Translate using `Translator` (which uses the active provider/factory). If `reasoning_enabled` or `system_prompt` are set, they are injected via settings overrides before translation, then restored.
    5. Inpaint (reuse `InpaintingHandler`).
    6. Render text (reuse rendering logic from `BatchProcessor`).
    7. Save result back to `image_states`.
    8. Emit progress signal.
  - Per-page retry: if translation fails, retry up to 3 times with exponential backoff (1s, 2s, 4s). Mark as failed after max retries.
  - Return summary: `{total, succeeded, failed, failed_paths, total_time}`.
  - Check `self._is_cancelled()` between each step.

**6.2 Create AutoTranslateController**
- File: `app/controllers/auto_translate.py`
- Manages the auto-translate lifecycle:
  - References `main_page`, `AutoTranslateOrchestrator`, and the `AutoTranslatePage` UI.
  - `start_translation()`: gather selected pages, provider, languages, reasoning, system prompt from UI. Validate (provider configured, pages selected, languages set). Run orchestrator in a worker thread via `task_runner_ctrl`.
  - `cancel_translation()`: set cancel flag on worker.
  - Progress signals: connect orchestrator's progress updates to the AutoTranslatePage progress panel.
  - `on_translation_finished(summary)`: display summary in the summary panel. Re-enable UI.
  - Emits Qt signals for thread-safe UI updates.

**6.3 Wire controller into main app**
- File: `controller.py`
- Instantiate `AutoTranslateController` in `ComicTranslate.__init__`.
- Connect `AutoTranslatePage.start_clicked` → `auto_translate_ctrl.start_translation()`.
- Connect `AutoTranslatePage.cancel_clicked` → `auto_translate_ctrl.cancel_translation()`.

---

### Phase 7: Progress UI & Summary

**7.1 Progress panel (inside AutoTranslatePage)**
- File: `app/ui/auto_translate/page.py` (within the same widget)
- Progress panel contains:
  - `MProgressBar` — shows percentage complete.
  - `QLabel` — current page name being translated.
  - `QLabel` — "Completed: X / Total: Y".
  - `QLabel` — "Remaining: Z".
  - `QLabel` — estimated time remaining (calculated from average time per completed page).
  - Status label: "Running..." / "Cancelled" / "Complete".
- Updated via Qt signals from `AutoTranslateController`.

**7.2 Summary panel (inside AutoTranslatePage)**
- File: `app/ui/auto_translate/page.py`
- Shown after translation completes. Contains:
  - Total pages processed.
  - Successfully translated count + list of page names.
  - Failed count + list of page names with error reasons.
  - Total processing time (formatted as Xm Ys).
  - "Close" button to dismiss summary and return to selection view.
  - "Retry Failed" button (only enabled if there are failed pages).

---

### Phase 8: Integration & Validation

**8.1 Update pipeline_config.py validation**
- File: `modules/utils/pipeline_config.py`
- Add `validate_auto_translate_settings(main, target_lang)` — checks that an active AI provider is configured (either via the provider manager or credentials). If using custom providers, check api_key + base_url + model.

**8.2 Update processor.py to use custom system prompt**
- File: `modules/translation/processor.py`
- In `Translator.__init__`, read `system_prompt` from llm settings and pass it to the engine. Add a `system_prompt_override` parameter that the `AutoTranslateOrchestrator` can set.

**8.3 Update BaseLLMTranslation to use custom system prompt**
- File: `modules/translation/llm/base.py`
- Modify `translate()` to use `self.system_prompt` (from settings) instead of always calling `get_system_prompt()`. If the custom prompt is empty, fall back to the built-in.
- Template substitution: replace `{source_lang}` and `{target_lang}` placeholders in the custom prompt.

**8.4 Ensure existing "Custom" translator integration works with new provider system**
- The existing single "Custom" entry in credentials and translator combo still works for backward compatibility.
- The new provider system adds additional entries. When the user selects "Auto Translate" tab, they choose from the new provider manager's list, not from the existing translator combo.

**8.5 Add messages for auto-translate errors**
- File: `app/ui/messages.py`
- Add `show_auto_translate_provider_not_configured()`.
- Add `show_auto_translate_no_pages_selected()`.
- Add `show_auto_translate_validation_error()`.

---

## File Inventory

### New files
| File | Purpose |
|------|---------|
| `app/ai_providers/__init__.py` | Package init |
| `app/ai_providers/provider.py` | `AIProvider` dataclass |
| `app/ai_providers/manager.py` | `AIProviderManager` (CRUD + validate + persist in QSettings) |
| `app/ui/auto_translate/__init__.py` | Package init |
| `app/ui/auto_translate/page.py` | AutoTranslatePage widget (page selector, provider picker, progress, summary) |
| `app/ui/settings/ai_providers_page.py` | Provider management settings page |
| `pipeline/auto_translate_orchestrator.py` | Full end-to-end orchestrator with retry |
| `app/controllers/auto_translate.py` | Controller bridging UI ↔ orchestrator |

### Modified files
| File | Changes |
|------|---------|
| `controller.py` | Add `AIProviderManager` and `AutoTranslateController` instances |
| `modules/translation/llm/base.py` | Add `reasoning_enabled`, `system_prompt` attributes; modify `translate()` to use custom prompt |
| `modules/translation/llm/gpt.py` | Add reasoning_effort to payload when enabled |
| `modules/translation/llm/deepseek.py` | Document reasoning behavior |
| `modules/translation/llm/claude.py` | Add thinking config with budget_tokens when enabled |
| `modules/translation/llm/gemini.py` | Adjust thinkingLevel when reasoning enabled |
| `modules/translation/llm/custom.py` | Support custom headers, provider timeout, reasoning |
| `modules/translation/factory.py` | Include reasoning + system_prompt in cache key hash |
| `app/ui/settings/llms_page.py` | Add reasoning checkbox, system prompt editor, restore-default button |
| `app/ui/settings/settings_ui.py` | Add AIProvidersPage to stacked widget + nav |
| `app/ui/settings/settings_page.py` | Extend get_llm_settings(), save/load for new fields; load/save AI providers |
| `app/ui/main_window/builders/nav.py` | Add auto-translate nav button |
| `app/ui/main_window/window.py` | Add auto-translate page to _center_stack, add show_auto_translate_page() |
| `modules/utils/pipeline_config.py` | Add validate_auto_translate_settings() |
| `modules/translation/processor.py` | Support system_prompt_override parameter |
| `app/ui/messages.py` | Add auto-translate error messages |

---

## Risks & Open Questions

- **Rate limiting**: The auto-translate orchestrator processes pages sequentially by default. If users add a concurrency option later, rate-limit handling for the specific provider must be considered. For now, sequential is safest.
- **Thinking mode cost**: Extended thinking on Claude or reasoning on OpenAI o-series significantly increases token usage and cost. The UI should show a brief warning when reasoning is toggled on.
- **Backward compat of existing Custom translator**: The existing single "Custom" entry via credentials_page stays functional. The new multi-provider system is additive. The auto-translate tab uses only the new provider system, but the main editor's "Custom" translator combo still works.
- **Provider connectivity test accuracy**: `GET /models` works for most OpenAI-compatible APIs but not all. Fallback: try `POST /chat/completions` with a minimal payload ("hi") and check for a non-connection-error response.
