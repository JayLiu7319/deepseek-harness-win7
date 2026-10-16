"""Current delegation depth validation and persona-prefix composition."""
from dsh.core.session.json import UNDEFINED
from dsh.cordis.utils import js_to_string
from dsh.subagent.composition import valid_depth,delegation_depth,MAX_SAFE,apply_composition


def assert_max_depth(value=UNDEFINED):
    if value is not UNDEFINED:
        try:valid_depth(value)
        except (ValueError,TypeError,OverflowError):raise TypeError('subagent maxDepth must be a non-negative safe integer')


def resolve_depth(parent,maximum=None):
    try:depth=delegation_depth(parent)+1
    except ValueError:raise TypeError('agent subagentDepth must be a non-negative safe integer')
    if depth>MAX_SAFE:
        error=ValueError('subagent child depth exceeds the safe-integer range');error.name='RangeError';raise error
    if maximum is not None and depth>maximum:
        error=ValueError('subagent depth %s exceeds maxDepth %s' % (depth,js_to_string(maximum)))
        error.name,error.attemptedDepth,error.maxDepth='SubagentDepthError',depth,maximum;raise error
    return depth


def apply_child_composition(child_ctx,parent,composition):
    return apply_composition(child_ctx,parent,composition,
        persona_section='deployment:persona-prefix',persona_order='DEPLOYMENT_PERSONA_PREFIX')
