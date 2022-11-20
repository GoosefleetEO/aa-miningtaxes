# Installation instructions

- Install the usual way with migrations, etc.
- `python manage.py miningtaxes_preload_prices`
- Set local settings

```
MININGTAXES_PRICE_JANICE_API_KEY = "XXXX"
MININGTAXES_PRICE_METHOD = "Janice"

CELERYBEAT_SCHEDULE['miningtaxes_update_daily'] = {
    'task': 'miningtaxes.tasks.update_daily',
    'schedule':  crontab(minute=0, hour='1'),
}
```

- Navigate to the admin panel and setup the accountants (1 per corp)
