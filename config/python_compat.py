"""Python 3.14 + Django 5.1 mosligi uchun monkey-patch.

Django 5.1 da `BaseContext.__copy__` metodi `copy(super())` chaqiriqdan foydalanadi,
lekin Python 3.14 da bu super proxy obyektini qaytaradi (avvallar yangi nusxani
qaytarardi). Buning natijasida admin sahifalarida render xatolik beradi:

    AttributeError: 'super' object has no attribute 'dicts'

Bu modul bu xatoni tuzatadi. settings.py boshida import qilinadi.
"""
import sys


def apply_django_context_copy_patch():
    """Django BaseContext.__copy__ ni Python 3.14 ga moslashtirish."""
    if sys.version_info < (3, 14):
        return  # 3.13 va undan past versiyalarda muammo yo'q

    from django.template import context as django_context

    def _patched_basecontext_copy(self):
        cls = self.__class__
        duplicate = cls.__new__(cls)
        if hasattr(self, '__dict__'):
            duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = list(self.dicts)
        return duplicate

    django_context.BaseContext.__copy__ = _patched_basecontext_copy
