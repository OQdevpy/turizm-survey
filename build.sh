#!/usr/bin/env bash
# Render.com (yoki boshqa Linux hosting) uchun build skripti
# Render Dashboard -> Settings -> Build Command: bash build.sh

set -o errexit  # xato bo'lsa to'xtatish

echo "================================================================"
echo "[1/5] Pip paketlarini o'rnatish..."
echo "================================================================"
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "================================================================"
echo "[2/5] Static fayllarni yig'ish (collectstatic)..."
echo "================================================================"
python manage.py collectstatic --no-input --clear

echo ""
echo "================================================================"
echo "[3/5] Migratsiyalarni qo'llash..."
echo "================================================================"
python manage.py migrate --no-input

echo ""
echo "================================================================"
echo "[4/5] Boshlang'ich postlar va xodimlarni yuklash..."
echo "================================================================"
python manage.py seed_data || echo "seed_data: skip (allaqachon mavjud)"
python manage.py import_interviewers || echo "import_interviewers: skip"

echo ""
echo "================================================================"
echo "[5/5] Superuser yaratish (agar mavjud bo'lmasa)..."
echo "================================================================"
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.contrib.auth.models import User
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin12345')
if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, email=email, password=password)
    print(f'[OK] Superuser yaratildi: {username}')
else:
    u = User.objects.get(username=username)
    u.set_password(password)
    u.is_superuser = True
    u.is_staff = True
    u.save()
    print(f'[OK] Superuser paroli yangilandi: {username}')
"

echo ""
echo "================================================================"
echo "[DONE] Build muvaffaqiyatli yakunlandi!"
echo "================================================================"
