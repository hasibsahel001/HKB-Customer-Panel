from enum import Enum


class FailureKind(str, Enum):
    TIMEOUT = "timeout"
    PORT_CLOSED = "port_closed"
    AUTH_REJECTED = "auth_rejected"
    UNREACHABLE = "unreachable"
    PROTOCOL = "protocol_error"


class InvalidInput(ValueError):
    pass


class ConnectionFailed(Exception):
    def __init__(self, attempts):
        # Only account index, port and failure kind; never any password.
        self.attempts = attempts
        super().__init__("all attempts failed")