"""rc.3 one-shot spawn/fork consumers of explicit Agent setup and ownership."""
import uuid

from dsh.core.react_loop_current import ReactLoopAgent
from dsh.subagent.in_process import InProcessRun, InProcessProvider, SpawnInProcess, ForkInProcess
from dsh.subagent.composition import child_options, child_meta, capture_policy, append_policy
from dsh.subagent.composition_current import assert_max_depth,resolve_depth,apply_child_composition
from dsh.core.session.json import UNDEFINED
from dsh.subagent.descriptor import completed_turn_prefix
from dsh.subagent.assistant_output_current import final_assistant_output
from dsh.subagent.structured import attach_structured


async def start_run(request, seed=None):
    signal, parent = request['signal'], request['parent']
    # Source validates the supplied budget even when publication is already aborted.
    assert_max_depth(request.get('maxDepth',UNDEFINED))
    if signal.aborted:
        raise RuntimeError('subagent request was aborted before child publication')
    depth = resolve_depth(parent,request.get('maxDepth'))
    boundary, inherited = len(seed or []), capture_policy(parent)
    structured = None

    def setup(child_ctx, child):
        nonlocal structured
        append_policy(child.session, inherited)
        apply_child_composition(child_ctx, parent, request)
        if 'outputSchema' in request:
            structured = attach_structured(child_ctx, request['outputSchema'])
        appended = False
        async def descriptor(payload, next_fn):
            nonlocal appended
            decision = await next_fn()
            if not appended and decision.get('kind') == 'enter':
                appended = True
                payload['agent'].session.append('subagent/descriptor', request['descriptor'])
            return decision
        child_ctx.on('agent/pre-step', descriptor)

    options = dict(sessionId=str(uuid.uuid4()), parentAgent=parent,
                   meta=child_meta(parent, depth, seed is not None),
                   agentOptions=child_options(parent, request.get('agentOptions'), depth), signal=signal, setup=setup)
    if seed is not None:
        options.update(seed=seed, inheritedEventCount=boundary)
    handle = await parent.ctx.get('agents').create(options)
    return InProcessRun(handle, signal, request['prompt'], boundary, structured,
                        output_reader=final_assistant_output, eager_start=ReactLoopAgent._start)


class CurrentInProcessProvider(InProcessProvider):
    async def start(self, request):
        seed = completed_turn_prefix(request['parent']) if self.inheritsParentContext else None
        return await start_run(request, seed if seed else None)


class CurrentSpawnInProcess(SpawnInProcess):
    def apply(self, ctx):
        ctx.get('subagents').registerProvider(CurrentInProcessProvider(self.config.get('providerName', 'spawn')))


class CurrentForkInProcess(ForkInProcess):
    def apply(self, ctx):
        ctx.get('subagents').registerProvider(CurrentInProcessProvider(self.config.get('providerName', 'fork'), True))
