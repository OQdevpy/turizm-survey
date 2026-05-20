"""30 ta turli case'li SurveyResponse seed.

Quyidagi case'larni yoqadi:
  - Toza yozuvlar (har xil davlat, til, device, IP)
  - Fraud signal'lari:
      * Staff va public bir IP'dan (R1)
      * High-volume IP (R2) — bir IP'dan 10+ public
      * Bot UA (R5) — curl, python-requests
      * Fast fill (R6) — 30 soniyadan kam to'ldirish
      * Device fingerprint takrori (R3)
      * Staff GPS pochta bo'limidan uzoq (R7)
      * Public GPS pochta bo'limi binosida (R8)
      * Burst (R4) — 1 daqiqada 3+ submission

Foydalanish:
    python manage.py seed_surveys              # 30 ta qo'shadi
    python manage.py seed_surveys --reset      # avval o'chirib qayta yaratadi
"""
import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import PostalOffice, StaffProfile
from surveys.models import SurveyResponse
from surveys.utils import parse_user_agent


# ============================================================
# UA va Device fingerprintlar
# ============================================================

DEVICES = {
    'iphone_safari': {
        'ua': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
        'screen': '390x844', 'platform': 'iPhone', 'language': 'en-US', 'timezone': 'Asia/Tashkent',
        'touch': True, 'cores': 6, 'memory': 4,
    },
    'iphone_safari_ja': {
        'ua': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'screen': '375x812', 'platform': 'iPhone', 'language': 'ja-JP', 'timezone': 'Asia/Tokyo',
        'touch': True, 'cores': 6, 'memory': 4,
    },
    'samsung_chrome': {
        'ua': 'Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        'screen': '412x915', 'platform': 'Linux armv8l', 'language': 'en-US', 'timezone': 'Asia/Tashkent',
        'touch': True, 'cores': 8, 'memory': 8,
    },
    'pixel_chrome': {
        'ua': 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        'screen': '412x915', 'platform': 'Linux armv8l', 'language': 'fr-FR', 'timezone': 'Europe/Paris',
        'touch': True, 'cores': 8, 'memory': 8,
    },
    'xiaomi_chrome': {
        'ua': 'Mozilla/5.0 (Linux; Android 13; 23049PCD8G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36',
        'screen': '393x873', 'platform': 'Linux armv8l', 'language': 'zh-CN', 'timezone': 'Asia/Shanghai',
        'touch': True, 'cores': 8, 'memory': 6,
    },
    'huawei_chrome': {
        'ua': 'Mozilla/5.0 (Linux; Android 12; ANA-NX9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36',
        'screen': '414x896', 'platform': 'Linux armv8l', 'language': 'de-DE', 'timezone': 'Europe/Berlin',
        'touch': True, 'cores': 8, 'memory': 8,
    },
    'windows_chrome': {
        'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'screen': '1920x1080', 'platform': 'Win32', 'language': 'ru-RU', 'timezone': 'Asia/Tashkent',
        'touch': False, 'cores': 8, 'memory': 16,
    },
    'windows_edge': {
        'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'screen': '1366x768', 'platform': 'Win32', 'language': 'en-US', 'timezone': 'Asia/Tashkent',
        'touch': False, 'cores': 4, 'memory': 8,
    },
    'mac_safari': {
        'ua': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'screen': '2560x1440', 'platform': 'MacIntel', 'language': 'es-ES', 'timezone': 'Europe/Madrid',
        'touch': False, 'cores': 10, 'memory': 16,
    },
    'ipad_safari': {
        'ua': 'Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
        'screen': '1024x1366', 'platform': 'iPad', 'language': 'it-IT', 'timezone': 'Europe/Rome',
        'touch': True, 'cores': 8, 'memory': 8,
    },
    # Shubhali devicelar
    'curl_bot': {
        'ua': 'curl/8.4.0',
        'screen': '', 'platform': '', 'language': '', 'timezone': '',
        'touch': False, 'cores': 0, 'memory': 0,
    },
    'python_bot': {
        'ua': 'python-requests/2.31.0',
        'screen': '', 'platform': '', 'language': '', 'timezone': '',
        'touch': False, 'cores': 0, 'memory': 0,
    },
}

# IP'lar — har xil case uchun
IPS = {
    'tourist_jp_1': '203.0.113.42',  # Yapon turist
    'tourist_us_1': '198.51.100.21',
    'tourist_us_2': '198.51.100.22',
    'tourist_cn_1': '203.0.113.88',
    'tourist_fr_1': '198.51.100.55',
    'tourist_de_1': '203.0.113.99',
    'tourist_es_1': '198.51.100.77',
    'tourist_kr_1': '203.0.113.150',
    'tourist_in_1': '198.51.100.200',
    'tourist_ae_1': '203.0.113.180',
    # UZ ISP'lar
    'uz_ucell_1': '195.158.16.45',
    'uz_ucell_2': '195.158.16.78',
    'uz_beeline_1': '94.158.32.101',
    'uz_uztelecom_1': '213.230.108.55',
    # Aeroport Wi-Fi
    'airport_tas': '178.218.207.10',
    # Fraud: staff bilan share qilingan
    'fraud_shared_1': '94.158.50.200',  # postallaridan birida loginlik staff + public
    'fraud_shared_2': '94.158.50.201',
    # High-volume IP
    'spammer_ip': '5.188.100.50',
    # Office Wi-Fi (subnet)
    'office_wifi_1': '178.218.100.51',
    'office_wifi_2': '178.218.100.52',
}

# Inbound: davlatlar va kelish maqsadlari
INBOUND_COUNTRIES = ['Japan', 'United States', 'China', 'France', 'Germany', 'Spain', 'Italy', 'South Korea', 'India', 'UAE', 'United Kingdom', 'Russia']
PURPOSES = ['leisure', 'friends', 'business', 'education', 'health', 'religion']
ACCOMMODATIONS = [0, 1, 2, 3, 4, 5, 6]  # 0=hotel, 1=rented, etc.

# Outbound: davlatlar
OUTBOUND_COUNTRIES = ['Turkey', 'Kazakhstan', 'Russia', 'UAE', 'Saudi Arabia', 'Egypt', 'Thailand', 'South Korea', 'China', 'Germany']

# GPS — turli joylar
GPS_AIRPORTS = {
    'Toshkent xalqaro aeroporti': (41.2579, 69.2812),
    'Samarqand xalqaro aeroporti': (39.7008, 66.9839),
    'Buxoro xalqaro aeroporti': (39.7747, 64.4286),
    'Urgench xalqaro aeroporti': (41.5848, 60.6417),
    'Namangan xalqaro aeroporti': (40.9846, 71.5567),
}
GPS_HOTELS = [
    (41.3275, 69.2817),  # Toshkent markaz mehmonxonalari
    (41.3110, 69.2401),
    (39.6542, 66.9597),  # Samarqand Registon yaqin
    (39.7758, 64.4214),  # Buxoro Eski shahar
    (41.5783, 60.6240),  # Xiva
    (41.3155, 69.2483),
]


# ============================================================
# Helperlar
# ============================================================

def _now_minus(days=0, hours=0, minutes=0):
    return timezone.now() - timedelta(days=days, hours=hours, minutes=minutes)


def _build_inbound_data(country, purpose='leisure', nights=4, with_full=True):
    """Inbound so'rovnoma uchun realistik JSON data."""
    data = {
        'q1': country,
        'q2': 'same',
        'q3': purpose,
        'q5_nights': nights,
        'q5_zero': False,
        'q6': {
            'Tashkent': {'nights': max(1, nights // 2)},
            'Samarkand': {'nights': nights - max(1, nights // 2)},
        },
        'q7': random.choice(ACCOMMODATIONS),
        'q8': {'restaurants': True, 'national': True},
        'q9': random.choice(['yes', 'no']),
        'q13': 'airplane',
        'q13_airline': random.choice(['uzair', 'other']),
        'q14': 'airplane',
        'q14_airline': random.choice(['uzair', 'other']),
        'q16_sum': random.randint(500, 5000),
        'q16_currency': 'USD',
        'q16_persons': random.randint(1, 4),
        'q19': '',
    }
    if data['q9'] == 'yes':
        data['q10_total'] = nights + 2
        data['q10_uz'] = nights
        data['q11'] = data['q16_persons']
        data['q12_amount'] = random.randint(1000, 4000)
        data['q12_currency'] = 'USD'
    if with_full:
        # Q17 xarajatlar
        data['q17'] = {
            f'r{i}': {
                'amount': random.randint(50, 800),
                'currency': 'USD',
                'inPackage': False,
            }
            for i in range(1, 15) if random.random() > 0.3
        }
        # Q18 ratinglar
        data['q18'] = {f'r{i}': random.randint(6, 10) for i in range(12)}
    return data


def _build_outbound_data(country, purpose='leisure', nights=5):
    data = {
        'q1': country,
        'q2': purpose,
        'q4_val': nights,
        'q5': random.choice(['hotel', 'rented', 'friends', 'own']),
        'q6': random.choice(['yes', 'no']),
        'q10': 'airplane',
        'q10_airline': random.choice(['uzair', 'other']),
        'q11': 'airplane',
        'q11_airline': random.choice(['uzair', 'other']),
        'q13_amount': random.randint(400, 3500),
        'q13_currency': 'USD',
        'q13_persons': random.randint(1, 4),
    }
    if data['q6'] == 'yes':
        data['q7'] = nights + 1
        data['q8'] = data['q13_persons']
        data['q9_amount'] = random.randint(800, 3000)
        data['q9_currency'] = 'USD'
    data['q14'] = {
        f'r{n}': {
            'amount': random.randint(40, 600),
            'currency': 'USD',
            'inPkg': False,
        }
        for n in ['1', '2', '3', '4', '5', '11', '13'] if random.random() > 0.3
    }
    return data


def _make(**kwargs):
    """SurveyResponse yaratadi va parsed UA fields'ni avtomatik to'ldiradi."""
    device_info = kwargs.get('device_info') or {}
    ua = device_info.get('ua', '') or kwargs.get('user_agent', '')
    parsed = parse_user_agent(ua)
    kwargs.setdefault('user_agent', ua[:500])
    kwargs.setdefault('device_type', parsed['device_type'])
    kwargs.setdefault('os_name', parsed['os_name'][:30])
    kwargs.setdefault('browser_name', parsed['browser_name'][:30])
    kwargs.setdefault('is_completed', True)
    kwargs.setdefault('language', 'en')
    kwargs.setdefault('location_granted', True)
    kwargs.setdefault('screening_status', SurveyResponse.SCREENING_ELIGIBLE)
    kwargs.setdefault(
        'screening_data',
        {'F1': 'yes', 'F2': 'no'} if kwargs.get('survey_type') == SurveyResponse.SURVEY_INBOUND else {'F1': 'yes', 'F2': 'no'},
    )
    started = kwargs.get('started_at') or _now_minus()
    completed = started + timedelta(milliseconds=kwargs.get('fill_duration_ms', 300_000))
    kwargs.setdefault('completed_at', completed)
    # Auto-compute summary from data
    d = kwargs.get('data') or {}
    if kwargs.get('survey_type') == SurveyResponse.SURVEY_INBOUND:
        kwargs.setdefault('country', d.get('q1', ''))
        kwargs.setdefault('purpose', d.get('q3', ''))
        if d.get('q5_nights') is not None:
            kwargs.setdefault('nights', d.get('q5_nights'))
        kwargs.setdefault('total_spent', Decimal(str(d.get('q16_sum') or 0)) or None)
        kwargs.setdefault('spent_currency', d.get('q16_currency', '') or '')
    else:
        kwargs.setdefault('country', d.get('q1', ''))
        kwargs.setdefault('purpose', d.get('q2', ''))
        kwargs.setdefault('nights', d.get('q4_val'))
        kwargs.setdefault('total_spent', Decimal(str(d.get('q13_amount') or 0)) or None)
        kwargs.setdefault('spent_currency', d.get('q13_currency', '') or '')
    # `started_at` auto_now_add — uni majburiy o'rnatish uchun bypass
    obj = SurveyResponse.objects.create(**{k: v for k, v in kwargs.items() if k != 'started_at'})
    if 'started_at' in kwargs:
        SurveyResponse.objects.filter(pk=obj.pk).update(started_at=kwargs['started_at'])
    return obj


class Command(BaseCommand):
    help = "30 ta turli case'li SurveyResponse yaratadi (toza + fraud signal'lari)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help="Avval mavjud SurveyResponse'larni o'chirib qayta yaratadi (DIQQAT)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options.get('reset'):
            cnt = SurveyResponse.objects.all().delete()[0]
            self.stdout.write(self.style.WARNING(f"⚠ {cnt} ta eski yozuv o'chirildi"))

        # Postal officelarni olib kelamiz
        offices = list(PostalOffice.objects.filter(is_active=True))
        if not offices:
            self.stdout.write(self.style.ERROR(
                "Pochta bo'limlari yo'q. Avval `python manage.py seed_data` ishga tushiring."
            ))
            return

        # Staff foydalanuvchilarni olib kelamiz (StaffProfile bilan)
        staff_users = list(User.objects.filter(staff_profile__isnull=False).select_related('staff_profile')[:20])
        if not staff_users:
            self.stdout.write(self.style.ERROR(
                "Staff yo'q. Avval `python manage.py import_interviewers` ishga tushiring."
            ))
            return

        created = []

        # ============================================================
        # GURUH A: Toza Inbound public (5 ta) — turli davlat va devicelar
        # ============================================================
        clean_inbound_cases = [
            ('Japan', 'iphone_safari_ja', IPS['tourist_jp_1'], 'en', GPS_HOTELS[0], 4),
            ('United States', 'iphone_safari', IPS['tourist_us_1'], 'en', GPS_HOTELS[1], 6),
            ('China', 'xiaomi_chrome', IPS['tourist_cn_1'], 'en', GPS_HOTELS[2], 5),
            ('France', 'pixel_chrome', IPS['tourist_fr_1'], 'en', GPS_HOTELS[3], 7),
            ('Germany', 'huawei_chrome', IPS['tourist_de_1'], 'en', GPS_HOTELS[4], 3),
        ]
        for i, (country, dev_key, ip, lang, (lat, lon), nights) in enumerate(clean_inbound_cases):
            dev = DEVICES[dev_key]
            ts = _now_minus(days=random.randint(0, 5), hours=random.randint(0, 23))
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language=lang,
                data=_build_inbound_data(country, 'leisure', nights),
                ip_address=ip,
                device_info=dev,
                latitude=Decimal(str(lat)), longitude=Decimal(str(lon)),
                location_accuracy=random.uniform(10, 50),
                started_at=ts,
                fill_duration_ms=random.randint(180_000, 480_000),  # 3-8 daqiqa
            ))

        self.stdout.write(self.style.SUCCESS(f"✅ Toza inbound public: {len(clean_inbound_cases)} ta"))

        # ============================================================
        # GURUH B: Toza Outbound public (5 ta) — UZ fuqarolari xorijdan qaytgan
        # ============================================================
        clean_outbound_cases = [
            ('Turkey', 'samsung_chrome', IPS['uz_ucell_1'], 'uz', GPS_AIRPORTS['Toshkent xalqaro aeroporti'], 8),
            ('Kazakhstan', 'samsung_chrome', IPS['uz_uztelecom_1'], 'ru', GPS_AIRPORTS['Toshkent xalqaro aeroporti'], 4),
            ('Russia', 'xiaomi_chrome', IPS['uz_beeline_1'], 'ru', GPS_HOTELS[0], 10),
            ('UAE', 'iphone_safari', IPS['uz_ucell_2'], 'uz', GPS_AIRPORTS['Samarqand xalqaro aeroporti'], 5),
            ('Saudi Arabia', 'huawei_chrome', IPS['airport_tas'], 'uz', GPS_AIRPORTS['Toshkent xalqaro aeroporti'], 7),
        ]
        for country, dev_key, ip, lang, (lat, lon), nights in clean_outbound_cases:
            dev = DEVICES[dev_key]
            ts = _now_minus(days=random.randint(0, 7), hours=random.randint(0, 23))
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_OUTBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language=lang,
                data=_build_outbound_data(country, 'leisure', nights),
                ip_address=ip,
                device_info=dev,
                latitude=Decimal(str(lat)), longitude=Decimal(str(lon)),
                location_accuracy=random.uniform(10, 50),
                started_at=ts,
                fill_duration_ms=random.randint(200_000, 500_000),
            ))
        self.stdout.write(self.style.SUCCESS(f"✅ Toza outbound public: {len(clean_outbound_cases)} ta"))

        # ============================================================
        # GURUH C: Toza staff inbound (5 ta) — har xil aeroport staff
        # ============================================================
        for i in range(5):
            staff = random.choice(staff_users)
            office = staff.staff_profile.postal_office
            # GPS — yaqin aeroport koordinatasi (agar bor bo'lsa) yoki random office
            office_gps = None
            for name, coords in GPS_AIRPORTS.items():
                if name in office.name:
                    office_gps = coords
                    break
            if office_gps is None:
                office_gps = (41.3275 + random.uniform(-0.5, 0.5), 69.2817 + random.uniform(-0.5, 0.5))
            country = random.choice(INBOUND_COUNTRIES)
            ts = _now_minus(days=random.randint(0, 10), hours=random.randint(8, 18))
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_STAFF,
                staff=staff,
                postal_office=office,
                language=random.choice(['en', 'ru']),
                data=_build_inbound_data(country, 'leisure', random.randint(3, 10)),
                ip_address=IPS['office_wifi_1'],
                device_info=DEVICES['windows_chrome'],
                latitude=Decimal(str(office_gps[0])),
                longitude=Decimal(str(office_gps[1])),
                location_accuracy=random.uniform(15, 30),
                started_at=ts,
                fill_duration_ms=random.randint(150_000, 350_000),
            ))
        self.stdout.write(self.style.SUCCESS("✅ Toza staff inbound: 5 ta"))

        # ============================================================
        # GURUH D: Toza staff outbound (3 ta)
        # ============================================================
        for i in range(3):
            staff = random.choice(staff_users)
            office = staff.staff_profile.postal_office
            office_gps = None
            for name, coords in GPS_AIRPORTS.items():
                if name in office.name:
                    office_gps = coords
                    break
            if office_gps is None:
                office_gps = (41.3275, 69.2817)
            country = random.choice(OUTBOUND_COUNTRIES)
            ts = _now_minus(days=random.randint(0, 10), hours=random.randint(8, 18))
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_OUTBOUND,
                source=SurveyResponse.SOURCE_STAFF,
                staff=staff,
                postal_office=office,
                language=random.choice(['uz', 'ru']),
                data=_build_outbound_data(country, 'leisure', random.randint(3, 10)),
                ip_address=IPS['office_wifi_2'],
                device_info=DEVICES['windows_edge'],
                latitude=Decimal(str(office_gps[0])),
                longitude=Decimal(str(office_gps[1])),
                location_accuracy=random.uniform(15, 30),
                started_at=ts,
                fill_duration_ms=random.randint(120_000, 300_000),
            ))
        self.stdout.write(self.style.SUCCESS("✅ Toza staff outbound: 3 ta"))

        # ============================================================
        # GURUH E: FRAUD R1 — staff va public bir IP'dan (3 ta)
        # ============================================================
        suspect_staff = staff_users[0]
        suspect_office = suspect_staff.staff_profile.postal_office
        suspect_office_gps = None
        for name, coords in GPS_AIRPORTS.items():
            if name in suspect_office.name:
                suspect_office_gps = coords
                break
        if suspect_office_gps is None:
            suspect_office_gps = (41.3275, 69.2817)

        # 1 ta staff yozuv — IP'si fraud_shared_1
        created.append(_make(
            survey_type=SurveyResponse.SURVEY_INBOUND,
            source=SurveyResponse.SOURCE_STAFF,
            staff=suspect_staff,
            postal_office=suspect_office,
            language='ru',
            data=_build_inbound_data('Russia', 'business', 5),
            ip_address=IPS['fraud_shared_1'],
            device_info=DEVICES['windows_chrome'],
            latitude=Decimal(str(suspect_office_gps[0])),
            longitude=Decimal(str(suspect_office_gps[1])),
            location_accuracy=20.0,
            started_at=_now_minus(days=1, hours=10),
            fill_duration_ms=240_000,
        ))
        # 2 ta public yozuv — bir xil IP'dan (fraud_shared_1)
        for cnt in range(2):
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language='en',
                data=_build_inbound_data(random.choice(['Japan', 'Germany']), 'leisure', 4),
                ip_address=IPS['fraud_shared_1'],  # SAME IP as staff
                device_info=DEVICES['windows_chrome'],
                latitude=Decimal(str(suspect_office_gps[0])),
                longitude=Decimal(str(suspect_office_gps[1])),
                location_accuracy=22.0,
                started_at=_now_minus(days=1, hours=12 + cnt),
                fill_duration_ms=210_000,
            ))
        self.stdout.write(self.style.SUCCESS("🚨 Fraud R1 (staff+public bir IP): 3 ta"))

        # ============================================================
        # GURUH F: FRAUD R2 — high-volume IP (12 ta public bir IP'dan)
        # ============================================================
        for i in range(12):
            dev_key = random.choice(['iphone_safari', 'samsung_chrome', 'xiaomi_chrome'])
            country = random.choice(INBOUND_COUNTRIES)
            ts = _now_minus(days=0, hours=random.randint(0, 23), minutes=random.randint(0, 59))
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language='en',
                data=_build_inbound_data(country, random.choice(PURPOSES), random.randint(2, 7)),
                ip_address=IPS['spammer_ip'],  # bir xil IP, 12 marta
                device_info=DEVICES[dev_key],
                latitude=Decimal(str(GPS_HOTELS[i % len(GPS_HOTELS)][0])),
                longitude=Decimal(str(GPS_HOTELS[i % len(GPS_HOTELS)][1])),
                location_accuracy=random.uniform(20, 60),
                started_at=ts,
                fill_duration_ms=random.randint(100_000, 200_000),
            ))
        self.stdout.write(self.style.SUCCESS("🚨 Fraud R2 (high-volume IP, 12 ta): 12 ta"))

        # ============================================================
        # GURUH G: FRAUD R5 — bot UA (2 ta)
        # ============================================================
        for bot_key in ['curl_bot', 'python_bot']:
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language='en',
                data=_build_inbound_data('United States', 'leisure', 3, with_full=False),
                ip_address='185.220.101.50',
                device_info=DEVICES[bot_key],
                latitude=None, longitude=None,
                location_granted=False, location_accuracy=None,
                started_at=_now_minus(days=2, hours=random.randint(0, 23)),
                fill_duration_ms=2_500,  # 2.5 sek — bot
            ))
        self.stdout.write(self.style.SUCCESS("🚨 Fraud R5 (bot UA): 2 ta"))

        # ============================================================
        # GURUH H: FRAUD R4 — burst (1 daqiqa ichida 4 ta)
        # ============================================================
        burst_ts = _now_minus(days=3, hours=15, minutes=30)
        for i in range(4):
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language='en',
                data=_build_inbound_data(random.choice(INBOUND_COUNTRIES), 'leisure', 4),
                ip_address='91.214.69.99',
                device_info=DEVICES['windows_chrome'],
                latitude=Decimal('41.3275'),
                longitude=Decimal('69.2817'),
                location_accuracy=30.0,
                # Hammasi bir daqiqada
                started_at=burst_ts + timedelta(seconds=i * 12),
                fill_duration_ms=12_000,
            ))
        self.stdout.write(self.style.SUCCESS("🚨 Fraud R4 (burst, 4 ta 1 daq.da): 4 ta"))

        # ============================================================
        # GURUH I: FRAUD R6 — fast fill (45 sek) (1 ta)
        # ============================================================
        created.append(_make(
            survey_type=SurveyResponse.SURVEY_INBOUND,
            source=SurveyResponse.SOURCE_PUBLIC,
            language='en',
            data=_build_inbound_data('United Kingdom', 'leisure', 2),
            ip_address='185.45.150.10',
            device_info=DEVICES['iphone_safari'],
            latitude=Decimal('41.3110'),
            longitude=Decimal('69.2401'),
            location_accuracy=15.0,
            started_at=_now_minus(days=4, hours=10),
            fill_duration_ms=45_000,  # 45 soniya — juda tez
        ))
        self.stdout.write(self.style.SUCCESS("🚨 Fraud R6 (fast fill 45s): 1 ta"))

        # ============================================================
        # GURUH J: FRAUD R3 — device fingerprint takrori (5 ta bir xil device)
        # ============================================================
        same_dev = DEVICES['iphone_safari']  # bir xil fingerprint
        for i in range(5):
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language='en',
                data=_build_inbound_data(random.choice(INBOUND_COUNTRIES), 'leisure', 3),
                ip_address=f"94.158.{60+i}.{100+i}",
                device_info=same_dev,
                latitude=Decimal(str(GPS_HOTELS[i % len(GPS_HOTELS)][0])),
                longitude=Decimal(str(GPS_HOTELS[i % len(GPS_HOTELS)][1])),
                location_accuracy=25.0,
                started_at=_now_minus(days=5, hours=random.randint(8, 22)),
                fill_duration_ms=180_000,
            ))
        self.stdout.write(self.style.SUCCESS("🚨 Fraud R3 (device fingerprint takrori, 5 ta): 5 ta"))

        # ============================================================
        # GURUH K: Multi-language Inbound (15 ta) — turli til va davlatlar
        # ============================================================
        # Til -> tipik mamlakat va device kombinatsiyalari
        multilang_inbound = [
            # (lang, country, device_key, base_ip)
            ('ar', 'Saudi Arabia', 'iphone_safari', '5.42.180.10'),
            ('ar', 'UAE',          'samsung_chrome', '5.42.180.11'),
            ('zh', 'China',        'xiaomi_chrome', '101.32.50.20'),
            ('zh', 'China',        'huawei_chrome', '101.32.50.21'),
            ('zh', 'China',        'iphone_safari', '101.32.50.22'),
            ('fr', 'France',       'pixel_chrome', '92.100.40.30'),
            ('fr', 'France',       'mac_safari', '92.100.40.31'),
            ('de', 'Germany',      'huawei_chrome', '85.220.60.40'),
            ('de', 'Germany',      'windows_chrome', '85.220.60.41'),
            ('it', 'Italy',        'ipad_safari', '79.150.70.50'),
            ('it', 'Italy',        'iphone_safari', '79.150.70.51'),
            ('es', 'Spain',        'mac_safari', '88.5.80.60'),
            ('es', 'Spain',        'samsung_chrome', '88.5.80.61'),
            ('tg', 'Tajikistan',   'xiaomi_chrome', '92.51.90.70'),
            ('tg', 'Tajikistan',   'samsung_chrome', '92.51.90.71'),
        ]
        for lang, country, dev_key, ip in multilang_inbound:
            dev = dict(DEVICES[dev_key])
            # Device fingerprint'ni tilga moslab yangilash (language/timezone)
            lang_overrides = {
                'ar': ('ar-SA', 'Asia/Riyadh'),
                'zh': ('zh-CN', 'Asia/Shanghai'),
                'fr': ('fr-FR', 'Europe/Paris'),
                'de': ('de-DE', 'Europe/Berlin'),
                'it': ('it-IT', 'Europe/Rome'),
                'es': ('es-ES', 'Europe/Madrid'),
                'tg': ('tg-TJ', 'Asia/Dushanbe'),
            }
            if lang in lang_overrides:
                dev['language'], dev['timezone'] = lang_overrides[lang]
            # GPS — Toshkent/Samarqand mehmonxonalar (turist UZ'da)
            gps = GPS_HOTELS[random.randint(0, len(GPS_HOTELS) - 1)]
            ts = _now_minus(days=random.randint(0, 14), hours=random.randint(0, 23))
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_INBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language=lang,
                data=_build_inbound_data(country, random.choice(PURPOSES), random.randint(3, 9)),
                ip_address=ip,
                device_info=dev,
                latitude=Decimal(str(gps[0])),
                longitude=Decimal(str(gps[1])),
                location_accuracy=random.uniform(15, 60),
                started_at=ts,
                fill_duration_ms=random.randint(200_000, 500_000),
            ))
        self.stdout.write(self.style.SUCCESS(
            f"🌐 Multi-lang Inbound: {len(multilang_inbound)} ta (ar/zh/fr/de/it/es/tg)"
        ))

        # ============================================================
        # GURUH L: Outbound diversity (25 ta) — turli til va sayohat davlatlari
        # ============================================================
        # UZ fuqarolari — qaysi davlatga sayohat qildi va qaysi tilda javob berdi
        OUTBOUND_LANG_OPTIONS = ['uz', 'ru']
        EXTENDED_OUTBOUND_COUNTRIES = [
            'Turkey', 'Kazakhstan', 'Russia', 'UAE', 'Saudi Arabia', 'Egypt', 'Thailand',
            'South Korea', 'China', 'Germany', 'Iran', 'Iraq', 'Tajikistan', 'Kyrgyzstan',
            'Azerbaijan', 'Vietnam', 'Singapore', 'Malaysia', 'India', 'United Kingdom',
            'France', 'Italy', 'Spain', 'Japan', 'Pakistan',
        ]
        UZ_DEVICES = ['samsung_chrome', 'xiaomi_chrome', 'huawei_chrome',
                      'iphone_safari', 'windows_chrome', 'windows_edge']
        UZ_IPS = [
            '195.158.16.45', '195.158.16.78', '195.158.16.121', '195.158.17.20',
            '94.158.32.101', '94.158.32.152', '94.158.50.50', '94.158.50.99',
            '213.230.108.55', '213.230.109.10', '213.230.109.88',
            '178.218.207.10', '178.218.207.55', '178.218.150.30',
            '84.54.64.20', '84.54.64.150', '84.54.80.5',
        ]
        # UZ GPS — turli viloyatlar
        UZ_RETURN_GPS = [
            (41.2579, 69.2812),  # Toshkent aeroport
            (41.3275, 69.2817),  # Toshkent markaz
            (41.3110, 69.2401),  # Toshkent boshqa
            (39.7008, 66.9839),  # Samarqand aeroport
            (39.6542, 66.9597),  # Samarqand markaz
            (39.7747, 64.4286),  # Buxoro aeroport
            (39.7758, 64.4214),  # Buxoro markaz
            (40.9846, 71.5567),  # Namangan aeroport
            (41.5848, 60.6417),  # Urgench aeroport
            (40.5283, 70.9425),  # Andijon
            (40.3717, 71.7842),  # Farg'ona
        ]
        for i in range(25):
            lang = OUTBOUND_LANG_OPTIONS[i % 2]  # uz va ru navbatma-navbat
            country = EXTENDED_OUTBOUND_COUNTRIES[i % len(EXTENDED_OUTBOUND_COUNTRIES)]
            dev_key = UZ_DEVICES[i % len(UZ_DEVICES)]
            dev = dict(DEVICES[dev_key])
            # Til'ga moslash
            dev['language'] = f"{lang}-UZ" if lang == 'uz' else 'ru-RU'
            dev['timezone'] = 'Asia/Tashkent'
            ip = UZ_IPS[i % len(UZ_IPS)]
            gps = UZ_RETURN_GPS[i % len(UZ_RETURN_GPS)]
            # Purpose — turli
            purpose = random.choice(['leisure', 'friends', 'business', 'religion', 'health', 'education'])
            ts = _now_minus(days=random.randint(0, 21), hours=random.randint(0, 23))
            created.append(_make(
                survey_type=SurveyResponse.SURVEY_OUTBOUND,
                source=SurveyResponse.SOURCE_PUBLIC,
                language=lang,
                data=_build_outbound_data(country, purpose, random.randint(2, 14)),
                ip_address=ip,
                device_info=dev,
                latitude=Decimal(str(gps[0])),
                longitude=Decimal(str(gps[1])),
                location_accuracy=random.uniform(10, 60),
                started_at=ts,
                fill_duration_ms=random.randint(150_000, 550_000),
            ))
        self.stdout.write(self.style.SUCCESS(
            "🌐 Outbound diversity: 25 ta (uz/ru, har xil davlatlar va maqsadlar)"
        ))

        # ============================================================
        # Yakuniy hisobot
        # ============================================================
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f"🎉 Jami {len(created)} ta SurveyResponse yaratildi"))
        self.stdout.write(self.style.SUCCESS(f"   DB'da hozir jami: {SurveyResponse.objects.count()} ta"))
        self.stdout.write('')
        self.stdout.write("Endi /staff/monitoring/ ga kirib quyidagilarni ko'rishingiz mumkin:")
        self.stdout.write("  • 🛬 Inbound — Public/Staff sub-tablar")
        self.stdout.write("  • 🛫 Outbound — Public/Staff sub-tablar")
        self.stdout.write("  • 🌐 IP-lar tab — Fraud markirovka, staff+public bir IP'da")
        self.stdout.write("  • 📱 Devicelar tab — Device fingerprint takrori")
        self.stdout.write("  • 🚨 Riskler tab — Critical/High/Medium darajalar")
