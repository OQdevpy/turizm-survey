#!/usr/bin/env bash
# Render.com (yoki boshqa Linux hosting) uchun build skripti
# Render Dashboard -> Settings -> Build Command: ./build.sh

set -o errexit  # xato bo'lsa to'xtatish

echo "[1/4] Pip paketlarini o'rnatish..."
pip install -r requirements.txt

echo "[2/4] Static fayllarni yig'ish (collectstatic)..."
python manage.py collectstatic --no-input --clear

echo "[3/4] Migratsiyalarni qo'llash..."
python manage.py migrate --no-input

echo "[4/4] Boshlang'ich ma'lumotlar (faqat birinchi marta)..."
# Pochta bo'limlarini va xodimlarni faqat birinchi marta yuklash
python manage.py seed_data || echo "seed_data: skipped (ehtimol allaqachon mavjud)"
# Excel'dan 165 xodim — agar fayl bor bo'lsa
python -c "
import os, django
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
django.setup()
from accounts.models import StaffProfile
if StaffProfile.objects.count() < 100:
    from django.core.management import call_command
    try:
        call_command('import_interviewers')
    except Exception as e:
        print(f'import_interviewers: skipped ({e})')
else:
    print('import_interviewers: skipped (xodimlar yetarli)')
"

echo "[OK] Build muvaffaqiyatli yakunlandi!"
