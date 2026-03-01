"""MemGit bridge for skill catalog storage.

This module keeps Memento-S decoupled from MemGit package installation details.
It lazily imports MemGit from `MEMGIT_ROOT` and provides read/write helpers for
skills catalog XML stored as an L1 `skill` item.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import importlib
import sys

from core.config import (
    MEMORY_BACKEND,
    MEMGIT_ROOT,
    MEMGIT_STORE_DIR,
    MEMGIT_ENV_KEY,
    MEMGIT_VERSION_KEY,
    MEMGIT_SKILLS_ITEM_ID,
    PROJECT_ROOT,
)
from core.utils.logging_utils import log_event


_L1_FILE = "l1_items.jsonl"


def is_memgit_enabled() -> bool:
    return MEMORY_BACKEND == "memgit"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _memgit_memory_file() -> Path:
    return (
        PROJECT_ROOT
        / MEMGIT_STORE_DIR
        / "memory"
        / MEMGIT_ENV_KEY
        / MEMGIT_VERSION_KEY
        / _L1_FILE
    )


def _ensure_memgit_imports() -> tuple[Any, Any, Any, Any] | None:
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
    except Exception as exc:
        log_event("memgit_import_failed", error=str(exc), memgit_root=MEMGIT_ROOT)
        return None

    return repo_service, env_service, item_service, json_store


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


def load_skills_xml_from_memgit() -> str | None:
    if not is_memgit_enabled():
        return None

    modules = _ensure_memgit_imports()
    if modules is None:
        return None

    repo_service, env_service, item_service, _json_store = modules
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


def _build_skills_item(skills_xml: str, prev: dict[str, Any] | None = None) -> dict[str, Any]:
    prev = prev or {}
    created_at = prev.get("created_at") or _now_iso()
    return {
        "id": MEMGIT_SKILLS_ITEM_ID,
        "env_key": MEMGIT_ENV_KEY,
        "version_key": MEMGIT_VERSION_KEY,
        "scope_binding_reason": f"Skills catalog for {MEMGIT_ENV_KEY}/{MEMGIT_VERSION_KEY}",
        "layer": "L1",
        "type": "skill",
        "payload": {
            "skills_xml": skills_xml,
            "skills_source": "memento-s",
        },
        "status": "stable",
        "write_reason": "Memento-S skill catalog update",
        "decision_summary": None,
        "evidence_refs": [],
        "source_context": None,
        "related_scopes": None,
        "extensions": None,
        "created_at": created_at,
        "updated_at": _now_iso(),
    }


def upsert_skills_xml_to_memgit(skills_xml: str) -> bool:
    if not is_memgit_enabled():
        return False

    modules = _ensure_memgit_imports()
    if modules is None:
        return False

    repo_service, env_service, _item_service, json_store = modules
    if not _ensure_scope_ready(repo_service, env_service):
        return False

    try:
        memory_file = _memgit_memory_file()
        records = json_store.read_jsonl(memory_file)
        prev: dict[str, Any] | None = None
        updated = False
        for idx, rec in enumerate(records):
            if str(rec.get("id") or "").strip() == MEMGIT_SKILLS_ITEM_ID:
                prev = rec
                records[idx] = _build_skills_item(skills_xml, prev=rec)
                updated = True
                break
        if not updated:
            records.append(_build_skills_item(skills_xml, prev=prev))
        json_store.write_jsonl_atomic(memory_file, records)
        return True
    except Exception as exc:
        log_event("memgit_write_skills_failed", error=str(exc), item_id=MEMGIT_SKILLS_ITEM_ID)
        return False
