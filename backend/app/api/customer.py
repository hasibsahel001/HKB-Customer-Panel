import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit
from app.auth.deps import AuthContext, client_ip, require_permission
from app.auth.permissions import Permission, has_permission
from app.auth.ratelimit import check_limiter
from app.core.config import settings
from app.core.errors import ConnectionFailed, InvalidInput
from app.db import get_db
from app.recent import list_recent, record_recent
from app.services.diagnostics import diagnose
from app.services.filtering import drop_infrastructure_devices, hide_findings
from app.services.live import collect_live
from app.services.live_devices import DEVICE_SESSIONS
from app.services.snapshot import collect_snapshot

log = logging.getLogger("hkb.api")

router = APIRouter(prefix="/api/customer", tags=["customer"])

check_permission = require_permission(Permission.CUSTOMER_CHECK)


class CheckRequest(BaseModel):
    ip: str = Field(max_length=64)
    tid: str = Field(max_length=32)


def strip_debug(report: dict) -> dict:
    for section in (report.get("sections") or {}).values():
        section.pop("error_type", None)
        section.pop("error_detail", None)
        data = section.get("data")
        if isinstance(data, dict):
            data.pop("skipped_reasons", None)
            for key in [k for k in data if k.startswith("debug_")]:
                data.pop(key)
    findings = (report.get("diagnostics") or {}).get("findings") or []
    for finding in findings:
        evidence = finding.get("evidence")
        if isinstance(evidence, dict):
            evidence.pop("reason", None)
    return report


def _build_report(ip: str, tid: str) -> dict:
    snapshot = collect_snapshot(ip, tid)
    try:
        drop_infrastructure_devices(snapshot)
    except Exception as exc:
        log.warning("device filtering failed: %s", type(exc).__name__)
    try:
        snapshot["diagnostics"] = hide_findings(diagnose(snapshot))
    except Exception as exc:
        log.warning("diagnostics failed: %s", type(exc).__name__)
        snapshot["diagnostics"] = {
            "overall": "unknown",
            "count": 0,
            "findings": [],
            "error": "diagnostics_failed",
        }
    return snapshot


def _to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidInput):
        return HTTPException(status_code=422, detail={"code": "invalid_input", "message": str(exc)})
    if isinstance(exc, ConnectionFailed):
        reasons = sorted({attempt.kind.value for attempt in exc.attempts})
        return HTTPException(
            status_code=502,
            detail={
                "code": "router_unreachable",
                "message": "Could not connect to the customer router",
                "reasons": reasons,
            },
        )
    return HTTPException(
        status_code=504, detail={"code": "timeout", "message": "The check took too long"}
    )


def _audit_details(exc: Exception) -> dict:
    if isinstance(exc, InvalidInput):
        return {"error": "invalid_input"}
    if isinstance(exc, ConnectionFailed):
        return {
            "error": "router_unreachable",
            "reasons": sorted({a.kind.value for a in exc.attempts}),
        }
    return {"error": "timeout"}


def _rate_limit(auth: AuthContext, name: str, per_minute: int) -> None:
    key = f"{name}:{auth.user.id}"
    if check_limiter.blocked(key, per_minute, 60):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many checks. Wait a moment."},
        )
    check_limiter.record(key)


@router.post("/check")
async def check_customer(
    req: CheckRequest,
    request: Request,
    auth: AuthContext = Depends(check_permission),
    db: Session = Depends(get_db),
):
    ip_addr = client_ip(request)
    target = f"{req.ip.strip()}/{req.tid.strip()}"
    _rate_limit(auth, "check", settings.customer_checks_per_minute)

    async def log_audit(success: bool, details: dict):
        await run_in_threadpool(
            audit.record,
            db,
            "customer.check",
            user=auth.user,
            ip=ip_addr,
            success=success,
            target=target,
            details=details,
        )

    try:
        report = await asyncio.wait_for(
            run_in_threadpool(_build_report, req.ip, req.tid), timeout=60
        )
    except (InvalidInput, ConnectionFailed, asyncio.TimeoutError) as exc:
        await log_audit(False, _audit_details(exc))
        raise _to_http(exc)

    timings = report.get("timings_ms") or {}
    log.info(
        "check %s connect=%sms total=%sms attempts=%s account=%s by=%s",
        target,
        timings.get("connect"),
        timings.get("total"),
        report.get("connect_attempts"),
        report.get("connected_with_account"),
        auth.user.username,
    )

    await log_audit(
        True,
        {
            "account_index": report.get("connected_with_account"),
            "api_port": report.get("api_port"),
            "overall": (report.get("diagnostics") or {}).get("overall"),
        },
    )
    try:
        await run_in_threadpool(record_recent, db, auth.user, report)
    except Exception as exc:
        log.warning("recent list update failed: %s", type(exc).__name__)

    if not has_permission(auth.user.role, Permission.DEBUG_VIEW):
        strip_debug(report)
    return report


@router.post("/live")
async def live_customer(
    req: CheckRequest,
    auth: AuthContext = Depends(check_permission),
):
    _rate_limit(auth, "live", settings.customer_checks_per_minute * 2)
    try:
        result = await asyncio.wait_for(
            run_in_threadpool(collect_live, req.ip, req.tid), timeout=40
        )
    except (InvalidInput, ConnectionFailed, asyncio.TimeoutError) as exc:
        raise _to_http(exc)

    result["diagnostics"] = hide_findings(result["diagnostics"])
    if not has_permission(auth.user.role, Permission.DEBUG_VIEW):
        strip_debug(
            {
                "sections": {"ping": result["ping"], "ap_probe": result["ap_probe"]},
                "diagnostics": result["diagnostics"],
            }
        )
    return result


@router.post("/devices")
async def live_devices(
    req: CheckRequest,
    auth: AuthContext = Depends(check_permission),
):
    """The online devices only, cheap enough to ask for about once a second."""
    _rate_limit(auth, "devices", settings.device_polls_per_minute)
    try:
        return await asyncio.wait_for(
            run_in_threadpool(DEVICE_SESSIONS.read, req.ip, req.tid), timeout=20
        )
    except (InvalidInput, ConnectionFailed, asyncio.TimeoutError) as exc:
        raise _to_http(exc)


@router.get("/recent")
def recent_customers(
    q: str = Query(default="", max_length=64),
    auth: AuthContext = Depends(check_permission),
    db: Session = Depends(get_db),
):
    return {"items": list_recent(db, auth.user, q)}