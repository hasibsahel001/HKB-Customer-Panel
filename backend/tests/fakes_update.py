from app.core.errors import ConnectionFailed


class FakeUpdateApi:
    """A stand-in for a router that answers the update and firmware commands."""

    def __init__(
        self,
        installed="6.49.7",
        latest="6.49.19",
        channel="long-term",
        check_status="New version is available",
        download_statuses=("Downloaded, please reboot router to upgrade it",),
        firmware="default",
        firmware_error=False,
        auto_upgrade_fails=False,
        fail_download=False,
    ):
        self.row = {"channel": channel, "installed-version": installed, "latest-version": None, "status": ""}
        self.latest = latest
        self.check_status = check_status
        self.download_statuses = list(download_statuses)
        if firmware == "default":
            firmware = {
                "routerboard": True,
                "model": "LHG 5",
                "current-firmware": "6.45",
                "upgrade-firmware": "6.49.19",
            }
        self.firmware = firmware
        self.firmware_error = firmware_error
        self.auto_upgrade_fails = auto_upgrade_fails
        self.fail_download = fail_download
        self.commands = []
        self.closed = False

    def path(self, *parts):
        if parts == ("system", "package", "update"):
            return [dict(self.row)]
        if parts == ("system", "routerboard"):
            if self.firmware_error:
                raise RuntimeError("no such menu")
            return [dict(self.firmware)]
        raise KeyError(parts)

    def rawCmd(self, cmd, *words):
        self.commands.append((cmd, words))
        if cmd == "/system/package/update/set":
            for word in words:
                if word.startswith("=channel="):
                    self.row["channel"] = word.split("=", 2)[2]
        elif cmd == "/system/package/update/check-for-updates":
            self.row["latest-version"] = self.latest
            self.row["status"] = self.check_status
        elif cmd == "/system/package/update/download":
            if self.fail_download:
                raise RuntimeError("download crashed")
            self.pending = list(self.download_statuses)
            self.row["status"] = "Downloading"
        elif cmd == "/system/routerboard/settings/set" and self.auto_upgrade_fails:
            raise RuntimeError("no such setting")
        elif cmd == "/system/reboot":
            raise OSError("connection reset by the router")
        return iter([])

    def poll_status(self):
        pending = getattr(self, "pending", None)
        if pending:
            self.row["status"] = pending.pop(0)

    def close(self):
        self.closed = True

    def names(self):
        return [cmd for cmd, _ in self.commands]


class FakeUpdateConn:
    def __init__(self, api, fail_connect=False):
        self.api = api
        self.fail_connect = fail_connect
        self.closed = False

    def connect(self):
        if self.fail_connect:
            raise ConnectionFailed([])
        return self

    def open_additional(self, timeout=None):
        return self.api

    def close(self):
        self.closed = True


def make_conn_factory(api, fail_connect=False):
    return lambda ip, tid: FakeUpdateConn(api, fail_connect)