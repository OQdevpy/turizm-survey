import json
from datetime import datetime

from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from accounts.decorators import staff_required

from .models import SurveyResponse


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _extract_screening(payload: dict) -> dict:
    """Screening (F1/F2/F3) javoblarini ajratib oladi va eligibility statusini aniqlaydi.

    Mantiq (Nonresident va Resident — bir xil):
    - F1='no' → terminated
    - F1='yes', F2='no' → eligible
    - F1='yes', F2='yes', F3='yes' → terminated
    - F1='yes', F2='yes', F3='no' → eligible
    - Hech narsa yuborilmasa → skipped
    """
    sc = payload.get('screening') or {}
    result = {
        'screening_status': SurveyResponse.SCREENING_SKIPPED,
        'screening_data': {},
    }
    if not isinstance(sc, dict):
        return result

    F1 = sc.get('F1')
    F2 = sc.get('F2')
    F3 = sc.get('F3')

    # Hech bo'lmaganda F1 javob bo'lishi kerak
    if F1 not in ('yes', 'no'):
        return result

    data = {'F1': F1}
    if F2 in ('yes', 'no'):
        data['F2'] = F2
    if F3 in ('yes', 'no'):
        data['F3'] = F3
    result['screening_data'] = data

    # Eligibility logic
    if F1 == 'no':
        result['screening_status'] = SurveyResponse.SCREENING_TERMINATED
    elif F1 == 'yes' and F2 == 'no':
        result['screening_status'] = SurveyResponse.SCREENING_ELIGIBLE
    elif F1 == 'yes' and F2 == 'yes' and F3 == 'yes':
        result['screening_status'] = SurveyResponse.SCREENING_TERMINATED
    elif F1 == 'yes' and F2 == 'yes' and F3 == 'no':
        result['screening_status'] = SurveyResponse.SCREENING_ELIGIBLE
    else:
        # Filtr to'liq emas — eligible deb qabul qilamiz (frontda davom etishi mumkin emas)
        result['screening_status'] = SurveyResponse.SCREENING_ELIGIBLE

    return result


def _extract_location(payload: dict) -> dict:
    """JSON payload dan GPS ma'lumotlarini xavfsiz tarzda ajratib olish."""
    loc = payload.get('location') or {}
    result = {
        'latitude': None,
        'longitude': None,
        'location_accuracy': None,
        'location_granted': False,
    }
    if not isinstance(loc, dict):
        return result
    if loc.get('granted'):
        try:
            lat = float(loc.get('latitude'))
            lon = float(loc.get('longitude'))
            # Koordinatalar mantiqiy chegarada
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                result['latitude'] = lat
                result['longitude'] = lon
                result['location_granted'] = True
                try:
                    acc = float(loc.get('accuracy'))
                    if 0 <= acc <= 100000:
                        result['location_accuracy'] = acc
                except (TypeError, ValueError):
                    pass
        except (TypeError, ValueError):
            pass
    else:
        # Ruxsat berilmagan bo'lsa, location_granted=False, qolganlari None
        result['location_granted'] = False
    return result


def _extract_summary(survey_type: str, payload: dict) -> dict:
    """JSON javoblardan asosiy maydonlarni ajratib olish.

    2026 versiya maydon nomlari:
    - Inbound: q1 (country), q3 (purpose), q5_nights (int), q16_sum, q16_currency
    - Outbound: q1 (country key), q2 (purpose), q4_val (int), q13_amount, q13_currency
    """
    summary = {
        'country': '', 'purpose': '', 'nights': None,
        'total_spent': None, 'spent_currency': '',
    }
    if survey_type == SurveyResponse.SURVEY_INBOUND:
        summary['country'] = payload.get('q1', '') or ''
        summary['purpose'] = payload.get('q3', '') or ''
        # Transit yo'lida q5 yo'q — 0 tunlar; employment yo'lida q5 mavjud
        purpose = summary['purpose']
        if purpose == 'transit':
            summary['nights'] = 0
        else:
            try:
                n = payload.get('q5_nights')
                if n in (None, ''):
                    summary['nights'] = 0 if payload.get('q5_zero') else None
                else:
                    summary['nights'] = int(n)
            except (TypeError, ValueError):
                summary['nights'] = None
        try:
            summary['total_spent'] = float(payload.get('q16_sum')) if payload.get('q16_sum') else None
        except (TypeError, ValueError):
            summary['total_spent'] = None
        summary['spent_currency'] = payload.get('q16_currency', '') or ''
    else:  # outbound
        summary['country'] = payload.get('q1', '') or ''
        summary['purpose'] = payload.get('q2', '') or ''
        # Yangi versiya: q4_val (integer); eski versiya bilan moslashuv: q4_nights
        try:
            n = payload.get('q4_val')
            if n in (None, ''):
                n = payload.get('q4_nights')
            # Outbound'da employment qisqartirilgan oqim — q4 ham bor
            summary['nights'] = int(n) if n not in (None, '') else None
        except (TypeError, ValueError):
            summary['nights'] = None
        # Yangi versiya: q13_amount; eski versiya: q13_sum
        try:
            amount = payload.get('q13_amount') or payload.get('q13_sum')
            summary['total_spent'] = float(amount) if amount else None
        except (TypeError, ValueError):
            summary['total_spent'] = None
        summary['spent_currency'] = payload.get('q13_currency', '') or ''
    return summary


# ============================================================
# PUBLIC (turistlar uchun, login YO'Q)
# ============================================================

def public_inbound(request):
    return render(request, 'surveys/inbound.html', {
        'is_staff_view': False,
        'submit_url': '/inbound/submit/',
    })


def public_outbound(request):
    return render(request, 'surveys/outbound.html', {
        'is_staff_view': False,
        'submit_url': '/outbound/submit/',
    })


@require_POST
@csrf_protect
def submit_public(request, survey_type):
    if survey_type not in (SurveyResponse.SURVEY_INBOUND, SurveyResponse.SURVEY_OUTBOUND):
        return HttpResponseBadRequest("Noto'g'ri so'rovnoma turi.")

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': "Noto'g'ri JSON."}, status=400)

    answers = payload.get('answers') or {}
    language = payload.get('language', 'uz')[:5]

    summary = _extract_summary(survey_type, answers)
    location = _extract_location(payload)
    screening = _extract_screening(payload)

    response = SurveyResponse.objects.create(
        survey_type=survey_type,
        source=SurveyResponse.SOURCE_PUBLIC,
        language=language,
        data=answers,
        completed_at=timezone.now(),
        is_completed=True,
        ip_address=_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        **summary,
        **location,
        **screening,
    )
    return JsonResponse({'ok': True, 'id': str(response.id)})


# ============================================================
# STAFF (xodimlar uchun, login KERAK)
# ============================================================

@staff_required
def staff_inbound(request):
    return render(request, 'surveys/inbound.html', {
        'is_staff_view': True,
        'submit_url': '/staff/survey/inbound/submit/',
    })


@staff_required
def staff_outbound(request):
    return render(request, 'surveys/outbound.html', {
        'is_staff_view': True,
        'submit_url': '/staff/survey/outbound/submit/',
    })


@staff_required
@require_POST
@csrf_protect
def submit_staff(request, survey_type):
    if survey_type not in (SurveyResponse.SURVEY_INBOUND, SurveyResponse.SURVEY_OUTBOUND):
        return HttpResponseBadRequest("Noto'g'ri so'rovnoma turi.")

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': "Noto'g'ri JSON."}, status=400)

    answers = payload.get('answers') or {}
    language = payload.get('language', 'uz')[:5]
    summary = _extract_summary(survey_type, answers)
    location = _extract_location(payload)
    screening = _extract_screening(payload)

    postal_office = None
    try:
        postal_office = request.user.staff_profile.postal_office
    except Exception:
        pass

    response = SurveyResponse.objects.create(
        survey_type=survey_type,
        source=SurveyResponse.SOURCE_STAFF,
        staff=request.user,
        postal_office=postal_office,
        language=language,
        data=answers,
        completed_at=timezone.now(),
        is_completed=True,
        ip_address=_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        **summary,
        **location,
        **screening,
    )
    return JsonResponse({'ok': True, 'id': str(response.id)})


def success_page(request):
    return render(request, 'surveys/success.html')
