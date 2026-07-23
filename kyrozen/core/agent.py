"""Base agent runtime for Kyrozen Core.

Future professional agents (ProblemDiscoveryAgent, HardwareAgent, etc.)
will inherit from BaseAgent.
"""

from __future__ import annotations

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

    def __init__(
        self,
        config: KyrozenConfig,
        model: ModelInterface | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryInterface | None = None,
        task_manager: TaskManager | None = None,
        permission_manager: PermissionManager | None = None,
        logger: KyrozenLogger | None = None,
    ) -> None:
        self.config = config
        self.model = model or get_model_provider(config)
        self.tools = tools or get_default_registry()
        self.memory = memory or InMemoryMemory()
        self.task_manager = task_manager or TaskManager(store_path=config.task_store_path)
        self.permission = permission_manager or PermissionManager(mode=config.permission_mode)
        self.logger = logger or get_logger(config.log_level)

    def _build_system_prompt(self) -> str:
        schemas = self.tools.list_schemas()
        tools_text = json.dumps(schemas, ensure_ascii=False, indent=2)
        return (
            "You are Kyrozen Core, an AI agent foundation. You have access to tools.\n\n"
            "When you need to use a tool, output a single JSON object in this exact format:\n"
            '{\n  "tool": "tool_name",\n  "action": "action_name",\n  "parameters": {...}\n}\n\n'
            "If you need multiple tools, output a JSON array of objects.\n"
            "If no tool is needed, reply with a plain text answer.\n\n"
            "Available tools:\n" + tools_text + "\n\n"
            "Rules:\n"
            "- Use structured parameters, not plain strings.\n"
            "- Do not invent tool names or actions.\n"
            "- For file paths, prefer relative paths from the current working directory.\n"
            "- When asked to analyze a project, start with list_dir or find_files.\n"
            "- DO NOT write files, execute terminal commands, run git operations, or update project state unless the user explicitly asks you to.\n"
            "- If the user asks 'what should I do next', '下一步怎么办', or similar, give a conversational answer. Only use update_project when the user explicitly asks to update the project stage/next_steps.\n"
        )

    def _extract_tool_calls(self, text: str) -> list[dict[str, Any]]:
        """Extract tool-call JSON objects from the model response."""
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

    def _strip_tool_calls_from_text(self, text: str) -> str:
        """Remove code blocks and inline tool-call JSON, keeping only conversational text."""
        # Remove fenced code blocks first.
        clean = re.sub(r"```(?:json)?\s*[\s\S]*?\s*```", "", text)
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
                        pass
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
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_input},
        ]

        max_rounds = 8
        final_answer = ""

        try:
            for round_num in range(max_rounds):
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
                if not calls:
                    final_answer = text
                    break

                # Strip code blocks and inline tool-call JSON to keep the conversational part clean.
                clean_text = self._strip_tool_calls_from_text(text)
                if clean_text:
                    final_answer = clean_text

                results = self._execute_tool_calls(task, calls, confirmed=confirmed)
                if task.status == "waiting_confirmation":
                    self.task_manager.update(task)
                    return

                tool_results_text = json.dumps(results, ensure_ascii=False, indent=2)
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": f"Tool results:\n{tool_results_text}\n\nPlease continue or provide the final answer.",
                })

            if not final_answer:
                if task.steps:
                    final_answer = "我已经完成了相关操作，但没有生成最终总结。请告诉我是否需要我补充说明。"
                else:
                    final_answer = "I processed your request but did not produce a final answer."

            task.complete(result={"answer": final_answer})
            self.memory.save("user", user_input, task_id=task.id, project_id=project_id)
            self.memory.save("agent", final_answer, task_id=task.id, project_id=project_id)
            self.logger.agent("Task completed", task_id=task.id, answer=final_answer, project_id=project_id)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            task.fail(error_msg)
            self.logger.error(error_msg, task_id=task.id, project_id=project_id)

        elapsed = time.time() - start_time
        self.logger.perf(f"Task finished in {elapsed:.2f}s", task_id=task.id, elapsed_seconds=elapsed, project_id=project_id)
        self.task_manager.update(task)

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
