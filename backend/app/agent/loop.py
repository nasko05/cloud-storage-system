"""The server-side tool-calling loop.

One ``run_turn`` runs the model until it produces a final answer or proposes
drive changes. Read-only tool calls execute inline and the loop continues; the
first assistant turn that contains any mutating calls stops the loop and returns
those calls as proposals for the user to approve. The system prompt is
server-owned and stripped from the returned messages so it is never echoed back
to the browser.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..errors import ApiError
from . import tools
from .client import OpenRouterClient

STEP_CAP_MESSAGE = (
    "I stopped after several steps without finishing. Could you narrow the request, "
    "or tell me to keep going?"
)


def run_turn(
    client: OpenRouterClient,
    db: Session,
    owner_id: str,
    incoming: list[dict[str, Any]],
    *,
    max_steps: int,
) -> dict[str, Any]:
    messages = _with_system_prompt(incoming)
    catalogue = tools.tool_definitions()

    assistant_text: str | None = None
    pending: list[dict[str, Any]] = []
    steps = 0

    while True:
        if steps >= max_steps:
            assistant_text = STEP_CAP_MESSAGE
            break
        steps += 1

        assistant = client.chat(messages, catalogue)
        messages.append(assistant)

        tool_calls = assistant.get("tool_calls") or []
        content = assistant.get("content")
        if not tool_calls:
            assistant_text = content if isinstance(content, str) else None
            break

        batch: list[dict[str, Any]] = []
        for call in tool_calls:
            name = str((call.get("function") or {}).get("name") or "")
            if tools.is_mutating(name):
                try:
                    batch.append(tools.build_pending(call))
                except ApiError as exc:
                    messages.append(_tool_result(call, f"Error: {exc.message}"))
            else:
                messages.append(_tool_result(call, _run_readonly(db, owner_id, call)))

        if batch:
            pending = batch
            assistant_text = content if isinstance(content, str) else None
            break

    return {
        "messages": [m for m in messages if m.get("role") != "system"],
        "assistant_text": assistant_text,
        "pending_actions": pending,
        "done": not pending,
    }


def _run_readonly(db: Session, owner_id: str, call: dict[str, Any]) -> str:
    function = call.get("function") or {}
    name = str(function.get("name") or "")
    try:
        args = tools.parse_args(function.get("arguments"))
        return tools.execute_readonly(db, owner_id, name, args)
    except ApiError as exc:
        return f"Error: {exc.message}"


def _tool_result(call: dict[str, Any], content: str) -> dict[str, Any]:
    function = call.get("function") or {}
    return {
        "role": "tool",
        "tool_call_id": str(call.get("id") or ""),
        "name": str(function.get("name") or ""),
        "content": content,
    }


def _with_system_prompt(incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt(_today_utc())}]
    # Drop any client-supplied system messages so the browser can't override the
    # server-owned instructions.
    out.extend(message for message in incoming if message.get("role") != "system")
    return out


def _today_utc() -> str:
    return f"{datetime.now(UTC):%A, %d %B %Y}"


def _system_prompt(today: str) -> str:
    return (
        "You are the file-organisation assistant built into a personal cloud drive. You help the user "
        "tidy and reorganise their files and folders.\n\n"
        "The drive is a tree of folders and files. Paths are relative to the drive root and use '/'. The "
        "root is '/'. Every file and folder has a stable id shown by list_tree; always reference existing "
        "items by their id.\n\n"
        f"Today's date is {today} (UTC). Resolve relative references like \"today\" or \"this year\" against "
        "it; never infer the current date from a file's name or contents.\n\n"
        "Read-only tools you may use freely: list_tree, read_file, search_files. Call list_tree first to see "
        "what exists. Use read_file to understand a file's contents when that helps you group it.\n\n"
        "Tools that change the drive — create_folder, move_node, rename_node — are PROPOSED to the user and "
        "applied only after they approve. Emit all the steps of a reorganization as tool calls in a single "
        "turn so the user can review and approve the whole plan at once. Never claim a change is finished; "
        "after you propose, the system tells you whether it was applied or declined.\n\n"
        "Guidelines:\n"
        "- Look at the real tree (and file contents when useful) before proposing moves.\n"
        "- To put files into a new folder, propose create_folder first, then move_node with that folder's "
        "path as the destination.\n"
        "- Use relative paths only — never absolute filesystem paths or '..'.\n"
        "- Deleting files is not available; never promise to delete anything."
    )
