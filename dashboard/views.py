import io
import json
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import staff_required, superuser_required
from accounts.models import PostalOffice
from surveys.models import SurveyResponse
from surveys.utils import device_fingerprint, ip_to_subnet24
from .fraud import evaluate_all, aggregate_risk_summary


# ============================================
# Excel export uchun yordamchi funksiyalar
# ============================================

# Inbound savol matnlari (qisqacha)
INBOUND_QUESTIONS = [
    ('q1', '1. Doimiy yashash mamlakati (oxirgi 12 oy)'),
    ('q2', '2. Pasport turi'),
    ('q2_country', '2a. Boshqa pasport mamlakati'),
    ('q3', '3. Tashrif maqsadi'),
    ('q4', '4. Biznes tashrif turi'),
    ('q5_nights', '5. UZ da tunlar soni'),
    ('q5_zero', '5a. 0-tun (kelgan kuni qaytgan)'),
    ('q6', '6. Tashrif buyurilgan shaharlar va tunlar'),
    ('q7', '7. Asosiy turar joy turi'),
    ('q8', '8. Ovqat olingan joylar'),
    ('q9', "9. Paketli tur orqali keldimi?"),
    ('q10_total', '10. Paket umumiy tunlar'),
    ('q10_uz', '10. Paketdagi UZ tunlari'),
    ('q11', '11. Paketdagi kishilar soni'),
    ('q12_amount', '12. Paket narxi'),
    ('q12_currency', '12. Paket valyutasi'),
    ('q13', '13. Kelish transporti'),
    ('q13_airline', '13. Aviakompaniya (kelish)'),
    ('q14', '14. Ketish transporti'),
    ('q14_airline', '14. Aviakompaniya (ketish)'),
    ('q15', '15. Oylik daromad ulushi (ishchilar uchun)'),
    ('q16_sum', '16. Umumiy xarajat (turpaketdan tashqari)'),
    ('q16_currency', '16. Valyuta'),
    ('q16_persons', '16. Kishilar soni (guruh)'),
    ('q17', '17. Xarajatlar jadvali'),
    ('q18', '18. Xizmatlar reytingi (1-10)'),
    ('q19', '19. Izoh'),
]

# Outbound savol matnlari (qisqacha)
OUTBOUND_QUESTIONS = [
    ('q1', '1. Sayohat asosiy davlati'),
    ('q2', '2. Sayohat maqsadi'),
    ('q3', '3. Biznes tashrif turi'),
    ('q4_val', '4. Chet elda tunlar soni'),
    ('q5', '5. Turar joy turi'),
    ('q6', '6. Paketli turmi?'),
    ('q7', '7. Paket tunlar (jami)'),
    ('q8', '8. Paket kishilar soni'),
    ('q9_amount', '9. Paket narxi'),
    ('q9_currency', '9. Paket valyutasi'),
    ('q10', '10. UZ dan chiqish transporti'),
    ('q10_airline', '10. Aviakompaniya (chiqish)'),
    ('q11', '11. UZ ga qaytish transporti'),
    ('q11_airline', '11. Aviakompaniya (qaytish)'),
    ('q12', '12. Daromad ulushi (chet elda ishlovchilar)'),
    ('q13_amount', '13. Umumiy xarajat (paketdan tashqari)'),
    ('q13_currency', '13. Valyuta'),
    ('q13_persons', '13. Kishilar soni'),
    ('q14', '14. Xarajatlar jadvali'),
]

# Reyting matnlari (Inbound Q18)
RATING_LABELS = [
    'Xalqaro transport (UZ kompaniyalari)',
    'Pasport nazorati',
    'Mehmondo\'stlik',
    'Sifat/narx nisbati',
    'Ovqat',
    'Tozalik',
    'Transport (UZ ichida)',
    'Xavfsizlik',
    'Madaniyat va ko\'ngilochar',
    'Turar joy',
    'Sog\'liq xizmatlari',
    'Aloqa/Internet/Wi-Fi',
]


def _flatten_dict(d, prefix='', sep='.'):
    """Nested dict/list ni dot-notation bilan tekis qiladi.

    {'q6': {'Tashkent': {'nights': 3}}} -> {'q6.Tashkent.nights': 3}
    """
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{prefix}{sep}{k}" if prefix else str(k)
            out.update(_flatten_dict(v, new_key, sep))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            new_key = f"{prefix}{sep}{i}" if prefix else str(i)
            out.update(_flatten_dict(v, new_key, sep))
    else:
        out[prefix] = d
    return out


def _format_answer(key, value):
    """JSON qiymatni o'qish uchun string formatga aylantirish."""
    if value is None or value == '':
        return ''
    if isinstance(value, bool):
        return 'Ha' if value else "Yo'q"
    if isinstance(value, dict):
        # q6 — shaharlar
        if key == 'q6':
            parts = []
            for city, info in value.items():
                if isinstance(info, dict):
                    parts.append(f"{city} ({info.get('nights', 0)} tun)")
            return ', '.join(parts)
        # q8 — ovqat joylari
        if key == 'q8':
            return ', '.join(k for k, v in value.items() if v)
        # q17 / q14 — xarajatlar jadvali
        if key == 'q17' or key == 'q14':
            parts = []
            for k, v in value.items():
                if not isinstance(v, dict):
                    continue
                row_num = k.replace('r', '', 1)
                amount = v.get('amount', '')
                cur = v.get('currency', '')
                in_pkg = v.get('inPackage') or v.get('inPkg')
                label = f"{row_num}: {amount or '0'} {cur or ''}".strip()
                if in_pkg:
                    label += ' [paketda]'
                if amount or in_pkg:
                    parts.append(label)
            return '; '.join(parts)
        # q18 — reytinglar
        if key == 'q18':
            parts = []
            for k, v in value.items():
                try:
                    idx = int(k.replace('r', ''))
                    name = RATING_LABELS[idx] if idx < len(RATING_LABELS) else f'#{idx}'
                except (ValueError, IndexError):
                    name = k
                parts.append(f"{name}: {v}")
            return '; '.join(parts)
        # Boshqa dict — JSON formatda
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return ', '.join(str(x) for x in value)
    return str(value)


def _date_ranges():
    now = timezone.now()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    return today, week_start, month_start


@staff_required
def index(request):
    """Xodim uchun shaxsiy dashboard."""
    user = request.user
    today, week_start, month_start = _date_ranges()

    if user.is_superuser:
        # Superuser uchun — barcha so'rovnomalar
        base_qs = SurveyResponse.objects.filter(is_completed=True)
    else:
        base_qs = SurveyResponse.objects.filter(is_completed=True, staff=user)

    today_count = base_qs.filter(started_at__date=today).count()
    week_count = base_qs.filter(started_at__date__gte=week_start).count()
    month_count = base_qs.filter(started_at__date__gte=month_start).count()
    total_count = base_qs.count()

    inbound_count = base_qs.filter(survey_type=SurveyResponse.SURVEY_INBOUND).count()
    outbound_count = base_qs.filter(survey_type=SurveyResponse.SURVEY_OUTBOUND).count()

    # So'nggi 14 kun grafigi
    fourteen_days_ago = today - timedelta(days=13)
    daily = (
        base_qs.filter(started_at__date__gte=fourteen_days_ago)
        .annotate(d=TruncDate('started_at'))
        .values('d')
        .annotate(c=Count('id'))
        .order_by('d')
    )
    daily_map = {row['d']: row['c'] for row in daily}
    chart_labels, chart_values = [], []
    for i in range(14):
        d = fourteen_days_ago + timedelta(days=i)
        chart_labels.append(d.strftime('%d.%m'))
        chart_values.append(daily_map.get(d, 0))

    recent = base_qs.select_related('postal_office', 'staff').order_by('-started_at')[:10]

    context = {
        'today_count': today_count,
        'week_count': week_count,
        'month_count': month_count,
        'total_count': total_count,
        'inbound_count': inbound_count,
        'outbound_count': outbound_count,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'recent': recent,
        'is_superuser_view': user.is_superuser,
    }
    return render(request, 'dashboard/index.html', context)


@superuser_required
def admin_reports(request):
    """Superuser uchun to'liq hisobotlar."""
    today, week_start, month_start = _date_ranges()

    qs = SurveyResponse.objects.filter(is_completed=True)

    # Sana filtrlash
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    if date_from:
        qs = qs.filter(started_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(started_at__date__lte=date_to)

    survey_filter = request.GET.get('type')
    if survey_filter in ('inbound', 'outbound'):
        qs = qs.filter(survey_type=survey_filter)

    office_filter = request.GET.get('office')
    if office_filter:
        qs = qs.filter(postal_office_id=office_filter)

    total = qs.count()
    by_source = list(qs.values('source').annotate(c=Count('id')))
    by_type = list(qs.values('survey_type').annotate(c=Count('id')))
    by_office = list(
        qs.exclude(postal_office__isnull=True)
        .values('postal_office__code', 'postal_office__name')
        .annotate(c=Count('id'))
        .order_by('-c')[:20]
    )
    by_staff = list(
        qs.exclude(staff__isnull=True)
        .values('staff__username', 'staff__first_name', 'staff__last_name')
        .annotate(c=Count('id'))
        .order_by('-c')[:20]
    )
    by_country = list(
        qs.exclude(country='')
        .values('country')
        .annotate(c=Count('id'))
        .order_by('-c')[:15]
    )
    by_purpose = list(
        qs.exclude(purpose='')
        .values('purpose')
        .annotate(c=Count('id'))
        .order_by('-c')
    )

    # Kunlik grafik (so'nggi 30 kun)
    thirty_days_ago = today - timedelta(days=29)
    daily = (
        qs.filter(started_at__date__gte=thirty_days_ago)
        .annotate(d=TruncDate('started_at'))
        .values('d')
        .annotate(c=Count('id'))
        .order_by('d')
    )
    daily_map = {row['d']: row['c'] for row in daily}
    chart_labels, chart_values = [], []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        chart_labels.append(d.strftime('%d.%m'))
        chart_values.append(daily_map.get(d, 0))

    context = {
        'total': total,
        'by_source': by_source,
        'by_type': by_type,
        'by_office': by_office,
        'by_staff': by_staff,
        'by_country': by_country,
        'by_purpose': by_purpose,
        'chart_labels': chart_labels,
        'chart_values': chart_values,
        'offices': PostalOffice.objects.filter(is_active=True),
        'filters': {
            'from': date_from or '',
            'to': date_to or '',
            'type': survey_filter or '',
            'office': office_filter or '',
        },
    }
    return render(request, 'dashboard/admin_reports.html', context)


@superuser_required
def export_excel(request):
    """To'liq Excel eksporti — bir necha sahifa bilan.

    Sahifalar:
    1. So'rovnomalar — asosiy summary (GPS, Google Maps link bilan)
    2. Inbound — barcha javoblar (Q1-Q19)
    3. Outbound — barcha javoblar (Q1-Q14)
    4. Shaharlar (Inbound Q6) — har shahar bo'yicha
    5. Xarajatlar (Q17 inbound, Q14 outbound) — har xarajat qatori
    6. Reytinglar (Inbound Q18) — har xizmat baholash
    7. JSON (raw) — to'liq JSON ma'lumot
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError:
        return HttpResponse("openpyxl o'rnatilmagan.", status=500)

    qs = SurveyResponse.objects.filter(is_completed=True).select_related('staff', 'postal_office')

    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    if date_from:
        qs = qs.filter(started_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(started_at__date__lte=date_to)

    wb = Workbook()

    # Header style
    header_font = Font(bold=True, color='FFFFFF', size=11)
    header_fill = PatternFill(start_color='0F3A6E', end_color='0F3A6E', fill_type='solid')
    header_align = Alignment(horizontal='center', vertical='center', wrap_text=True)

    def style_header_row(ws, row_num=1):
        for cell in ws[row_num]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align

    def autofit_columns(ws, max_width=50):
        for col in ws.columns:
            try:
                col_letter = get_column_letter(col[0].column)
            except Exception:
                continue
            max_len = 0
            for cell in col:
                try:
                    val = str(cell.value) if cell.value is not None else ''
                    if len(val) > max_len:
                        max_len = len(val)
                except Exception:
                    pass
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), max_width)

    # ============================================
    # SHEET 1: Asosiy summary
    # ============================================
    ws = wb.active
    ws.title = "Asosiy"

    headers = [
        '#', 'ID', 'Turi', 'Manba', 'Til',
        'Xodim (login)', 'Xodim (F.I.SH)', 'Bo\'lim kodi', 'Bo\'lim nomi', 'Region',
        'Davlat', 'Maqsad', 'Tunlar', 'Xarajat', 'Valyuta',
        'Filtr holati', 'F1', 'F2', 'F3',
        'GPS bormi', 'Latitude', 'Longitude', 'GPS aniqlik (m)', 'Google Maps',
        'Boshlangan', 'Yakunlangan', 'IP', 'User-Agent',
        'Device turi', 'OS', 'Brauzer', 'Device screen', 'Device platform',
        'Device til', 'Device timezone', "To'ldirish (ms)",
    ]
    ws.append(headers)
    style_header_row(ws)

    for idx, r in enumerate(qs, start=1):
        gmaps_url = ''
        if r.latitude is not None and r.longitude is not None:
            gmaps_url = f'https://www.google.com/maps?q={r.latitude},{r.longitude}'

        staff_login = r.staff.username if r.staff else ''
        staff_full = ''
        if r.staff:
            try:
                staff_full = r.staff.staff_profile.full_name or r.staff.get_full_name() or r.staff.username
            except Exception:
                staff_full = r.staff.get_full_name() or r.staff.username

        sc = r.screening_data or {}
        di = r.device_info or {}
        ws.append([
            idx,
            str(r.id),
            r.get_survey_type_display(),
            r.get_source_display(),
            r.language,
            staff_login,
            staff_full,
            r.postal_office.code if r.postal_office else '',
            r.postal_office.name if r.postal_office else '',
            r.postal_office.region_code if r.postal_office else '',
            r.country or '',
            r.purpose or '',
            r.nights if r.nights is not None else '',
            float(r.total_spent) if r.total_spent else '',
            r.spent_currency or '',
            r.get_screening_status_display(),
            sc.get('F1', '') or '',
            sc.get('F2', '') or '',
            sc.get('F3', '') or '',
            'Ha' if r.location_granted else "Yo'q",
            float(r.latitude) if r.latitude is not None else '',
            float(r.longitude) if r.longitude is not None else '',
            float(r.location_accuracy) if r.location_accuracy is not None else '',
            gmaps_url,
            r.started_at.strftime('%Y-%m-%d %H:%M:%S') if r.started_at else '',
            r.completed_at.strftime('%Y-%m-%d %H:%M:%S') if r.completed_at else '',
            r.ip_address or '',
            (r.user_agent or '')[:150],
            r.device_type or '',
            r.os_name or '',
            r.browser_name or '',
            di.get('screen', '') if isinstance(di, dict) else '',
            di.get('platform', '') if isinstance(di, dict) else '',
            di.get('language', '') if isinstance(di, dict) else '',
            di.get('timezone', '') if isinstance(di, dict) else '',
            r.fill_duration_ms if r.fill_duration_ms else '',
        ])

    # Google Maps ustunini hyperlink qilish
    # Headers tartibi: 1-15 oddiy, 16-19 screening (Filtr holati, F1, F2, F3),
    # 20 GPS bormi, 21 Lat, 22 Lon, 23 Aniqlik, 24 Google Maps
    gmaps_col = 24  # 1-indexed
    for row_num in range(2, ws.max_row + 1):
        cell = ws.cell(row=row_num, column=gmaps_col)
        if cell.value:
            cell.hyperlink = cell.value
            cell.font = Font(color='0563C1', underline='single')

    autofit_columns(ws)
    ws.freeze_panes = 'A2'

    # ============================================
    # SHEET 2: Inbound — barcha javoblar
    # ============================================
    ws2 = wb.create_sheet("Inbound — javoblar")
    inb_headers = [
        'ID', 'Sana', 'Xodim', 'Bo\'lim',
        'Q1 Mamlakat', 'Q2 Pasport', 'Q2 Boshqa pasport', 'Q3 Maqsad', 'Q4 Biznes turi',
        'Q5 Tunlar', 'Q5 0-tun', 'Q6 Shaharlar (qisqacha)',
        'Q7 Turar joy', 'Q8 Ovqat joylari', 'Q9 Paket?',
        'Q10 Paket tunlar (jami)', 'Q10 Paket tunlar (UZ)', 'Q11 Kishilar',
        'Q12 Paket narxi', 'Q12 Valyuta',
        'Q13 Kelish transport', 'Q13 Aviakompaniya',
        'Q14 Ketish transport', 'Q14 Aviakompaniya',
        'Q15 Daromad ulushi',
        'Q16 Umumiy xarajat', 'Q16 Valyuta', 'Q16 Kishilar soni',
        'Q19 Izoh',
    ]
    ws2.append(inb_headers)
    style_header_row(ws2)

    for r in qs.filter(survey_type=SurveyResponse.SURVEY_INBOUND):
        d = r.data or {}
        q6 = d.get('q6') or {}
        q6_summary = ', '.join(f"{c} ({v.get('nights', 0)})" for c, v in q6.items() if isinstance(v, dict))
        q8 = d.get('q8') or {}
        q8_summary = ', '.join(q8.keys()) if isinstance(q8, dict) else ''

        ws2.append([
            str(r.id),
            r.started_at.strftime('%Y-%m-%d %H:%M') if r.started_at else '',
            r.staff.username if r.staff else '',
            r.postal_office.code if r.postal_office else '',
            d.get('q1', ''),
            d.get('q2', ''),
            d.get('q2_country', ''),
            d.get('q3', ''),
            d.get('q4', ''),
            d.get('q5_nights', ''),
            'Ha' if d.get('q5_zero') else '',
            q6_summary,
            d.get('q7', ''),
            q8_summary,
            d.get('q9', ''),
            d.get('q10_total', ''),
            d.get('q10_uz', ''),
            d.get('q11', ''),
            d.get('q12_amount', ''),
            d.get('q12_currency', ''),
            d.get('q13', ''),
            d.get('q13_airline', ''),
            d.get('q14', ''),
            d.get('q14_airline', ''),
            d.get('q15', ''),
            d.get('q16_sum', ''),
            d.get('q16_currency', ''),
            d.get('q16_persons', ''),
            (d.get('q19') or '')[:1000],
        ])
    autofit_columns(ws2)
    ws2.freeze_panes = 'A2'

    # ============================================
    # SHEET 3: Outbound — barcha javoblar
    # ============================================
    ws3 = wb.create_sheet("Outbound — javoblar")
    out_headers = [
        'ID', 'Sana', 'Xodim', 'Bo\'lim',
        'Q1 Mamlakat', 'Q2 Maqsad', 'Q3 Biznes turi',
        'Q4 Tunlar',
        'Q5 Turar joy', 'Q6 Paket?',
        'Q7 Paket tunlar', 'Q8 Kishilar', 'Q9 Paket narxi', 'Q9 Valyuta',
        'Q10 Chiqish transport', 'Q10 Aviakompaniya',
        'Q11 Qaytish transport', 'Q11 Aviakompaniya',
        'Q12 Daromad ulushi',
        'Q13 Umumiy summa', 'Q13 Valyuta', 'Q13 Kishilar',
    ]
    ws3.append(out_headers)
    style_header_row(ws3)

    for r in qs.filter(survey_type=SurveyResponse.SURVEY_OUTBOUND):
        d = r.data or {}
        ws3.append([
            str(r.id),
            r.started_at.strftime('%Y-%m-%d %H:%M') if r.started_at else '',
            r.staff.username if r.staff else '',
            r.postal_office.code if r.postal_office else '',
            d.get('q1', ''),
            d.get('q2', ''),
            d.get('q3', ''),
            d.get('q4_val', d.get('q4_nights', '')),
            d.get('q5', ''),
            d.get('q6', ''),
            d.get('q7', ''),
            d.get('q8', d.get('q8_persons', '')),
            d.get('q9_amount', ''),
            d.get('q9_currency', ''),
            d.get('q10', ''),
            d.get('q10_airline', ''),
            d.get('q11', ''),
            d.get('q11_airline', ''),
            d.get('q12', ''),
            d.get('q13_amount', d.get('q13_sum', '')),
            d.get('q13_currency', ''),
            d.get('q13_persons', ''),
        ])
    autofit_columns(ws3)
    ws3.freeze_panes = 'A2'

    # ============================================
    # SHEET 4: Shaharlar (Inbound Q6)
    # ============================================
    ws4 = wb.create_sheet("Shaharlar (Inbound Q6)")
    ws4.append(['ID', 'Sana', 'Bo\'lim', 'Mamlakat', 'Shahar', 'Tunlar'])
    style_header_row(ws4)

    for r in qs.filter(survey_type=SurveyResponse.SURVEY_INBOUND):
        d = r.data or {}
        q6 = d.get('q6') or {}
        if not isinstance(q6, dict):
            continue
        for city, info in q6.items():
            if not isinstance(info, dict):
                continue
            ws4.append([
                str(r.id),
                r.started_at.strftime('%Y-%m-%d') if r.started_at else '',
                r.postal_office.code if r.postal_office else '',
                r.country or '',
                city,
                info.get('nights', 0),
            ])
    autofit_columns(ws4)
    ws4.freeze_panes = 'A2'

    # ============================================
    # SHEET 5: Xarajatlar (Inbound Q17 + Outbound Q14)
    # ============================================
    ws5 = wb.create_sheet("Xarajatlar")
    ws5.append([
        'ID', 'Sana', 'Bo\'lim', 'Tur (Inbound/Outbound)', 'Mamlakat',
        'Qator #', 'Summa', 'Valyuta', 'Paketga kiritilgan',
    ])
    style_header_row(ws5)

    for r in qs:
        d = r.data or {}
        # Inbound: q17, Outbound: q14
        if r.survey_type == SurveyResponse.SURVEY_INBOUND:
            exp_data = d.get('q17') or {}
            type_label = 'Inbound'
            pkg_key = 'inPackage'
        else:
            exp_data = d.get('q14') or {}
            type_label = 'Outbound'
            pkg_key = 'inPkg'

        if not isinstance(exp_data, dict):
            continue
        for key, val in exp_data.items():
            if not isinstance(val, dict):
                continue
            row_num = key.replace('r', '', 1) if key.startswith('r') else key
            amount = val.get('amount', '')
            currency = val.get('currency', '')
            in_pkg = val.get(pkg_key, False)
            # Bo'sh qatorlar ham skip qilamiz
            if not amount and not in_pkg:
                continue
            ws5.append([
                str(r.id),
                r.started_at.strftime('%Y-%m-%d') if r.started_at else '',
                r.postal_office.code if r.postal_office else '',
                type_label,
                r.country or '',
                row_num,
                amount or '',
                currency or '',
                'Ha' if in_pkg else "Yo'q",
            ])
    autofit_columns(ws5)
    ws5.freeze_panes = 'A2'

    # ============================================
    # SHEET 6: Reytinglar (Inbound Q18)
    # ============================================
    ws6 = wb.create_sheet("Reytinglar (Q18)")
    rating_labels = [
        'International transport',
        'Passport control procedures',
        'Hospitality',
        'Value for money',
        'Food',
        'Cleanliness',
        'Transport (within Uzbekistan)',
        'Safety',
        'Cultural and entertainment',
        'Accommodation',
        'Health and medical',
        'Communication, Internet, Wi-Fi',
    ]
    ws6.append(['ID', 'Sana', 'Bo\'lim', 'Mamlakat', '№', 'Xizmat', 'Baho (1-10 yoki N/A)'])
    style_header_row(ws6)

    for r in qs.filter(survey_type=SurveyResponse.SURVEY_INBOUND):
        d = r.data or {}
        q18 = d.get('q18') or {}
        if not isinstance(q18, dict):
            continue
        for i, label in enumerate(rating_labels):
            score = q18.get(f'r{i}')
            if score is None:
                continue
            ws6.append([
                str(r.id),
                r.started_at.strftime('%Y-%m-%d') if r.started_at else '',
                r.postal_office.code if r.postal_office else '',
                r.country or '',
                i + 1,
                label,
                score,
            ])
    autofit_columns(ws6)
    ws6.freeze_panes = 'A2'

    # ============================================
    # SHEET 7: Savol-javob (long format)
    # Har bir savol-javob alohida qatorda — Pivot table uchun ideal
    # ============================================
    ws7 = wb.create_sheet("Savol-javob")
    ws7.append([
        'ID', 'Sana', 'Turi', 'Xodim', "Bo'lim", 'Davlat',
        'Savol kodi', 'Savol matni', 'Javob',
    ])
    style_header_row(ws7)

    for r in qs:
        d = r.data or {}
        if r.survey_type == SurveyResponse.SURVEY_INBOUND:
            questions = INBOUND_QUESTIONS
        else:
            questions = OUTBOUND_QUESTIONS

        base_row = [
            str(r.id),
            r.started_at.strftime('%Y-%m-%d %H:%M') if r.started_at else '',
            r.get_survey_type_display(),
            r.staff.username if r.staff else '',
            r.postal_office.code if r.postal_office else '',
            r.country or '',
        ]

        for q_code, q_text in questions:
            answer = _format_answer(q_code, d.get(q_code))
            if answer == '':
                continue  # bo'sh javoblarni o'tkazib yuborish
            ws7.append(base_row + [q_code, q_text, answer])

    autofit_columns(ws7, max_width=80)
    ws7.freeze_panes = 'A2'

    # ============================================
    # SHEET 8: JSON yoyilgan (wide format)
    # Har JSON kalit — alohida ustun (q6.Tashkent.nights, q17.r1.amount, ...)
    # ============================================
    ws8 = wb.create_sheet("JSON yoyilgan")

    # 1) Avval barcha yozuvlarni flatten qilamiz va unique kalitlarni yig'amiz
    flattened_responses = []
    all_keys = set()
    for r in qs:
        flat = _flatten_dict(r.data or {})
        flattened_responses.append((r, flat))
        all_keys.update(flat.keys())

    sorted_keys = sorted(all_keys)
    base_headers = ['ID', 'Sana', 'Turi', 'Xodim', "Bo'lim", 'Davlat']
    ws8.append(base_headers + sorted_keys)
    style_header_row(ws8)

    for r, flat in flattened_responses:
        row = [
            str(r.id),
            r.started_at.strftime('%Y-%m-%d %H:%M') if r.started_at else '',
            r.get_survey_type_display(),
            r.staff.username if r.staff else '',
            r.postal_office.code if r.postal_office else '',
            r.country or '',
        ]
        for k in sorted_keys:
            v = flat.get(k, '')
            if isinstance(v, bool):
                v = 'Ha' if v else "Yo'q"
            elif isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            elif v is None:
                v = ''
            row.append(v)
        ws8.append(row)

    autofit_columns(ws8, max_width=30)
    ws8.freeze_panes = 'B2'  # ID ustuni doim ko'rinadigan

    # ============================================
    # SHEET 9: JSON (raw) — to'liq JSON saqlanadi (zaxira)
    # ============================================
    ws9 = wb.create_sheet("JSON (raw)")
    ws9.append(['ID', 'Turi', 'Sana', 'Xodim', "Bo'lim", "JSON ma'lumot"])
    style_header_row(ws9)
    for r in qs:
        ws9.append([
            str(r.id),
            r.get_survey_type_display(),
            r.started_at.strftime('%Y-%m-%d %H:%M') if r.started_at else '',
            r.staff.username if r.staff else '',
            r.postal_office.code if r.postal_office else '',
            json.dumps(r.data or {}, ensure_ascii=False, indent=None),
        ])
    ws9.column_dimensions['A'].width = 38
    ws9.column_dimensions['B'].width = 14
    ws9.column_dimensions['C'].width = 17
    ws9.column_dimensions['D'].width = 22
    ws9.column_dimensions['E'].width = 12
    ws9.column_dimensions['F'].width = 100
    ws9.freeze_panes = 'A2'

    # ============================================
    # SHEET 10: MASTER — barcha savollar bitta keng sheetda (~199 ustun)
    # Inbound va Outbound savollarini IN.* / OUT.* prefiks bilan birlashtiradi.
    # Pivot table, Power BI, statistik tahlil uchun ideal.
    # ============================================
    ws10 = wb.create_sheet("Master (barcha savollar)")
    master_columns = _build_master_columns()
    ws10.append(master_columns)

    # Header'ni guruh bo'yicha ranglash
    in_fill = PatternFill(start_color='1A5FA8', end_color='1A5FA8', fill_type='solid')
    out_fill = PatternFill(start_color='2E7D32', end_color='2E7D32', fill_type='solid')
    header_font_compact = Font(bold=True, color='FFFFFF', size=10)
    for col_idx, col_name in enumerate(master_columns, start=1):
        cell = ws10.cell(row=1, column=col_idx)
        cell.font = header_font_compact
        cell.alignment = header_align
        if col_name.startswith('IN.'):
            cell.fill = in_fill
        elif col_name.startswith('OUT.'):
            cell.fill = out_fill
        else:
            cell.fill = header_fill

    # Har bir SurveyResponse uchun bitta satr
    for idx, r in enumerate(qs.iterator(chunk_size=500), start=1):
        row = _build_master_row(r, idx, master_columns)
        ws10.append(row)

    # Ustun kengligi
    for col_idx, col_name in enumerate(master_columns, start=1):
        col_letter = get_column_letter(col_idx)
        width = max(len(col_name) + 2, 12)
        if col_name.startswith(('IN.Q17.', 'IN.Q18.', 'OUT.Q14.')):
            width = max(width, 16)
        elif col_name.startswith(('IN.', 'OUT.')):
            width = max(width, 18)
        ws10.column_dimensions[col_letter].width = min(width, 40)
    ws10.row_dimensions[1].height = 45
    ws10.freeze_panes = 'I2'  # 1-qator + 1-8 ustun freeze

    # Save and return
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"surveys_full_{timezone.now():%Y%m%d_%H%M}.xlsx"
    response = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ============================================
# MASTER SHEET helpers — barcha savollar bitta keng formatda
# ============================================

# Inbound shaharlar (Q6) — har shahar uchun alohida ustun
_MASTER_INBOUND_CITIES = [
    'Tashkent', 'Samarkand', 'Bukhara', 'Khiva', 'Shakhrisabz', 'Termez',
    'Kokand', 'Fergana', 'Namangan', 'Andijan', 'Nukus', 'Urgench', 'Other',
]
# Inbound ovqat joylari (Q8) — har biri uchun alohida bool ustun
_MASTER_INBOUND_FOOD = [
    'restaurants', 'street', 'fastfood', 'national',
    'friends_home', 'rented', 'other',
]
# Inbound Q18 reyting xizmatlari (12 ta)
_MASTER_INBOUND_RATINGS = [
    'r0_intl_transport', 'r1_passport_control', 'r2_hospitality',
    'r3_value_for_money', 'r4_food', 'r5_cleanliness',
    'r6_local_transport', 'r7_safety', 'r8_culture',
    'r9_accommodation', 'r10_health', 'r11_communication',
]
# Outbound Q14 xarajat qatorlari (sub-rows 1.1/1.2 bilan)
_MASTER_OUTBOUND_EXP_ROWS = [
    '1', '1.1', '1.2', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13',
]


def _build_master_columns():
    """Master sheet'ning barcha ustunlarini ro'yxat qilib qaytaradi."""
    cols = []
    # 1) Identifikatsiya va meta (8)
    cols += ['#', 'ID', 'Turi', 'Manba', 'Til',
             'Boshlangan', 'Yakunlangan', "To'ldirish (s)"]
    # 2) Xodim va bo'lim (7)
    cols += ['Xodim login', 'Xodim F.I.SH', 'Xodim telefon',
             "Bo'lim kodi", "Bo'lim nomi", 'Region kodi', 'Post turi']
    # 3) Tarmoq va device (10)
    cols += ['IP', 'Subnet /24', 'Device turi', 'OS', 'Brauzer',
             'Screen', 'Platform', 'Til (client)', 'Timezone', 'User-Agent']
    # 4) GPS (5)
    cols += ['GPS bormi', 'Latitude', 'Longitude', 'GPS aniqlik (m)', 'Google Maps URL']
    # 5) Screening (4)
    cols += ['Filtr holati', 'F1', 'F2', 'F3']
    # 6) Auto-summary (5)
    cols += ['Davlat', 'Maqsad', 'Tunlar', 'Xarajat (umumiy)', 'Valyuta']

    # 7) INBOUND
    cols += ['IN.Q1 (Doimiy davlat)', 'IN.Q2 (Pasport)', 'IN.Q2_country (Boshqa pasport)',
             'IN.Q3 (Maqsad)', 'IN.Q4 (Biznes turi)',
             'IN.Q5_nights', 'IN.Q5_zero']
    cols += [f'IN.Q6.{c}' for c in _MASTER_INBOUND_CITIES]
    cols += ['IN.Q7 (Turar joy)']
    cols += [f'IN.Q8.{f}' for f in _MASTER_INBOUND_FOOD]
    cols += ['IN.Q9 (Paket?)',
             'IN.Q10_total', 'IN.Q10_uz', 'IN.Q11 (Paket kishi)',
             'IN.Q12_amount', 'IN.Q12_currency',
             'IN.Q13 (Kelish)', 'IN.Q13_airline',
             'IN.Q14 (Ketish)', 'IN.Q14_airline',
             'IN.Q15 (Daromad ulushi)',
             'IN.Q16_sum', 'IN.Q16_currency', 'IN.Q16_persons']
    # Q17 — 14 qator × 3
    for n in range(1, 15):
        cols += [f'IN.Q17.r{n}.amount', f'IN.Q17.r{n}.currency', f'IN.Q17.r{n}.inPackage']
    # Q18 — 12 reyting
    cols += [f'IN.Q18.{r}' for r in _MASTER_INBOUND_RATINGS]
    cols += ['IN.Q19 (Izoh)']

    # 8) OUTBOUND
    cols += ['OUT.Q1 (Asosiy davlat)', 'OUT.Q2 (Maqsad)', 'OUT.Q3 (Biznes turi)',
             'OUT.Q4_val (Tunlar)',
             'OUT.Q5 (Turar joy)', 'OUT.Q6 (Paket?)',
             'OUT.Q7 (Paket tunlari)', 'OUT.Q8 (Paket kishi)',
             'OUT.Q9_amount', 'OUT.Q9_currency',
             'OUT.Q10 (Chiqish)', 'OUT.Q10_airline',
             'OUT.Q11 (Qaytish)', 'OUT.Q11_airline',
             'OUT.Q12 (Daromad ulushi)',
             'OUT.Q13_amount', 'OUT.Q13_currency', 'OUT.Q13_persons']
    # Q14 — sub-rowlar bilan
    for n in _MASTER_OUTBOUND_EXP_ROWS:
        cols += [f'OUT.Q14.r{n}.amount', f'OUT.Q14.r{n}.currency', f'OUT.Q14.r{n}.inPkg']

    return cols


def _ipnetwork24(ip):
    """IPv4 ni /24 subnet'ga aylantiradi."""
    if not ip or ':' in ip:
        return ip or ''
    parts = ip.split('.')
    if len(parts) != 4:
        return ip
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"


def _yn(value):
    """Bool -> 'Ha' / 'Yo'q' / ''. None bo'lsa bo'sh."""
    if value is None:
        return ''
    return 'Ha' if value else "Yo'q"


def _build_master_row(r, idx, columns):
    """Bitta SurveyResponse'ni master sheet qatoriga aylantiradi.

    columns ro'yxati tartibi bo'yicha qiymatlar qaytaradi (bo'sh joy = '').
    """
    d = r.data or {}
    di = r.device_info or {}
    sc = r.screening_data or {}

    # Staff ma'lumotlari
    staff_login, staff_full, staff_phone = '', '', ''
    if r.staff:
        staff_login = r.staff.username or ''
        try:
            staff_full = r.staff.staff_profile.full_name or r.staff.get_full_name() or r.staff.username
            staff_phone = r.staff.staff_profile.phone or ''
        except Exception:
            staff_full = r.staff.get_full_name() or r.staff.username

    # Bo'lim
    office_code, office_name, region_code, post_type = '', '', '', ''
    if r.postal_office:
        office_code = r.postal_office.code or ''
        office_name = r.postal_office.name or ''
        region_code = r.postal_office.region_code or ''
        post_type = r.postal_office.get_post_type_display() if r.postal_office else ''

    # GPS
    gmaps_url = ''
    if r.latitude is not None and r.longitude is not None:
        gmaps_url = f'https://www.google.com/maps?q={r.latitude},{r.longitude}'

    # To'liq qiymatlar map'i — har ustun nomi -> qiymat
    values = {
        '#': idx,
        'ID': str(r.id),
        'Turi': r.get_survey_type_display(),
        'Manba': r.get_source_display(),
        'Til': r.language or '',
        'Boshlangan': r.started_at.strftime('%Y-%m-%d %H:%M:%S') if r.started_at else '',
        'Yakunlangan': r.completed_at.strftime('%Y-%m-%d %H:%M:%S') if r.completed_at else '',
        "To'ldirish (s)": round(r.fill_duration_ms / 1000, 1) if r.fill_duration_ms else '',
        'Xodim login': staff_login,
        'Xodim F.I.SH': staff_full,
        'Xodim telefon': staff_phone,
        "Bo'lim kodi": office_code,
        "Bo'lim nomi": office_name,
        'Region kodi': region_code,
        'Post turi': post_type,
        'IP': r.ip_address or '',
        'Subnet /24': _ipnetwork24(r.ip_address or ''),
        'Device turi': r.device_type or '',
        'OS': r.os_name or '',
        'Brauzer': r.browser_name or '',
        'Screen': di.get('screen', '') if isinstance(di, dict) else '',
        'Platform': di.get('platform', '') if isinstance(di, dict) else '',
        'Til (client)': di.get('language', '') if isinstance(di, dict) else '',
        'Timezone': di.get('timezone', '') if isinstance(di, dict) else '',
        'User-Agent': (r.user_agent or '')[:200],
        'GPS bormi': _yn(r.location_granted),
        'Latitude': float(r.latitude) if r.latitude is not None else '',
        'Longitude': float(r.longitude) if r.longitude is not None else '',
        'GPS aniqlik (m)': float(r.location_accuracy) if r.location_accuracy is not None else '',
        'Google Maps URL': gmaps_url,
        'Filtr holati': r.get_screening_status_display(),
        'F1': sc.get('F1', '') or '',
        'F2': sc.get('F2', '') or '',
        'F3': sc.get('F3', '') or '',
        'Davlat': r.country or '',
        'Maqsad': r.purpose or '',
        'Tunlar': r.nights if r.nights is not None else '',
        'Xarajat (umumiy)': float(r.total_spent) if r.total_spent else '',
        'Valyuta': r.spent_currency or '',
    }

    # ============================================================
    # Inbound bo'lsa — IN.* ustunlarni to'ldiramiz
    # ============================================================
    if r.survey_type == SurveyResponse.SURVEY_INBOUND:
        values['IN.Q1 (Doimiy davlat)'] = d.get('q1', '')
        values['IN.Q2 (Pasport)'] = d.get('q2', '')
        values['IN.Q2_country (Boshqa pasport)'] = d.get('q2_country', '')
        values['IN.Q3 (Maqsad)'] = d.get('q3', '')
        values['IN.Q4 (Biznes turi)'] = d.get('q4', '')
        values['IN.Q5_nights'] = d.get('q5_nights', '')
        values['IN.Q5_zero'] = _yn(d.get('q5_zero')) if 'q5_zero' in d else ''
        # Q6: har shahar uchun tunlar
        q6 = d.get('q6') or {}
        for city in _MASTER_INBOUND_CITIES:
            if isinstance(q6, dict) and city in q6 and isinstance(q6[city], dict):
                values[f'IN.Q6.{city}'] = q6[city].get('nights', '')
            else:
                values[f'IN.Q6.{city}'] = ''
        values['IN.Q7 (Turar joy)'] = d.get('q7', '') if d.get('q7') is not None else ''
        # Q8: har ovqat joyi uchun bool
        q8 = d.get('q8') or {}
        for food in _MASTER_INBOUND_FOOD:
            if isinstance(q8, dict) and q8.get(food):
                values[f'IN.Q8.{food}'] = 'Ha'
            else:
                values[f'IN.Q8.{food}'] = ''
        values['IN.Q9 (Paket?)'] = d.get('q9', '')
        values['IN.Q10_total'] = d.get('q10_total', '')
        values['IN.Q10_uz'] = d.get('q10_uz', '')
        values['IN.Q11 (Paket kishi)'] = d.get('q11', '')
        values['IN.Q12_amount'] = d.get('q12_amount', '')
        values['IN.Q12_currency'] = d.get('q12_currency', '')
        values['IN.Q13 (Kelish)'] = d.get('q13', '')
        values['IN.Q13_airline'] = d.get('q13_airline', '')
        values['IN.Q14 (Ketish)'] = d.get('q14', '')
        values['IN.Q14_airline'] = d.get('q14_airline', '')
        values['IN.Q15 (Daromad ulushi)'] = d.get('q15', '')
        values['IN.Q16_sum'] = d.get('q16_sum', '')
        values['IN.Q16_currency'] = d.get('q16_currency', '')
        values['IN.Q16_persons'] = d.get('q16_persons', '')
        # Q17 — 14 qator
        q17 = d.get('q17') or {}
        for n in range(1, 15):
            row = q17.get(f'r{n}') if isinstance(q17, dict) else None
            row = row if isinstance(row, dict) else {}
            values[f'IN.Q17.r{n}.amount'] = row.get('amount', '')
            values[f'IN.Q17.r{n}.currency'] = row.get('currency', '')
            values[f'IN.Q17.r{n}.inPackage'] = _yn(row.get('inPackage')) if row else ''
        # Q18 — 12 reyting
        q18 = d.get('q18') or {}
        for i, label in enumerate(_MASTER_INBOUND_RATINGS):
            if isinstance(q18, dict):
                v = q18.get(f'r{i}')
                values[f'IN.Q18.{label}'] = v if v is not None else ''
            else:
                values[f'IN.Q18.{label}'] = ''
        values['IN.Q19 (Izoh)'] = (d.get('q19') or '')[:1000]

    # ============================================================
    # Outbound bo'lsa — OUT.* ustunlarni to'ldiramiz
    # ============================================================
    else:
        values['OUT.Q1 (Asosiy davlat)'] = d.get('q1', '')
        values['OUT.Q2 (Maqsad)'] = d.get('q2', '')
        values['OUT.Q3 (Biznes turi)'] = d.get('q3', '')
        # q4_val (yangi) yoki q4_nights (eski)
        values['OUT.Q4_val (Tunlar)'] = d.get('q4_val', d.get('q4_nights', ''))
        values['OUT.Q5 (Turar joy)'] = d.get('q5', '')
        values['OUT.Q6 (Paket?)'] = d.get('q6', '')
        values['OUT.Q7 (Paket tunlari)'] = d.get('q7', '')
        values['OUT.Q8 (Paket kishi)'] = d.get('q8', d.get('q8_persons', ''))
        values['OUT.Q9_amount'] = d.get('q9_amount', '')
        values['OUT.Q9_currency'] = d.get('q9_currency', '')
        values['OUT.Q10 (Chiqish)'] = d.get('q10', '')
        values['OUT.Q10_airline'] = d.get('q10_airline', '')
        values['OUT.Q11 (Qaytish)'] = d.get('q11', '')
        values['OUT.Q11_airline'] = d.get('q11_airline', '')
        values['OUT.Q12 (Daromad ulushi)'] = d.get('q12', '')
        values['OUT.Q13_amount'] = d.get('q13_amount', d.get('q13_sum', ''))
        values['OUT.Q13_currency'] = d.get('q13_currency', '')
        values['OUT.Q13_persons'] = d.get('q13_persons', '')
        # Q14 — sub-rowlar bilan
        q14 = d.get('q14') or {}
        for n in _MASTER_OUTBOUND_EXP_ROWS:
            row = q14.get(f'r{n}') if isinstance(q14, dict) else None
            row = row if isinstance(row, dict) else {}
            values[f'OUT.Q14.r{n}.amount'] = row.get('amount', '')
            values[f'OUT.Q14.r{n}.currency'] = row.get('currency', '')
            values[f'OUT.Q14.r{n}.inPkg'] = _yn(row.get('inPkg')) if row else ''

    # Tartib bo'yicha qaytarish — bo'lmagan kalitlar uchun bo'sh
    return [values.get(col, '') for col in columns]


# ============================================
# MONITORING — har bir savol bo'yicha taqsimot (faqat superuser)
# ============================================

# Inbound savollarining ko'rinadigan nomlari (UZ)
INBOUND_Q_LABELS = {
    'q1': '1. Doimiy yashash mamlakati',
    'q2': '2. Pasport',
    'q3': '3. Tashrif maqsadi',
    'q4': '4. Biznes tashrif turi',
    'q5': '5. Tunlar soni',
    'q6': '6. Shaharlar / regionlar',
    'q7': '7. Turar joy turi',
    'q8': '8. Ovqat olingan joylar',
    'q9': '9. Paketli tur orqali keldimi?',
    'q10': '10. Paket tunlari (jami / UZ)',
    'q11': '11. Paketdagi kishilar',
    'q12': '12. Paket narxi',
    'q13': '13. Kelish transporti',
    'q14': '14. Ketish transporti',
    'q15': '15. Daromad ulushi (xorijiy ishchilar)',
    'q16': '16. Umumiy xarajat',
    'q17': '17. Xarajatlar jadvali (TOP qatorlar)',
    'q18': '18. Xizmatlar reytingi (1-10)',
    'q19': '19. Izoh',
}

OUTBOUND_Q_LABELS = {
    'q1': '1. Sayohat asosiy davlati',
    'q2': '2. Sayohat maqsadi',
    'q3': '3. Biznes tashrif turi',
    'q4': '4. Chet elda tunlar',
    'q5': '5. Turar joy turi',
    'q6': '6. Paket tur?',
    'q7': '7. Paket tunlar',
    'q8': '8. Paket kishilar',
    'q9': '9. Paket narxi',
    'q10': '10. UZ dan chiqish transporti',
    'q11': '11. UZ ga qaytish transporti',
    'q12': '12. Daromad ulushi (employment)',
    'q13': '13. Umumiy xarajat',
    'q14': '14. Xarajatlar jadvali',
}

# Inbound Q18 — 12 ta xizmat
RATING_LABELS_UZ = [
    'Xalqaro transport (UZ kompaniyalari)',
    'Pasport nazorati',
    'Mehmondo\'stlik',
    'Sifat/narx nisbati',
    'Ovqat',
    'Tozalik',
    'Transport (UZ ichida)',
    'Xavfsizlik',
    'Madaniyat va ko\'ngilochar',
    'Turar joy',
    'Sog\'liq xizmatlari',
    'Aloqa/Internet/Wi-Fi',
]

# Inbound Q17 — 14 ta xarajat qatori
INBOUND_EXP_LABELS = [
    'Turar joy', 'Ovqat', 'Xalqaro transport', 'Mahalliy transport',
    'Madaniy xizmatlar', 'Sport / ko\'ngilochar', 'Ta\'lim', 'Turizm xizmatlari (UZ)',
    'Tibbiy', 'Yoqilg\'i va xizmat', 'Qimmatbaho buyumlar', 'Xaridlar (do\'kon)',
    'Qayta sotish uchun', 'Boshqa',
]
# Outbound Q14 — 13 ta xarajat (1, 1.1, 1.2, 2..13)
OUTBOUND_EXP_LABELS = [
    ('1', 'Turar joy'),
    ('1.1', '— kommunal toʻlovlar (employment)'),
    ('1.2', '— soliqlar va ruxsatnoma (employment)'),
    ('2', 'Ovqat va ichimliklar'),
    ('3', 'Xalqaro transport'),
    ('4', 'Mahalliy transport'),
    ('5', 'Madaniy xizmatlar'),
    ('6', 'Sport / ko\'ngilochar'),
    ('7', 'Ta\'lim'),
    ('8', 'Tibbiy xizmatlar'),
    ('9', 'Yoqilg\'i va xizmat'),
    ('10', 'Qimmatbaho buyumlar'),
    ('11', 'Xaridlar'),
    ('12', 'Qayta sotish uchun'),
    ('13', 'Boshqa xarajatlar'),
]


def _counter_top(counter, top=15):
    """Counter dan top N ta itemni list of (label, count) qaytaradi."""
    return [{'label': k or '—', 'count': v} for k, v in counter.most_common(top)]


def _nights_buckets(nights_list):
    """Tunlar ro'yxatini diapazonlarga bo'lish."""
    buckets = [
        ('0 tun', lambda n: n == 0),
        ('1 tun', lambda n: n == 1),
        ('2 tun', lambda n: n == 2),
        ('3-5 tun', lambda n: 3 <= n <= 5),
        ('6-10 tun', lambda n: 6 <= n <= 10),
        ('11-20 tun', lambda n: 11 <= n <= 20),
        ('21-30 tun', lambda n: 21 <= n <= 30),
        ('30+ tun', lambda n: n > 30),
    ]
    result = []
    for label, predicate in buckets:
        count = sum(1 for n in nights_list if predicate(n))
        if count:
            result.append({'label': label, 'count': count})
    return result


def _currency_stats(amounts_by_currency):
    """Valyuta bo'yicha statistika.

    Args:
        amounts_by_currency: dict[currency_code] -> list[float]
    Returns:
        list of {currency, count, sum, avg, median, min, max}, count DESC
    """
    result = []
    for cur, amounts in (amounts_by_currency or {}).items():
        # Faqat musbat sonlar
        clean = []
        for a in amounts or []:
            try:
                v = float(a)
                if v > 0:
                    clean.append(v)
            except (TypeError, ValueError):
                continue
        if not clean:
            continue
        clean_sorted = sorted(clean)
        n = len(clean_sorted)
        if n % 2 == 1:
            median = clean_sorted[n // 2]
        else:
            median = (clean_sorted[n // 2 - 1] + clean_sorted[n // 2]) / 2
        total = sum(clean)
        result.append({
            'currency': cur or '—',
            'count': n,
            'sum': round(total, 2),
            'avg': round(total / n, 2),
            'median': round(median, 2),
            'min': round(min(clean), 2),
            'max': round(max(clean), 2),
        })
    result.sort(key=lambda x: (-x['count'], x['currency']))
    return result


def _format_money(amount, currency=''):
    """Pul summasini o'qib bo'ladigan formatga keltiradi: '1,234.56 USD'."""
    try:
        return f"{float(amount):,.2f} {currency}".strip()
    except (TypeError, ValueError):
        return ''


def _build_expense_currency_table(labels, used_counter, by_currency_dict):
    """Xarajat jadvali — valyutalar kolonka, qatorlar xarajat turlari.

    Args:
        labels: xarajat turlari ro'yxati (tartibli)
        used_counter: Counter[label] -> used count
        by_currency_dict: dict[label] -> dict[currency] -> list of amounts

    Returns:
        {
          'currencies': ['USD', 'UZS', ...],  # umumiy summa DESC
          'rows': [
            {'label': 'Turar joy', 'used_count': 46,
             'values': [14940, 12795687, 935, ...]},  # currencies tartibida
            ...
          ],
          'totals': [sum_USD, sum_UZS, ...],  # currencies tartibida
          'total_used': 309,
        }
    """
    # Avval — barcha valyutalar bo'yicha umumiy summalarni hisoblaymiz
    grand_totals = {}
    label_sums = {}  # label -> {currency: sum}
    for label in labels:
        by_cur = by_currency_dict.get(label, {}) or {}
        sums = {}
        for cur, amounts in by_cur.items():
            try:
                total = sum(float(a) for a in amounts if a is not None and float(a) > 0)
            except (TypeError, ValueError):
                total = 0
            if total > 0:
                sums[cur] = round(total, 2)
                grand_totals[cur] = grand_totals.get(cur, 0) + total
        label_sums[label] = sums

    # Valyutalarni umumiy summa bo'yicha sortlash (eng katta avval)
    currencies = sorted(grand_totals.keys(), key=lambda c: -grand_totals[c])
    # Agar valyuta yo'q bo'lsa, bo'sh table
    if not currencies:
        return {'currencies': [], 'rows': [], 'totals': [], 'total_used': 0}

    rows = []
    total_used = 0
    for label in labels:
        used = used_counter.get(label, 0)
        if used == 0:
            continue  # bo'sh qatorlarni ko'rsatmaymiz
        sums = label_sums.get(label, {})
        values = [round(sums.get(cur, 0), 2) for cur in currencies]
        rows.append({
            'label': label,
            'used_count': used,
            'values': values,
        })
        total_used += used

    totals = [round(grand_totals.get(cur, 0), 2) for cur in currencies]
    return {
        'currencies': currencies,
        'rows': rows,
        'totals': totals,
        'total_used': total_used,
    }


def _money_buckets(amounts):
    """Xarajat summalarini diapazonlarga bo'lish (USD ekvivalent emas — yaqinroqlik uchun)."""
    buckets = [
        ('< 100', lambda v: v < 100),
        ('100–500', lambda v: 100 <= v < 500),
        ('500–1k', lambda v: 500 <= v < 1000),
        ('1k–5k', lambda v: 1000 <= v < 5000),
        ('5k–10k', lambda v: 5000 <= v < 10000),
        ('10k+', lambda v: v >= 10000),
    ]
    result = []
    for label, predicate in buckets:
        count = sum(1 for v in amounts if predicate(v))
        if count:
            result.append({'label': label, 'count': count})
    return result


def _analyze_inbound(qs):
    """Inbound so'rovnomalari uchun har bir savol bo'yicha statistika.

    Performance: faqat `data` JSON maydonini olamiz va iterator() bilan
    katta querysetni xotiraga butunlay yuklamasdan o'tamiz.
    """
    qs = qs.only('data').iterator(chunk_size=500)
    stats = {}
    countries = Counter()
    purposes = Counter()
    passport_types = Counter()
    business_types = Counter()
    nights = []
    cities = Counter()
    accommodation = Counter()
    food_places = Counter()
    package = Counter()
    pkg_nights_total = []
    pkg_nights_uz = []
    pkg_persons = []
    pkg_amount = []
    transport_in = Counter()
    transport_out = Counter()
    airline_in = Counter()
    airline_out = Counter()
    income_share = Counter()
    total_spent = []
    total_persons = []
    # Q16 — valyuta bo'yicha jami va kishi boshi
    total_spent_by_currency = defaultdict(list)
    per_person_by_currency = defaultdict(list)
    # Q12 — paket narxi valyuta bo'yicha
    pkg_amount_by_currency = defaultdict(list)
    # Q17 — har xarajat qatori uchun: used/in_package/has_amount + per-currency stats
    expense_used = Counter()
    expense_in_package = Counter()
    expense_has_amount = Counter()
    expense_by_currency = {label: defaultdict(list) for label in INBOUND_EXP_LABELS}
    rating_sums = [0] * 12
    rating_counts = [0] * 12
    rating_na = [0] * 12
    comments_count = 0

    for r in qs:
        d = r.data or {}
        if d.get('q1'): countries[d['q1']] += 1
        if d.get('q3'): purposes[d['q3']] += 1
        if d.get('q2'): passport_types[d['q2']] += 1
        if d.get('q4'): business_types[d['q4']] += 1
        try:
            n = int(d.get('q5_nights')) if d.get('q5_nights') not in (None, '') else None
            if d.get('q5_zero'): n = 0
            if n is not None: nights.append(n)
        except (TypeError, ValueError):
            pass
        q6 = d.get('q6') or {}
        if isinstance(q6, dict):
            for city in q6.keys(): cities[city] += 1
        if d.get('q7') is not None and d.get('q7') != '': accommodation[str(d['q7'])] += 1
        q8 = d.get('q8') or {}
        if isinstance(q8, dict):
            for k, v in q8.items():
                if v: food_places[k] += 1
        if d.get('q9'): package[d['q9']] += 1
        try:
            if d.get('q10_total'): pkg_nights_total.append(int(d['q10_total']))
        except (TypeError, ValueError): pass
        try:
            if d.get('q10_uz'): pkg_nights_uz.append(int(d['q10_uz']))
        except (TypeError, ValueError): pass
        try:
            if d.get('q11'): pkg_persons.append(int(d['q11']))
        except (TypeError, ValueError): pass
        # Q12 — paket narxi (jami) + valyuta bo'yicha
        try:
            if d.get('q12_amount'):
                amt = float(d['q12_amount'])
                pkg_amount.append(amt)
                pkg_amount_by_currency[d.get('q12_currency') or 'UNK'].append(amt)
        except (TypeError, ValueError): pass
        if d.get('q13'): transport_in[d['q13']] += 1
        if d.get('q13_airline'): airline_in[d['q13_airline']] += 1
        if d.get('q14'): transport_out[d['q14']] += 1
        if d.get('q14_airline'): airline_out[d['q14_airline']] += 1
        if d.get('q15'): income_share[d['q15']] += 1
        # Q16 — umumiy xarajat: total + per-person + per-currency
        try:
            if d.get('q16_sum'):
                amt = float(d['q16_sum'])
                total_spent.append(amt)
                cur = d.get('q16_currency') or 'UNK'
                total_spent_by_currency[cur].append(amt)
                try:
                    persons = int(d.get('q16_persons') or 1) or 1
                    if persons > 0:
                        per_person_by_currency[cur].append(amt / persons)
                except (TypeError, ValueError): pass
        except (TypeError, ValueError): pass
        try:
            if d.get('q16_persons'): total_persons.append(int(d['q16_persons']))
        except (TypeError, ValueError): pass

        # Q17 — har qator: used / in_package / has_amount + per-currency stats
        q17 = d.get('q17') or {}
        if isinstance(q17, dict):
            for k, row in q17.items():
                if not isinstance(row, dict): continue
                idx = k.replace('r', '', 1)
                try:
                    i = int(idx) - 1
                    if i < 0 or i >= len(INBOUND_EXP_LABELS): continue
                    label = INBOUND_EXP_LABELS[i]
                    in_pkg = bool(row.get('inPackage'))
                    amount_raw = row.get('amount')
                    has_amt = False
                    if amount_raw not in (None, ''):
                        try:
                            amt = float(amount_raw)
                            if amt > 0:
                                has_amt = True
                                expense_by_currency[label][row.get('currency') or 'UNK'].append(amt)
                        except (TypeError, ValueError): pass
                    if in_pkg or has_amt:
                        expense_used[label] += 1
                    if in_pkg:
                        expense_in_package[label] += 1
                    if has_amt:
                        expense_has_amount[label] += 1
                except (ValueError, TypeError): continue

        q18 = d.get('q18') or {}
        if isinstance(q18, dict):
            for k, v in q18.items():
                try:
                    i = int(k.replace('r', ''))
                    if 0 <= i < 12:
                        if v == 'na': rating_na[i] += 1
                        else:
                            try:
                                rating_sums[i] += float(v); rating_counts[i] += 1
                            except (TypeError, ValueError): pass
                except (ValueError, TypeError): pass

        if d.get('q19'): comments_count += 1

    stats['countries'] = _counter_top(countries, 15)
    stats['purposes'] = _counter_top(purposes, 12)
    stats['passport_types'] = _counter_top(passport_types, 5)
    stats['business_types'] = _counter_top(business_types, 6)
    stats['nights_buckets'] = _nights_buckets(nights)
    stats['nights_avg'] = round(sum(nights) / len(nights), 1) if nights else 0
    stats['cities'] = _counter_top(cities, 15)
    stats['accommodation'] = _counter_top(accommodation, 10)
    stats['food_places'] = _counter_top(food_places, 10)
    stats['package'] = _counter_top(package, 3)
    stats['pkg_nights_total_avg'] = round(sum(pkg_nights_total) / len(pkg_nights_total), 1) if pkg_nights_total else 0
    stats['pkg_nights_uz_avg'] = round(sum(pkg_nights_uz) / len(pkg_nights_uz), 1) if pkg_nights_uz else 0
    stats['pkg_persons_avg'] = round(sum(pkg_persons) / len(pkg_persons), 1) if pkg_persons else 0
    stats['pkg_amount_buckets'] = _money_buckets(pkg_amount)
    stats['pkg_amount_currencies'] = _currency_stats(pkg_amount_by_currency)
    stats['transport_in'] = _counter_top(transport_in, 5)
    stats['transport_out'] = _counter_top(transport_out, 5)
    stats['airline_in'] = _counter_top(airline_in, 5)
    stats['airline_out'] = _counter_top(airline_out, 5)
    stats['income_share'] = _counter_top(income_share, 5)
    stats['total_spent_buckets'] = _money_buckets(total_spent)
    stats['total_spent_avg'] = round(sum(total_spent) / len(total_spent), 2) if total_spent else 0
    stats['total_persons_avg'] = round(sum(total_persons) / len(total_persons), 1) if total_persons else 0
    # Currency-aware breakdown
    stats['total_spent_currencies'] = _currency_stats(total_spent_by_currency)
    stats['per_person_currencies'] = _currency_stats(per_person_by_currency)
    # Q17 — har xarajat qatori uchun to'liq breakdown (eski format saqlangan)
    stats['expense_breakdown'] = [
        {
            'label': label,
            'used_count': expense_used.get(label, 0),
            'in_package_count': expense_in_package.get(label, 0),
            'has_amount_count': expense_has_amount.get(label, 0),
            'currencies': _currency_stats(expense_by_currency.get(label, {})),
        }
        for label in INBOUND_EXP_LABELS
    ]
    # Yangi: valyutalar — kolonka, qatorlar — xarajat turlari, pastida Umumiy
    stats['expense_currency_table'] = _build_expense_currency_table(
        INBOUND_EXP_LABELS, expense_used, expense_by_currency,
    )
    # Eski strukturani saqlash (orqaga moslik uchun)
    stats['expense_used'] = [{'label': l, 'count': expense_used.get(l, 0)} for l in INBOUND_EXP_LABELS]
    stats['expense_in_package'] = [{'label': l, 'count': expense_in_package.get(l, 0)} for l in INBOUND_EXP_LABELS]
    ratings = []
    for i, label in enumerate(RATING_LABELS_UZ):
        avg = round(rating_sums[i] / rating_counts[i], 2) if rating_counts[i] else 0
        ratings.append({
            'label': label, 'avg': avg,
            'count': rating_counts[i], 'na': rating_na[i],
        })
    stats['ratings'] = ratings
    stats['comments_count'] = comments_count
    return stats


def _analyze_outbound(qs):
    """Outbound so'rovnomalari uchun har bir savol bo'yicha statistika."""
    qs = qs.only('data').iterator(chunk_size=500)
    stats = {}
    countries = Counter()
    purposes = Counter()
    business_types = Counter()
    nights = []
    accommodation = Counter()
    package = Counter()
    pkg_nights = []
    pkg_persons = []
    pkg_amount = []
    transport_out = Counter()
    transport_in = Counter()
    airline_out = Counter()
    airline_in = Counter()
    income_share = Counter()
    total_spent = []
    total_persons = []
    # Q13 — valyuta bo'yicha jami va kishi boshi
    total_spent_by_currency = defaultdict(list)
    per_person_by_currency = defaultdict(list)
    # Q9 — paket narxi valyuta bo'yicha
    pkg_amount_by_currency = defaultdict(list)
    # Q14 — har xarajat qatori
    expense_used = Counter()
    expense_in_pkg = Counter()
    expense_has_amount = Counter()
    ordered_labels_for_init = [lbl for _, lbl in OUTBOUND_EXP_LABELS]
    expense_by_currency = {label: defaultdict(list) for label in ordered_labels_for_init}

    for r in qs:
        d = r.data or {}
        if d.get('q1'): countries[d['q1']] += 1
        if d.get('q2'): purposes[d['q2']] += 1
        if d.get('q3'): business_types[d['q3']] += 1
        try:
            n = d.get('q4_val')
            if n in (None, ''): n = d.get('q4_nights')
            if n not in (None, ''):
                nights.append(int(n))
        except (TypeError, ValueError): pass
        if d.get('q5'): accommodation[str(d['q5'])] += 1
        if d.get('q6'): package[d['q6']] += 1
        try:
            if d.get('q7'): pkg_nights.append(int(d['q7']))
        except (TypeError, ValueError): pass
        try:
            v = d.get('q8') or d.get('q8_persons')
            if v: pkg_persons.append(int(v))
        except (TypeError, ValueError): pass
        # Q9 — paket narxi + valyuta
        try:
            if d.get('q9_amount'):
                amt = float(d['q9_amount'])
                pkg_amount.append(amt)
                pkg_amount_by_currency[d.get('q9_currency') or 'UNK'].append(amt)
        except (TypeError, ValueError): pass
        if d.get('q10'): transport_out[d['q10']] += 1
        if d.get('q10_airline'): airline_out[d['q10_airline']] += 1
        if d.get('q11'): transport_in[d['q11']] += 1
        if d.get('q11_airline'): airline_in[d['q11_airline']] += 1
        if d.get('q12'): income_share[d['q12']] += 1
        # Q13 — umumiy xarajat + valyuta + kishi boshi
        try:
            amount = d.get('q13_amount') or d.get('q13_sum')
            if amount:
                amt = float(amount)
                total_spent.append(amt)
                cur = d.get('q13_currency') or 'UNK'
                total_spent_by_currency[cur].append(amt)
                try:
                    persons = int(d.get('q13_persons') or 1) or 1
                    if persons > 0:
                        per_person_by_currency[cur].append(amt / persons)
                except (TypeError, ValueError): pass
        except (TypeError, ValueError): pass
        try:
            if d.get('q13_persons'): total_persons.append(int(d['q13_persons']))
        except (TypeError, ValueError): pass

        # Q14 — har qator: used / in_pkg / has_amount + per-currency stats
        q14 = d.get('q14') or {}
        if isinstance(q14, dict):
            label_map = {n: lbl for n, lbl in OUTBOUND_EXP_LABELS}
            for k, row in q14.items():
                if not isinstance(row, dict): continue
                rn = k.replace('r', '', 1)
                label = label_map.get(rn, rn)
                in_pkg = bool(row.get('inPkg'))
                amount_raw = row.get('amount')
                has_amt = False
                if amount_raw not in (None, ''):
                    try:
                        amt = float(amount_raw)
                        if amt > 0:
                            has_amt = True
                            if label in expense_by_currency:
                                expense_by_currency[label][row.get('currency') or 'UNK'].append(amt)
                    except (TypeError, ValueError): pass
                if in_pkg or has_amt:
                    expense_used[label] += 1
                if in_pkg:
                    expense_in_pkg[label] += 1
                if has_amt:
                    expense_has_amount[label] += 1

    stats['countries'] = _counter_top(countries, 15)
    stats['purposes'] = _counter_top(purposes, 12)
    stats['business_types'] = _counter_top(business_types, 6)
    stats['nights_buckets'] = _nights_buckets(nights)
    stats['nights_avg'] = round(sum(nights) / len(nights), 1) if nights else 0
    stats['accommodation'] = _counter_top(accommodation, 10)
    stats['package'] = _counter_top(package, 3)
    stats['pkg_nights_avg'] = round(sum(pkg_nights) / len(pkg_nights), 1) if pkg_nights else 0
    stats['pkg_persons_avg'] = round(sum(pkg_persons) / len(pkg_persons), 1) if pkg_persons else 0
    stats['pkg_amount_buckets'] = _money_buckets(pkg_amount)
    stats['pkg_amount_currencies'] = _currency_stats(pkg_amount_by_currency)
    stats['transport_out'] = _counter_top(transport_out, 5)
    stats['transport_in'] = _counter_top(transport_in, 5)
    stats['airline_out'] = _counter_top(airline_out, 5)
    stats['airline_in'] = _counter_top(airline_in, 5)
    stats['income_share'] = _counter_top(income_share, 5)
    stats['total_spent_buckets'] = _money_buckets(total_spent)
    stats['total_spent_avg'] = round(sum(total_spent) / len(total_spent), 2) if total_spent else 0
    stats['total_persons_avg'] = round(sum(total_persons) / len(total_persons), 1) if total_persons else 0
    # Currency-aware breakdown
    stats['total_spent_currencies'] = _currency_stats(total_spent_by_currency)
    stats['per_person_currencies'] = _currency_stats(per_person_by_currency)
    # Q14 — har xarajat qatori uchun to'liq breakdown (eski)
    ordered_labels = [lbl for _, lbl in OUTBOUND_EXP_LABELS]
    stats['expense_breakdown'] = [
        {
            'label': label,
            'used_count': expense_used.get(label, 0),
            'in_package_count': expense_in_pkg.get(label, 0),
            'has_amount_count': expense_has_amount.get(label, 0),
            'currencies': _currency_stats(expense_by_currency.get(label, {})),
        }
        for label in ordered_labels
    ]
    # Yangi: valyutalar — kolonka, pastida Umumiy
    stats['expense_currency_table'] = _build_expense_currency_table(
        ordered_labels, expense_used, expense_by_currency,
    )
    # Eski strukturani saqlash
    stats['expense_used'] = [{'label': l, 'count': expense_used.get(l, 0)} for l in ordered_labels]
    stats['expense_in_package'] = [{'label': l, 'count': expense_in_pkg.get(l, 0)} for l in ordered_labels]
    return stats


@superuser_required
def monitoring(request):
    """Har bir savol bo'yicha monitoring — faqat superuser.

    Filtr: sana oralig'i, manba (public/staff), bo'lim, til.
    Sahifa Inbound va Outbound uchun alohida tab/qism bilan ko'rsatadi.
    """
    qs = SurveyResponse.objects.filter(is_completed=True)

    # Filtrlar
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    source = request.GET.get('source')  # 'public' | 'staff' | ''
    office_id = request.GET.get('office')
    language = request.GET.get('language')
    screening_status = request.GET.get('screening')  # 'eligible' | 'terminated' | ''

    if date_from: qs = qs.filter(started_at__date__gte=date_from)
    if date_to: qs = qs.filter(started_at__date__lte=date_to)
    if source in ('public', 'staff'): qs = qs.filter(source=source)
    if office_id:
        try: qs = qs.filter(postal_office_id=int(office_id))
        except ValueError: pass
    if language: qs = qs.filter(language=language)
    if screening_status in ('eligible', 'terminated', 'skipped'):
        qs = qs.filter(screening_status=screening_status)

    inbound_qs = qs.filter(survey_type=SurveyResponse.SURVEY_INBOUND)
    outbound_qs = qs.filter(survey_type=SurveyResponse.SURVEY_OUTBOUND)

    # Asosiy summary
    total = qs.count()
    inbound_total = inbound_qs.count()
    outbound_total = outbound_qs.count()
    public_total = qs.filter(source=SurveyResponse.SOURCE_PUBLIC).count()
    staff_total = qs.filter(source=SurveyResponse.SOURCE_STAFF).count()

    # Screening taqsimoti
    screening_dist = list(
        qs.values('screening_status')
        .annotate(c=Count('id')).order_by('-c')
    )

    # Tillar taqsimoti
    languages_dist = list(
        qs.values('language').annotate(c=Count('id')).order_by('-c')
    )

    # Har bir savol bo'yicha tahlil — manba bo'yicha alohida
    def _analyze_split(base_qs, analyzer):
        total = base_qs.count()
        if not total:
            return None
        public_qs = base_qs.filter(source=SurveyResponse.SOURCE_PUBLIC)
        staff_qs = base_qs.filter(source=SurveyResponse.SOURCE_STAFF)
        result = {
            'all': analyzer(base_qs),
            'all_total': total,
            'public_total': public_qs.count(),
            'staff_total': staff_qs.count(),
        }
        result['public'] = analyzer(public_qs) if result['public_total'] else None
        result['staff'] = analyzer(staff_qs) if result['staff_total'] else None
        return result

    inbound_stats = _analyze_split(inbound_qs, _analyze_inbound)
    outbound_stats = _analyze_split(outbound_qs, _analyze_outbound)

    # ============================================
    # IP tahlil
    # ============================================
    ip_stats = _analyze_ips(qs)

    # ============================================
    # Device tahlil
    # ============================================
    device_stats = _analyze_devices(qs)

    # ============================================
    # Fraud / Risk hisobi
    # ============================================
    postal_office_coords = {}  # office_id → (lat, lon) — agar saqlangan bo'lsa
    # PostalOffice modelda lat/lon saqlanmagan (faqat address) — bu lekin foydali bo'lardi
    risks = evaluate_all(qs, postal_office_coords=postal_office_coords, only_risky=True, top_n=100)
    risk_summary = aggregate_risk_summary(risks)

    context = {
        'total': total,
        'inbound_total': inbound_total,
        'outbound_total': outbound_total,
        'public_total': public_total,
        'staff_total': staff_total,
        'screening_dist': screening_dist,
        'languages_dist': languages_dist,
        'inbound_stats': inbound_stats,
        'outbound_stats': outbound_stats,
        'inbound_q_labels': INBOUND_Q_LABELS,
        'outbound_q_labels': OUTBOUND_Q_LABELS,
        'offices': PostalOffice.objects.filter(is_active=True),
        'languages_choices': SurveyResponse.LANGUAGES,
        'ip_stats': ip_stats,
        'device_stats': device_stats,
        'risks': risks,
        'risk_summary': risk_summary,
        'filters': {
            'from': date_from or '',
            'to': date_to or '',
            'source': source or '',
            'office': office_id or '',
            'language': language or '',
            'screening': screening_status or '',
        },
    }
    return render(request, 'dashboard/monitoring.html', context)


# ============================================
# IP & Device analytics
# ============================================

def _analyze_ips(qs, top_n=30):
    """IP bo'yicha tahlil: har IP uchun source, type, devices, staff loginlari."""
    ip_data = {}
    iterable = qs.only(
        'ip_address', 'source', 'survey_type', 'device_type', 'os_name',
        'started_at', 'staff_id', 'staff__username', 'country', 'device_info',
    ).select_related('staff').iterator(chunk_size=500)

    for r in iterable:
        ip = r.ip_address or ''
        if not ip:
            continue
        if ip not in ip_data:
            ip_data[ip] = {
                'ip': ip,
                'subnet': ip_to_subnet24(ip),
                'total': 0,
                'public': 0,
                'staff': 0,
                'inbound': 0,
                'outbound': 0,
                'devices': Counter(),
                'os': Counter(),
                'countries': Counter(),
                'staff_logins': set(),
                'first_seen': None,
                'last_seen': None,
                'suspicious': False,
                'reasons': [],
            }
        d = ip_data[ip]
        d['total'] += 1
        d[r.source] += 1
        if r.survey_type == SurveyResponse.SURVEY_INBOUND:
            d['inbound'] += 1
        else:
            d['outbound'] += 1
        if r.device_type: d['devices'][r.device_type] += 1
        if r.os_name: d['os'][r.os_name] += 1
        if r.country: d['countries'][r.country] += 1
        if r.staff_id and r.staff:
            # tuple: (id, username) — template'da link qilish uchun
            d['staff_logins'].add((r.staff_id, r.staff.username or f"user#{r.staff_id}"))
        if r.started_at:
            if d['first_seen'] is None or r.started_at < d['first_seen']:
                d['first_seen'] = r.started_at
            if d['last_seen'] is None or r.started_at > d['last_seen']:
                d['last_seen'] = r.started_at

    # Shubhali belgilash + Counter -> dict (Django template lookup uchun)
    for ip, d in ip_data.items():
        reasons = []
        if d['public'] > 0 and d['staff'] > 0:
            reasons.append("Staff va public bir IP'da")
        if d['public'] >= 10:
            reasons.append(f"{d['public']} ta public so'rovnoma (yuqori hajm)")
        if len(d['countries']) >= 5 and d['public'] > 0:
            reasons.append(f"{len(d['countries'])} ta turli davlat — shubhali")
        d['reasons'] = reasons
        d['suspicious'] = bool(reasons)
        d['unique_countries'] = len(d['countries'])
        # Counter -> plain dict (Counter.__getitem__ missing keys uchun 0 qaytaradi
        # va Django {% for x, y in d.devices.items %} chaqirig'ini buzadi)
        d['devices'] = dict(d['devices'])
        d['os'] = dict(d['os'])
        d['countries'] = dict(d['countries'])
        # tuplelarni sort qilamiz username bo'yicha
        d['staff_logins'] = sorted(d['staff_logins'], key=lambda x: x[1])

    # Sort: shubhali avval, keyin total DESC
    items = list(ip_data.values())
    items.sort(key=lambda x: (not x['suspicious'], -x['total']))
    return {
        'top': items[:top_n],
        'total_unique_ips': len(ip_data),
        'suspicious_count': sum(1 for d in ip_data.values() if d['suspicious']),
        'shared_ips_count': sum(1 for d in ip_data.values() if d['public'] > 0 and d['staff'] > 0),
        'high_volume_count': sum(1 for d in ip_data.values() if d['public'] >= 10),
    }


@superuser_required
def monitoring_staff_detail(request, staff_id):
    """Bir xodim bo'yicha to'liq monitoring (IP, device, GPS, takrorlangan).

    Faqat superuser kira oladi.
    """
    from django.contrib.auth.models import User
    from django.shortcuts import get_object_or_404

    staff_user = get_object_or_404(User, id=staff_id)
    qs = SurveyResponse.objects.filter(staff=staff_user, is_completed=True)

    total = qs.count()
    if total == 0:
        return render(request, 'dashboard/monitoring_staff.html', {
            'staff_user': staff_user, 'total': 0,
        })

    # Asosiy taqsimotlar
    by_type = list(qs.values('survey_type').annotate(c=Count('id')).order_by('-c'))
    by_lang = list(qs.values('language').annotate(c=Count('id')).order_by('-c'))

    # IP'lar
    ip_counter = Counter()
    device_counter = Counter()
    os_counter = Counter()
    browser_counter = Counter()
    fingerprints = Counter()
    durations = []
    gps_points = []

    iterable = qs.only(
        'ip_address', 'device_type', 'os_name', 'browser_name',
        'device_info', 'fill_duration_ms', 'latitude', 'longitude',
        'started_at', 'survey_type', 'country',
    ).iterator(chunk_size=500)
    for r in iterable:
        if r.ip_address: ip_counter[r.ip_address] += 1
        if r.device_type: device_counter[r.device_type] += 1
        if r.os_name: os_counter[r.os_name] += 1
        if r.browser_name: browser_counter[r.browser_name] += 1
        fp = device_fingerprint(r.device_info or {})
        if fp: fingerprints[fp] += 1
        if r.fill_duration_ms: durations.append(r.fill_duration_ms)
        if r.latitude is not None and r.longitude is not None:
            gps_points.append({
                'lat': float(r.latitude),
                'lon': float(r.longitude),
                'date': r.started_at.strftime('%Y-%m-%d %H:%M') if r.started_at else '',
                'type': r.survey_type,
                'country': r.country or '',
            })

    # Pochta bo'limi yaqindan masofa hisobi (agar pochta bo'limining GPS si mavjud bo'lsa)
    avg_duration_ms = round(sum(durations) / len(durations)) if durations else 0

    # Recent so'rovnomalar (50 ta)
    recent = list(
        qs.select_related('postal_office').order_by('-started_at')[:50]
    )

    # Fraud detection (faqat shu staff'ning yozuvlari uchun) — meaningful emas,
    # chunki staff bir o'zining yozuvlari evaluator'da staff_public_same_ip ni sezmaydi
    # Lekin biz uni qo'shsa-qo'shmasak ham foydali.

    # IP'lar — public so'rovnomalar bilan kross-reference
    public_qs = SurveyResponse.objects.filter(
        is_completed=True, source=SurveyResponse.SOURCE_PUBLIC,
    )
    public_ips = set(
        public_qs.filter(ip_address__in=list(ip_counter.keys()))
        .values_list('ip_address', flat=True).distinct()
    )
    suspicious_ips = sorted(
        [(ip, cnt) for ip, cnt in ip_counter.items() if ip in public_ips],
        key=lambda x: -x[1],
    )

    context = {
        'staff_user': staff_user,
        'total': total,
        'by_type': by_type,
        'by_lang': by_lang,
        'ip_list': ip_counter.most_common(20),
        'device_list': device_counter.most_common(),
        'os_list': os_counter.most_common(),
        'browser_list': browser_counter.most_common(),
        'fingerprint_list': fingerprints.most_common(10),
        'avg_duration_ms': avg_duration_ms,
        'avg_duration_sec': round(avg_duration_ms / 1000) if avg_duration_ms else 0,
        'gps_points': gps_points,
        'recent': recent,
        'suspicious_ips': suspicious_ips,
        'staff_profile': getattr(staff_user, 'staff_profile', None),
    }
    return render(request, 'dashboard/monitoring_staff.html', context)


def _analyze_devices(qs):
    """Device turi, OS, brauzer bo'yicha tahlil."""
    device_types = Counter()
    os_dist = Counter()
    browsers = Counter()
    by_source = defaultdict(Counter)  # (source, device_type)
    fingerprints = Counter()
    iterable = qs.only(
        'device_type', 'os_name', 'browser_name', 'source', 'device_info',
    ).iterator(chunk_size=500)
    for r in iterable:
        dt = r.device_type or 'unknown'
        device_types[dt] += 1
        if r.os_name: os_dist[r.os_name] += 1
        if r.browser_name: browsers[r.browser_name] += 1
        by_source[r.source][dt] += 1
        fp = device_fingerprint(r.device_info or {})
        if fp: fingerprints[fp] += 1

    reused_devices = [(fp, count) for fp, count in fingerprints.most_common(20) if count >= 3]

    return {
        'device_types': [{'label': k, 'count': v} for k, v in device_types.most_common()],
        'os': [{'label': k, 'count': v} for k, v in os_dist.most_common(10)],
        'browsers': [{'label': k, 'count': v} for k, v in browsers.most_common(10)],
        'by_source_public': dict(by_source.get('public', {})),
        'by_source_staff': dict(by_source.get('staff', {})),
        'reused_devices': [{'fp': fp, 'count': c} for fp, c in reused_devices],
        'total_unique_devices': len(fingerprints),
    }
