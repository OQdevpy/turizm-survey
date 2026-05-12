import io
import json
from datetime import timedelta

from django.db.models import Count, Sum, Q
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
    gmaps_col = 20  # 1-indexed
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
