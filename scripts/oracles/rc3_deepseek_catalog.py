"""Compare actual native provider/catalog/prepared calls with saved rc.3 Source."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dsh.cordis.context import Context
from dsh.llm.runtime_current import CurrentLlmRuntime
from dsh.llm.llm_deepseek import LLMDeepSeekPlugin
from dsh.llm.deepseek_schema import config_schema


async def observe():
    observations = []
    for config in ({}, dict(models=[dict(id='custom', name='Custom', systemPromptUpdate='in-history')])):
        ctx = Context()
        try:
            await ctx.plugin(CurrentLlmRuntime)
            await ctx.plugin(LLMDeepSeekPlugin, config)
            llm = ctx.get('llm')
            catalog = await llm.listModels('deepseek-official')
            resolved, prepared = [], []
            for row in catalog + [dict(id='unlisted')]:
                resolved.append(await llm.resolveModelInfo('deepseek-official', row['id']))
                call = await llm.prepareCall(dict(provider='deepseek-official', model=row['id']))
                prepared.append({key: value for key, value in call.items() if key != 'stream'})
            observations.append(dict(catalog=catalog, resolved=resolved, prepared=prepared))
        finally:
            await ctx.fiber.dispose()
    return dict(models=config_schema()({})['models'], observations=observations)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-observation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    source = json.loads(options.source_observation.read_text(encoding='utf-8'))
    if source['pin'] != 'a4c74a91e06b00fe0b0937bde982170c526cc842' or source['node'] != 'v22.22.2':
        raise ValueError('Source observation identity differs')
    native = asyncio.run(observe())
    with options.output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(native, indent=2, ensure_ascii=True) + '\n')
    assert native == {key: source[key] for key in native}, 'Actual default/custom provider observations differ'
    print('matched actual default/custom catalogs, seven resolutions and seven prepared calls')
