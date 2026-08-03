"""Base agent runtime for Kyrozen Core.

Future professional agents (ProblemDiscoveryAgent, HardwareAgent, etc.)
will inherit from BaseAgent.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from kyrozen.config import KyrozenConfig
from kyrozen.logs import KyrozenLogger, get_logger
from kyrozen.memory import InMemoryMemory, MemoryInterface
from kyrozen.models import ModelInterface, get_model_provider
from kyrozen.tools import ToolRegistry, ToolResult, get_default_registry

from .permission import PermissionManager
from .task import Task, TaskManager


class BaseAgent:
    """Base agent that can receive tasks, call models, and execute tools."""

    #: Tool names of which at least ONE must execute successfully before a
    #: plain-text response is accepted as the final answer (only enforced when
    #: :meth:`_action_required` returns True for the user input). Subclasses
    #: (e.g. SoftwareDevelopmentAgent) override this so the model can no longer
    #: "narrate a plan" and have the loop treat it as task completion.
    required_actions: tuple[str, ...] = ()

    #: How many corrective re-prompts to send when the model answers with prose
    #: even though a required action has not happened yet.
    max_action_nudges: int = 2

    #: Appended to EVERY agent's system prompt (including subclasses that fully
    #: override :meth:`_build_system_prompt`) so there is exactly one way to ask
    #: the user anything: the structured question card. Plain-prose questions --
    #: even a throwaway "需要我帮你做吗" -- are forbidden, because the user then
    #: has to guess the expected answer format instead of just clicking.
    QUESTION_PROTOCOL_PROMPT: str = (
        "MANDATORY QUESTION PROTOCOL (this overrides every other instruction about asking):\n"
        "- You MUST NEVER ask the user anything in plain prose. EVERY question you ask, without\n"
        "  exception, has to be emitted as exactly ONE fenced ```kyrozen-question block placed at\n"
        "  the very END of your reply.\n"
        "- This explicitly includes small confirmations and yes/no checks such as \"需要我帮你做吗\",\n"
        "  \"要继续推进吗\", \"这样可以吗\", \"Shall I proceed?\", \"Is that OK?\". No question is too\n"
        "  small for the block.\n"
        "- The block body MUST be one valid JSON object with exactly these keys:\n"
        '  {"question": "<the question, in the user\'s language>", "options": [{"label": "<short\n'
        '  choice>", "value": "<short choice>"}], "allow_other": true}\n'
        "- When the question has natural choices, give 2-4 short options and keep allow_other true.\n"
        "  The UI automatically appends an \"其他（自己输入）\" free-text field, so NEVER add your own\n"
        "  \"other\" / \"其他\" / \"以上都不是\" option.\n"
        "- For a yes/no confirmation use exactly two options (for example 好的 / 先不用).\n"
        "- When the question is genuinely open-ended and any option list would bias the answer, use\n"
        "  \"options\": [] together with allow_other true. The UI then shows a plain text input.\n"
        "- Ask at most ONE question per reply, and never repeat the question text outside the block.\n"
        "- If you are not asking anything, do not emit the block at all.\n"
    )

    def __init__(
        self,
        config: KyrozenConfig,
        model: ModelInterface | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryInterface | None = None,
        task_manager: TaskManager | None = None,
        permission_manager: PermissionManager | None = None,
        logger: KyrozenLogger | None = None,
        confirmation_callback: callable | None = None,
    ) -> None:
        self.config = config
        self.model = model or get_model_provider(config)
        self.tools = tools or get_default_registry()
        self.memory = memory or InMemoryMemory()
        self.task_manager = task_manager or TaskManager(store_path=config.task_store_path)
        self.permission = permission_manager or PermissionManager(mode=config.permission_mode)
        self.logger = logger or get_logger(config.log_level)
        self.confirmation_callback = confirmation_callback
        self._cancelled = False

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        return (
            "You are Kyrozen Core, an AI agent foundation. You have access to tools.\n\n"
            "When you need to use a tool, output ONLY a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "If no tool is needed, reply with a plain text answer.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            "Rules:\n"
            "- Always respond in the same language as the user's latest message.\n"
            "- Use structured parameters, not plain strings.\n"
            "- Do not invent tool names or actions.\n"
            "- Do NOT use XML tags such as <tool_call> for tool calls; use JSON only.\n"
            "- For file paths, prefer relative paths from the current working directory.\n"
            "- When asked to analyze a project, start with list_dir or find_files.\n"
            "- DO NOT write files, execute terminal commands, run git operations, or update project state unless the user explicitly asks you to.\n"
            "- If the user asks 'what should I do next', '下一步怎么办', or similar, give a conversational answer. Only use update_project for metadata when explicitly asked; use advance_project_stage for any gated stage transition.\n"
        )

    def _extract_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Extract tool-call JSON objects (and XML-style tool calls) from the model response."""
        calls: list[dict[str, Any]] = []
        # Try to parse the entire text as JSON first
        text = text.strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tool" in data:
                calls.append(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "tool" in item:
                        calls.append(item)
            return calls
        except json.JSONDecodeError:
            pass

        # Look for JSON inside code blocks
        code_block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        for match in re.finditer(code_block_pattern, text):
            raw = match.group(1).strip()
            try:
                data = json.loads(raw)
                if isinstance(data, dict) and "tool" in data:
                    calls.append(data)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "tool" in item:
                            calls.append(item)
            except json.JSONDecodeError:
                continue

        # Look for inline JSON objects/arrays (e.g. model preamble + JSON)
        calls.extend(self._extract_inline_tool_calls(text))

        # Some models emit XML-style tool calls such as:
        # <tool_call><tool_name>list_dir</tool_name><action>list</action>...</tool_call>
        calls.extend(self._extract_xml_tool_calls(text))

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_calls: list[dict[str, Any]] = []
        for call in calls:
            key = json.dumps(call, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                unique_calls.append(call)
        return unique_calls

    def _extract_inline_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Find tool-call JSON objects/arrays embedded anywhere in the text."""
        calls: list[dict[str, Any]] = []
        pairs = {"{": "}", "[": "]"}
        i = 0
        while i < len(text):
            char = text[i]
            if char in pairs:
                close = pairs[char]
                depth = 1
                j = i + 1
                in_string = False
                escape = False
                while j < len(text) and depth > 0:
                    c = text[j]
                    if escape:
                        escape = False
                    elif c == "\\":
                        escape = True
                    elif c == '"' and not in_string:
                        in_string = True
                    elif c == '"' and in_string:
                        in_string = False
                    elif not in_string:
                        if c == char:
                            depth += 1
                        elif c == close:
                            depth -= 1
                    j += 1
                if depth == 0:
                    raw = text[i:j]
                    try:
                        data = json.loads(raw)
                        if isinstance(data, dict) and "tool" in data:
                            calls.append(data)
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict) and "tool" in item:
                                    calls.append(item)
                    except json.JSONDecodeError:
                        pass
                    i = j
                    continue
            i += 1
        return calls

    def _extract_xml_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Parse XML-style tool calls like <tool_call><tool_name>x</tool_name>...</tool_call>."""
        calls: list[dict[str, Any]] = []
        pattern = re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", re.IGNORECASE)
        for match in pattern.finditer(text):
            inner = match.group(1)
            tool_match = re.search(r"<tool_name>\s*([\s\S]*?)\s*</tool_name>", inner, re.IGNORECASE)
            action_match = re.search(r"<action>\s*([\s\S]*?)\s*</action>", inner, re.IGNORECASE)
            params_match = re.search(r"<parameters>\s*([\s\S]*?)\s*</parameters>", inner, re.IGNORECASE)
            if not tool_match or not action_match:
                continue
            parameters: dict[str, Any] = {}
            if params_match:
                params_inner = params_match.group(1)
                for param_match in re.finditer(r"<(\w+)>\s*([\s\S]*?)\s*</\1>", params_inner):
                    # Skip nested metadata tags that some models may include.
                    key = param_match.group(1)
                    if key in ("tool_name", "action", "parameters"):
                        continue
                    parameters[key] = param_match.group(2).strip()
            calls.append({
                "tool": tool_match.group(1).strip(),
                "action": action_match.group(1).strip(),
                "parameters": parameters,
            })
        return calls

    def _strip_tool_calls_from_text(self, text: str) -> str:
        """Remove code blocks, inline tool-call JSON, and XML tool-call blocks, keeping only conversational text."""
        # Remove fenced code blocks first.
        clean = re.sub(r"```(?:json)?\s*[\s\S]*?\s*```", "", text)
        # Remove XML-style tool call blocks.
        clean = re.sub(r"<tool_call>\s*[\s\S]*?\s*</tool_call>", "", clean, flags=re.IGNORECASE)
        # Scan for inline JSON objects/arrays and drop ones that look like tool calls.
        result: list[str] = []
        pairs = {"{": "}", "[": "]"}
        i = 0
        while i < len(clean):
            char = clean[i]
            if char in pairs:
                close = pairs[char]
                depth = 1
                j = i + 1
                in_string = False
                escape = False
                while j < len(clean) and depth > 0:
                    c = clean[j]
                    if escape:
                        escape = False
                    elif c == "\\":
                        escape = True
                    elif c == '"' and not in_string:
                        in_string = True
                    elif c == '"' and in_string:
                        in_string = False
                    elif not in_string:
                        if c == char:
                            depth += 1
                        elif c == close:
                            depth -= 1
                    j += 1
                if depth == 0:
                    raw = clean[i:j]
                    try:
                        data = json.loads(raw)
                        is_tool_call = False
                        if isinstance(data, dict) and "tool" in data:
                            is_tool_call = True
                        elif isinstance(data, list) and data:
                            is_tool_call = all(isinstance(item, dict) and "tool" in item for item in data)
                        if is_tool_call:
                            i = j
                            continue
                    except json.JSONDecodeError:
                        # The model emitted a tool-call-shaped JSON that is not
                        # strictly valid (e.g. contains Chinese comments such as
                        # "← 使用空数组替代 none"). If it clearly looks like a
                        # tool call, drop it so raw JSON never reaches the user.
                        if '"tool"' in raw or '"action"' in raw:
                            i = j
                            continue
            result.append(clean[i])
            i += 1
        return "".join(result).strip()

    def _execute_tool_calls(self, task: Task, calls: list[dict[str, Any]], confirmed: bool = False) -> list[dict[str, Any]]:
        """Execute tool calls and return their results."""
        results: list[dict[str, Any]] = []
        for call in calls:
            tool_name = call.get("tool", "")
            action = call.get("action", "")
            parameters = call.get("parameters", {})

            step = task.add_step(f"Call {tool_name}.{action}")
            step.metadata = {"tool": tool_name, "action": action, "parameters": parameters}
            step.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            decision = self.permission.check(tool_name, action, parameters)
            if not decision.allowed:
                if decision.requires_confirmation and not confirmed:
                    # If a confirmation callback is registered, ask it and re-run
                    # this single tool call with the user's decision.
                    if self.confirmation_callback is not None:
                        task.update_status("waiting_confirmation")
                        step.status = "waiting_confirmation"
                        self.task_manager.update(task)
                        callback_result = self.confirmation_callback(
                            task=task,
                            tool=tool_name,
                            action=action,
                            parameters=parameters,
                            reason=decision.reason,
                        )
                        user_confirmed = bool(callback_result)
                        trust_session = (
                            isinstance(callback_result, dict) and callback_result.get("trust_for_session") is True
                        )
                        if user_confirmed:
                            if trust_session:
                                self.permission.trust_for_session(tool_name, action)
                            decision = self.permission.confirm(tool_name, action, parameters)
                            task.update_status("running")
                            step.status = "running"
                            self.task_manager.update(task)
                        else:
                            step.error = decision.reason
                            step.status = "failed"
                            step.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                            task.update_status("running")
                            self.task_manager.update(task)
                            results.append({
                                "tool": tool_name,
                                "action": action,
                                "parameters": parameters,
                                "success": False,
                                "error": f"User declined: {decision.reason}",
                            })
                            continue
                    else:
                        task.update_status("waiting_confirmation")
                        step.error = decision.reason
                        step.status = "waiting_confirmation"
                        step.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        self.task_manager.update(task)
                        results.append({
                            "tool": tool_name,
                            "action": action,
                            "parameters": parameters,
                            "requires_confirmation": True,
                            "reason": decision.reason,
                        })
                        continue
                if decision.requires_confirmation and confirmed:
                    decision = self.permission.confirm(tool_name, action, parameters)
                else:
                    step.error = decision.reason
                    step.status = "failed"
                    step.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    self.task_manager.update(task)
                    results.append({
                        "tool": tool_name,
                        "action": action,
                        "parameters": parameters,
                        "success": False,
                        "error": decision.reason,
                    })
                    continue

            tool_parameters = dict(parameters)
            if task.project_id:
                tool_parameters["project_id"] = task.project_id

            result: ToolResult = self.tools.execute(tool_name, action, tool_parameters)
            self.logger.tool(
                f"Executed {tool_name}.{action}",
                task_id=task.id,
                tool=tool_name,
                action=action,
                parameters=tool_parameters,
                success=result.success,
            )
            step.status = "completed" if result.success else "failed"
            step.result = result.to_dict()
            step.error = result.error
            step.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.task_manager.update(task)

            results.append({
                "tool": tool_name,
                "action": action,
                "parameters": parameters,
                "success": result.success,
                "result": result.to_dict(),
            })
        return results

    def _run_loop(self, task: Task, user_input: str, confirmed: bool = False) -> None:
        """Execute the agent loop for an already-created task."""
        start_time = time.time()
        project_id = task.project_id
        # The question protocol is appended here rather than inside
        # _build_system_prompt() so that subclasses which fully override that
        # method (every specialised agent does) still cannot opt out of it.
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": f"{self._build_system_prompt()}\n\n{self.QUESTION_PROTOCOL_PROMPT}",
            },
            {"role": "user", "content": user_input},
        ]

        max_rounds = getattr(self, "max_rounds", 8)
        final_answer = ""
        last_response_had_tools = False
        executed_tools: set[str] = set()
        nudges_used = 0
        action_needed = bool(self.required_actions) and self._action_required(user_input)

        try:
            for round_num in range(max_rounds):
                self._check_cancelled(task)
                self.logger.model(f"Calling model (round {round_num + 1})", task_id=task.id)
                response = self.model.chat(messages)
                self.logger.model(
                    "Model response received",
                    task_id=task.id,
                    model=response.model,
                    provider=response.provider,
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                )

                text = response.content
                calls = self._extract_tool_calls(text)
                last_response_had_tools = bool(calls)
                if not calls:
                    # The model answered in prose. If this stage REQUIRES a real
                    # deliverable action that has not happened yet, do NOT accept
                    # the prose as completion -- force the model to act.
                    if (
                        action_needed
                        and not (executed_tools & set(self.required_actions))
                        and nudges_used < self.max_action_nudges
                    ):
                        nudges_used += 1
                        self.logger.agent(
                            f"Model replied with prose but required action missing; nudging ({nudges_used}/{self.max_action_nudges})",
                            task_id=task.id,
                        )
                        messages.append({"role": "assistant", "content": text})
                        messages.append({
                            "role": "user",
                            "content": (
                                "你刚才只输出了文字描述，但没有调用任何工具。禁止只描述计划或宣布“即将保存/即将写入”。"
                                f"你必须现在立即调用以下工具之一真实产出交付物：{', '.join(self.required_actions)}。"
                                "只输出工具调用 JSON（格式 {\"tool\": ..., \"action\": ..., \"parameters\": {...}}），不要输出任何其他文字。"
                            ),
                        })
                        continue
                    final_answer = text
                    break

                # Strip code blocks and inline tool-call JSON to keep the conversational part clean.
                clean_text = self._strip_tool_calls_from_text(text)
                if clean_text:
                    final_answer = clean_text

                results = self._execute_tool_calls(task, calls, confirmed=confirmed)
                for item in results:
                    if item.get("success"):
                        executed_tools.add(str(item.get("tool", "")))
                self._check_cancelled(task)
                if task.status == "waiting_confirmation":
                    self.task_manager.update(task)
                    return

                tool_results_text = json.dumps(results, ensure_ascii=False, indent=2)
                messages.append({"role": "assistant", "content": text})
                if round_num == max_rounds - 1:
                    messages.append({
                        "role": "user",
                        "content": f"Tool results:\n{tool_results_text}\n\nYou have used the maximum number of tool calls. Do NOT use any more tools. Provide a final natural-language summary for the user based on all results above.",
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": f"Tool results:\n{tool_results_text}\n\nPlease continue or provide the final answer.",
                    })

            # If the last response requested tools, make a final synthesis call that is
            # not allowed to invoke tools. This prevents raw planning text from being shown.
            if last_response_had_tools:
                self.logger.model("Calling model (final synthesis)", task_id=task.id)
                synthesis_messages = list(messages)
                synthesis_messages.append({
                    "role": "user",
                    "content": (
                        "You have finished using tools. Do NOT output any tool JSON, code blocks, or internal planning text. "
                        "Provide a concise final answer in the same language as the user's original request, summarizing what was learned and what remains unknown."
                    ),
                })
                response = self.model.chat(synthesis_messages)
                self.logger.model(
                    "Model response received",
                    task_id=task.id,
                    model=response.model,
                    provider=response.provider,
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                )
                synthesized = self._strip_tool_calls_from_text(response.content).strip()
                if synthesized:
                    final_answer = synthesized

            # If the stage REQUIRED a real deliverable action and the model still
            # never performed one, try the deterministic fallback (e.g. the
            # development agent scaffolds the project itself). If no fallback is
            # available, FAIL the task explicitly instead of pretending success --
            # the UI then shows a clear error with a retry button.
            if action_needed and not (executed_tools & set(self.required_actions)):
                fallback_answer = self._deterministic_fallback(task, user_input, final_answer)
                if fallback_answer is not None:
                    final_answer = fallback_answer
                else:
                    error_msg = (
                        f"本阶段需要真实产出交付物（必需工具：{', '.join(self.required_actions)}），"
                        "但 AI 多次尝试后仍未执行任何工具调用，任务未完成。请点击重试，或换一种更明确的表述再试一次。"
                    )
                    task.fail(error_msg)
                    task.result = {"answer": error_msg}
                    self.logger.error(
                        "Required deliverable action never executed; task failed",
                        task_id=task.id,
                        project_id=project_id,
                    )
                    self.task_manager.update(task)
                    return

            if not final_answer:
                if task.steps:
                    final_answer = "我已经完成了相关操作，但没有生成最终总结。请告诉我是否需要我补充说明。"
                else:
                    final_answer = "I processed your request but did not produce a final answer."

            # Last line of defence: a question must always reach the user as a
            # clickable card, never as prose the user has to answer by typing.
            final_answer = self._enforce_question_protocol(final_answer)

            task.complete(result={"answer": final_answer})
            self.memory.save("user", user_input, task_id=task.id, project_id=project_id)
            self.memory.save("agent", final_answer, task_id=task.id, project_id=project_id)
            self.logger.agent("Task completed", task_id=task.id, answer=final_answer, project_id=project_id)
        except asyncio.CancelledError as e:
            error_msg = f"Cancelled: {e}"
            task.update_status("cancelled")
            task.result = {"answer": error_msg}
            self.logger.warning(error_msg, task_id=task.id, project_id=project_id)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            task.fail(error_msg)
            self.logger.error(error_msg, task_id=task.id, project_id=project_id)

        elapsed = time.time() - start_time
        self.logger.perf(f"Task finished in {elapsed:.2f}s", task_id=task.id, elapsed_seconds=elapsed, project_id=project_id)
        self.task_manager.update(task)

    # ------------------------------------------------------------------
    # Mandatory question protocol enforcement
    # ------------------------------------------------------------------
    #: Detects an already-correct question card (fenced or XML-tag form).
    _QUESTION_BLOCK_PRESENT_RE = re.compile(
        r"```\s*kyrozen[-_]?question\b|<kyrozen[-_]?question>", re.IGNORECASE
    )
    #: A trailing question that reads as a yes/no confirmation. Any Chinese
    #: sentence ending in "吗？" is one, plus the common 是否/要不要 forms and the
    #: English confirmations models fall back to.
    _YES_NO_QUESTION_RE = re.compile(
        r"(吗[?？]?$|呢[?？]?$|要不要|是否|好不好|行不行|可以吗|对吗|"
        r"^\s*(shall|should|do you|would you|can i|may i|is that|does that|sound)\b)",
        re.IGNORECASE,
    )
    #: Sentence boundary used to isolate the trailing question. An ASCII period
    #: only counts when followed by whitespace, so "app.py" / "v1.0" stay intact.
    _SENTENCE_BOUNDARY_RE = re.compile(r"[。！!？?；;\n]|\.\s")
    #: Trailing markdown decoration to look past, e.g. "**要继续吗？**".
    _TRAILING_DECORATION = "*_`>)】」 　"

    @classmethod
    def _split_trailing_question(cls, answer: str) -> tuple[str, str | None]:
        """Split ``answer`` into (body, trailing question) if it ends in a question.

        Returns ``(answer, None)`` when the text does not end with a question, or
        when extracting one would be unsafe (inside a code fence, too long, ...).
        """
        stripped = (answer or "").rstrip()
        if not stripped:
            return answer, None

        # Look past trailing markdown emphasis before testing for "?".
        probe = stripped.rstrip(cls._TRAILING_DECORATION)
        if not probe or probe[-1] not in "?？":
            return answer, None

        # Never reach into an unterminated code fence.
        if stripped.count("```") % 2 != 0:
            return answer, None

        boundaries = [m.end() for m in cls._SENTENCE_BOUNDARY_RE.finditer(probe[:-1])]
        cut = boundaries[-1] if boundaries else 0
        question = probe[cut:].strip()
        body = probe[:cut].rstrip()

        # Drop markdown decoration so the card shows a clean sentence.
        question = re.sub(r"^[\s>#*\-•\d.、)）]+", "", question)
        question = question.replace("**", "").replace("__", "").strip()

        if not question or len(question) > 160:
            return answer, None
        return body, question

    @classmethod
    def _enforce_question_protocol(cls, answer: str) -> str:
        """Guarantee that a question reaching the user is always a question card.

        The system prompt already demands this, but models drift -- especially on
        casual confirmations like "需要我帮你做吗？". Rather than letting that
        become a plain sentence the user has to answer by typing, deterministically
        rewrite it into the canonical block so the UI always renders clickable
        options plus a free-text "其他" field.
        """
        if not answer or cls._QUESTION_BLOCK_PRESENT_RE.search(answer):
            return answer

        body, question = cls._split_trailing_question(answer)
        if not question:
            return answer

        if cls._YES_NO_QUESTION_RE.search(question):
            options = [
                {"label": "好的，继续", "value": "好的，继续"},
                {"label": "先不用", "value": "先不用"},
            ]
        else:
            # Open-ended: no invented options, the UI shows a text input.
            options = []

        block = json.dumps(
            {"question": question, "options": options, "allow_other": True},
            ensure_ascii=False,
        )
        return f"{body}\n\n```kyrozen-question\n{block}\n```".strip()

    def _action_required(self, user_input: str) -> bool:
        """Whether the current user input demands a real deliverable action.

        Subclasses override this with intent heuristics so plain Q&A messages
        (e.g. "当前进度如何？") are NOT forced into tool calls.
        """
        return False

    def _deterministic_fallback(self, task: Task, user_input: str, model_answer: str) -> str | None:
        """Last-resort deterministic deliverable generation.

        Called when the model failed to execute any of :attr:`required_actions`.
        Return the final answer text on success, or ``None`` to signal that no
        fallback exists (the task will then be failed explicitly).
        """
        return None

    def cancel(self) -> None:
        """Request cancellation of the currently running agent loop."""
        self._cancelled = True

    def _check_cancelled(self, task: Task) -> None:
        """Raise CancelledError if cancellation has been requested."""
        if self._cancelled:
            raise asyncio.CancelledError("Task cancelled by user")

    def run(self, user_input: str, confirmed: bool = False, project_id: str | None = None) -> Task:
        """Run one user request through the agent loop."""
        task = self.task_manager.create(
            title=user_input[:60],
            description=user_input,
            project_id=project_id,
        )
        task.update_status("running")
        self.task_manager.update(task)
        self.logger.user(user_input, task_id=task.id)
        self._run_loop(task, user_input, confirmed=confirmed)
        return task

    def run_task(self, task: Task, user_input: str, confirmed: bool = False) -> Task:
        """Run the agent loop for an externally created task."""
        task.update_status("running")
        self.task_manager.update(task)
        self.logger.user(user_input, task_id=task.id)
        self._run_loop(task, user_input, confirmed=confirmed)
        return task
