# Turizm so'rovnoma — Django loyihasi

O'zbekiston turizm statistikasi yig'ish tizimi. Inbound (xorijiy turistlar) va Outbound (chiqish turizmi) so'rovnomalari.

## ✨ Asosiy imkoniyatlar

- 🛬 **Inbound** so'rovnoma (EN/RU, 19 savol) — xorijiy turistlar uchun
- 🛫 **Outbound** so'rovnoma (UZ/RU, 14 savol) — O'zbekiston fuqarolari uchun
- 🌍 **Turist mustaqil to'ldirsa** — login talab etilmaydi (`/inbound/`, `/outbound/`)
- 👤 **Xodim turistdan so'rab kiritsa** — login + parol kerak (`/staff/...`)
- 🏢 **Pochta bo'limlari** — har bir xodim aniq bo'limga biriktiriladi
- 📊 **Dashboard** — xodim uchun shaxsiy statistika, superuser uchun to'liq hisobot
- 🔐 **reCAPTCHA** — Django admin loginida bot himoyasi
- 📥 **Excel eksport** — sana oralig'i bo'yicha
- 📱 Telefon, planshet, desktop — to'liq responsive

## 🛠 Texnologiya

- Python 3.11+ (3.14 sinaldi)
- Django 5.1
- SQLite (dev) — production uchun PostgreSQL tavsiya qilinadi
- Chart.js — grafiklar
- django-recaptcha, openpyxl, whitenoise

## 📁 Loyiha tuzilishi

```
project/
├── config/                  # Django sozlamalari (settings, urls)
├── accounts/                # Xodimlar, pochta bo'limlari, login
├── surveys/                 # So'rovnoma modeli va viewlar
├── dashboard/               # Statistika va hisobotlar
├── templates/               # HTML templatelar
│   ├── base.html
│   ├── home.html
│   ├── accounts/login.html
│   ├── admin/login.html     # reCAPTCHA bilan
│   ├── surveys/{inbound,outbound,success}.html
│   └── dashboard/{index,admin_reports}.html
├── static/                  # CSS, JS
│   ├── css/{common,inbound,outbound,dashboard}.css
│   └── js/{inbound,outbound}.js
├── manage.py
├── requirements.txt
└── .env.example
```

## 🚀 O'rnatish (Windows)

```powershell
# 1) project/ papkasiga kirish
cd "C:\Users\o.qosimov\projects\turizm-so'rovnoma\project"

# 2) Virtual muhit
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3) Paketlarni o'rnatish
pip install -r requirements.txt

# 4) .env faylini sozlash
Copy-Item .env.example .env
# .env'da o'z reCAPTCHA kalitlaringizni qo'shing (ixtiyoriy — test kalitlari mavjud)

# 5) DB migratsiyalari
python manage.py migrate

# 6) Boshlang'ich ma'lumotlar (pochta bo'limlari + namuna xodimlar)
python manage.py seed_data --with-staff

# 7) Superuser yaratish
python manage.py createsuperuser

# 8) Serverni ishga tushirish
python manage.py runserver
```

Brauzerda oching: http://127.0.0.1:8000/

## 🚀 O'rnatish (Linux/Mac)

```bash
cd project/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_data --with-staff
python manage.py createsuperuser
python manage.py runserver
```

## 🔗 URL ro'yxati

| URL | Tavsif | Auth |
|-----|--------|------|
| `/` | Bosh sahifa (so'rovnoma tanlash) | — |
| `/inbound/` | Turist mustaqil — Inbound | — |
| `/outbound/` | Turist mustaqil — Outbound | — |
| `/staff/login/` | Xodim kirish | — |
| `/staff/` | Xodim dashboard | Staff |
| `/staff/survey/inbound/` | Xodim — Inbound kiritish | Staff |
| `/staff/survey/outbound/` | Xodim — Outbound kiritish | Staff |
| `/staff/reports/` | Batafsil hisobotlar | Superuser |
| `/staff/export/` | Excel eksport | Superuser |
| `/admin/` | Django admin (reCAPTCHA) | Superuser |

## 👥 Test foydalanuvchilar (seed_data --with-staff)

| Login | Parol | Bo'lim |
|-------|-------|--------|
| `staff_1140` | `test12345` | Toshkent aeroporti |
| `staff_1180` | `test12345` | Samarqand aeroporti |
| `staff_1330` | `test12345` | Buxoro aeroporti |
| `staff_1260` | `test12345` | Urganch aeroporti |

## 🏢 Pochta bo'limlari

`seed_data` komandasi 13 ta bo'limni yaratadi:
- Aeroportlar: 1140, 1180, 1330, 1260
- Vokzal/markazlar: 3350, 2030, 2060, 2180, 2220, 2221, 3270, 2270, 2271

Yangi bo'lim qo'shish: Django admin `/admin/accounts/postaloffice/`

## 🔐 reCAPTCHA sozlash

`.env` faylida o'z kalitlaringizni qo'shing:
```
RECAPTCHA_PUBLIC_KEY=...
RECAPTCHA_PRIVATE_KEY=...
```

Test kalitlari (har doim ishlaydi, lekin barcha javoblarni qabul qiladi) — `.env.example`'da.

reCAPTCHA Django admin login sahifasida ishlaydi (`/admin/login/`).

## 📊 Dashboard imkoniyatlari

### Xodim uchun (`/staff/`)
- Bugun / hafta / oy / jami statistika
- Inbound vs Outbound nisbati
- 14 kunlik dinamika grafigi
- So'nggi 10 ta yozuv

### Superuser uchun (`/staff/reports/`)
- Sana, tur, bo'lim bo'yicha filtr
- Pochta bo'limlari reytingi (TOP 20)
- Eng faol xodimlar (TOP 20)
- Davlatlar bo'yicha doughnut chart (TOP 15)
- 30 kunlik dinamika
- Excel eksport

## 🧪 Sinov

Inbound submit endpoint'ni tekshirish (test):
```powershell
# 1) Brauzerdan /inbound/ ochib, so'rovnomani to'ldirib ko'ring
# 2) Yoki cURL/PowerShell orqali POST yuborish (CSRF cookie bilan)
```

DB'da yozuvlarni ko'rish:
```bash
python manage.py shell
>>> from surveys.models import SurveyResponse
>>> SurveyResponse.objects.count()
```

## 🚢 Production deploy

1. `.env`'da:
   - `DEBUG=False`
   - `SECRET_KEY` — yangi ishonchli kalit
   - `ALLOWED_HOSTS` — domen
   - reCAPTCHA real kalitlari
2. PostgreSQL ulash: `settings.py`'da `DATABASES` o'zgartiring
3. `python manage.py collectstatic`
4. Gunicorn + Nginx (Linux) yoki Waitress + IIS (Windows)

## 📝 Litsenziya

Ichki foydalanish uchun.
