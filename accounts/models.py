from django.conf import settings
from django.db import models


class PostalOffice(models.Model):
    POST_TYPE_AIRPORT = 'airport'
    POST_TYPE_AUTO = 'auto'
    POST_TYPE_RAILWAY = 'railway'
    POST_TYPE_OTHER = 'other'
    POST_TYPES = [
        (POST_TYPE_AIRPORT, "Xalqaro aeroport"),
        (POST_TYPE_AUTO, "Avto bojxona posti"),
        (POST_TYPE_RAILWAY, "Temir yo'l bojxona posti"),
        (POST_TYPE_OTHER, "Boshqa"),
    ]

    code = models.CharField("Post kodi", max_length=10, unique=True, db_index=True)
    region_code = models.CharField("Hudud kodi", max_length=10, db_index=True, blank=True,
                                   help_text="4 raqamli, masalan 1735")
    name = models.CharField("Bo'lim nomi", max_length=255)
    region = models.CharField("Viloyat", max_length=100, blank=True)
    address = models.CharField("Manzil", max_length=255, blank=True)
    post_type = models.CharField("Post turi", max_length=20, choices=POST_TYPES, default=POST_TYPE_OTHER)
    is_airport = models.BooleanField("Aeroport bo'limi", default=False)
    is_active = models.BooleanField("Faolmi", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pochta/Bojxona posti"
        verbose_name_plural = "Pochta/Bojxona postlari"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"

    def save(self, *args, **kwargs):
        # Avtomatik region_code ajratish: code dan 2-5 indeks (masalan 317350 → 1735)
        if self.code and not self.region_code and len(self.code) >= 5:
            self.region_code = self.code[1:5]
        super().save(*args, **kwargs)


class StaffProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='staff_profile',
        verbose_name="Foydalanuvchi",
    )
    postal_office = models.ForeignKey(
        PostalOffice,
        on_delete=models.PROTECT,
        related_name='staff_members',
        verbose_name="Asosiy post",
    )
    full_name = models.CharField("To'liq F.I.SH (Excel'dan)", max_length=255, blank=True,
                                 help_text="Excel'dan import qilingan asl ism (masalan: Tajibekov Baxtiyar Nietullaevich)")
    region_code = models.CharField("Hudud kodi", max_length=10, blank=True, db_index=True)
    phone = models.CharField("Telefon raqami", max_length=20, blank=True)
    position = models.CharField("Lavozim", max_length=100, blank=True)
    can_enter_surveys = models.BooleanField(
        "So'rovnoma kiritish huquqi", default=True, db_index=True,
        help_text="False bo'lsa xodim faqat monitoringga kira oladi, so'rovnoma kirita olmaydi.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Xodim profili (Intervyuver)"
        verbose_name_plural = "Xodimlar profillari (Intervyuverlar)"
        ordering = ['postal_office__code', 'full_name']

    def __str__(self):
        return f"{self.full_name or self.user.username} ({self.postal_office.code})"
