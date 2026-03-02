"""MemGit bridge for Memento-S memory read/write paths.

This module keeps Memento-S decoupled from MemGit package installation details.
It lazily imports MemGit from `MEMGIT_ROOT` and provides helpers to:
- Read/write skills catalog XML as L1 `skill` memory
- Append workflow trajectory/meta/skill events into MemGit memory layers
- Optionally persist MemGit changes into git commits (version control)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import importlib
import sys
import time

from core.config import (
    MEMORY_BACKEND,
    MEMGIT_ROOT,
    MEMGIT_STORE_DIR,
    MEMGIT_ENV_KEY,
    MEMGIT_VERSION_KEY,
    MEMGIT_SKILLS_ITEM_ID,
    PROJECT_ROOT,
    _env_flag,
)
from core.utils.logging_utils import log_event


_L0_FILE = "l0_prompt.jsonl"
_L1_FILE = "l1_items.jsonl"
_L2_FILE = "l2_trajectory.jsonl"

_MEMGIT_AUTO_GIT_COMMIT = _env_flag("MEMGIT_AUTO_GIT_COMMIT", True)


def is_memgit_enabled() -> bool:
    return MEMORY_BACKEND == "memgit"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _item_id(prefix: str) -> str:
    ts = int(time.time() * 1000)
    return f"item_{prefix}_{ts}_{uuid4().hex[:8]}"


def _memory_file_for_type(item_type: str) -> Path:
    t = str(item_type or "").strip().lower()
    if t == "prompt":
        layer_file = _L0_FILE
    elif t == "trajectory":
        layer_file = _L2_FILE
    else:
        layer_file = _L1_FILE
    return (
        PROJECT_ROOT
        / MEMGIT_STORE_DIR
        / "memory"
        / MEMGIT_ENV_KEY
        / MEMGIT_VERSION_KEY
        / layer_file
    )


def _ensure_memgit_imports() -> tuple[Any, Any, Any, Any, Any] | None:
    root = Path(MEMGIT_ROOT).expanduser() if MEMGIT_ROOT else None
    if root and root.exists():
        root_text = str(root.resolve())
        if root_text not in sys.path:
            sys.path.insert(0, root_text)

    try:
        repo_service = importlib.import_module("memgit.services.repo_service")
        env_service = importlib.import_module("memgit.services.env_service")
        item_service = importlib.import_module("memgit.services.item_service")
        json_store = importlib.import_module("memgit.store.json_store")
        git_adapter = importlib.import_module("memgit.adapters.git_adapter")
    except Exception as exc:
        log_event("memgit_import_failed", error=str(exc), memgit_root=MEMGIT_ROOT)
        return None

    return repo_service, env_service, item_service, json_store, git_adapter


def _ensure_scope_ready(repo_service: Any, env_service: Any) -> bool:
    try:
        repo_service.init_repo(PROJECT_ROOT, store_dir=MEMGIT_STORE_DIR, init_git=True)
        current = env_service.get_current_scope(PROJECT_ROOT, store_dir=MEMGIT_STORE_DIR) or {}
        if not current.get("env_key") or not current.get("version_key"):
            env_service.set_current_scope(
                PROJECT_ROOT,
                env_key=MEMGIT_ENV_KEY,
                version_key=MEMGIT_VERSION_KEY,
                store_dir=MEMGIT_STORE_DIR,
            )
        return True
    except Exception as exc:
        log_event(
            "memgit_scope_init_failed",
            error=str(exc),
            env_key=MEMGIT_ENV_KEY,
            version_key=MEMGIT_VERSION_KEY,
        )
        return False


def _build_item(
    *,
    item_type: str,
    item_id: str,
    payload: dict[str, Any],
    write_reason: str,
    status: str = "candidate",
    prev: dict[str, Any] | None = None,
    decision_summary: str | None = None,
    source_context: dict[str, Any] | None = None,
    related_scopes: Any = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    t = str(item_type or "meta").strip().lower() or "meta"
    layer = "L1"
    if t == "prompt":
        layer = "L0"
    elif t == "trajectory":
        layer = "L2"

    prev = prev or {}
    created_at = prev.get("created_at") or _now_iso()
    return {
        "id": item_id,
        "env_key": MEMGIT_ENV_KEY,
        "version_key": MEMGIT_VERSION_KEY,
        "scope_binding_reason": f"Memento-S memory for {MEMGIT_ENV_KEY}/{MEMGIT_VERSION_KEY}",
        "layer": layer,
        "type": t,
        "payload": payload,
        "status": status,
        "write_reason": write_reason,
        "decision_summary": decision_summary,
        "evidence_refs": prev.get("evidence_refs") or [],
        "source_context": source_context,
        "related_scopes": related_scopes,
        "extensions": extensions,
        "created_at": created_at,
        "updated_at": _now_iso(),
    }


def _append_or_upsert_item(
    *,
    item_type: str,
    payload: dict[str, Any],
    write_reason: str,
    status: str = "candidate",
    item_id: str | None = None,
    decision_summary: str | None = None,
    source_context: dict[str, Any] | None = None,
    related_scopes: Any = None,
    extensions: dict[str, Any] | None = None,
    upsert: bool = False,
) -> str | None:
    if not is_memgit_enabled():
        return None

    modules = _ensure_memgit_imports()
    if modules is None:
        return None

    repo_service, env_service, _item_service, json_store, _git_adapter = modules
    if not _ensure_scope_ready(repo_service, env_service):
        return None

    target_id = str(item_id or "").strip() or _item_id(str(item_type or "meta"))

    try:
        memory_file = _memory_file_for_type(item_type)
        records = json_store.read_jsonl(memory_file)

        prev: dict[str, Any] | None = None
        replaced = False
        if upsert:
            for idx, rec in enumerate(records):
                if str(rec.get("id") or "").strip() == target_id:
                    prev = rec
                    records[idx] = _build_item(
                        item_type=item_type,
                        item_id=target_id,
                        payload=payload,
                        write_reason=write_reason,
                        status=status,
                        prev=rec,
                        decision_summary=decision_summary,
                        source_context=source_context,
                        related_scopes=related_scopes,
                        extensions=extensions,
                    )
                    replaced = True
                    break

        if not replaced:
            records.append(
                _build_item(
                    item_type=item_type,
                    item_id=target_id,
                    payload=payload,
                    write_reason=write_reason,
                    status=status,
                    prev=prev,
                    decision_summary=decision_summary,
                    source_context=source_context,
                    related_scopes=related_scopes,
                    extensions=extensions,
                )
            )

        json_store.write_jsonl_atomic(memory_file, records)
        return target_id
    except Exception as exc:
        log_event(
            "memgit_append_item_failed",
            error=str(exc),
            item_type=item_type,
            item_id=target_id,
        )
        return None


def load_skills_xml_from_memgit() -> str | None:
    if not is_memgit_enabled():
        return None

    modules = _ensure_memgit_imports()
    if modules is None:
        return None

    repo_service, env_service, item_service, _json_store, _git_adapter = modules
    if not _ensure_scope_ready(repo_service, env_service):
        return None

    try:
        items = item_service.list_items(
            PROJECT_ROOT,
            item_type="skill",
            env_key=MEMGIT_ENV_KEY,
            version_key=MEMGIT_VERSION_KEY,
            store_dir=MEMGIT_STORE_DIR,
        )
        for item in items:
            if str(item.get("id") or "").strip() != MEMGIT_SKILLS_ITEM_ID:
                continue
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            skills_xml = payload.get("skills_xml")
            if isinstance(skills_xml, str) and skills_xml.strip():
                return skills_xml
    except Exception as exc:
        log_event("memgit_read_skills_failed", error=str(exc), item_id=MEMGIT_SKILLS_ITEM_ID)

    return None


def upsert_skills_xml_to_memgit(skills_xml: str) -> bool:
    payload = {
        "skills_xml": str(skills_xml or ""),
        "skills_source": "memento-s",
    }
    item_id = _append_or_upsert_item(
        item_type="skill",
        item_id=MEMGIT_SKILLS_ITEM_ID,
        payload=payload,
        write_reason="Memento-S skill catalog update",
        status="stable",
        decision_summary="Synchronized available skills catalog.",
        extensions={"memory_kind": "skills_catalog"},
        upsert=True,
    )
    return bool(item_id)


def append_memgit_item(
    *,
    item_type: str,
    payload: dict[str, Any],
    write_reason: str,
    status: str = "candidate",
    decision_summary: str | None = None,
    source_context: dict[str, Any] | None = None,
    related_scopes: Any = None,
    extensions: dict[str, Any] | None = None,
) -> str | None:
    return _append_or_upsert_item(
        item_type=item_type,
        payload=payload,
        write_reason=write_reason,
        status=status,
        decision_summary=decision_summary,
        source_context=source_context,
        related_scopes=related_scopes,
        extensions=extensions,
        upsert=False,
    )


def record_workflow_step(
    *,
    user_text: str,
    step_num: int,
    skill_name: str,
    instruction: str,
    output: str,
) -> str | None:
    return append_memgit_item(
        item_type="trajectory",
        payload={
            "kind": "workflow_step",
            "user_text": str(user_text or ""),
            "step_num": int(step_num),
            "skill_name": str(skill_name or ""),
            "instruction": str(instruction or ""),
            "output": str(output or ""),
        },
        write_reason=f"Workflow step {int(step_num)} executed by skill {skill_name}",
        decision_summary="Captured execution trajectory for reflective learning.",
        status="candidate",
        extensions={"memory_kind": "workflow_step"},
    )


def record_reflection(
    *,
    user_text: str,
    step_num: int,
    skill_name: str,
    summarized_output: str,
) -> str | None:
    return append_memgit_item(
        item_type="meta",
        payload={
            "kind": "step_reflection",
            "user_text": str(user_text or ""),
            "step_num": int(step_num),
            "skill_name": str(skill_name or ""),
            "summary": str(summarized_output or ""),
        },
        write_reason=f"Reflective summary for step {int(step_num)} ({skill_name})",
        decision_summary="Saved compressed reflection to guide next routing decisions.",
        status="candidate",
        extensions={"memory_kind": "step_reflection"},
    )


def record_skill_event(
    *,
    event: str,
    skill_name: str,
    detail: str,
    step_num: int | None = None,
) -> str | None:
    payload: dict[str, Any] = {
        "kind": "skill_event",
        "event": str(event or "").strip(),
        "skill_name": str(skill_name or "").strip(),
        "detail": str(detail or "").strip(),
    }
    if step_num is not None:
        payload["step_num"] = int(step_num)
    return append_memgit_item(
        item_type="skill",
        payload=payload,
        write_reason=f"Skill lifecycle event: {payload['event']} ({payload['skill_name']})",
        decision_summary="Recorded skill evolution event.",
        status="candidate",
        extensions={"memory_kind": "skill_event"},
    )


def record_turn(
    *,
    user_text: str,
    assistant_text: str,
    interrupted: bool,
    turn_index: int,
    session_id: str,
) -> str | None:
    return append_memgit_item(
        item_type="trajectory",
        payload={
            "kind": "turn",
            "turn_index": int(turn_index),
            "session_id": str(session_id or "").strip(),
            "user_text": str(user_text or ""),
            "assistant_text": str(assistant_text or ""),
            "interrupted": bool(interrupted),
        },
        write_reason=f"Persisted conversational turn {int(turn_index)}",
        decision_summary="Stored turn-level interaction trajectory.",
        status="candidate",
        extensions={"memory_kind": "turn"},
    )


def commit_memgit_changes(message: str) -> tuple[bool, str]:
    if not is_memgit_enabled():
        return False, "memgit_backend_disabled"
    if not _MEMGIT_AUTO_GIT_COMMIT:
        return False, "memgit_auto_git_commit_disabled"

    modules = _ensure_memgit_imports()
    if modules is None:
        return False, "memgit_import_failed"

    repo_service, env_service, _item_service, _json_store, git_adapter = modules
    if not _ensure_scope_ready(repo_service, env_service):
        return False, "memgit_scope_init_failed"

    try:
        commit_hash = git_adapter.commit_paths(
            PROJECT_ROOT,
            paths=[MEMGIT_STORE_DIR],
            message=str(message or "memgit memory update"),
        )
        if commit_hash:
            return True, commit_hash
        return True, "no_changes"
    except Exception as exc:
        log_event("memgit_git_commit_failed", error=str(exc), message=message)
        return False, str(exc)
