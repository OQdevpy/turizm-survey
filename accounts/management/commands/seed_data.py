"""Boshlang'ich ma'lumotlarni yuklash: pochta/bojxona postlari (Excel Sheet1 asosida)."""
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import PostalOffice


# Excel `Postlar va intervyuverlar+.xlsx` -> Sheet1 dan
POSTAL_OFFICES = [
    # code, region_code, name, region, post_type, is_airport
    ('317350', '1735', "Qoraqalpog'iston Respublikasi, \"Qoraqalpog'iston\" temir yo'l chegara bojxona posti",
     'Qoraqalpog\'iston', 'railway', False),
    ('217030', '1703', "Andijon viloyati \"Do'stlik\" bojxona posti (MPP Dustlik-avto)",
     'Andijon', 'auto', False),
    ('217060', '1706', "Buxoro viloyati \"Olot\" bojxona posti (MPP Alat-avto)",
     'Buxoro', 'auto', False),
    ('117140', '1714', "Namangan xalqaro aeroporti (NXA)",
     'Namangan', 'airport', True),
    ('217180', '1718', "Samarqand viloyati \"Jartepa\" bojxona posti (MPP Djartepa-avto)",
     'Samarqand', 'auto', False),
    ('117180', '1718', "Samarqand xalqaro aeroporti (SXA)",
     'Samarqand', 'airport', True),
    ('217220', '1722', "Surxondaryo viloyati \"Sariosiyo\" bojxona posti (MPP Sariasiya-avto)",
     'Surxondaryo', 'auto', False),
    ('217221', '1722', "Surxondaryo viloyati \"Ayritom\" bojxona posti (MPP Termiz-avto)",
     'Surxondaryo', 'auto', False),
    ('317270', '1727', "Toshkent viloyati, \"Keles\" temir yo'l chegara bojxona posti",
     'Toshkent vil.', 'railway', False),
    ('217270', '1727', "Toshkent viloyati \"Navoiy\" bojxona posti (DPP Zangiota-avto)",
     'Toshkent vil.', 'auto', False),
    ('217271', '1727', "Toshkent viloyati \"Oybek\" bojxona posti (MPP Oybek-avto)",
     'Toshkent vil.', 'auto', False),
    ('117330', '1733', "Urgench xalqaro aeroporti (UXA)",
     'Xorazm', 'airport', True),
    ('117260', '1726', "Toshkent shahri Islom Karimov nomidagi \"Toshkent xalqaro aeroporti\"",
     'Toshkent shahri', 'airport', True),
]


class Command(BaseCommand):
    help = "Pochta/bojxona postlarini Excel Sheet1 asosida yaratadi"

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Eski postlarni o\'chirib qayta yaratish')

    @transaction.atomic
    def handle(self, *args, **options):
        if options.get('reset'):
            # Eski 4 raqamli kod-larni o'chirish (StaffProfile lar uchun PROTECT bor — avval profillarni o'chirish kerak)
            from accounts.models import StaffProfile
            old_codes = ['1140', '1180', '1330', '1260', '3350', '2030', '2060',
                         '2180', '2220', '2221', '3270', '2270', '2271']
            old = PostalOffice.objects.filter(code__in=old_codes)
            if old.exists():
                # Avval bog'liq profillarni o'chirish
                from django.contrib.auth.models import User
                related_profiles = StaffProfile.objects.filter(postal_office__in=old)
                related_user_ids = list(related_profiles.values_list('user_id', flat=True))
                related_profiles.delete()
                # Test xodimlarni ham (admin emas) o'chirish
                User.objects.filter(id__in=related_user_ids, is_superuser=False).delete()
                old.delete()
                self.stdout.write(self.style.WARNING(f"[!] {old.count()} ta eski post o'chirildi"))

        created = updated = 0
        for code, region_code, name, region, post_type, is_airport in POSTAL_OFFICES:
            obj, was_created = PostalOffice.objects.update_or_create(
                code=code,
                defaults={
                    'region_code': region_code,
                    'name': name,
                    'region': region,
                    'post_type': post_type,
                    'is_airport': is_airport,
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"[OK] {created} ta yangi yaratildi, {updated} ta yangilandi "
            f"(jami: {PostalOffice.objects.count()})"
        ))
        self.stdout.write(self.style.SUCCESS("\n>>> Postlar seed yakunlandi!"))
        self.stdout.write("\nKeyingi qadam: 'python manage.py import_interviewers' — 165 ta xodimni Excel'dan import qilish")
