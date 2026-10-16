"""rc.3 prepared-call system prompt capabilities, without moving the active pin."""
from dsh.llm.llm_service import LLMService, LlmRuntime
from dsh.llm.model_info import normalize_model_info


class CurrentLLMService(LLMService):
    registerAdapter = LLMService.register_adapter
    @staticmethod
    def _normalize_model_info(provider, identifier, model, error_type):
        return normalize_model_info(provider, identifier, model, error_type, system_prompt_update=True)

    def _call_capabilities(self, model_info):
        return {key: model_info[key] for key in ('systemPromptUpdate',) if key in model_info}


class CurrentLlmRuntime(LlmRuntime):
    _service_class = CurrentLLMService
