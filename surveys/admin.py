import json

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import SurveyResponse


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = (
        'short_id', 'survey_type', 'source', 'staff', 'postal_office',
        'country', 'purpose', 'nights', 'total_spent', 'spent_currency',
        'has_location', 'is_completed', 'started_at',
    )
    list_filter = ('survey_type', 'source', 'is_completed', 'language', 'location_granted', 'postal_office')
    search_fields = ('id', 'country', 'staff__username', 'staff__first_name', 'staff__last_name')
    readonly_fields = (
        'id', 'started_at', 'completed_at', 'ip_address', 'user_agent',
        'pretty_data', 'map_widget', 'gmaps_link',
    )
    date_hierarchy = 'started_at'
    list_per_page = 50

    fieldsets = (
        ("Asosiy", {
            'fields': ('id', 'survey_type', 'source', 'language', 'is_completed'),
        }),
        ("Kim kiritgan", {
            'fields': ('staff', 'postal_office'),
        }),
        ("Asosiy javoblar", {
            'fields': ('country', 'purpose', 'nights', 'total_spent', 'spent_currency'),
        }),
        ("📍 Joylashuv (GPS)", {
            'fields': ('location_granted', 'latitude', 'longitude', 'location_accuracy',
                       'gmaps_link', 'map_widget'),
        }),
        ("To'liq ma'lumot", {
            'fields': ('pretty_data',),
            'classes': ('collapse',),
        }),
        ("Audit", {
            'fields': ('started_at', 'completed_at', 'ip_address', 'user_agent'),
            'classes': ('collapse',),
        }),
    )

    class Media:
        css = {
            'all': (
                'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
                'css/admin_map.css',
            )
        }
        js = (
            'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
            'js/admin_map.js',
        )

    @admin.display(description="📍", boolean=True)
    def has_location(self, obj):
        return obj.location_granted and obj.latitude is not None

    @admin.display(description="JSON ma'lumot")
    def pretty_data(self, obj):
        return format_html(
            '<pre style="background:#f5f5f5;padding:10px;border-radius:6px;'
            'max-height:400px;overflow:auto;font-family:monospace;font-size:12px">{}</pre>',
            json.dumps(obj.data, ensure_ascii=False, indent=2),
        )

    @admin.display(description="🗺 Google Maps'da ochish")
    def gmaps_link(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return "—"
        url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener" '
            'style="display:inline-block;padding:6px 14px;background:#4285f4;color:white;'
            'border-radius:6px;text-decoration:none;font-weight:600">'
            '🌐 Google Maps\'da ochish ↗</a> &nbsp; '
            '<span style="color:#666;font-size:12px">({}, {})</span>',
            url, obj.latitude, obj.longitude
        )

    @admin.display(description="🗺 Xarita")
    def map_widget(self, obj):
        if obj.latitude is None or obj.longitude is None:
            return mark_safe(
                '<div style="padding:20px;background:#f7f7f7;border-radius:8px;'
                'text-align:center;color:#888;font-family:system-ui">'
                '📭 GPS ma\'lumoti yo\'q</div>'
            )
        lat = float(obj.latitude)
        lon = float(obj.longitude)
        accuracy = float(obj.location_accuracy or 0)
        # admin_map.js .gps-map ni avtomatik topadi
        # O'lcham va styling admin_map.css'da bor — bu yerda inline yo'q
        return mark_safe(
            f'<div class="gps-map" '
            f'data-lat="{lat}" data-lon="{lon}" data-accuracy="{accuracy}"></div>'
        )
