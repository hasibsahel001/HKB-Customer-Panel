import logging
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from librouteros import exceptions as ros_exc

from app.core.errors import ConnectionFailed, InvalidInput
from app.services import router_actions as ra

log = logging.getLogger("hkb.update")

LONG_TIMEOUT = 60.0      # read timeout for the update check and download
KEEP_SECONDS = 6 * 3600  # finished jobs stay visible for a while


class JobBusy(Exception):
    """An update is already running for this router."""


@dataclass
class Job:
    id: str
    user_id: int
    ip: str
    tid: str
    mode: str
    firmware: bool
    state: str = "running"
    message: str | None = None
    steps: list = field(default_factory=list)
    result: dict = field(default_factory=dict)
    created: float = field(default_factory=time.time)

    def step(self, text: str) -> None:
        self.steps.append({"at": datetime.now(timezone.utc).isoformat(), "text": text})

    def finish(self, message: str) -> None:
        self.state = "done"
        self.message = message

    def fail(self, message: str) -> None:
        self.state = "failed"
        self.message = message

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "mode": self.mode,
            "firmware": self.firmware,
            "message": self.message,
            "steps": list(self.steps),
            "result": dict(self.result),
        }


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, *, user_id: int, ip: str, tid: str, mode: str, firmware: bool) -> Job:
        with self._lock:
            now = time.time()
            for job_id in [j for j, job in self._jobs.items() if now - job.created > KEEP_SECONDS]:
                del self._jobs[job_id]
            if any(job.ip == ip and job.state == "running" for job in self._jobs.values()):
                raise JobBusy()
            job = Job(id=uuid.uuid4().hex, user_id=user_id, ip=ip, tid=tid, mode=mode, firmware=firmware)
            self._jobs[job.id] = job
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)


JOBS = JobStore()


def _close(thing) -> None:
    if thing is None:
        return
    try:
        thing.close()
    except Exception:
        pass


def run_update(job: Job, make_conn, sleep=time.sleep) -> None:
    """Check, download and (optionally) reboot. Always ends with the job done or failed."""
    conn = None
    api = None
    try:
        job.step("Connecting to the router")
        conn = make_conn(job.ip, job.tid)
        conn.connect()
        api = conn.open_additional(LONG_TIMEOUT)

        job.step("Checking the latest stable version")
        info = ra.check_updates(api)
        job.result["check"] = info
        latest, installed = info.get("latest"), info.get("installed")

        if info["state"] == "error":
            job.fail(f"The router could not check for updates: {info.get('status')}")
            return
        if info["state"] == "unknown":
            job.fail("The version information could not be read from the router")
            return
        if info["state"] == "major_change":
            job.fail(
                f"The latest stable version ({latest}) is a different major version than the installed one "
                f"({installed}). Major upgrades are not done from the panel."
            )
            return
        if info["state"] == "up_to_date":
            job.finish(f"The router already runs the latest stable version ({installed}).")
            return

        firmware_supported = bool(info["firmware"]["supported"])
        job.result["firmware_auto"] = False
        if job.firmware and firmware_supported:
            if ra.enable_auto_firmware(api):
                job.result["firmware_auto"] = True
                job.step("Automatic Routerboard firmware upgrade enabled for the next boot")
            else:
                job.step("Could not enable automatic firmware upgrade; upgrade the firmware manually after the reboot")
        elif job.firmware:
            job.step("This device has no Routerboard firmware to upgrade")

        job.step(f"Downloading RouterOS {latest} (this can take a few minutes)")
        ra.download_update(api, sleep=sleep)
        job.step("Download finished")

        if job.mode == "now":
            job.step("Rebooting the router to install the update")
            ra.send_reboot(api)
            message = f"The reboot command was sent. The router installs RouterOS {latest} and stays offline for a few minutes."
            if job.result["firmware_auto"]:
                message += " It then upgrades its firmware automatically and restarts once more."
            job.finish(message)
        else:
            job.finish(f"RouterOS {latest} was downloaded. It installs the next time the router reboots.")
    except InvalidInput as exc:
        job.fail(str(exc))
    except (ra.RouterCommandFailed, ros_exc.TrapError) as exc:
        job.fail(f"The router rejected a command: {str(exc)[:200]}")
    except ConnectionFailed:
        job.fail("Could not connect to the customer router")
    except (socket.timeout, TimeoutError):
        job.fail("The router did not answer in time")
    except Exception as exc:
        log.warning("update job failed: %s", type(exc).__name__)
        job.fail(f"Unexpected error ({type(exc).__name__})")
    finally:
        _close(api)
        _close(conn)


def start_job_thread(job: Job, make_conn, on_finish=None) -> threading.Thread:
    def target():
        try:
            run_update(job, make_conn)
        finally:
            if on_finish is not None:
                try:
                    on_finish(job)
                except Exception as exc:
                    log.warning("update audit failed: %s", type(exc).__name__)

    thread = threading.Thread(target=target, daemon=True, name=f"update-{job.id[:6]}")
    thread.start()
    return thread