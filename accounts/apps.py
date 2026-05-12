from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
    verbose_name = "Xodimlar va bo'limlar"

    def ready(self):
        # Python 3.14 + Django 5.1 mosligi uchun patch
        from config.python_compat import apply_django_context_copy_patch
        apply_django_context_copy_patch()

        # Admin login formiga reCAPTCHA qo'shish
        from . import admin_site  # noqa
