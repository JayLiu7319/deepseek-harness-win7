"""Explicit test-only LLM provider loaded before canonical activation checks."""
from test_e2e_core_spine_strict_parity import StrictMockLlmAdapter


class ProfileLlmAdapter(StrictMockLlmAdapter):
    def prepareCall(self, config, signal):
        signal.throwIfAborted()
        return dict(config=dict(config), adapterDefaults={}, stream=self.stream)

    def stream(self, request):
        return self.chat_completion_stream(request['messages'], request.get('tools'))


def plugin(ctx, config):
    ctx.provide('llm', ProfileLlmAdapter((config or {}).get('responses', [])))
