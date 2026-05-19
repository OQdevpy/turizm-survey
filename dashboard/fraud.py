"""Fraud / shubhali harakatlarni aniqlash.

Bu modul SurveyResponse jadvalida turli signallar bo'yicha shubhali
harakatlarni aniqlaydi va risk score (0-100) hisoblaydi.

Aniqlangan signallar:
  R1. IP cross-reference — bir IP'dan ham staff (loginlik) ham public so'rovnoma
  R2. High-volume IP — bir IP'dan ko'p public so'rovnoma kelmoqda
  R3. Device fingerprint takrori — bir telefon/brauzer ko'p public uchun
  R4. Tezlik (burst) — bir IP'dan qisqa vaqt ichida ko'p submission
  R5. Bot UA — UA'da bot/crawler/script keywords
  R6. Tez to'ldirish — fill_duration ortiqcha qisqa (5 minutdan kam)
  R7. Staff GPS — pochta bo'limidan uzoq (GPS bor bo'lsa)
  R8. Public GPS = pochta bo'limi binosi — public yozuv staff joyida
"""
from collections import Counter, defaultdict
from datetime import timedelta

from surveys.models import SurveyResponse
from surveys.utils import device_fingerprint, haversine_distance_km, ip_to_subnet24


# Risk konstantalari (har signal nechta ball qo'shadi — jami 100 dan)
WEIGHT_STAFF_PUBLIC_IP = 35   # eng kuchli
WEIGHT_HIGH_VOLUME_IP = 20
WEIGHT_FAST_FILL = 10         # 5 daqiqadan kam
WEIGHT_BURST = 15             # 1 daq.da 3+
WEIGHT_BOT_UA = 25
WEIGHT_DEVICE_REUSE = 15
WEIGHT_STAFF_FAR_GPS = 10     # staff pochta bo'limidan 50km+ uzoq
WEIGHT_PUBLIC_AT_OFFICE = 20  # public so'rovnoma pochta bo'limi atrofida

# Chegaralar
HIGH_VOLUME_THRESHOLD = 10      # bir IP'dan kuni 10+ public — shubhali
FAST_FILL_THRESHOLD_MS = 5 * 60 * 1000   # 5 minutdan kam
BURST_WINDOW_SEC = 60
BURST_THRESHOLD = 3
STAFF_FAR_GPS_KM = 50           # staff o'z bo'limidan 50km+
PUBLIC_NEAR_OFFICE_KM = 0.5     # public so'rovnoma 500m radiusda


def _classify(score):
    """Risk darajasini aniqlaydi: low/medium/high/critical."""
    if score >= 60:
        return 'critical'
    if score >= 35:
        return 'high'
    if score >= 15:
        return 'medium'
    return 'low'


def _gather_indices(qs):
    """Cross-reference uchun zarur indekslarni quradi.

    Qaytaradi:
        ip_to_sources: dict[ip] = {'public': N, 'staff': N}
        ip_volume: dict[ip] = total public count
        device_volume: dict[fingerprint] = total public count
        burst_buckets: dict[(ip, minute_bucket)] = count
    """
    ip_to_sources = defaultdict(lambda: {'public': 0, 'staff': 0})
    ip_volume = Counter()  # faqat public
    device_volume = Counter()  # faqat public
    burst_buckets = Counter()

    # qs ni iterator bilan o'tamiz (xotira xavfsizligi)
    iterable = qs.only(
        'id', 'ip_address', 'source', 'started_at', 'device_info', 'survey_type',
    ).iterator(chunk_size=500)
    for r in iterable:
        ip = r.ip_address or ''
        if ip:
            ip_to_sources[ip][r.source] += 1
            if r.source == SurveyResponse.SOURCE_PUBLIC:
                ip_volume[ip] += 1
                if r.started_at:
                    bucket = (ip, r.started_at.strftime('%Y-%m-%d %H:%M'))
                    burst_buckets[bucket] += 1
        fp = device_fingerprint(r.device_info or {})
        if fp and r.source == SurveyResponse.SOURCE_PUBLIC:
            device_volume[fp] += 1

    return {
        'ip_to_sources': dict(ip_to_sources),
        'ip_volume': dict(ip_volume),
        'device_volume': dict(device_volume),
        'burst_buckets': dict(burst_buckets),
    }


def evaluate_response(r, indices, postal_office_coords=None):
    """Bitta SurveyResponse uchun risk score va sabablar.

    Args:
        r: SurveyResponse instance (kerakli maydonlar bilan)
        indices: _gather_indices() natijasi
        postal_office_coords: dict[postal_office_id] = (lat, lon)

    Qaytaradi: (score: int 0-100, reasons: list[dict])
    """
    score = 0
    reasons = []
    ip = r.ip_address or ''
    fp = device_fingerprint(r.device_info or {}) if r.device_info else ''

    # R1: IP bir vaqtning o'zida staff va public so'rovnoma yuborgan
    if ip:
        sources = indices['ip_to_sources'].get(ip, {})
        if sources.get('staff', 0) > 0 and sources.get('public', 0) > 0:
            score += WEIGHT_STAFF_PUBLIC_IP
            reasons.append({
                'code': 'staff_public_same_ip',
                'severity': 'critical',
                'label': "Bir IP'dan ham staff (login bilan) ham public so'rovnoma kelgan",
                'detail': f"IP: {ip} — staff: {sources['staff']}, public: {sources['public']}",
            })

    # R2: High-volume IP (public)
    if ip and r.source == SurveyResponse.SOURCE_PUBLIC:
        volume = indices['ip_volume'].get(ip, 0)
        if volume >= HIGH_VOLUME_THRESHOLD:
            score += WEIGHT_HIGH_VOLUME_IP
            reasons.append({
                'code': 'high_volume_ip',
                'severity': 'high',
                'label': f"Bu IP'dan {volume} ta public so'rovnoma kelgan (chegara: {HIGH_VOLUME_THRESHOLD})",
                'detail': f"IP: {ip}",
            })

    # R3: Device fingerprint takrori
    if fp and r.source == SurveyResponse.SOURCE_PUBLIC:
        vol = indices['device_volume'].get(fp, 0)
        if vol >= 5:
            score += WEIGHT_DEVICE_REUSE
            reasons.append({
                'code': 'device_reuse',
                'severity': 'high',
                'label': f"Bir device'dan {vol} ta public so'rovnoma yuborilgan",
                'detail': f"Fingerprint: {fp}",
            })

    # R4: Burst — 1 daqiqada 3+ submission shu IP'dan
    if ip and r.started_at:
        bucket = (ip, r.started_at.strftime('%Y-%m-%d %H:%M'))
        burst = indices['burst_buckets'].get(bucket, 0)
        if burst >= BURST_THRESHOLD:
            score += WEIGHT_BURST
            reasons.append({
                'code': 'burst',
                'severity': 'high',
                'label': f"1 daqiqa ichida {burst} ta so'rovnoma — bot belgisi",
                'detail': f"IP: {ip}, vaqt: {r.started_at:%H:%M}",
            })

    # R5: Bot UA
    if (r.device_type or '') == SurveyResponse.DEVICE_BOT:
        score += WEIGHT_BOT_UA
        reasons.append({
            'code': 'bot_ua',
            'severity': 'critical',
            'label': "User-Agent bot/crawler signaturasiga ega",
            'detail': (r.user_agent or '')[:80],
        })

    # R6: Tez to'ldirish (< 5 min)
    if r.fill_duration_ms is not None and r.fill_duration_ms < FAST_FILL_THRESHOLD_MS:
        # Faqat haqiqatan tez bo'lsa belgilash (juda qisqa)
        if r.fill_duration_ms < 90 * 1000:  # 90 sek dan kam — juda shubhali
            score += WEIGHT_FAST_FILL
            sec = round(r.fill_duration_ms / 1000)
            reasons.append({
                'code': 'fast_fill',
                'severity': 'medium',
                'label': f"To'ldirish vaqti juda qisqa ({sec} sek)",
                'detail': f"Odatda 3-5 daqiqa kerak",
            })

    # R7/R8: GPS asosida — agar koordinatalar va pochta bo'limi koordinatasi mavjud bo'lsa
    if postal_office_coords and r.latitude is not None and r.longitude is not None:
        if r.source == SurveyResponse.SOURCE_STAFF and r.postal_office_id:
            office_coords = postal_office_coords.get(r.postal_office_id)
            if office_coords:
                dist = haversine_distance_km(
                    r.latitude, r.longitude, office_coords[0], office_coords[1],
                )
                if dist is not None and dist > STAFF_FAR_GPS_KM:
                    score += WEIGHT_STAFF_FAR_GPS
                    reasons.append({
                        'code': 'staff_far_gps',
                        'severity': 'medium',
                        'label': f"Staff o'z pochta bo'limidan {dist} km uzoqda to'ldirgan",
                        'detail': f"Chegara: {STAFF_FAR_GPS_KM} km",
                    })
        elif r.source == SurveyResponse.SOURCE_PUBLIC:
            # Public so'rovnoma biror pochta bo'limi yaqinida bo'lsa — shubhali
            for office_id, (olat, olon) in postal_office_coords.items():
                dist = haversine_distance_km(r.latitude, r.longitude, olat, olon)
                if dist is not None and dist < PUBLIC_NEAR_OFFICE_KM:
                    score += WEIGHT_PUBLIC_AT_OFFICE
                    reasons.append({
                        'code': 'public_at_office',
                        'severity': 'high',
                        'label': f"Public so'rovnoma pochta bo'limi binosida (#{office_id}) to'ldirilgan",
                        'detail': f"Masofa: {dist} km",
                    })
                    break

    # Score chegarasi
    score = min(score, 100)
    return score, reasons


def evaluate_all(qs, postal_office_coords=None, only_risky=False, top_n=200):
    """Querysetdagi har bir SurveyResponse uchun risk hisoblaydi.

    Args:
        qs: SurveyResponse queryset
        postal_office_coords: optional dict[office_id] = (lat, lon)
        only_risky: True bo'lsa, faqat score>0 bo'lganlarni qaytaradi
        top_n: maksimal natija soni

    Qaytaradi: list of {
        'response': r, 'score': int, 'level': 'low|medium|high|critical', 'reasons': [...]
    }, score DESC bo'yicha sortlangan.
    """
    indices = _gather_indices(qs)

    # Endi har bir yozuvni baholash — kerakli maydonlarni olib kelamiz
    detailed_qs = qs.select_related('staff', 'postal_office').only(
        'id', 'survey_type', 'source', 'language', 'country',
        'ip_address', 'user_agent', 'device_info', 'device_type', 'os_name',
        'browser_name', 'fill_duration_ms', 'started_at',
        'latitude', 'longitude', 'location_granted',
        'staff__username', 'staff__first_name', 'staff__last_name',
        'postal_office_id', 'postal_office__code', 'postal_office__name',
    )

    results = []
    for r in detailed_qs.iterator(chunk_size=500):
        score, reasons = evaluate_response(r, indices, postal_office_coords)
        if only_risky and score == 0:
            continue
        results.append({
            'response': r,
            'score': score,
            'level': _classify(score),
            'reasons': reasons,
        })

    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_n]


def aggregate_risk_summary(results):
    """Risk natijalardan umumiy statistika tuzadi.

    Qaytaradi: {
      'total_evaluated': int,
      'by_level': {'critical': N, 'high': N, 'medium': N, 'low': N},
      'by_reason': {'staff_public_same_ip': N, ...},
    }
    """
    by_level = Counter()
    by_reason = Counter()
    for item in results:
        by_level[item['level']] += 1
        for reason in item['reasons']:
            by_reason[reason['code']] += 1

    return {
        'total_evaluated': len(results),
        'by_level': dict(by_level),
        'by_reason': dict(by_reason),
    }
