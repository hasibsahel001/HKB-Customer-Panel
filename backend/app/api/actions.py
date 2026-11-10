import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from librouteros import exceptions as ros_exc
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import audit
from app.auth.deps import AuthContext, client_ip, require_permission
from app.auth.permissions import Permission, has_permission
from app.auth.ratelimit import check_limiter
from app.core.config import settings
from app.core.errors import ConnectionFailed, InvalidInput
from app.db import SessionLocal, get_db
from app.devices.customer_router import make_connector
from app.devices.validation import validate_target_ip, validate_tid
from app.models import User
from app.services import router_actions as ra
from app.services.network_parsing import is_active_arp
from app.services.snapshot import rows
from app.services.limit_jobs import TIMERS, make_clear_job
from app.services.update_jobs import JOBS, JobBusy, start_job_thread
from app.services.usage import DEFAULT_SECONDS, sample_usage
from app.services.windows_vpn import VpnSetupFailed, apply_pptp

log = logging.getLogger("hkb.actions")

router = APIRouter(prefix="/api/router", tags=["router actions"])

manage = require_permission(Permission.ROUTER_MANAGE)
update_perm = require_permission(Permission.ROUTER_UPDATE)
view = require_permission(Permission.CUSTOMER_CHECK)


class Target(BaseModel):
    ip: str = Field(max_length=64)
    tid: str = Field(max_length=32)


class QueueSave(Target):
    id: str | None = Field(default=None, max_length=16)
    name: str = Field(max_length=100)
    targets: list[str] = Field(max_length=100)
    max_up: str = Field(max_length=16)
    max_down: str = Field(max_length=16)
    disabled: bool = False


class QueueDelete(Target):
    ids: list[str] = Field(min_length=1, max_length=200)


class DeleteAll(Target):
    confirm: str = Field(max_length=32)


class Reboot(Target):
    confirm: bool = False


class UpdateStart(Target):
    mode: Literal["now", "later"]
    firmware: bool = True


class FirmwareUpgrade(Target):
    reboot: bool = False


class UsageRequest(Target):
    seconds: int = Field(default=DEFAULT_SECONDS, ge=3, le=30)


class ApAccess(Target):
    pass


class VpnLocal(BaseModel):
    ip: str = Field(max_length=64)  # the customer's PPPoE IP, the VPN server address
    ap_ip: str = Field(max_length=64)


class DnsSave(Target):
    servers: list[str] = Field(default_factory=list, max_length=4)
    allow_remote_requests: bool


def _rate_limit(auth: AuthContext) -> None:
    key = f"act:{auth.user.id}"
    if check_limiter.blocked(key, settings.actions_per_minute, 60):
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many actions. Wait a moment."},
        )
    check_limiter.record(key)


def _with_long_api(conn, fn, timeout):
    api = conn.open_additional(timeout)
    try:
        return fn(api)
    finally:
        try:
            api.close()
        except Exception:
            pass


async def _execute(req: Target, request: Request, auth: AuthContext, db: Session, action, work, details, audited=True):
    _rate_limit(auth)
    target = f"{req.ip.strip()}/{req.tid.strip()}"

    def job():
        conn = make_connector(req.ip, req.tid)
        conn.connect()
        try:
            return work(conn)
        except ros_exc.TrapError as exc:
            raise ra.RouterCommandFailed(str(exc)[:200]) from exc
        finally:
            conn.close()

    async def log_audit(success: bool, extra: dict):
        if audited:
            await run_in_threadpool(
                audit.record,
                db,
                action,
                user=auth.user,
                ip=client_ip(request),
                success=success,
                target=target,
                details={**details, **extra},
            )

    try:
        result = await asyncio.wait_for(run_in_threadpool(job), timeout=45)
    except InvalidInput as exc:
        await log_audit(False, {"error": "invalid_input"})
        raise HTTPException(status_code=422, detail={"code": "invalid_input", "message": str(exc)})
    except ConnectionFailed as exc:
        reasons = sorted({a.kind.value for a in exc.attempts})
        await log_audit(False, {"error": "router_unreachable", "reasons": reasons})
        raise HTTPException(
            status_code=502,
            detail={
                "code": "router_unreachable",
                "message": "Could not connect to the customer router",
                "reasons": reasons,
            },
        )
    except ra.RouterCommandFailed as exc:
        await log_audit(False, {"error": "router_command_failed"})
        raise HTTPException(
            status_code=502,
            detail={"code": "router_command_failed", "message": f"The router rejected the command: {exc}"},
        )
    except asyncio.TimeoutError:
        await log_audit(False, {"error": "timeout"})
        raise HTTPException(status_code=504, detail={"code": "timeout", "message": "The action took too long"})

    await log_audit(True, {})
    return result


# ---------------------------------------------------------------- queues


@router.post("/queues/list")
async def queues_list(req: Target, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    def work(conn):
        ips = [conn.ip] + [r.get("address") for r in rows(conn.api, "ip", "arp") if is_active_arp(r)]
        return {"queues": ra.list_all_queues(conn.api, ips)}

    return await _execute(req, request, auth, db, "router.queues_view", work, {}, audited=False)


@router.post("/queues/save")
async def queues_save(req: QueueSave, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    name = ra.validate_name(req.name)
    targets = ra.normalize_targets(req.targets)
    up, down = ra.normalize_rate(req.max_up), ra.normalize_rate(req.max_down)

    def work(conn):
        qid = ra.save_queue(
            conn.api,
            queue_id=req.id,
            name=name,
            targets=targets,
            max_up=up,
            max_down=down,
            disabled=req.disabled,
        )
        return {"id": qid}

    details = {
        "queue": name,
        "queue_id": req.id,
        "targets": ",".join(targets)[:200],
        "max_limit": f"{up}/{down}",
        "disabled": req.disabled,
    }
    return await _execute(req, request, auth, db, "router.queue_saved", work, details)


@router.post("/queues/delete")
async def queues_delete(req: QueueDelete, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    ids = ra.validate_ids(req.ids)
    return await _execute(
        req, request, auth, db, "router.queue_deleted",
        lambda conn: {"deleted": ra.delete_queues(conn.api, ids)},
        {"ids": ",".join(ids)[:200]},
    )


@router.post("/queues/delete-all")
async def queues_delete_all(req: DeleteAll, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    if req.confirm != ra.DELETE_ALL_PHRASE:
        raise HTTPException(
            status_code=422,
            detail={"code": "confirmation_required", "message": f"Type {ra.DELETE_ALL_PHRASE} to confirm"},
        )
    return await _execute(
        req, request, auth, db, "router.queues_deleted_all",
        lambda conn: {"deleted": ra.delete_all_queues(conn.api)},
        {},
    )


# ---------------------------------------------------------------- reboot


@router.post("/reboot")
async def reboot(req: Reboot, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    if not req.confirm:
        raise HTTPException(
            status_code=422,
            detail={"code": "confirmation_required", "message": "The reboot must be confirmed"},
        )

    def work(conn):
        ra.send_reboot(conn.api)
        return {"status": "reboot_command_sent"}

    return await _execute(req, request, auth, db, "router.reboot", work, {})


# ---------------------------------------------------------------- usage sample (bandwidth report)


@router.post("/usage-sample")
async def usage_sample(req: UsageRequest, request: Request, auth: AuthContext = Depends(view), db: Session = Depends(get_db)):
    return await _execute(
        req, request, auth, db, "router.usage_sample",
        lambda conn: sample_usage(conn.api, req.seconds),
        {},
        audited=False,
    )


# ---------------------------------------------------------------- RouterOS update and firmware


@router.post("/update/check")
async def update_check(req: Target, request: Request, auth: AuthContext = Depends(update_perm), db: Session = Depends(get_db)):
    return await _execute(
        req, request, auth, db, "router.update_checked",
        lambda conn: _with_long_api(conn, ra.check_updates, 30.0),
        {},
    )


@router.post("/update/start", status_code=202)
async def update_start(req: UpdateStart, request: Request, auth: AuthContext = Depends(update_perm), db: Session = Depends(get_db)):
    ip = validate_target_ip(req.ip)
    tid = validate_tid(req.tid)
    _rate_limit(auth)
    try:
        job = JOBS.create(user_id=auth.user.id, ip=ip, tid=tid, mode=req.mode, firmware=req.firmware)
    except JobBusy:
        raise HTTPException(
            status_code=409,
            detail={"code": "update_in_progress", "message": "An update is already running for this router"},
        )
    await run_in_threadpool(
        audit.record,
        db,
        "router.update_started",
        user=auth.user,
        ip=client_ip(request),
        target=f"{ip}/{tid}",
        details={"mode": req.mode, "firmware": req.firmware},
    )
    start_job_thread(job, make_connector, on_finish=_audit_finished)
    return {"job_id": job.id}


def _audit_finished(job) -> None:
    db = SessionLocal()
    try:
        user = db.get(User, job.user_id)
        audit.record(
            db,
            "router.update_finished",
            user=user,
            success=job.state == "done",
            target=f"{job.ip}/{job.tid}",
            details={"mode": job.mode, "firmware": job.firmware, "message": (job.message or "")[:150]},
        )
    finally:
        db.close()


@router.get("/update/jobs/{job_id}")
def update_job(job_id: str, auth: AuthContext = Depends(update_perm)):
    job = JOBS.get(job_id)
    allowed = job is not None and (
        job.user_id == auth.user.id or has_permission(auth.user.role, Permission.USERS_MANAGE)
    )
    if not allowed:
        raise HTTPException(status_code=404, detail={"code": "job_not_found", "message": "Job not found"})
    return job.to_dict()


@router.post("/firmware/upgrade")
async def firmware_upgrade(req: FirmwareUpgrade, request: Request, auth: AuthContext = Depends(update_perm), db: Session = Depends(get_db)):
    def work(conn):
        info = ra.upgrade_firmware(conn.api)
        if req.reboot:
            ra.send_reboot(conn.api)
        return {
            "upgraded": True,
            "rebooting": req.reboot,
            "from_version": info["current"],
            "to_version": info["upgrade"],
        }

    return await _execute(req, request, auth, db, "router.firmware_upgraded", work, {"reboot": req.reboot})


# ---------------------------------------------------------------- customer AP access (NAT / local VPN)


@router.post("/manage/nat-enter")
async def nat_enter(req: ApAccess, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    def work(conn):
        ap_ip = ra.find_customer_ap_ip(conn.api, settings.ap_probe_peers)
        if ap_ip is None:
            raise InvalidInput("None of the customer's access point addresses answered")
        state = ra.ensure_nat_rule(conn.api, ap_ip)
        return {
            "pppoe_ip": conn.ip,
            "ap_ip": ap_ip,
            "port": ra.NAT_PORT,
            "rule_added": state == "added",
            "rule_state": state,
        }

    return await _execute(req, request, auth, db, "router.nat_entered", work, {})


@router.post("/manage/vpn-enter")
async def vpn_enter(req: ApAccess, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    def work(conn):
        ap_ip = ra.find_customer_ap_ip(conn.api, settings.ap_probe_peers)
        if ap_ip is None:
            raise InvalidInput("None of the customer's access point addresses answered")
        ra.ensure_pptp_access(conn.api)
        return {"pppoe_ip": conn.ip, "ap_ip": ap_ip}

    return await _execute(req, request, auth, db, "router.vpn_entered", work, {})


@router.post("/manage/vpn-connect")
async def vpn_connect(req: VpnLocal, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    """Points the Windows VPN entry of the panel PC at this customer and connects it."""
    _rate_limit(auth)
    target = req.ip.strip()

    async def log_audit(success: bool, extra: dict):
        await run_in_threadpool(
            audit.record, db, "router.vpn_connected", user=auth.user, ip=client_ip(request),
            success=success, target=target, details=extra,
        )

    try:
        server = validate_target_ip(req.ip)
        result = await asyncio.wait_for(
            run_in_threadpool(lambda: apply_pptp(server, req.ap_ip.strip(), connect=settings.vpn_auto_connect)),
            timeout=75,
        )
    except InvalidInput as exc:
        await log_audit(False, {"error": "invalid_input"})
        raise HTTPException(status_code=422, detail={"code": "invalid_input", "message": str(exc)})
    except VpnSetupFailed as exc:
        await log_audit(False, {"error": "vpn_setup_failed"})
        raise HTTPException(status_code=502, detail={"code": "vpn_setup_failed", "message": str(exc)})
    except asyncio.TimeoutError:
        await log_audit(False, {"error": "timeout"})
        raise HTTPException(status_code=504, detail={"code": "timeout", "message": "The VPN setup took too long"})
    await log_audit(True, {"state": result.get("state"), "connected": result.get("connected")})
    return result


# ---------------------------------------------------------------- limit user (temporary queues)


@router.post("/manage/limit-user")
async def limit_user(req: Target, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    seconds = settings.limit_user_seconds

    def work(conn):
        result = ra.apply_limit_user(
            conn.api,
            allow_targets=[f"{peer}/32" for peer in settings.ap_probe_peers],
            allow_rate=settings.limit_allow_rate,
            block_target=settings.limit_block_target,
            block_rate=settings.limit_block_rate,
            backup_seconds=seconds + 30,
        )
        return {**result, "seconds": seconds}

    result = await _execute(req, request, auth, db, "router.limit_user", work, {"seconds": seconds})
    ip, tid = req.ip.strip(), req.tid.strip()
    TIMERS.schedule(f"{ip}/{tid}", seconds, make_clear_job(ip, tid, auth.user.id))
    return result


@router.post("/manage/limit-user/clear")
async def limit_user_clear(req: Target, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    result = await _execute(
        req, request, auth, db, "router.limit_user_released",
        lambda conn: {"removed": ra.clear_limit_user(conn.api)},
        {},
    )
    TIMERS.cancel(f"{req.ip.strip()}/{req.tid.strip()}")
    return result


# ---------------------------------------------------------------- DNS settings


@router.post("/dns/get")
async def dns_get(req: Target, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    return await _execute(
        req, request, auth, db, "router.dns_viewed",
        lambda conn: ra.read_dns(conn.api),
        {},
        audited=False,
    )


@router.post("/dns/save")
async def dns_save(req: DnsSave, request: Request, auth: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    servers = req.servers

    def work(conn):
        return ra.save_dns(conn.api, servers, req.allow_remote_requests)

    return await _execute(
        req, request, auth, db, "router.dns_saved", work,
        {"servers": ",".join(servers)[:200], "allow_remote_requests": req.allow_remote_requests},
    )