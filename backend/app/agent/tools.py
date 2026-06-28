"""The agent's tool catalogue and dispatch.

Read-only tools (``list_tree``, ``read_file``, ``search_files``) execute inline
against the owner's drive. Mutating tools (``create_folder``, ``move_node``,
``rename_node``) are never executed here: :func:`build_pending` turns each call
into a proposal the user approves, which is then applied transactionally by
``agent.apply`` through the same operation cores the REST routers use.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import storage
from ..errors import ApiError
from ..models import File, Folder
from ..services import ROOT_FOLDER_ID, require_owned_file
from .extract import MAX_READ_BYTES, extract_text

# Caps so one tool result can't blow the model's context on a large drive.
MAX_TREE_NODES = 2000
MAX_TREE_CHARS = 40_000
SEARCH_LIMIT = 50
# list_tree shows a shallow overview by default and lets the model drill into a
# specific folder, so a big drive is never dumped into the context at once.
DEFAULT_TREE_DEPTH = 2
MAX_TREE_DEPTH = 10

# Tools that change the drive. The loop refuses to execute these and routes them
# to the user for approval instead.
MUTATING_TOOLS = frozenset({"create_folder", "move_node", "rename_node"})


def is_mutating(name: str) -> bool:
    return name in MUTATING_TOOLS


def tool_definitions() -> list[dict[str, Any]]:
    """The full catalogue advertised to the model."""

    def fn(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
        return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}

    node_props = {
        "nodeType": {
            "type": "string",
            "enum": ["file", "folder"],
            "description": "Whether `id` is a file or a folder.",
        },
        "id": {"type": "string", "description": "The id of the existing file or folder, from list_tree."},
        "path": {"type": "string", "description": "The node's current path (for the human summary)."},
    }
    return [
        fn(
            "list_tree",
            "List folders and files as a tree, with their ids, types, and sizes. By default it shows the drive "
            "root a couple of levels deep; folders that aren't expanded show an item count and how to expand "
            "them. Pass `path` to drill into one folder and `depth` for how many levels to show — fetch only "
            "what you need rather than listing the whole drive at once.",
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": 'Folder to list, e.g. "/Documents". Defaults to the root "/".',
                    },
                    "depth": {
                        "type": "integer",
                        "description": "How many levels deep to show (1-10). Defaults to 2.",
                    },
                },
                "additionalProperties": False,
            },
        ),
        fn(
            "read_file",
            "Read and return the extracted text of one file (text, PDF, or Word). Use it to understand a "
            "file's contents so you can group it sensibly. `id` is from list_tree.",
            {
                "type": "object",
                "properties": {"id": {"type": "string", "description": "The file id to read."}},
                "required": ["id"],
                "additionalProperties": False,
            },
        ),
        fn(
            "search_files",
            "Find files whose name contains the query (case-insensitive). Returns matching paths and ids.",
            {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Substring to look for in file names."}},
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        fn(
            "create_folder",
            "Propose creating a new folder. `parentPath` is the destination folder path ('/' for the root). "
            "Requires user approval before it is applied.",
            {
                "type": "object",
                "properties": {
                    "parentPath": {"type": "string", "description": "Path of the parent folder, '/' for root."},
                    "name": {"type": "string", "description": "Name for the new folder."},
                },
                "required": ["parentPath", "name"],
                "additionalProperties": False,
            },
        ),
        fn(
            "move_node",
            "Propose moving a file or folder into another folder. `destinationPath` may be a folder you proposed "
            "creating earlier in the same plan. Requires user approval before it is applied.",
            {
                "type": "object",
                "properties": {
                    **node_props,
                    "destinationPath": {"type": "string", "description": "Destination folder path ('/' for root)."},
                },
                "required": ["nodeType", "id", "destinationPath"],
                "additionalProperties": False,
            },
        ),
        fn(
            "rename_node",
            "Propose renaming a file or folder in place. Requires user approval before it is applied.",
            {
                "type": "object",
                "properties": {**node_props, "newName": {"type": "string", "description": "The new name."}},
                "required": ["nodeType", "id", "newName"],
                "additionalProperties": False,
            },
        ),
    ]


# --- Read-only execution ----------------------------------------------------

def execute_readonly(db: Session, owner_id: str, name: str, args: dict[str, Any]) -> str:
    if name == "list_tree":
        path = args.get("path")
        start_path = path if isinstance(path, str) and path.strip() else "/"
        raw_depth = args.get("depth")
        if isinstance(raw_depth, bool) or not isinstance(raw_depth, int | float):
            depth = DEFAULT_TREE_DEPTH
        else:
            depth = max(1, min(MAX_TREE_DEPTH, int(raw_depth)))
        return _list_tree(db, owner_id, start_path, depth)
    if name == "read_file":
        return _read_file(db, owner_id, args)
    if name == "search_files":
        return _search_files(db, owner_id, args)
    raise ApiError(400, f"unknown read-only tool: {name}")


def render_drive_tree(db: Session, owner_id: str) -> str:
    """The full drive structure (folders + file names + ids, no contents), capped.
    Fed to the model up front so it can pick which files it actually needs to read."""
    return _list_tree(db, owner_id, "/", MAX_TREE_DEPTH)


def _list_tree(db: Session, owner_id: str, start_path: str = "/", max_depth: int = DEFAULT_TREE_DEPTH) -> str:
    start_id = _resolve_existing_folder_id(db, owner_id, start_path)
    if start_id is None:
        return f'Folder not found: "{start_path}". Call list_tree with no arguments to see the drive root.'

    folders = db.execute(select(Folder).where(Folder.owner_id == owner_id)).scalars().all()
    files = db.execute(select(File).where(File.owner_id == owner_id)).scalars().all()

    child_folders: dict[str, list[Folder]] = defaultdict(list)
    for folder in folders:
        child_folders[folder.parent_folder_id].append(folder)
    child_files: dict[str, list[File]] = defaultdict(list)
    for file in files:
        child_files[file.parent_folder_id].append(file)

    lines: list[str] = []
    count = 0
    chars = 0
    truncated = False

    def emit(line: str) -> None:
        nonlocal count, chars, truncated
        if truncated:
            return
        if count >= MAX_TREE_NODES or chars >= MAX_TREE_CHARS:
            truncated = True
            return
        lines.append(line)
        count += 1
        chars += len(line)

    def walk(folder_id: str, path: str, depth: int) -> None:
        for folder in sorted(child_folders[folder_id], key=lambda f: f.name.lower()):
            if truncated:
                return
            child_path = f"{path}/{folder.name}"
            items = len(child_folders[folder.id]) + len(child_files[folder.id])
            # At the depth frontier, summarise a non-empty folder instead of
            # expanding it — the model can drill in with a targeted list_tree.
            if depth >= max_depth and items > 0:
                emit(f'{child_path}/  [folder id={folder.id}, {items} items — list_tree path="{child_path}" to expand]')
            else:
                emit(f"{child_path}/  [folder id={folder.id}]")
                walk(folder.id, child_path, depth + 1)
        for file in sorted(child_files[folder_id], key=lambda f: f.filename.lower()):
            if truncated:
                return
            emit(f"{path}/{file.filename}  [file id={file.id} type={file.content_type} size={file.size}]")

    base = "" if start_id == ROOT_FOLDER_ID else "/" + "/".join(_path_segments(start_path))
    walk(start_id, base, 1)

    if not lines:
        return "(the drive is empty)" if start_id == ROOT_FOLDER_ID else f'(folder "{start_path}" is empty)'
    out = "\n".join(lines)
    if truncated:
        out += '\n…(tree truncated; narrow with list_tree path="/Folder" or a smaller depth)'
    return out


def _path_segments(path: str | None) -> list[str]:
    if not path:
        return []
    return [seg for seg in path.replace("\\", "/").split("/") if seg and seg != "."]


def _resolve_existing_folder_id(db: Session, owner_id: str, path: str | None) -> str | None:
    """Resolve a '/'-relative path to an owned folder id (ROOT for '/'); None if
    any segment doesn't exist."""
    segments = _path_segments(path)
    if any(seg == ".." for seg in segments):
        return None
    current = ROOT_FOLDER_ID
    for seg in segments:
        folder = db.execute(
            select(Folder).where(
                Folder.owner_id == owner_id,
                Folder.parent_folder_id == current,
                func.lower(Folder.name) == seg.lower(),
            )
        ).scalars().first()
        if folder is None:
            return None
        current = folder.id
    return current


def _read_file(db: Session, owner_id: str, args: dict[str, Any]) -> str:
    file_id = args.get("id")
    if not isinstance(file_id, str) or not file_id:
        raise ApiError(400, "read_file requires an `id`")
    file = require_owned_file(db, owner_id, file_id)
    if file.status != "ready" or not storage.exists(file.storage_key):
        return f"[file “{file.filename}” has no stored content yet]"
    with storage.open_read(file.storage_key) as handle:
        data = handle.read(MAX_READ_BYTES)
    return extract_text(file.filename, file.content_type, data)


def _search_files(db: Session, owner_id: str, args: dict[str, Any]) -> str:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ApiError(400, "search_files requires a `query`")
    needle = query.strip().lower()
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = db.execute(
        select(File)
        .where(File.owner_id == owner_id, func.lower(File.filename).like(f"%{escaped}%", escape="\\"))
        .order_by(func.lower(File.filename))
        .limit(SEARCH_LIMIT + 1)
    ).scalars().all()
    if not rows:
        return f'No files match "{query}".'

    index = _folder_index(db, owner_id)
    lines = [
        f"{_path_of_folder(index, row.parent_folder_id)}/{row.filename}  "
        f"[file id={row.id} type={row.content_type} size={row.size}]"
        for row in rows[:SEARCH_LIMIT]
    ]
    out = "\n".join(lines)
    if len(rows) > SEARCH_LIMIT:
        out += f"\n…(more than {SEARCH_LIMIT} matches; refine the query)"
    return out


def _folder_index(db: Session, owner_id: str) -> dict[str, tuple[str, str]]:
    rows = db.execute(
        select(Folder.id, Folder.name, Folder.parent_folder_id).where(Folder.owner_id == owner_id)
    ).all()
    return {row.id: (row.name, row.parent_folder_id) for row in rows}


def _path_of_folder(index: dict[str, tuple[str, str]], folder_id: str) -> str:
    if folder_id == ROOT_FOLDER_ID:
        return ""
    parts: list[str] = []
    seen: set[str] = set()
    current = folder_id
    while current and current != ROOT_FOLDER_ID and current not in seen:
        seen.add(current)
        entry = index.get(current)
        if entry is None:
            break
        name, parent = entry
        parts.append(name)
        current = parent
    return "/" + "/".join(reversed(parts))


# --- Proposals --------------------------------------------------------------

def build_pending(call: dict[str, Any]) -> dict[str, Any]:
    """Turn a mutating tool call into a confirmable proposal. Raises
    ``ApiError`` only when the model emitted arguments that aren't valid JSON."""
    function = call.get("function") or {}
    name = str(function.get("name") or "")
    args = parse_args(function.get("arguments"))
    return {
        "tool_call_id": str(call.get("id") or ""),
        "tool": name,
        "args": args,
        "summary": _summarize(name, args),
    }


def parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise ApiError(400, "the model produced invalid tool arguments") from exc
    return parsed if isinstance(parsed, dict) else {}


def _summarize(name: str, args: dict[str, Any]) -> str:
    def arg(key: str) -> str:
        value = args.get(key)
        return value if isinstance(value, str) and value else "?"

    if name == "create_folder":
        return f"Create folder “{arg('name')}” in {arg('parentPath')}"
    if name == "move_node":
        return f"Move {arg('path')} → {arg('destinationPath')}"
    if name == "rename_node":
        return f"Rename {arg('path')} → {arg('newName')}"
    return f"{name} {args}"
