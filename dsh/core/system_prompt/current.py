"""rc.3 persona framing; activated with the coordinated profile migration."""
from .service import SystemPrompt
from .types import FIRST_PARTY_SECTION_ORDER as _previous, _FirstPartySectionOrder


FIRST_PARTY_SECTION_ORDER = _FirstPartySectionOrder(
    (key, value) for key, value in _previous.items() if key != 'DEPLOYMENT_PERSONA')
FIRST_PARTY_SECTION_ORDER.update(DEPLOYMENT_PERSONA_PREFIX=0, HARNESS_SOURCE=10000,
                                WEB_SURFACE=10100, DEPLOYMENT_PERSONA_SUFFIX=10200)
PERSONA_PREFIX_SECTION = 'deployment:persona-prefix'
PERSONA_SUFFIX_SECTION = 'deployment:persona-suffix'


class CurrentSystemPrompt(SystemPrompt):
    _section_orders = FIRST_PARTY_SECTION_ORDER

    def _persona_sections(self, config):
        return [dict(name=PERSONA_PREFIX_SECTION, order=0, text=config.get('personaPrefix', '')),
                dict(name=PERSONA_SUFFIX_SECTION, order=10200, text=config.get('personaSuffix', ''))]
