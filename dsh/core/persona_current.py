"""rc.3 scoped persona prefix/suffix provider."""
from dsh.cordis.plugin import Plugin
from dsh.cordis.schema import Schema
from dsh.core.system_prompt.current import PERSONA_PREFIX_SECTION, PERSONA_SUFFIX_SECTION


class CurrentPersonaPlugin(Plugin):
    id = 'persona'
    name = '@deepseek-ai/dsh-persona'
    inject = ['systemPrompt']
    Config = Schema.object(dict(prefix=Schema.string().required(), suffix=Schema.string().default(''),
                                complete=Schema.boolean().default(False), includeRuntimeContext=Schema.boolean().default(True)))

    def apply(self, ctx):
        prompt = ctx.get('systemPrompt')
        prefix = dict(name=PERSONA_PREFIX_SECTION, order=prompt.getSectionOrder('DEPLOYMENT_PERSONA_PREFIX'), text=self.config['prefix'])
        if self.config['complete']:
            prefix['complete'] = True
        ctx.effect(lambda: prompt.section(prefix), 'persona.section()')
        ctx.effect(lambda: prompt.section(dict(name=PERSONA_SUFFIX_SECTION,
            order=prompt.getSectionOrder('DEPLOYMENT_PERSONA_SUFFIX'), text=self.config['suffix'])), 'persona.suffix()')
        if not self.config['includeRuntimeContext']:
            prompt.suppressRuntimeContext()
