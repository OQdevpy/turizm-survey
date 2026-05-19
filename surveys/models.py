import uuid

from django.conf import settings
from django.db import models

from accounts.models import PostalOffice


class SurveyResponse(models.Model):
    SURVEY_INBOUND = 'inbound'
    SURVEY_OUTBOUND = 'outbound'
    SURVEY_TYPES = [
        (SURVEY_INBOUND, "Inbound (xorijliklar)"),
        (SURVEY_OUTBOUND, "Outbound (chiqish)"),
    ]

    SOURCE_PUBLIC = 'public'
    SOURCE_STAFF = 'staff'
    SOURCES = [
        (SOURCE_PUBLIC, "Turist o'zi to'ldirgan"),
        (SOURCE_STAFF, "Xodim kiritgan"),
    ]

    LANG_UZ = 'uz'
    LANG_RU = 'ru'
    LANG_EN = 'en'
    LANG_AR = 'ar'
    LANG_ZH = 'zh'
    LANG_FR = 'fr'
    LANG_DE = 'de'
    LANG_IT = 'it'
    LANG_ES = 'es'
    LANG_TG = 'tg'
    LANGUAGES = [
        (LANG_UZ, "O'zbekcha"),
        (LANG_RU, 'Русский'),
        (LANG_EN, 'English'),
        (LANG_AR, 'العربية'),
        (LANG_ZH, '中文'),
        (LANG_FR, 'Français'),
        (LANG_DE, 'Deutsch'),
        (LANG_IT, 'Italiano'),
        (LANG_ES, 'Español'),
        (LANG_TG, 'Тоҷикӣ'),
    ]

    # Screening (filtr) natijasi — F1/F2/F3 yes/no/null
    SCREENING_ELIGIBLE = 'eligible'
    SCREENING_TERMINATED = 'terminated'
    SCREENING_SKIPPED = 'skipped'
    SCREENING_STATUSES = [
        (SCREENING_ELIGIBLE, "O'tdi"),
        (SCREENING_TERMINATED, "To'xtatildi"),
        (SCREENING_SKIPPED, "O'tkazib yuborildi"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey_type = models.CharField("So'rovnoma turi", max_length=10, choices=SURVEY_TYPES, db_index=True)
    source = models.CharField("Manba", max_length=10, choices=SOURCES, default=SOURCE_PUBLIC, db_index=True)

    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='entered_surveys',
        verbose_name="Kiritgan xodim",
    )
    postal_office = models.ForeignKey(
        PostalOffice,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='surveys',
        verbose_name="Pochta bo'limi",
    )

    language = models.CharField("Til", max_length=5, choices=LANGUAGES, default=LANG_UZ)

    # Screening (filtr) javoblari — saqlash uchun
    screening_status = models.CharField(
        "Filtr (screening) holati",
        max_length=20, choices=SCREENING_STATUSES, default=SCREENING_SKIPPED, db_index=True,
    )
    screening_data = models.JSONField(
        "Filtr javoblari (F1/F2/F3)",
        default=dict, blank=True,
        help_text="{F1: 'yes'/'no', F2: 'yes'/'no'/null, F3: 'yes'/'no'/null}",
    )

    # Tezkor filtrlash uchun ko'p ishlatiladigan maydonlar:
    country = models.CharField("Mamlakat", max_length=100, blank=True, db_index=True)
    purpose = models.CharField("Tashrif maqsadi", max_length=50, blank=True, db_index=True)
    nights = models.PositiveIntegerField("Tunlar soni", null=True, blank=True)
    total_spent = models.DecimalField("Umumiy xarajat", max_digits=14, decimal_places=2, null=True, blank=True)
    spent_currency = models.CharField("Valyuta", max_length=10, blank=True)

    # Barcha javoblar JSON formatda:
    data = models.JSONField("Javoblar (JSON)", default=dict, blank=True)

    started_at = models.DateTimeField("Boshlangan", auto_now_add=True)
    completed_at = models.DateTimeField("Yakunlangan", null=True, blank=True)
    is_completed = models.BooleanField("Yakunlanganmi", default=False, db_index=True)

    ip_address = models.GenericIPAddressField("IP manzil", null=True, blank=True)
    user_agent = models.CharField("User-Agent", max_length=500, blank=True)

    # GPS — so'rovnoma yakunlanganda olingan (foydalanuvchi ruxsat bersa)
    latitude = models.DecimalField("Kenglik (latitude)", max_digits=10, decimal_places=7,
                                   null=True, blank=True)
    longitude = models.DecimalField("Uzunlik (longitude)", max_digits=10, decimal_places=7,
                                    null=True, blank=True)
    location_accuracy = models.FloatField("GPS aniqligi (metr)", null=True, blank=True)
    location_granted = models.BooleanField("GPS ruxsat berildi", default=False)

    class Meta:
        verbose_name = "So'rovnoma javobi"
        verbose_name_plural = "So'rovnoma javoblari"
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['survey_type', '-started_at']),
            models.Index(fields=['source', '-started_at']),
        ]

    def __str__(self):
        return f"{self.get_survey_type_display()} — {self.started_at:%Y-%m-%d %H:%M}"

    @property
    def short_id(self):
        return str(self.id)[:8]
