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
    expense_used = Counter()
    expense_in_package = Counter()
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
        try:
            if d.get('q12_amount'): pkg_amount.append(float(d['q12_amount']))
        except (TypeError, ValueError): pass
        if d.get('q13'): transport_in[d['q13']] += 1
        if d.get('q13_airline'): airline_in[d['q13_airline']] += 1
        if d.get('q14'): transport_out[d['q14']] += 1
        if d.get('q14_airline'): airline_out[d['q14_airline']] += 1
        if d.get('q15'): income_share[d['q15']] += 1
        try:
            if d.get('q16_sum'): total_spent.append(float(d['q16_sum']))
        except (TypeError, ValueError): pass
        try:
            if d.get('q16_persons'): total_persons.append(int(d['q16_persons']))
        except (TypeError, ValueError): pass

        q17 = d.get('q17') or {}
        if isinstance(q17, dict):
            for k, row in q17.items():
                if not isinstance(row, dict): continue
                idx = k.replace('r', '', 1)
                try:
                    i = int(idx) - 1
                    if i < 0 or i >= len(INBOUND_EXP_LABELS): continue
                    label = INBOUND_EXP_LABELS[i]
                    if row.get('amount') or row.get('inPackage'):
                        expense_used[label] += 1
                    if row.get('inPackage'):
                        expense_in_package[label] += 1
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
    stats['transport_in'] = _counter_top(transport_in, 5)
    stats['transport_out'] = _counter_top(transport_out, 5)
    stats['airline_in'] = _counter_top(airline_in, 5)
    stats['airline_out'] = _counter_top(airline_out, 5)
    stats['income_share'] = _counter_top(income_share, 5)
    stats['total_spent_buckets'] = _money_buckets(total_spent)
    stats['total_spent_avg'] = round(sum(total_spent) / len(total_spent), 2) if total_spent else 0
    stats['total_persons_avg'] = round(sum(total_persons) / len(total_persons), 1) if total_persons else 0
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
    expense_used = Counter()
    expense_in_pkg = Counter()

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
        try:
            if d.get('q9_amount'): pkg_amount.append(float(d['q9_amount']))
        except (TypeError, ValueError): pass
        if d.get('q10'): transport_out[d['q10']] += 1
        if d.get('q10_airline'): airline_out[d['q10_airline']] += 1
        if d.get('q11'): transport_in[d['q11']] += 1
        if d.get('q11_airline'): airline_in[d['q11_airline']] += 1
        if d.get('q12'): income_share[d['q12']] += 1
        try:
            amount = d.get('q13_amount') or d.get('q13_sum')
            if amount: total_spent.append(float(amount))
        except (TypeError, ValueError): pass
        try:
            if d.get('q13_persons'): total_persons.append(int(d['q13_persons']))
        except (TypeError, ValueError): pass

        q14 = d.get('q14') or {}
        if isinstance(q14, dict):
            label_map = {n: lbl for n, lbl in OUTBOUND_EXP_LABELS}
            for k, row in q14.items():
                if not isinstance(row, dict): continue
                rn = k.replace('r', '', 1)
                label = label_map.get(rn, rn)
                if row.get('amount') or row.get('inPkg'):
                    expense_used[label] += 1
                if row.get('inPkg'):
                    expense_in_pkg[label] += 1

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
    stats['transport_out'] = _counter_top(transport_out, 5)
    stats['transport_in'] = _counter_top(transport_in, 5)
    stats['airline_out'] = _counter_top(airline_out, 5)
    stats['airline_in'] = _counter_top(airline_in, 5)
    stats['income_share'] = _counter_top(income_share, 5)
    stats['total_spent_buckets'] = _money_buckets(total_spent)
    stats['total_spent_avg'] = round(sum(total_spent) / len(total_spent), 2) if total_spent else 0
    stats['total_persons_avg'] = round(sum(total_persons) / len(total_persons), 1) if total_persons else 0
    ordered_labels = [lbl for _, lbl in OUTBOUND_EXP_LABELS]
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

    # Screening taqsimoti
    screening_dist = list(
        qs.values('screening_status')
        .annotate(c=Count('id')).order_by('-c')
    )

    # Tillar taqsimoti
    languages_dist = list(
        qs.values('language').annotate(c=Count('id')).order_by('-c')
    )

    # Har bir savol bo'yicha tahlil
    inbound_stats = _analyze_inbound(inbound_qs) if inbound_total else None
    outbound_stats = _analyze_outbound(outbound_qs) if outbound_total else None

    context = {
        'total': total,
        'inbound_total': inbound_total,
        'outbound_total': outbound_total,
        'screening_dist': screening_dist,
        'languages_dist': languages_dist,
        'inbound_stats': inbound_stats,
        'outbound_stats': outbound_stats,
        'inbound_q_labels': INBOUND_Q_LABELS,
        'outbound_q_labels': OUTBOUND_Q_LABELS,
        'offices': PostalOffice.objects.filter(is_active=True),
        'languages_choices': SurveyResponse.LANGUAGES,
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
