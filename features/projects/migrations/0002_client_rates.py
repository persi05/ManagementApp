from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='client_hourly_rate',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name='project',
            name='client_rate_currency',
            field=models.CharField(default='PLN', max_length=8),
        ),
        migrations.CreateModel(
            name='ProjectLabelRate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=80)),
                ('hourly_rate', models.DecimalField(decimal_places=2, max_digits=8)),
                ('currency', models.CharField(default='PLN', max_length=8)),
                ('project', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='label_rates', to='projects.project')),
            ],
            options={
                'ordering': ['label'],
                'unique_together': {('project', 'label')},
            },
        ),
    ]
