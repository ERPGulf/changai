"""Scheduling for ChangAI's schema and master data rebuilds.

Kept free of heavy imports (torch, FAISS, LLM SDKs) so the scheduler, after_migrate and
the Settings buttons can import it without loading models into their process. The stage
functions are referenced by dotted path and only imported inside the background job.
"""
import gc
import logging
import os
import resource
import sys
import time
from contextlib import contextmanager
from typing import Dict, Optional, Tuple

import frappe
import psutil
from frappe import _
from frappe.utils.background_jobs import is_job_enqueued

SETTINGS = "ChangAI Settings"
RAG_FOLDER = "Home/RAG Sources"
SCHEMA_RAG_FILES = ("schema.yaml", "tables.json", "reports.json")
MASTERDATA_RAG_FILES = ("master_data.yaml",)

# One job per stage. Each queues the next only when it succeeds, so a failure stops the
# chain, and each stage is killed on its own timeout instead of one 4-hour budget.
SCHEMA_STAGES = [
    ("sync", "changai.changai.api.v2.auto_gen_api.sync_tables_and_schema_smart", 1800),
    ("descriptions", "changai.changai.api.v2.auto_gen_api.fill_missing_field_descriptions", 7200),
    ("sqlglot", "changai.changai.api.v2.schema_utils.convert_yaml_schema_to_sqlglot_meta", 900),
    ("table_faiss", "changai.changai.api.v2.build_cards_faiss_index_v2.build_table_fvs_job", 1800),
    ("schema_faiss", "changai.changai.api.v2.build_cards_faiss_index_v2.build_schema_fvs_job", 3600),
]
SCHEMA_JOB_ID = "changai_full_schema_rebuild"
MASTERDATA_JOB_ID = "changai_masterdata_sync"
MASTERDATA_TIMEOUT = 1800


# --- logging and memory ---------------------------------------------------------------

def _logger():
    """logs/changai.log at INFO. Frappe's default level (ERROR in production) would drop
    the stage timing and memory lines."""
    log = frappe.logger("changai")
    log.setLevel(logging.INFO)
    return log


def _memory_mb() -> Tuple[float, float]:
    """Current RSS and this process's peak RSS, in MB (ru_maxrss is KB on Linux)."""
    rss = psutil.Process().memory_info().rss / 1048576
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return rss, peak


@contextmanager
def log_stage(name: str):
    """Log start and end of a stage with elapsed time and memory to logs/changai.log."""
    log = _logger()
    start = time.monotonic()
    log.info(f"[{name}] start rss={_memory_mb()[0]:.0f}MB")
    try:
        yield
    except Exception:
        rss, peak = _memory_mb()
        log.error(f"[{name}] failed after {time.monotonic() - start:.1f}s rss={rss:.0f}MB peak={peak:.0f}MB")
        raise
    rss, peak = _memory_mb()
    log.info(f"[{name}] end {time.monotonic() - start:.1f}s rss={rss:.0f}MB peak={peak:.0f}MB")


def release_models() -> None:
    """Drop the embedding model and vector stores a job loaded, so it ends holding nothing."""
    retrieve = sys.modules.get("changai.changai.api.v2.retrieve")
    if retrieve:
        for name in ("_EMBEDDER_INSTANCE", "_VS_TABLE", "_VS_REPORT", "_VS_MASTER", "_FULL_FIELDS_VS",
                     "_FIELD_DOCS_CACHE", "_FIELD_EMBS_CACHE", "_TABLE_TO_IDX_CACHE"):
            setattr(retrieve, name, None)
    gc.collect()


# --- prerequisites --------------------------------------------------------------------

def missing_prerequisites(rag_files) -> Optional[str]:
    """Why a rebuild can't run on this site yet, or None when it can."""
    # Same path as retrieve._get_model_path(); not imported to keep this module light
    model_path = frappe.get_site_path("private", "files", "changai_model")
    if not os.path.isfile(os.path.join(model_path, "config.json")):
        return _("The embedding model isn't downloaded yet. Click Download Embedding Model in ChangAI Settings first.")
    existing = set(frappe.get_all("File", filters={"folder": RAG_FOLDER, "file_name": ["in", list(rag_files)]}, pluck="file_name"))
    missing = [f for f in rag_files if f not in existing]
    if missing:
        return _("ChangAI's source files are missing from {0}: {1}").format(RAG_FOLDER, ", ".join(missing))
    return None


# --- schema rebuild -------------------------------------------------------------------

def _schema_stage_job_id(stage: int) -> str:
    return SCHEMA_JOB_ID if stage == 0 else f"{SCHEMA_JOB_ID}::{SCHEMA_STAGES[stage][0]}"


def schema_rebuild_running() -> bool:
    return any(is_job_enqueued(_schema_stage_job_id(i)) for i in range(len(SCHEMA_STAGES)))


def _enqueue_schema_stage(stage: int) -> None:
    frappe.enqueue(
        "changai.changai.api.v2.rebuild_jobs.run_schema_stage",
        queue="long",
        timeout=SCHEMA_STAGES[stage][2],
        job_id=_schema_stage_job_id(stage),
        deduplicate=True,
        # A chained stage reads files the previous one wrote, so it waits for that commit.
        # The first stage is queued at once so a second click sees it and is refused.
        enqueue_after_commit=stage > 0,
        stage=stage,
    )


def schedule_schema_rebuild() -> Tuple[bool, str]:
    reason = missing_prerequisites(SCHEMA_RAG_FILES)
    if reason:
        _logger().warning(f"[schema] rebuild not queued: {reason}")
        return False, reason
    if schema_rebuild_running():
        return False, _("A schema rebuild is already running.")
    _enqueue_schema_stage(0)
    return True, _("Schema rebuild started in the background.")


def schedule_index_rebuild() -> Tuple[bool, str]:
    """Rebuild only the FAISS indexes (table, then schema) from the current RAG files."""
    reason = missing_prerequisites(SCHEMA_RAG_FILES)
    if reason:
        _logger().warning(f"[schema] index rebuild not queued: {reason}")
        return False, reason
    if schema_rebuild_running():
        return False, _("A schema rebuild is already running.")
    _enqueue_schema_stage(_stage_index("table_faiss"))
    return True, _("Index rebuild started in the background.")


def _stage_index(name: str) -> int:
    return next(i for i, stage in enumerate(SCHEMA_STAGES) if stage[0] == name)


def run_schema_stage(stage: int = 0) -> None:
    name, method, _timeout = SCHEMA_STAGES[stage]
    try:
        with log_stage(f"schema:{name}"):
            result = frappe.get_attr(method)()
    finally:
        release_models()
    if isinstance(result, dict) and result.get("ok") is False:
        frappe.log_error(title=f"ChangAI schema rebuild stopped at '{name}'", message=frappe.as_json(result))
        return
    if stage + 1 < len(SCHEMA_STAGES):
        _enqueue_schema_stage(stage + 1)
    else:
        frappe.db.set_single_value(SETTINGS, "schema_rebuild_pending", 0)
        _logger().info("[schema] rebuild complete")


# --- master data sync -----------------------------------------------------------------

def masterdata_sync_running() -> bool:
    return is_job_enqueued(MASTERDATA_JOB_ID)


def schedule_masterdata_sync() -> Tuple[bool, str]:
    reason = missing_prerequisites(MASTERDATA_RAG_FILES)
    if reason:
        _logger().warning(f"[masterdata] sync not queued: {reason}")
        return False, reason
    if masterdata_sync_running():
        return False, _("A master data sync is already running.")
    frappe.enqueue(
        "changai.changai.api.v2.rebuild_jobs.run_masterdata_sync",
        queue="long",
        timeout=MASTERDATA_TIMEOUT,
        job_id=MASTERDATA_JOB_ID,
        deduplicate=True,
    )
    return True, _("Master data sync started in the background.")


def run_masterdata_sync() -> None:
    from changai.changai.api.v2.auto_gen_api import sync_master_data_smart
    from changai.changai.api.v2.build_cards_faiss_index_v2 import build_master_data_fvs_job

    try:
        with log_stage("masterdata:sync"):
            sync_master_data_smart()
        with log_stage("masterdata:faiss"):
            build_master_data_fvs_job()
    finally:
        release_models()


# --- hooks and buttons ----------------------------------------------------------------

def mark_schema_rebuild_pending() -> None:
    """after_migrate: migrations can change DocTypes. Flag a rebuild for the 03:00 job
    instead of running one inside migrate."""
    frappe.db.set_single_value(SETTINGS, "schema_rebuild_pending", 1)


def nightly_sync() -> None:
    """03:00 scheduler job: rebuild only what is pending or out of date."""
    from changai.changai.api.v2.schema_utils import check_file_updates

    schema = check_file_updates("schema.yaml")
    if frappe.db.get_single_value(SETTINGS, "schema_rebuild_pending") or schema.get("is_stale") or not schema.get("data"):
        schedule_schema_rebuild()
    masterdata = check_file_updates("master_data.yaml")
    if masterdata.get("is_stale") or not masterdata.get("data"):
        schedule_masterdata_sync()


@frappe.whitelist()
def rebuild_schema_from_ui() -> Dict[str, object]:
    frappe.has_permission(SETTINGS, "write", throw=True)
    started, message = schedule_schema_rebuild()
    return {"ok": started, "message": message}


@frappe.whitelist()
def sync_masterdata_from_ui() -> Dict[str, object]:
    frappe.has_permission(SETTINGS, "write", throw=True)
    started, message = schedule_masterdata_sync()
    return {"ok": started, "message": message}
