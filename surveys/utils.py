"""Yordamchi funksiyalar — UA parser, GPS distance, IP utility.

UA parser oddiy regex bilan ishlaydi (qo'shimcha paket talab qilmaydi).
Asosiy maqsad: device_type, os_name, browser_name'ni aniqlash.
"""
import math
import re


# ============================================================
# User-Agent parser
# ============================================================

# Bot/crawler signaturalari
_BOT_PATTERNS = re.compile(
    r'(bot|crawler|spider|slurp|googlebot|bingbot|yandex|baidu|duckduckgo|'
    r'facebookexternalhit|whatsapp|telegrambot|headlesschrome|phantomjs|'
    r'curl|wget|python-requests|httpie|postman|insomnia|libwww-perl)',
    re.IGNORECASE,
)

# Tablet signaturalari (mobile'dan oldin tekshiriladi — chunki "Tablet"/"iPad" mobile'ga ham mos kelishi mumkin)
_TABLET_PATTERNS = re.compile(
    r'(iPad|Android(?!.*Mobile)|Tablet|Kindle|Silk|PlayBook)',
    re.IGNORECASE,
)

# Mobile signaturalari
_MOBILE_PATTERNS = re.compile(
    r'(Mobile|iPhone|iPod|Android.*Mobile|Windows Phone|BlackBerry|Opera Mini|Opera Mobi|IEMobile)',
    re.IGNORECASE,
)


def parse_device_type(ua: str) -> str:
    """User-Agent stringdan device turini aniqlaydi.

    Qaytaradi: 'mobile' | 'tablet' | 'desktop' | 'bot' | 'unknown'
    """
    if not ua:
        return 'unknown'
    if _BOT_PATTERNS.search(ua):
        return 'bot'
    if _TABLET_PATTERNS.search(ua):
        return 'tablet'
    if _MOBILE_PATTERNS.search(ua):
        return 'mobile'
    # Agar UA bor lekin yuqoridagilarga mos kelmasa — desktop deb taxmin qilamiz
    return 'desktop'


def parse_os(ua: str) -> str:
    """Operatsion tizimni aniqlaydi.

    Qaytaradi: 'iOS' | 'Android' | 'Windows' | 'macOS' | 'Linux' | 'Other' | ''
    """
    if not ua:
        return ''
    # Tartib muhim: iOS Android'dan oldin (chunki "Mac OS" iOS UA da ham bo'ladi)
    if re.search(r'iPhone|iPad|iPod|iOS', ua, re.IGNORECASE):
        return 'iOS'
    if re.search(r'Android', ua, re.IGNORECASE):
        return 'Android'
    if re.search(r'Windows NT', ua, re.IGNORECASE):
        return 'Windows'
    if re.search(r'Mac OS X|Macintosh', ua, re.IGNORECASE):
        return 'macOS'
    if re.search(r'Linux|X11', ua, re.IGNORECASE):
        return 'Linux'
    return 'Other'


# Brauzerlar — tartib muhim (Chrome Edge'dan oldin tekshirilsa noto'g'ri natija)
_BROWSER_PATTERNS = [
    ('Edge',     re.compile(r'Edg(?:e|A|iOS)?/', re.IGNORECASE)),
    ('Opera',    re.compile(r'(?:Opera|OPR)/', re.IGNORECASE)),
    ('Firefox',  re.compile(r'Firefox/|FxiOS/', re.IGNORECASE)),
    ('Samsung',  re.compile(r'SamsungBrowser/', re.IGNORECASE)),
    ('Chrome',   re.compile(r'Chrome/|CriOS/', re.IGNORECASE)),
    ('Safari',   re.compile(r'Safari/', re.IGNORECASE)),
    ('IE',       re.compile(r'MSIE |Trident/', re.IGNORECASE)),
]


def parse_browser(ua: str) -> str:
    """Brauzer nomini aniqlaydi.

    Qaytaradi: 'Chrome' | 'Safari' | 'Firefox' | 'Edge' | 'Opera' | 'IE' | 'Samsung' | 'Other' | ''
    """
    if not ua:
        return ''
    for name, pattern in _BROWSER_PATTERNS:
        if pattern.search(ua):
            return name
    return 'Other'


def parse_user_agent(ua: str) -> dict:
    """User-Agent ni to'liq parse qiladi.

    Qaytaradi: {'device_type', 'os_name', 'browser_name'}
    """
    return {
        'device_type': parse_device_type(ua),
        'os_name': parse_os(ua),
        'browser_name': parse_browser(ua),
    }


# ============================================================
# GPS distance (Haversine formula)
# ============================================================

def haversine_distance_km(lat1, lon1, lat2, lon2):
    """Ikki GPS nuqta orasidagi masofani km da hisoblaydi.

    Haversine formula. Argumentlar None bo'lsa None qaytaradi.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return None

    R = 6371.0  # Yer radiusi km da
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(R * c, 2)


# ============================================================
# IP utility
# ============================================================

def ip_to_subnet24(ip: str) -> str:
    """IPv4 ni /24 subnet'ga aylantiradi (masalan 192.168.1.50 → 192.168.1.0/24).

    IPv6 yoki noto'g'ri format bo'lsa, original IP'ni qaytaradi.
    """
    if not ip or ':' in ip:  # IPv6
        return ip or ''
    parts = ip.split('.')
    if len(parts) != 4:
        return ip
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"


def device_fingerprint(device_info: dict) -> str:
    """Device info'dan unique fingerprint string yasaydi.

    {screen: '375x812', platform: 'iPhone', timezone: 'Asia/Tashkent', language: 'en'}
      → "iPhone|375x812|Asia/Tashkent|en"
    """
    if not isinstance(device_info, dict):
        return ''
    parts = [
        str(device_info.get('platform') or ''),
        str(device_info.get('screen') or ''),
        str(device_info.get('timezone') or ''),
        str(device_info.get('language') or ''),
    ]
    fp = '|'.join(parts)
    return fp if any(parts) else ''
