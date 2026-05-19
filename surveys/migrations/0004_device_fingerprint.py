# Manual migration — device fingerprint + parsed UA fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0003_screening_languages'),
    ]

    operations = [
        # IP'ga index qo'shish (analytics uchun)
        migrations.AlterField(
            model_name='surveyresponse',
            name='ip_address',
            field=models.GenericIPAddressField(
                blank=True, db_index=True, null=True, verbose_name='IP manzil',
            ),
        ),
        # Yangi maydonlar
        migrations.AddField(
            model_name='surveyresponse',
            name='device_info',
            field=models.JSONField(
                blank=True, default=dict,
                help_text='{screen, platform, language, timezone, ua}',
                verbose_name='Device info (JSON)',
            ),
        ),
        migrations.AddField(
            model_name='surveyresponse',
            name='device_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('mobile', 'Mobile'),
                    ('tablet', 'Tablet'),
                    ('desktop', 'Desktop'),
                    ('bot', 'Bot/Crawler'),
                    ('unknown', "Noma'lum"),
                ],
                db_index=True, default='unknown', max_length=10,
                verbose_name='Device turi',
            ),
        ),
        migrations.AddField(
            model_name='surveyresponse',
            name='os_name',
            field=models.CharField(blank=True, db_index=True, max_length=30, verbose_name='OS'),
        ),
        migrations.AddField(
            model_name='surveyresponse',
            name='browser_name',
            field=models.CharField(blank=True, max_length=30, verbose_name='Brauzer'),
        ),
        migrations.AddField(
            model_name='surveyresponse',
            name='fill_duration_ms',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text='Boshlangandan tugaganga qadar millisekund',
                verbose_name="To'ldirish vaqti (ms)",
            ),
        ),
    ]
