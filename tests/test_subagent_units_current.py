"""Parent discovery facts retain identity, bounded copies and own-event cuts."""
import json
from pathlib import Path

import pytest

from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.session.projections import SessionProjectionsPlugin
from dsh.subagent.catalog_current import CATALOG,apply,append_chunk,view,establish_catalog_child
from scripts.oracles.agent_loop_current_python import execute
from scripts.oracles.session_format_python import decode


CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/subagent_units_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_subagent_units(case):
    assert execute(case,decode)==case['expected']


def test_chunk_append_copies_at_most_one_chunk_and_preserves_borrowed_values():
    head=None;values=[dict(index=i) for i in range(130)];prefixes=[]
    for value in values:
        prefixes.append(head);head=append_chunk(head,value)
    assert len(head['values'])==2
    assert head['previous'] is prefixes[128]
    assert head['previous']['previous'] is prefixes[64]
    assert head['values'][-1] is values[-1]
    assert len(prefixes[65]['values'])==1


@pytest.mark.asyncio
async def test_catalog_registry_live_changes_own_cut_and_detached_views():
    ctx=Context()
    try:
        await ctx.plugin(CurrentSessionPlugin);await ctx.plugin(SessionProjectionsPlugin)
        registry=ctx.get('sessionProjections');registry.register(CATALOG)
        store=ctx.get('sessions');parent=store.create('parent');child=store.create('child')
        establish_catalog_child(parent,child.header,dict(mode='continuable',label='first'))
        first=registry.snapshot(parent)['values']['subagentCatalog']
        first[0]['label']='mutated';first.clear()
        assert registry.snapshot(parent)['values']['subagentCatalog'][0]['label']=='first'
        inherited=store.create('fork',dict(seed=parent.snapshotEvents(),inheritedEventCount=parent.seq,meta=dict(isSeeded=True)))
        assert registry.snapshot(inherited)['values']['subagentCatalog']==[]
        establish_catalog_child(inherited,child.header,dict(mode='one-shot'))
        assert registry.snapshot(inherited)['values']['subagentCatalog']==[dict(id='child',createdAt=child.header.createdAt,mode='one-shot')]
        state=registry.stateOf(inherited,'subagentCatalog')
        assert apply(state,dict(type='irrelevant')) is state
        assert view(state)[0]['id']=='child'
    finally:await ctx.fiber.dispose()
