from django.core.management.base import BaseCommand

from ...tasks import update_daily


class Command(BaseCommand):
    help = "Runs daily update manually"

    def handle(self, *args, **options):
        update_daily()
