# Manual migration — StaffProfile.can_enter_surveys + 22 xodimga False qo'yish
import re
import unicodedata

from django.db import migrations, models


# Cheklanadigan 22 xodim (turizm qo'mitasidan)
RESTRICTED_NAMES = [
    'Xakimov Oybek Olimovich',
    'Abduraximov Dilmurod Oktamovich',
    'Igamberdiyev Rustam Abduazizovich',
    'Djalalov Shahrux Anvarovich',
    'Ashurov Zuhriddin Sadriddinovich',
    'Yusupov Zokir Yoqubjanovich',
    "Qirg'izboyev Zoxidjon G'ulomjonovich",
    'Shodmonov Jahongir Ulugbekovich',
    'Sadullayev Dilshod Davlatovich',
    "Mardonov Muhammad Sanjar o'g'li",
    'Ishmetova Aziza Boxodirovna',
    'Babamuradova Nozimaxon Farxod qizi',
    'Jumaniyazov Azamat Qudratovich',
    "Sabirov San'atbek Rahimbergenovich",
    'Xakimova Mavjuda Abobakirovna',
    "Po'latov Abdulxamid Alijon o'g'li",
    'Jabborov Aznaur Abdusalomovich',
    'Maxmudov Xurshidbek Abdurasulovich',
    'Toreev Berdax Maxsetovich',
    'Pulatov Jasur Safarovich',
    "Almatov Avazbek Toxir o'g'li",
    "Ubaydullayev Ramziddin Raim o'g'li",
]


def _normalize_name(s):
    """Apostroflar, qatlamalar va katta-kichik harflarni normalize qiladi.

    "Po'latov Abdulxamid Alijon o'g'li"
    "Po‘latov Abdulxamid Alijon o‘g‘li"
    "Po'latov Abdulxamid Alijon o'g'li"
    barchasi bir xil string'ga aylantiriladi.
    """
    if not s:
        return ''
    # Unicode normalize (NFKD), apostrof variantlarini bir xilga keltirish
    s = unicodedata.normalize('NFKC', s)
    apostrophe_variants = ['‘', '’', '`', "'", 'ʼ', 'ʻ']
    for ch in apostrophe_variants:
        s = s.replace(ch, "'")
    # Ko'p bo'sh joylarni bittaga
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def restrict_22(apps, schema_editor):
    """22 xodimning can_enter_surveys qiymatini False ga o'rnatish."""
    StaffProfile = apps.get_model('accounts', 'StaffProfile')
    targets = {_normalize_name(n) for n in RESTRICTED_NAMES}
    matched = 0
    skipped = []
    for profile in StaffProfile.objects.all():
        if _normalize_name(profile.full_name) in targets:
            profile.can_enter_surveys = False
            profile.save(update_fields=['can_enter_surveys'])
            matched += 1
    if matched != len(RESTRICTED_NAMES):
        # Foydalanuvchi DB'ga import qilmagan yoki ism formatlari farq qilishi mumkin —
        # migration warning beradi (xato emas) — admin keyinchalik qo'lda o'rnatishi kerak
        all_normalized = {_normalize_name(p.full_name): p.full_name for p in StaffProfile.objects.all()}
        for name in RESTRICTED_NAMES:
            n = _normalize_name(name)
            if n not in all_normalized:
                skipped.append(name)
    # Maydonni allaqachon orqali ko'rsataman (print django migration outputida ko'rinadi)
    print(f"\n[restrict_22] {matched}/{len(RESTRICTED_NAMES)} xodim cheklandi.")
    if skipped:
        print("[restrict_22] DB'da topilmagan xodimlar (qo'lda admin'dan o'rnating):")
        for n in skipped:
            print(f"  - {n}")


def unrestrict_all(apps, schema_editor):
    """Reverse migration — barcha xodimlarga huquq qaytarish."""
    StaffProfile = apps.get_model('accounts', 'StaffProfile')
    StaffProfile.objects.update(can_enter_surveys=True)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_postaloffice_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='staffprofile',
            name='can_enter_surveys',
            field=models.BooleanField(
                db_index=True, default=True,
                help_text="False bo'lsa xodim faqat monitoringga kira oladi, "
                          "so'rovnoma kirita olmaydi.",
                verbose_name="So'rovnoma kiritish huquqi",
            ),
        ),
        migrations.RunPython(restrict_22, reverse_code=unrestrict_all),
    ]
