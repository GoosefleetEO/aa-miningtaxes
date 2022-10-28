from django.apps import AppConfig

from . import __version__


class MiningTaxesConfig(AppConfig):
    name = "miningtaxes"
    label = "miningtaxes"
    verbose_name = f"Mining Taxes v{__version__}"
