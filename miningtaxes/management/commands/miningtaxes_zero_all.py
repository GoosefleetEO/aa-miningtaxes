from django.core.management.base import BaseCommand

from ...models import Character


class Command(BaseCommand):
    help = "Zeros all taxes of all characters"

    def handle(self, *args, **options):
        alltoons = Character.objects.all()
        for char in alltoons:
            balance = char.get_lifetime_taxes() - char.get_lifetime_credits()
            if balance > 0:
                char.give_credit(balance, "credit")
