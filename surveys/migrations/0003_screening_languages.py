# Manual migration — screening (F1/F2/F3) + 10 ta til
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0002_surveyresponse_latitude_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='surveyresponse',
            name='screening_status',
            field=models.CharField(
                choices=[
                    ('eligible', "O'tdi"),
                    ('terminated', "To'xtatildi"),
                    ('skipped', "O'tkazib yuborildi"),
                ],
                db_index=True,
                default='skipped',
                max_length=20,
                verbose_name='Filtr (screening) holati',
            ),
        ),
        migrations.AddField(
            model_name='surveyresponse',
            name='screening_data',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="{F1: 'yes'/'no', F2: 'yes'/'no'/null, F3: 'yes'/'no'/null}",
                verbose_name='Filtr javoblari (F1/F2/F3)',
            ),
        ),
        migrations.AlterField(
            model_name='surveyresponse',
            name='language',
            field=models.CharField(
                choices=[
                    ('uz', "O'zbekcha"),
                    ('ru', 'Русский'),
                    ('en', 'English'),
                    ('ar', 'العربية'),
                    ('zh', '中文'),
                    ('fr', 'Français'),
                    ('de', 'Deutsch'),
                    ('it', 'Italiano'),
                    ('es', 'Español'),
                    ('tg', 'Тоҷикӣ'),
                ],
                default='uz',
                max_length=5,
                verbose_name='Til',
            ),
        ),
    ]
