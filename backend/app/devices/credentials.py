from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class Attempt:
    account_index: int   # فقط برای لاگ
    username: str
    password: str
    port: int

    def __repr__(self):  # جلوگیری از لو رفتن رمز در لاگ
        return f"Attempt(acc={self.account_index}, user={self.username}, port={self.port})"


def build_attempts(tid: str) -> list[Attempt]:
    """ترتیب: حساب‌ها به ترتیب؛ برای هر حساب اول پورت 2299 و بعد 8728."""
    accounts = [
        (
            settings.tid_username_template.format(tid=tid),
            settings.tid_password_template.format(tid=tid),
        )
    ] + [(a.username, a.password) for a in settings.fallback_accounts]

    attempts: list[Attempt] = []
    for i, (user, pwd) in enumerate(accounts):
        for port in settings.api_ports:
            attempts.append(Attempt(i, user, pwd, port))
    return attempts