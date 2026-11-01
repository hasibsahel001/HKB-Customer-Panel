from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Account(BaseModel):
    username: str
    password: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HKB_")

    api_ports: list[int] = [2299, 8728]
    connect_timeout: float = 4.0
    allowed_networks: list[str] = ["10.229.0.0/16"]

    tid_username_template: str = "{tid}HKB"
    tid_password_template: str = ""
    fallback_accounts: list[Account] = []

    # Connection speed
    probe_timeout: float = 2.0
    connect_hint_enabled: bool = True
    connect_hint_ttl_seconds: int = 86400
    parallel_connections: bool = True

    # Wireless thresholds (starting values, tune them for your network)
    signal_normal_dbm: float = -60.0
    signal_warning_dbm: float = -70.0
    signal_serious_dbm: float = -80.0
    ccq_normal_percent: float = 70.0
    ccq_serious_percent: float = 50.0
    ccq_critical_percent: float = 35.0
    chain_imbalance_db: float = 8.0

    # LAN port and the customer's own access point
    link_downs_warning: int = 3
    ap_probe_peers: list[str] = ["10.10.10.2", "192.168.0.1", "192.168.1.1"]
    ap_expected_addresses: list[str] = ["192.168.0.2/24", "192.168.1.2/24"]

    # Queues
    queue_very_low_limit_bps: int = 10_000
    queue_usage_warning_percent: float = 90.0

    # Ping settings (the ping runs on the customer router itself)
    ping_targets: list[str] = ["8.8.8.8"]
    ping_count: int = 3
    ping_interval: str = "200ms"

    # Ping thresholds (starting values, tune them for your network)
    ping_loss_warning_percent: float = 2.0
    ping_loss_serious_percent: float = 10.0
    ping_latency_warning_ms: float = 150.0
    ping_latency_serious_ms: float = 300.0

    # Router load thresholds (starting values)
    cpu_warning_percent: float = 80.0
    cpu_serious_percent: float = 95.0
    ram_warning_percent: float = 85.0
    ram_serious_percent: float = 95.0
    # If the first CPU reading is at/above cpu_warning_percent, wait this long and read once
    # more; a brief spike from opening several connections at once should settle by then.
    cpu_recheck_delay_seconds: float = 0.4

    # Database
    database_url: str = "sqlite:///./hkb.db"

    # Sessions and cookies
    session_cookie_name: str = "hkb_session"
    session_absolute_hours: int = 12
    session_idle_minutes: int = 60
    cookie_secure: bool = False

    # Passwords and login protection
    password_min_length: int = 10
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    login_ip_max_attempts: int = 20
    login_ip_window_seconds: int = 300

    # Rate limits per user per minute
    customer_checks_per_minute: int = 20
    actions_per_minute: int = 30
    # The dashboard refreshes the online devices about once a second while a customer is open.
    device_polls_per_minute: int = 150

    # The Windows VPN entry the panel creates for "Enter via Local IP" (only on a Windows panel PC)
    vpn_connection_name: str = "VPN"
    vpn_auto_connect: bool = False

    # Recent customers list
    recent_hours: int = 24


settings = Settings()