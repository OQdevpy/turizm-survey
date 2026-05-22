from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import AdminTOTPDevice, PostalOffice, StaffProfile


@admin.register(PostalOffice)
class PostalOfficeAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'region', 'is_airport', 'is_active', 'staff_count')
    list_filter = ('is_airport', 'is_active', 'region')
    search_fields = ('code', 'name', 'region')
    list_editable = ('is_active',)

    @admin.display(description="Xodimlar soni")
    def staff_count(self, obj):
        return obj.staff_members.count()


class StaffProfileInline(admin.StackedInline):
    model = StaffProfile
    can_delete = False
    verbose_name_plural = "Xodim profili"
    fk_name = 'user'


class UserAdmin(BaseUserAdmin):
    inlines = (StaffProfileInline,)
    list_display = ('username', 'get_full_name', 'email', 'get_postal_office', 'is_staff', 'is_superuser', 'is_active')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'staff_profile__postal_office')

    @admin.display(description="Bo'lim")
    def get_postal_office(self, obj):
        try:
            return obj.staff_profile.postal_office.code
        except StaffProfile.DoesNotExist:
            return '—'


admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(AdminTOTPDevice)
class AdminTOTPDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_active', 'is_verified', 'created_at', 'last_used_at')
    list_filter = ('is_active', 'is_verified')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('secret', 'created_at', 'last_used_at')
    actions = ['reset_devices']

    @admin.action(description="Tanlangan qurilmalarni reset qilish (qayta sozlash kerak)")
    def reset_devices(self, request, queryset):
        n = queryset.update(is_verified=False)
        self.message_user(request, f"{n} ta qurilma reset qilindi. Foydalanuvchilar qayta QR skanlashi kerak.")


admin.site.site_header = "Turizm so'rovnoma — Boshqaruv paneli"
admin.site.site_title = "Turizm so'rovnoma"
admin.site.index_title = "Bosh sahifa"
