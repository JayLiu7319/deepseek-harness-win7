"""Parent-owned rc.3 discovery facts, with persistent 64-entry chunks."""
import math


def integer(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0 and value == int(value)


def fact(value):
    if (not isinstance(value, dict) or set(value)-{'version','childId','childCreatedAt','mode','label'}
            or type(value.get('version')) not in (int,float) or value['version'] != 0
            or not isinstance(value.get('childId'),str) or not integer(value.get('childCreatedAt'))
            or value.get('mode') not in ('one-shot','continuable')
            or ('label' in value or value.get('mode')=='continuable') and not isinstance(value.get('label'),str)):
        raise ValueError('invalid subagent catalog fact')
    return dict(value)


def append_chunk(head, value):
    if head is None or len(head['values'])==64:
        return dict(values=[value],**(dict(previous=head) if head is not None else {}))
    return dict(values=head['values']+[value],**(dict(previous=head['previous']) if 'previous' in head else {}))


def iterate_chunks(head):
    chunks=[]
    while head is not None:
        chunks.append(head);head=head.get('previous')
    for chunk in reversed(chunks):
        yield from chunk['values']


def parse_state(value):
    if (not isinstance(value,dict) or set(value)-{'inheritedEventCount','head'}
            or not integer(value.get('inheritedEventCount'))):
        raise ValueError('invalid subagent catalog state')
    result=dict(inheritedEventCount=value['inheritedEventCount']);target=result;node=value.get('head')
    # Iterative validation keeps long Python checkpoints below the recursion limit.
    while node is not None:
        if (not isinstance(node,dict) or set(node)-{'values','previous'}
                or not isinstance(node.get('values'),list) or not 1<=len(node['values'])<=64):
            raise ValueError('invalid subagent catalog chunk')
        parsed=dict(values=[fact(item) for item in node['values']])
        target['head' if target is result else 'previous']=parsed
        target=parsed
        if 'previous' in node and node['previous'] is None:raise ValueError('invalid subagent catalog chunk')
        node=node.get('previous')
    if 'head' in value and value['head'] is None:raise ValueError('invalid subagent catalog chunk')
    return result


def apply(state,event):
    if event['type']!='subagent/catalog' or event['seq']<state['inheritedEventCount']:return state
    return dict(state,head=append_chunk(state.get('head'),fact(event['data'])))


def view(state):
    return [dict(id=data['childId'],createdAt=data['childCreatedAt'],mode=data['mode'],
                 **(dict(label=data['label']) if 'label' in data else {})) for data in iterate_chunks(state.get('head'))]


def parse_view(value):
    if not isinstance(value,list):raise ValueError('invalid subagent catalog view')
    result=[]
    for row in value:
        if not isinstance(row,dict) or set(row)-{'id','createdAt','mode','label'}:raise ValueError('invalid subagent catalog row')
        data=fact(dict(version=0,childId=row.get('id'),childCreatedAt=row.get('createdAt'),mode=row.get('mode'),
                       **(dict(label=row['label']) if 'label' in row else {})))
        result.append(dict(id=data['childId'],createdAt=data['childCreatedAt'],mode=data['mode'],
                           **(dict(label=data['label']) if 'label' in data else {})))
    return result


CATALOG=dict(key='subagentCatalog',stateVersion=2,stateSchema=parse_state,
             init=lambda header,cut:dict(inheritedEventCount=cut),apply=apply,wire=dict(viewSchema=parse_view,view=view))
subagentCatalogProjectionDefinition=CATALOG


def establish_catalog_child(parent,child,descriptor):
    parent.append('subagent/catalog',dict(version=0,childId=child.id,childCreatedAt=child.createdAt,
        mode=descriptor['mode'],**(dict(label=descriptor['label']) if 'label' in descriptor else {})))


establishCatalogChild=establish_catalog_child
