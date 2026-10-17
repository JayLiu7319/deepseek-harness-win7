"""Current cursor chains, termination, failure precedence and previous state."""
import json
from pathlib import Path
cases=[]
def tool(name):return dict(name=name,inputSchema=dict(type='object'))
def add(name,pages,**options):cases.append(dict(case=name,kind='mcp-current',pages=pages,**options))
add('empty', [dict(tools=[])])
add('single',[dict(tools=[tool('one')])])
add('pages',[dict(tools=[tool('one')],nextCursor='a'),dict(tools=[tool('two')],nextCursor='b'),dict(tools=[tool('three')])])
add('empty-middle',[dict(tools=[],nextCursor='a'),dict(tools=[],nextCursor='b'),dict(tools=[tool('last')],nextCursor='')])
add('repeated',[dict(tools=[],nextCursor='a'),dict(tools=[],nextCursor='a')])
add('cycle',[dict(tools=[tool('one')],nextCursor='a'),dict(tools=[tool('two')],nextCursor='b'),dict(tools=[tool('three')],nextCursor='a')])
add('space-cursor',[dict(tools=[],nextCursor=' '),dict(tools=[],nextCursor=' ')])
add('case-sensitive-cursor',[dict(tools=[],nextCursor='a'),dict(tools=[],nextCursor='A'),dict(tools=[tool('last')])])
add('unicode-cursor',[dict(tools=[],nextCursor='游标'),dict(tools=[],nextCursor='游标')])
add('duplicate-before-cursor',[dict(tools=[tool('one')],nextCursor='a'),dict(tools=[tool('one')],nextCursor='a')])
add('duplicate-before-next-fetch',[dict(tools=[tool('one'),tool('one')],nextCursor='a'),dict(error='must not reach this page')])
add('network-preserves',[dict(tools=[tool('one')],nextCursor='a'),dict(error='network failed')])
add('old-multiple-preserve',[dict(tools=[],nextCursor='a'),dict(tools=[],nextCursor='a')],previous=['old1','old2'])
add('initial-reject',[dict(tools=[],nextCursor='a'),dict(tools=[],nextCursor='a')],previous=[])
add('long-valid-chain',[dict(tools=[tool(str(i))],**(dict(nextCursor=str(i)) if i<20 else {})) for i in range(21)])
Path(__file__).with_name('mcp_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
