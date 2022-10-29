from django.core.management.base import BaseCommand

from ...tasks import update_all_prices


class Command(BaseCommand):
    help = "Preloads price data for ores"

    def handle(self, *args, **options):
        update_all_prices()
