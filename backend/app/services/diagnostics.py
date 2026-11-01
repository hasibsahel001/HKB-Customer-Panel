import re
from datetime import datetime, timezone

from app.core.config import settings
from app.services.network_parsing import parse_duration_seconds

_ORDER = {"critical": 0, "serious": 1, "warning": 2, "unknown": 3}
_BAD = ("warning", "serious", "critical")

_SECTIONS_NEEDED = ("wireless", "ether1", "dhcp", "devices", "pppoe", "ping", "queues")

_SECTION_FA = {
    "wireless": "وایرلس",
    "ether1": "پورت LAN",
    "dhcp": "DHCP",
    "devices": "دستگاه‌ها",
    "pppoe": "PPPoE",
    "ping": "پینگ",
    "queues": "صف‌های سرعت",
}

_DIRECTION_FA = {"upload": "آپلود", "download": "دانلود"}

_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmMgG]?)bps\s*$")

_KNOWN_REASONS = {
    "no dhcp server": (
        "dhcp_server_not_found",
        "سرور DHCP روی روتر پیدا نشد",
        "warning",
        ["مشتری ممکن است از IP ثابت استفاده کند",
         "سرور DHCP ممکن است روی دستگاه دیگری (مثلاً مودم یا اکسس‌پوینت داخل منزل) اجرا شود"],
        "بررسی کنید IP دستگاه‌های داخل منزل از کدام دستگاه داده می‌شود",
    ),
    "no wireless interface": (
        "wireless_interface_not_found",
        "اینترفیس وایرلس روی روتر پیدا نشد",
        "serious",
        ["ممکن است این مدل یا نسخه RouterOS از بسته‌ی وایرلس دیگری استفاده کند که پنل هنوز نمی‌خواند"],
        "فهرست اینترفیس‌های روتر را به‌صورت دستی بررسی کنید",
    ),
    "no pppoe client": (
        "pppoe_client_not_found",
        "کلاینت PPPoE روی روتر پیدا نشد",
        "warning",
        ["روتر ممکن است با روش دیگری به شبکه وصل شده باشد",
         "کلاینت PPPoE ممکن است حذف یا تغییر نام داده شده باشد"],
        "بررسی کنید این روتر چگونه آدرس می‌گیرد",
    ),
    "ether1 not found": (
        "ether1_not_found",
        "اینترفیس ether1 روی روتر پیدا نشد",
        "serious",
        ["نام اینترفیس ممکن است تغییر کرده باشد"],
        "فهرست اینترفیس‌های روتر را به‌صورت دستی بررسی کنید",
    ),
}


def _level(value, warning, serious):
    if value >= serious:
        return "serious"
    if value >= warning:
        return "warning"
    return None


def _rate_mbps(value):
    match = _RATE_RE.match(str(value or ""))
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    return number * 1000 if unit == "g" else number / 1000 if unit == "k" else number


def _is_blocking_queue(name) -> bool:
    """A queue meant to throttle/block a device (e.g. "block-h") is not a real speed package,
    so its limit is intentionally tiny or its "near the cap" state is expected and not
    worth a finding."""
    return "block" in str(name or "").lower()


def _check_unavailable(sections, add):
    for name in _SECTIONS_NEEDED:
        section = sections.get(name)
        if section is None or section.get("ok"):
            continue
        reason = section.get("error_detail")
        known = _KNOWN_REASONS.get(reason)
        if known:
            code, title, severity, causes, action = known
            add(code, title, severity, {"section": name}, causes=causes, action=action)
        else:
            add(
                "section_unavailable",
                f"اطلاعات بخش «{_SECTION_FA.get(name, name)}» خوانده نشد",
                "unknown",
                {"section": name, "reason": reason},
                causes=["فرمان در این نسخه RouterOS ممکن است پشتیبانی نشود",
                        "روتر ممکن است به‌موقع پاسخ نداده باشد",
                        "حساب ورود ممکن است دسترسی لازم را نداشته باشد"],
                action="یک بار رفرش کنید؛ اگر ادامه داشت نسخه و دسترسی‌های حساب روتر را بررسی کنید",
            )


def _check_resource(resource, add):
    if not resource:
        return
    cpu = resource.get("cpu_load")
    if cpu is not None:
        severity = _level(cpu, settings.cpu_warning_percent, settings.cpu_serious_percent)
        if severity:
            add(
                "cpu_high",
                "بار پردازنده (CPU) روتر بالاست",
                severity,
                {"cpu_load_percent": cpu},
                {"warning_percent": settings.cpu_warning_percent,
                 "serious_percent": settings.cpu_serious_percent},
                causes=["ترافیک یا پردازش بسته‌ها سنگین است",
                        "سرویس یا تنظیمات معیوب روی روتر"],
                action="رفرش کنید؛ اگر بار پایدار بود ترافیک و سرویس‌های روتر را بررسی کنید",
            )
    ram = resource.get("ram_used_percent")
    if ram is not None:
        severity = _level(ram, settings.ram_warning_percent, settings.ram_serious_percent)
        if severity:
            add(
                "ram_high",
                "مصرف حافظه (RAM) روتر بالاست",
                severity,
                {"ram_used_percent": ram},
                {"warning_percent": settings.ram_warning_percent,
                 "serious_percent": settings.ram_serious_percent},
                causes=["جدول‌ها یا لاگ‌های بزرگ روی دستگاه کم‌حافظه",
                        "آپ‌تایم طولانی و انباشته شدن اطلاعات"],
                action="مصرف‌کننده‌های حافظه را بررسی کنید و در صورت نیاز ریبوت کنترل‌شده انجام دهید",
            )


def _rx_spread(chains):
    values = [c.get("rx_dbm") for c in chains if c.get("rx_dbm") is not None]
    if len(values) < 2:
        return None
    return max(values) - min(values)


def _check_wireless(wireless, add):
    if not wireless:
        return
    if wireless.get("running") is False or wireless.get("disabled") is True:
        add(
            "wireless_interface_down",
            "اینترفیس وایرلس خاموش یا قطع است",
            "critical",
            {"interface": wireless.get("interface"),
             "running": wireless.get("running"),
             "disabled": wireless.get("disabled")},
            causes=["اینترفیس در تنظیمات غیرفعال شده است",
                    "احتمال مشکل سخت‌افزار یا فریمور رادیو"],
            action="فعال بودن اینترفیس و تنظیمات رادیو را بررسی کنید؛ اگر ادامه داشت تیم را برای بررسی یا تعویض رادیو اعزام کنید",
        )
        return
    if wireless.get("registration_count") == 0:
        add(
            "wireless_not_registered",
            "رادیو به هیچ اکسس‌پوینتی متصل نیست",
            "critical",
            {"interface": wireless.get("interface"),
             "ssid": wireless.get("ssid"),
             "frequency": wireless.get("frequency")},
            causes=["احتمال به‌هم‌خوردن تراز آنتن یا آسیب فیزیکی",
                    "اکسس‌پوینت خاموش است یا مشتری خارج از برد آن است",
                    "احتمال اختلاف SSID، فرکانس یا Access List"],
            action="اول وضعیت اکسس‌پوینت مربوطه را بررسی کنید؛ اگر AP سالم است، تیم را برای بررسی آنتن، کابل و برق رادیو به محل اعزام کنید",
        )
        return

    analysis = wireless.get("analysis") or {}
    registration = wireless.get("registration") or {}
    chains = registration.get("chains") or []
    signal_bad = analysis.get("signal") in _BAD
    ccq_bad = analysis.get("ccq") in _BAD

    evidence = {
        "signal_dbm": registration.get("signal_dbm"),
        "snr_db": registration.get("snr_db"),
        "noise_floor_dbm": registration.get("noise_floor_dbm"),
        "ccq_used": wireless.get("ccq_used"),
        "ccq_source": wireless.get("ccq_source"),
        "tx_ccq": registration.get("tx_ccq"),
        "rx_ccq": registration.get("rx_ccq"),
        "tx_rate": registration.get("tx_rate"),
        "rx_rate": registration.get("rx_rate"),
    }
    thresholds = {
        "signal_normal_dbm": settings.signal_normal_dbm,
        "signal_warning_dbm": settings.signal_warning_dbm,
        "signal_serious_dbm": settings.signal_serious_dbm,
        "ccq_normal_percent": settings.ccq_normal_percent,
        "ccq_serious_percent": settings.ccq_serious_percent,
    }

    if signal_bad and ccq_bad:
        add(
            "wireless_link_quality_low",
            "کیفیت لینک وایرلس پایین است (سیگنال و CCQ هر دو ضعیف‌اند)",
            analysis.get("overall"),
            evidence,
            thresholds,
            causes=["احتمال خارج شدن آنتن از تراز (Alignment) یا وجود مانع در مسیر",
                    "فاصله زیاد یا افت سیگنال در مسیر",
                    "احتمال تداخل روی کانال"],
            action="پیشنهاد: تیم فنی به محل اعزام شود تا آنتن را تراز کند و مسیر، کابل و کانکتور را بررسی کند. اگر مشکل برطرف نشد یا مسیر مانع دارد، مشتری به اکسس‌پوینت دیگری با دید بهتر منتقل (Shift) شود.",
        )
    elif signal_bad:
        add(
            "wireless_signal_weak",
            "سیگنال وایرلس ضعیف است",
            analysis.get("signal"),
            evidence,
            thresholds,
            causes=["احتمال خارج شدن آنتن از تراز",
                    "احتمال obstruction یا فاصله زیاد"],
            action="تراز آنتن را بررسی کنید؛ اگر با تراز بهتر سیگنال بالا نیامد، انتقال مشتری به اکسس‌پوینت دیگر را در نظر بگیرید",
        )
    elif ccq_bad:
        causes = ["احتمال تداخل یا نویز روی کانال",
                  "احتمال شلوغی (ازدحام) روی اکسس‌پوینت",
                  "احتمال ناهماهنگی پلاریزاسیون یا ضعف یکی از چین‌ها",
                  "احتمال خرابی کابل یا کانکتور"]
        tx, rx = registration.get("tx_ccq"), registration.get("rx_ccq")
        if tx is not None and rx is not None and abs(tx - rx) >= 25:
            causes.insert(
                0,
                "اختلاف زیاد بین CCQ ارسال و دریافت یعنی مشکل بیشتر یک‌طرفه است "
                "(مثلاً نویز سمت اکسس‌پوینت یا ضعف ارسال رادیوی مشتری)",
            )
        add(
            "wireless_ccq_low_with_good_signal",
            "CCQ پایین است در حالی که سیگنال قابل قبول است",
            analysis.get("ccq"),
            evidence,
            thresholds,
            causes=causes,
            action="با سایر مشتریان همان اکسس‌پوینت مقایسه کنید. اگر چند مشتری مشکل دارند، نویز، فرکانس یا ازدحام AP را بررسی کنید؛ اگر فقط همین مشتری مشکل دارد، آنتن و کابل او را در محل چک کنید.",
        )

    if analysis.get("signal") == "unknown" or analysis.get("ccq") == "unknown":
        add(
            "wireless_metrics_missing",
            "بعضی شاخص‌های وایرلس از دستگاه گزارش نشد",
            "unknown",
            {"signal": analysis.get("signal"), "ccq": analysis.get("ccq")},
            causes=["رادیو این فیلد را در این نسخه RouterOS گزارش نمی‌کند"],
            action="در صورت نیاز جدول Registration را دستی بخوانید",
        )


    link_up = parse_duration_seconds(registration.get("uptime"))
    device_up = parse_duration_seconds(wireless.get("device_uptime"))
    if link_up is not None and device_up is not None and link_up < 600 and device_up >= 3600:
        add(
            "wireless_link_recent_drop",
            "لینک وایرلس به‌تازگی قطع و دوباره وصل شده است",
            "warning",
            {"link_uptime_seconds": link_up, "device_uptime_seconds": device_up},
            causes=["افت لحظه‌ای سیگنال یا تداخل",
                    "مشکل برق یا کابل رادیو"],
            action="اگر تکرار شد، لاگ قطعی را از سمت اکسس‌پوینت بررسی کنید و در صورت تکرار تیم را به محل بفرستید",
        )


def _check_ether1(ether1, add):
    if not ether1:
        return
    if ether1.get("disabled") is True or ether1.get("running") is False:
        add(
            "ether1_down",
            "پورت LAN (ether1) فعال نیست",
            "serious",
            {"running": ether1.get("running"),
             "disabled": ether1.get("disabled"),
             "link_status": ether1.get("link_status"),
             "last_link_up_time": ether1.get("last_link_up_time")},
            causes=["کابل بین روتر و مودم یا اکسس‌پوینت داخل منزل قطع یا آسیب‌دیده است",
                    "دستگاه داخل منزل خاموش است",
                    "احتمال خرابی پورت"],
            action="کابل و برق دستگاه متصل به ether1 را بررسی کنید",
        )
        return

    mbps = _rate_mbps(ether1.get("link_rate"))
    half = ether1.get("full_duplex") is False
    if (mbps is not None and mbps < 100) or half:
        add(
            "lan_link_slow",
            "لینک ether1 با سرعت یا حالت دوبل‌کس ضعیف‌تر از حد انتظار برقرار شده است",
            "warning",
            {"link_rate": ether1.get("link_rate"), "full_duplex": ether1.get("full_duplex")},
            causes=["کابل معیوب یا کانکتور خراب (پین‌های ناقص)",
                    "طول یا کیفیت نامناسب کابل",
                    "دستگاه مقابل با سرعت دستی تنظیم شده است"],
            action="کابل داخل منزل را با یک کابل سالم عوض کنید و دوباره بررسی کنید",
        )

    downs = ether1.get("link_downs")
    if isinstance(downs, int) and downs >= settings.link_downs_warning:
        add(
            "lan_link_flapping",
            f"پورت LAN از آخرین بوت روتر {downs} بار لینک‌داون شده است",
            "warning",
            {"link_downs": downs},
            {"link_downs_warning": settings.link_downs_warning},
            causes=["کابل شل یا کانکتور معیوب",
                    "نوسان برق دستگاه داخل منزل",
                    "ناپایداری پورت"],
            action="کابل و کانکتور را بررسی کنید. توجه: این عدد از زمان بوت روتر شمرده می‌شود و روتر با آپ‌تایم طولانی طبیعتاً عدد بزرگ‌تری دارد.",
        )


def _check_dhcp_and_devices(dhcp, devices, ether1, add):
    if dhcp and dhcp.get("conflict_count", 0) > 0:
        add(
            "dhcp_ip_conflict",
            "DHCP تداخل آدرس IP گزارش کرده است",
            "warning",
            {"conflict_count": dhcp["conflict_count"]},
            causes=["دستگاهی با IP ثابت داخل محدوده‌ی DHCP قرار دارد",
                    "دو دستگاه از یک آدرس استفاده می‌کنند"],
            action="دستگاه‌های دارای IP ثابت در محدوده‌ی DHCP را پیدا کنید",
        )
    if devices and devices.get("count") == 0 and not (ether1 and ether1.get("running") is False):
        add(
            "no_devices_detected",
            "هیچ دستگاه فعالی پشت روتر پیدا نشد",
            "warning",
            {"device_count": 0, "interfaces": devices.get("interfaces")},
            causes=["ممکن است در حال حاضر کسی از شبکه استفاده نمی‌کند",
                    "دستگاه‌ها ممکن است آدرس نگرفته باشند",
                    "اکسس‌پوینت داخل منزل ممکن است در حالت بریج یا قطع باشد"],
            action="با مشتری تأیید کنید که دستگاهی متصل است",
        )


def _check_pppoe(pppoe, wireless, add):
    if not pppoe:
        return
    status = pppoe.get("status")
    if pppoe.get("running") is False or (status is not None and status != "connected"):
        add(
            "pppoe_down",
            "اتصال PPPoE برقرار نیست",
            "critical",
            {"name": pppoe.get("name"),
             "running": pppoe.get("running"),
             "status": status,
             "underlying_interface": pppoe.get("underlying_interface")},
            causes=["احتمال مشکل در لینک وایرلس",
                    "سرور PPPoE نشست را رد می‌کند",
                    "احتمال اشتباه بودن نام کاربری، رمز یا نام سرویس"],
            action="اول لینک وایرلس را بررسی کنید و بعد تنظیمات کلاینت PPPoE را",
        )
    if pppoe.get("matches_panel_ip") is False:
        add(
            "pppoe_ip_mismatch",
            "آدرس PPPoE با IP واردشده در پنل یکی نیست",
            "serious",
            {"panel_ip_matches": False, "pppoe_local_address": pppoe.get("local_address")},
            causes=["Technical ID یا IP ممکن است مربوط به مشتری دیگری باشد",
                    "روتر از مسیر دیگری در دسترس بوده است"],
            action="IP و Technical ID را قبل از اعتماد به این گزارش بررسی کنید",
        )

    pppoe_up = parse_duration_seconds(pppoe.get("uptime"))
    link_up = parse_duration_seconds(((wireless or {}).get("registration") or {}).get("uptime"))
    if pppoe_up is not None and link_up is not None and pppoe_up < 600 and link_up >= 3600:
        add(
            "pppoe_recent_reconnect",
            "PPPoE به‌تازگی دوباره وصل شده است در حالی که لینک وایرلس پایدار مانده",
            "warning",
            {"pppoe_uptime_seconds": pppoe_up, "link_uptime_seconds": link_up},
            causes=["سشن از سمت سرور PPPoE قطع شده است",
                    "اختلال کوتاه در مسیر بالادستی",
                    "تغییر یا ریستارت سرویس PPPoE"],
            action="لاگ سرور PPPoE را برای علت قطع بررسی کنید؛ اگر تکرار شد با مشتری هم‌زمان چند مشتری دیگر را مقایسه کنید",
        )


def _ping_evidence(entry):
    summary = entry.get("summary") or {}
    return {
        "host": entry.get("host"),
        "loss_percent": summary.get("loss_percent"),
        "avg_ms": summary.get("avg_ms"),
        "max_ms": summary.get("max_ms"),
    }


def _check_ping(ping, add):
    if not ping:
        return
    thresholds = {
        "loss_warning_percent": settings.ping_loss_warning_percent,
        "loss_serious_percent": settings.ping_loss_serious_percent,
        "latency_warning_ms": settings.ping_latency_warning_ms,
        "latency_serious_ms": settings.ping_latency_serious_ms,
    }
    gateway = ping.get("gateway")
    gateway_ok = gateway.get("reachable") if gateway else None

    if gateway and gateway_ok is False:
        add(
            "gateway_unreachable",
            "گیت‌وی PPPoE به پینگ پاسخ نمی‌دهد",
            "critical",
            _ping_evidence(gateway),
            causes=["احتمال مشکل در لینک وایرلس یا اکسس‌پوینت",
                    "احتمال مشکل سمت ارائه‌دهنده در سشن PPPoE"],
            action="اول لینک وایرلس و اکسس‌پوینت را بررسی کنید و بعد سراغ بالادست بروید",
        )
    elif gateway and gateway.get("status") in ("warning", "serious"):
        add(
            "gateway_ping_degraded",
            "پینگ به گیت‌وی PPPoE ضعیف یا ناپایدار است",
            gateway["status"],
            _ping_evidence(gateway),
            thresholds,
            causes=["احتمال مشکل کیفیت لینک وایرلس",
                    "احتمال ازدحام روی اکسس‌پوینت"],
            action="با یافته‌های وایرلس و با سایر مشتریان همان اکسس‌پوینت مقایسه کنید",
        )

    layers = ping.get("layers") or {}
    targets = ping.get("targets") or []
    if layers.get("internet_reachable") is False and gateway_ok is not False:
        title = (
            "گیت‌وی پاسخ می‌دهد ولی مقصدهای تست اینترنت پاسخ نمی‌دهند"
            if gateway_ok
            else "مقصدهای تست اینترنت پاسخ نمی‌دهند"
        )
        add(
            "internet_unreachable",
            title,
            "serious",
            {"targets": [t.get("host") for t in targets], "gateway_reachable": gateway_ok},
            causes=["احتمال مشکل در مسیر بالادستی",
                    "مقصدهای تست ممکن است ICMP را مسدود کرده باشند",
                    "احتمال مشکل مسیریابی یا فایروال"],
            action="یک مقصد تست دیگر امتحان کنید و با مشتریان دیگر مقایسه کنید، بعد نتیجه بگیرید",
        )

    for target in targets:
        if target.get("reachable") and target.get("status") in ("warning", "serious"):
            add(
                "internet_ping_degraded",
                f"پینگ به {target.get('host')} بالا یا ناپایدار است",
                target["status"],
                _ping_evidence(target),
                thresholds,
                causes=["احتمال ازدحام در مسیر بالادستی",
                        "مقصد ممکن است دور باشد؛ با مقدار پایه‌ی شبکه مقایسه کنید"],
                action="با مشتریان دیگر مقایسه کنید؛ اگر فقط همین مشتری پینگ بالا دارد، کیفیت لینک وایرلس را هم ببینید",
            )


def _check_queues(queues, add):
    if not queues:
        return
    items = [
        q for q in queues.get("queues", [])
        if not q.get("disabled") and not _is_blocking_queue(q.get("name"))
    ]

    for q in items:
        if q.get("very_low_limit"):
            add(
                "queue_very_low_limit",
                f"صف «{q.get('name')}» محدودیت سرعت بسیار پایینی دارد",
                "serious",
                {"queue": q.get("name"),
                 "target": q.get("target"),
                 "max_limit_upload_bps": q.get("max_limit_upload_bps"),
                 "max_limit_download_bps": q.get("max_limit_download_bps")},
                {"very_low_limit_bps": settings.queue_very_low_limit_bps},
                causes=["ممکن است مسدودسازی عمدی یا تعلیق سرویس باشد",
                        "ممکن است باقی‌مانده‌ی یک تغییر قبلی باشد"],
                action="از سیستم حسابداری بررسی کنید این مشتری باید محدود باشد یا نه",
            )
            continue
        for direction in ("upload", "download"):
            limit = q.get(f"max_limit_{direction}_bps")
            current = q.get(f"current_{direction}_bps")
            if limit and current is not None and current * 100 >= limit * settings.queue_usage_warning_percent:
                add(
                    "queue_near_limit",
                    f"صف «{q.get('name')}» به سقف سرعت {_DIRECTION_FA[direction]} نزدیک شده است",
                    "warning",
                    {"queue": q.get("name"),
                     "direction": direction,
                     "current_bps": current,
                     "limit_bps": limit,
                     "usage_percent": round(current * 100 / limit, 1)},
                    {"usage_warning_percent": settings.queue_usage_warning_percent},
                    causes=["مشتری از کل سرعت مجاز استفاده می‌کند",
                            "یک دستگاه ممکن است کل پهنای باند را اشغال کرده باشد"],
                    action="بررسی کنید سرعت تعریف‌شده با بسته‌ی مشتری هم‌خوانی دارد",
                )

    if len(items) > 1:
        add(
            "queue_overlap",
            "چند صف روی این مشتری فعال است؛ سرعت مؤثر قابل تشخیص نیست",
            "unknown",
            {"queues": [{"name": q.get("name"), "target": q.get("target")} for q in items]},
            causes=["صف‌های ساده معمولاً به ترتیب ارزیابی می‌شوند و ممکن است زمان‌بندی داشته باشند؛ پنل ترتیب و زمان‌بندی را نمی‌خواند"],
            action="اگر سرعت دقیق مهم است، ترتیب و زمان‌بندی صف‌ها را روی روتر بررسی کنید",
        )


def _overall(findings):
    severities = {f["severity"] for f in findings}
    for level in ("critical", "serious", "warning"):
        if level in severities:
            return level
    return "unknown" if severities else "normal"


def _collector(now):
    detected_at = now or datetime.now(timezone.utc).isoformat()
    findings = []

    def add(code, title, severity, evidence=None, threshold=None, causes=None, action=""):
        findings.append(
            {
                "code": code,
                "title": title,
                "severity": severity,
                "evidence": evidence or {},
                "threshold": threshold,
                "probable_causes": list(causes or []),
                "suggested_action": action,
                "detected_at": detected_at,
            }
        )

    return findings, add, detected_at


def _finish(findings, detected_at):
    findings.sort(key=lambda f: (_ORDER.get(f["severity"], 9), f["code"]))
    return {
        "overall": _overall(findings),
        "count": len(findings),
        "generated_at": detected_at,
        "findings": findings,
    }


def diagnose(snapshot, now=None):
    """Analyze a collected snapshot. Only real data is used; missing data becomes 'unknown'."""
    findings, add, detected_at = _collector(now)
    sections = snapshot.get("sections") or {}

    def data(name):
        section = sections.get(name) or {}
        return section.get("data") if section.get("ok") else None

    wireless = data("wireless")
    resource = data("resource")
    if wireless is not None and resource is not None:
        wireless = {**wireless, "device_uptime": resource.get("uptime")}

    _check_unavailable(sections, add)
    _check_resource(resource, add)
    _check_wireless(wireless, add)
    _check_ether1(data("ether1"), add)
    _check_dhcp_and_devices(data("dhcp"), data("devices"), data("ether1"), add)
    _check_pppoe(data("pppoe"), wireless, add)
    _check_ping(data("ping"), add)
    _check_queues(data("queues"), add)
    return _finish(findings, detected_at)


def diagnose_live(ping, mac_ping, now=None):
    """Findings from the slow measurements that run after the main snapshot has been shown."""
    findings, add, detected_at = _collector(now)
    _check_ping(ping, add)
    return _finish(findings, detected_at)