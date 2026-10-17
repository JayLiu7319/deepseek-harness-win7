"""One owned Agent turn, started only after the complete profile is ready."""
import asyncio
import os
import sys
import uuid

from dsh.cordis.plugin import Plugin
from dsh.core.model_selection import ModelSelection, ModelSelectionRef, install_model_selection
from dsh.llm.message import create_user_message


def summarize(events, first_seq):
    started, text, reason = False, "", None
    for event in events:
        if event["seq"] < first_seq:
            continue
        if event["type"] == "turn/start":
            started = True
        if not started:
            continue
        if event["type"] == "assistant/message":
            content = event["data"]["message"]["content"]
            joined = "".join(b["text"] for b in content if b["type"] == "text")
            if joined:
                text = joined
        if event["type"] == "turn/end":
            reason = event["data"]["reason"]
    return text, reason


class HeadlessRunnerPlugin(Plugin):
    id = "headless-runner"
    inject = ["agentDefaultModel", "agents", "sessions"]

    def stream_reasoning(self, ctx, agent):
        line = {"open": False, "newline": True, "started": False}

        def close_line():
            if line["open"] and not line["newline"]:
                sys.stderr.write("\n")
            line["open"], line["newline"] = False, True

        def observe(session, event):
            if session is not agent.session:
                return
            if event["type"] == "turn/start":
                close_line()
                line["started"] = True
            if not line["started"] or event["type"] != "assistant/chunk":
                return
            chunk = event["data"]["chunk"]
            if chunk["type"] == "reasoning-delta" and chunk.get("text"):
                if not line["open"]:
                    sys.stderr.write("dsh: reasoning:\n")
                sys.stderr.write(chunk["text"])
                sys.stderr.flush()
                line["open"], line["newline"] = True, chunk["text"].endswith("\n")
            elif chunk["type"] not in ("usage", "reasoning-delta"):
                if chunk.get("blockType") != "reasoning" and chunk.get("block", {}).get("type") != "reasoning":
                    close_line()

        return ctx.on("session/event", observe), close_line

    async def create_agent(self, ctx, selected, setup):
        return await ctx.get("agents").create("session-" + str(uuid.uuid4()), options=selected,
            meta={"cwd": os.getcwd()}, setup=setup)

    def summarize(self, session, first_seq):
        return summarize(session.events, first_seq)

    def validate_task(self, task):
        if not isinstance(task, str) or not task.strip():
            raise ValueError("headless-runner requires a task")

    def apply(self, ctx):
        exit_fn, ready = ctx.get("appExit"), ctx.get("appReady")
        if exit_fn is None or ready is None:
            raise RuntimeError("headless-runner requires launcher appExit and appReady")
        task_text = self.config.get("task")
        self.validate_task(task_text)
        active = [None]

        async def run():
            try:
                selected = ctx.get("agentDefaultModel").current_selection()

                def setup(agent_ctx):
                    selection = ModelSelection(selected["provider"], selected["model"], selected.get("reasoningEffort"))
                    install_model_selection(agent_ctx, ModelSelectionRef(selection))

                handle = await self.create_agent(ctx, selected, setup)
                agent = handle.agent
                await agent.when_idle()
                first_seq = agent.session.seq
                stop, close_line = self.stream_reasoning(ctx, agent)
                try:
                    agent.followup(create_user_message({"content": [{"type": "text", "text": task_text}], "source": {"kind": "user"}}))
                    await agent.when_idle()
                finally:
                    stop()
                    close_line()
                await ctx.get("sessions").flush(agent.session)
                text, reason = self.summarize(agent.session, first_seq)
                sys.stdout.write(text + "\n")
                if reason and reason.get("kind") == "error":
                    error = reason["error"]
                    sys.stderr.write("dsh: {}: {}\n".format(error["code"], error["message"]))
                exit_fn(0 if reason and reason.get("kind") == "completed" else 1)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                sys.stderr.write("dsh: {}\n".format(error))
                exit_fn(1)

        def start():
            active[0] = asyncio.create_task(run())

        cancel_ready = ready.on_ready(start)

        async def dispose():
            cancel_ready()
            task = active[0]
            if task is not None and not task.done() and task is not asyncio.current_task():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        ctx.effect(lambda: dispose)
