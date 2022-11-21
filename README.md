# Mining Taxes

An Alliance Auth app for tracking mining activities and charging taxes. 

[![pipeline](https://gitlab.com/arctiru/aa-miningtaxes/badges/master/pipeline.svg)](https://gitlab.com/arctiru/aa-miningtaxes/-/commits/master)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Credit to AA's [memberaudit](https://gitlab.com/ErikKalkoken/aa-memberaudit) and [buyback](https://gitlab.com/paulipa/allianceauth-buyback-program) plugins which formed the foundation for this plugin. 

## Features

- Supports multiple corps under one system (Add one character with the accountant role per corp in the admin setup)
- Supports corp moon mining tracking.
- Able to track when unrecognized characters are mining your corp's private moons.
- Support separate tax rates for Regular Ore, Mercoxit, Gas, Ice, R64, R32, R16, R8, and R4.
- Tracks tax payments into the corp master wallet filtering with a user defined phrase. 
- Set a monthly interest rate that penalizes for unpaid tax balances. 
- Automatic monthly notifications and monthly interest applied with unpaid balance. 
- Support Fuzzworks and Janice for daily price updates. 
- Support refined price calculation versus raw ore prices (the higher price will be the taxed price).
- Support multiple mining characters under one user. 
- Monthly statistics and detailed tax calculations available to each user and auditor.
- Provides a current Ore price chart that is updated each day with the latest prices. 
- Export tax information in CSV format.

## Installation instructions

- Install using pip: `pip install git+https://gitlab.com/arctiru/aa-miningtaxes.git`
- Add `miningtaxes` to `myauth/settings/local.py`
- Run migrations: `python manage.py migrate`
- Collect and deploy static assets: `python manage.py collectstatic`
- Preload pricing information `python manage.py miningtaxes_preload_prices`
- Set local settings
```
MININGTAXES_PRICE_JANICE_API_KEY = "XXXX"
MININGTAXES_PRICE_METHOD = "Janice"

CELERYBEAT_SCHEDULE['miningtaxes_update_daily'] = {
    'task': 'miningtaxes.tasks.update_daily',
    'schedule':  crontab(minute=0, hour='1'),
}

# Notifiy everyone of their current taxes on the second day of every month.
CELERYBEAT_SCHEDULE['miningtaxes_notifications'] = {
    'task': 'miningtaxes.tasks.notify_taxes_due',
    'schedule': crontab(0, 0, day_of_month='2'), 
}

# Charge interest and notify everyone on the 15th of every month.
CELERYBEAT_SCHEDULE['miningtaxes_apply_interest'] = {
    'task': 'miningtaxes.tasks.apply_interest',
    'schedule': crontab(0, 0, day_of_month='15'), 
}
```
- Navigate to the admin panel and setup the accountants (1 per corp)

## Local settings


Name | Description | Default
-- | -- | --
MININGTAXES_TAX_ONLY_CORP_MOONS | Only tax corporate moons using moon observers as opposed to all moons appearing in the personal mining ledgers. | True
MININGTAXES_UPDATE_LEDGER_STALE | Minutes after which a character's mining ledger is considered stale | 240
MININGTAXES_REFINED_RATE | Refining rate for ores. | 0.9063
MININGTAXES_PRICE_METHOD | By default Fuzzwork API will be used for pricing, if this is set to "Janice" then the Janice API will be used. | Fuzzwork
MININGTAXES_PRICE_JANICE_API_KEY | The API key to access Janice API. |
MININGTAXES_PRICE_SOURCE_ID | Station ID for fetching base prices. Supports IDs listed on [Fuzzworks API](https://market.fuzzwork.co.uk/api/). Does not work with Janice API!| 60003760


## Permissions

Name | Purpose | Example Target Audience
-- | -- | --
basic_access | Can access this app and see own tax information, current ore prices, and FAQ. | Member State
auditor_access | Can view everyone's tax information and see statistics on taxes. | Auditors
admin_access | Can set tax rate and add characters with the accountant role to pull information from the corp Master Wallet and the corp moons. | Leadership


