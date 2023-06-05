# Shamelessly stolen from Member Audit
import datetime as dt

from dateutil.relativedelta import relativedelta

from django.db import models
from django.urls import reverse
from django.utils.timezone import now

from allianceauth.eveonline.models import EveCharacter
from allianceauth.services.hooks import get_extension_logger
from app_utils.logging import LoggerAddTag
from app_utils.views import bootstrap_icon_plus_name_html

from .. import __title__
from ..helpers import PriceGroups
from . import (
    AdminMiningCorpLedgerEntry,
    AdminMiningObsLog,
    Character,
    CharacterMiningLedgerEntry,
    OrePrices,
    Settings,
    ore_calc_prices,
)

logger = LoggerAddTag(get_extension_logger(__name__), __title__)


class Stats(models.Model):
    admin_char_json = models.JSONField(default=None, null=True)
    admin_main_json = models.JSONField(default=None, null=True)
    ore_prices_json = models.JSONField(default=None, null=True)
    admin_mining_by_sys_json = models.JSONField(default=None, null=True)
    admin_tax_revenue_json = models.JSONField(default=None, null=True)
    admin_month_json = models.JSONField(default=None, null=True)
    admin_corp_ledger = models.JSONField(default=None, null=True)
    admin_corp_mining_history = models.JSONField(default=None, null=True)
    leaderboards = models.JSONField(default=None, null=True)
    admin_get_all_activity_json = models.JSONField(default=None, null=True)

    def precalc_all(self):
        self.calc_admin_char_json()
        self.calc_admin_main_json()
        self.calc_ore_prices_json()
        self.calc_admin_mining_by_sys_json()
        self.calc_admin_tax_revenue_json()
        self.calc_admin_month_json()
        self.calc_admin_corp_ledger()
        self.calc_admin_corp_mining_history()
        self.calc_leaderboards()
        self.calc_admin_get_all_activity_json()

    def characterize(self, char):
        eve_char = None
        category = None
        name = None
        try:
            eve_char = EveCharacter.objects.get(character_id=char)
        except EveCharacter.DoesNotExist:
            name = f"<a href='https://evewho.com/character/{char}'>{char}</a>"
            category = "unknown"
            pass
        if eve_char is not None:
            try:
                character = eve_char.miningtaxes_character
                name = character.main_character.character_name
                category = "found"
            except AttributeError:
                name = eve_char.character_name
                category = "unregistered"
                pass
        return name, category

    def calctaxes(self):
        n = now().date()
        curmonth = dt.date(year=n.year, month=n.month, day=1)
        user2taxes = {}
        characters = Character.objects.all()
        for character in characters:
            if character.user is None:
                continue
            taxes = character.get_monthly_taxes()
            total = 0.0
            for k in taxes.keys():
                if k != curmonth:
                    total += taxes[k]
            if character.user not in user2taxes:
                user2taxes[character.user] = [0.0, 0.0, character]
            user2taxes[character.user][0] += total
            if total > user2taxes[character.user][1]:
                user2taxes[character.user][1] = total
                user2taxes[character.user][2] = character
            credits = character.get_lifetime_credits()
            user2taxes[character.user][0] -= credits

        for user in user2taxes.keys():
            taxes_due = round(user2taxes[user][0], 2)
            if taxes_due == 0.00:
                taxes_due = abs(taxes_due)
            user2taxes[user][0] = taxes_due
        return user2taxes

    def calc_admin_char_json(self):
        char_level = {}

        for char in Character.objects.all():
            char_level[char] = {
                "life_tax": char.get_lifetime_taxes(),
                "life_credits": char.get_lifetime_credits(),
            }
            char_level[char]["bal"] = (
                char_level[char]["life_tax"] - char_level[char]["life_credits"]
            )

        char_data = []
        for c in char_level.keys():
            if c.eve_character is None or c.main_character is None:
                continue
            char_data.append(
                {
                    "name": bootstrap_icon_plus_name_html(
                        icon_url=c.eve_character.portrait_url(),
                        name=c.eve_character.character_name,
                        size=16,
                    ),
                    "corp": bootstrap_icon_plus_name_html(
                        icon_url=c.eve_character.corporation_logo_url(),
                        name=c.eve_character.corporation_name,
                        size=16,
                    ),
                    "main_name": bootstrap_icon_plus_name_html(
                        icon_url=c.main_character.portrait_url(),
                        name=c.main_character.character_name,
                        size=16,
                    ),
                    "taxes": char_level[c]["life_tax"],
                    "credits": char_level[c]["life_credits"],
                    "balance": char_level[c]["bal"],
                }
            )
            self.admin_char_json = char_data
            self.save()

    def get_admin_char_json(self):
        if self.admin_char_json is None:
            self.calc_admin_char_json()
        return self.admin_char_json

    def main_data_helper(self, chars):
        main_level = {}
        char2user = {}
        user2taxes = self.calctaxes()

        for char in chars:
            if char.main_character is None:
                logger.error(f"Missing main: {char}")
                continue
            m = char.main_character
            char2user[m] = char.user
            if m not in main_level:
                main_level[m] = {
                    "life_tax": 0.0,
                    "life_credits": 0.0,
                    "last_paid": None,
                }
            main_level[m]["life_tax"] += char.get_lifetime_taxes()
            main_level[m]["life_credits"] += char.get_lifetime_credits()
            if char.last_paid() is not None and (
                main_level[m]["last_paid"] is None
                or char.last_paid() > main_level[m]["last_paid"]
            ):
                main_level[m]["last_paid"] = char.last_paid()
        for m in main_level.keys():
            main_level[m]["balance"] = (
                main_level[m]["life_tax"] - main_level[m]["life_credits"]
            )
        return main_level, char2user, user2taxes

    def calc_admin_main_json(self):
        main_level, char2user, user2taxes = self.main_data_helper(
            Character.objects.all()
        )
        main_data = []
        for i, m in enumerate(main_level.keys()):
            summary_url = reverse("miningtaxes:user_summary", args=[char2user[m].pk])
            action_html = (
                '<a class="btn btn-primary btn-sm" '
                f"href='{summary_url}'>"
                '<i class="fas fa-search"></i></a>'
                '<button type="button" class="btn btn-primary btn-sm" '
                'data-toggle="modal" data-target="#modalCredit" '
                f'onClick="populate({i})" >'
                "$$</button>"
            )
            main_data.append(
                {
                    "name": bootstrap_icon_plus_name_html(
                        icon_url=m.portrait_url(), name=m.character_name, size=16
                    ),
                    "corp": bootstrap_icon_plus_name_html(
                        icon_url=m.corporation_logo_url(),
                        name=m.corporation_name,
                        size=16,
                    ),
                    "balance": main_level[m]["balance"],
                    "last_paid": str(main_level[m]["last_paid"]),
                    "action": action_html,
                    "user": char2user[m].pk,
                    "taxes_due": user2taxes[char2user[m]][0],
                }
            )

        self.admin_main_json = main_data
        self.save()

    def get_admin_main_json(self):
        if self.admin_main_json is None:
            self.calc_admin_main_json()
        return self.admin_main_json

    def calc_ore_prices_json(self):
        settings = Settings.load()
        data = []
        pg = PriceGroups()
        for ore in OrePrices.objects.all():
            if "Compressed" in ore.eve_type.name:
                continue
            if ore.eve_type.eve_group_id not in pg.taxgroups:
                continue
            raw = 1000.0 * ore.raw_price
            refined = 1000.0 * ore.refined_price
            taxed = 1000.0 * ore.taxed_price
            group = "tax_" + pg.taxgroups[ore.eve_type.eve_group_id]
            tax_rate = settings.__dict__[group] / 100.0

            tax = taxed * tax_rate
            remaining = taxed - tax
            tax_rate = "{0:.0%}".format(tax_rate)
            group = pg.taxgroups[ore.eve_type.eve_group_id]
            data.append(
                {
                    "group": group,
                    "name": ore.eve_type.name,
                    "raw": raw,
                    "refined": refined,
                    "taxed": taxed,
                    "tax_rate": tax_rate,
                    "remaining": remaining,
                    "tax": tax,
                }
            )
        self.ore_prices_json = data
        self.save()

    def get_ore_prices_json(self):
        if self.ore_prices_json is None:
            self.calc_ore_prices_json()
        return self.ore_prices_json

    def calc_admin_get_all_activity_json(self):
        entries = CharacterMiningLedgerEntry.objects.all().prefetch_related(
            "character", "eve_type", "eve_solar_system"
        )
        sys = {}
        pg = PriceGroups()
        csv_data = [
            [
                "Date",
                "Sys",
                "Character",
                "Main",
                "Ore",
                "Group",
                "Amount",
                "ISK Value",
                "Taxed",
            ]
        ]
        for e in entries:
            try:
                s = e.eve_solar_system.name
                if s not in sys:
                    sys[s] = {}

                group = pg.taxgroups[e.eve_type.eve_group_id]

                csv_data.append(
                    [
                        str(e.date),
                        s,
                        e.character.eve_character.character_name,
                        e.character.main_character.character_name,
                        e.eve_type.name,
                        group,
                        e.quantity,
                        e.taxed_value,
                        e.taxes_owed,
                    ]
                )
            except Exception as e:
                logger.error(f"Failed: {e}")
                continue

        self.admin_get_all_activity_json = csv_data
        self.save()

    def get_admin_get_all_activity_json(self):
        if self.admin_get_all_activity_json is None:
            self.calc_admin_get_all_activity_json()
        return self.admin_get_all_activity_json

    def calc_admin_mining_by_sys_json(self):
        entries = CharacterMiningLedgerEntry.objects.all().prefetch_related(
            "character", "eve_type", "eve_solar_system"
        )
        sys = {}
        pg = PriceGroups()
        allgroups = set()
        tables = {}

        for e in entries:
            try:
                s = e.eve_solar_system.name
                if s not in sys:
                    sys[s] = {}

                group = pg.taxgroups[e.eve_type.eve_group_id]
                allgroups.add(group)
            except Exception as e:
                logger.error(f"Failed: {e}")
                continue

            month = "%d-%02d" % (e.date.year, e.date.month)
            if month not in tables:
                tables[month] = {}
            if s not in tables[month]:
                tables[month][s] = {}
            if group not in tables[month][s]:
                tables[month][s][group] = {"tax": 0.0, "isk": 0.0}

            tables[month][s][group]["tax"] += e.taxes_owed
            tables[month][s][group]["isk"] += e.taxed_value

            if group not in sys[s]:
                sys[s][group] = {
                    "first": e.date,
                    "last": e.date,
                    "q": e.quantity,
                    "isk": e.taxed_value,
                    "tax": e.taxes_owed,
                }
                continue
            if e.date < sys[s][group]["first"]:
                sys[s][group]["first"] = e.date
            if e.date > sys[s][group]["last"]:
                sys[s][group]["last"] = e.date
            sys[s][group]["isk"] += e.taxed_value
            sys[s][group]["tax"] += e.taxes_owed
            sys[s][group]["q"] += e.quantity

        # Reformat for billboard and calc stats
        for s in sys.keys():
            for g in allgroups:
                if g not in sys[s]:
                    sys[s][g] = {"isk": 0, "tax": 0, "q": 0}
                    continue
                # t = (sys[s][g]["last"] - sys[s][g]["first"]).days
                t = (now().date() - sys[s][g]["first"]).days
                t /= 365.25 / 12
                if t < 1:
                    t = 1
                sys[s][g]["isk"] /= t
                sys[s][g]["tax"] /= t
                sys[s][g]["q"] /= t

        anal = {}
        for a in ("isk", "tax", "q"):
            x = ["x"]
            order = sorted(
                sys.keys(), key=lambda x: (sum(map(lambda y: -sys[x][y][a], allgroups)))
            )
            gorder = sorted(
                allgroups, key=lambda g: sum(map(lambda s: -sys[s][g][a], sys.keys()))
            )
            ys = []
            for g in gorder:
                ys.append([g])
            for s in order:
                x.append(s)
                for i, g in enumerate(gorder):
                    ys[i].append(sys[s][g][a])
                if len(x) > 11:
                    break
            ys.append(x)
            anal[a] = ys
        self.admin_mining_by_sys_json = {
            "anal": anal,
            "tables": tables,
        }
        self.save()

    def get_admin_mining_by_sys_json(self):
        if self.admin_mining_by_sys_json is None:
            self.calc_admin_mining_by_sys_json()
        return self.admin_mining_by_sys_json

    def calc_admin_tax_revenue_json(self):
        entries = AdminMiningCorpLedgerEntry.objects.all()
        settings = Settings.load()

        months = {}
        for e in entries:
            if settings.phrase != "" and settings.phrase not in e.reason:
                continue
            d = dt.date(year=e.date.year, month=e.date.month, day=15)
            if d not in months:
                months[d] = 0.0
            months[d] += e.amount

        xs = list(sorted(months.keys()))
        ys = list(map(lambda x: months[x], xs))
        xs = ["x"] + xs
        ys = ["Revenue"] + ys

        csv_data = [["Month", "Amount (ISK)"]]
        for i in range(1, len(xs)):
            csv_data.append([str(xs[i]), ys[i]])
        xs = list(map(str, xs))
        self.admin_tax_revenue_json = {"xdata": xs, "ydata": ys, "csv": csv_data}
        self.save()

    def get_admin_tax_revenue_json(self):
        if self.admin_tax_revenue_json is None:
            self.calc_admin_tax_revenue_json()
        return self.admin_tax_revenue_json

    def calc_admin_month_json(self):
        characters = Character.objects.all()
        newchars = []
        for c in characters:
            if c.main_character is None:
                logger.error(f"Missing main for {c}")
                continue
            newchars.append(c)
        characters = newchars
        monthly = list(map(lambda x: x.get_monthly_taxes(), characters))
        users = list(map(lambda x: x.main_character.character_name, characters))
        firstmonth = None
        for entries in monthly:
            if len(entries.keys()) == 0:
                continue
            if firstmonth is None or firstmonth > sorted(entries.keys())[0]:
                firstmonth = sorted(entries.keys())[0]
        xs = None
        ys = {}
        for i, entries in enumerate(monthly):
            if not users[i] in ys:
                ys[users[i]] = []
            x = ["x"]
            y = []
            curmonth = firstmonth
            lastmonth = dt.date(now().year, now().month, 1)
            while curmonth <= lastmonth:
                if curmonth not in entries:
                    entries[curmonth] = 0.0
                x.append(curmonth)
                curmonth += relativedelta(months=1)

            if xs is None:
                xs = x

            for yi in range(1, len(xs)):
                y.append(entries[xs[yi]])
            ys[users[i]].append(y)
        yout = []
        for user in sorted(ys.keys()):
            yout.append([user] + [sum(x) for x in zip(*ys[user])])

        yall = ["all"]
        for yi in range(1, len(xs)):
            sumy = 0
            for row in yout:
                sumy += row[yi]
            yall.append(sumy)
        yout.insert(0, yall)
        yout = [yall]  # disable per main retrieval

        csvdata = [["Month", "Main", "Taxes Total"]]
        for xi in range(1, len(xs)):
            month = xs[xi]
            for userarr in yout:
                row = [str(month), userarr[0], userarr[xi]]
                csvdata.append(row)

        xs = list(map(str, xs))
        self.admin_month_json = {"xdata": xs, "ydata": yout, "csv": csvdata}
        self.save()

    def get_admin_month_json(self):
        if self.admin_month_json is None:
            self.calc_admin_month_json()
        return self.admin_month_json

    def calc_admin_corp_ledger(self):
        obs = AdminMiningCorpLedgerEntry.objects.all().order_by("-date")
        data = []
        for o in obs:
            char = o.taxed_id
            name = None
            eve_char = None
            try:
                eve_char = EveCharacter.objects.get(character_id=char)
            except EveCharacter.DoesNotExist:
                name = f"<a href='https://evewho.com/character/{char}'>{char}</a>"
                pass
            except Exception as e:
                logger.error(f"Error unknown user: {char}, error: {e}")
                continue
            if eve_char is not None:
                try:
                    character = eve_char.miningtaxes_character
                    name = character.main_character.character_name
                except AttributeError:
                    name = eve_char.character_name
                    pass
                except Exception as e:
                    logger.error(f"Error unknown user: {eve_char}, error: {e}")
                    continue
            data.append(
                {
                    "date": str(o.date),
                    "name": name,
                    "amount": o.amount,
                    "reason": o.reason,
                }
            )
        self.admin_corp_ledger = {"data": data}
        self.save()

    def get_admin_corp_ledger(self):
        if self.admin_corp_ledger is None:
            self.calc_admin_corp_ledger()
        return self.admin_corp_ledger

    def calc_admin_corp_mining_history(self):
        days_90 = now() - dt.timedelta(days=90)
        obs = AdminMiningObsLog.objects.filter(date__gte=days_90).order_by("-date")
        cache = {}
        data = []
        unknown_chars = {}
        unregistered_chars = {}
        for o in obs:
            char = o.miner_id
            if char not in cache:
                cache[char] = self.characterize(char)
            (name, category) = cache[char]

            if category == "unknown":
                if name not in unknown_chars:
                    unknown_chars[name] = {}
                if o.eve_solar_system not in unknown_chars[name]:
                    unknown_chars[name][o.eve_solar_system] = [0, 0.0, None]
                unknown_chars[name][o.eve_solar_system][0] += o.quantity
                (_, _, value) = ore_calc_prices(o.eve_type, o.quantity)
                unknown_chars[name][o.eve_solar_system][1] += value
                if (
                    unknown_chars[name][o.eve_solar_system][2] is None
                    or unknown_chars[name][o.eve_solar_system][2] < o.date
                ):
                    unknown_chars[name][o.eve_solar_system][2] = o.date
            elif category == "unregistered":
                if name not in unregistered_chars:
                    unregistered_chars[name] = {}
                if o.eve_solar_system not in unregistered_chars[name]:
                    unregistered_chars[name][o.eve_solar_system] = [0, 0.0, None]
                unregistered_chars[name][o.eve_solar_system][0] += o.quantity
                (_, _, value) = ore_calc_prices(o.eve_type, o.quantity)
                unregistered_chars[name][o.eve_solar_system][1] += value
                if (
                    unregistered_chars[name][o.eve_solar_system][2] is None
                    or unregistered_chars[name][o.eve_solar_system][2] < o.date
                ):
                    unregistered_chars[name][o.eve_solar_system][2] = o.date
            data.append(
                {
                    "date": str(o.date),
                    "ore": o.eve_type.name,
                    "name": name,
                    "quantity": o.quantity,
                    "location": o.eve_solar_system.name,
                }
            )

        unknown_data = []
        for name in unknown_chars.keys():
            for sys in unknown_chars[name].keys():
                unknown_data.append(
                    {
                        "name": name,
                        "sys": str(sys),
                        "quantity": unknown_chars[name][sys][0],
                        "isk": unknown_chars[name][sys][1],
                        "last": str(unknown_chars[name][sys][2]),
                    }
                )

        unregistered_data = []
        for name in unregistered_chars.keys():
            for sys in unregistered_chars[name].keys():
                unregistered_data.append(
                    {
                        "name": name,
                        "sys": str(sys),
                        "quantity": unregistered_chars[name][sys][0],
                        "isk": unregistered_chars[name][sys][1],
                        "last": str(unregistered_chars[name][sys][2]),
                    }
                )

        self.admin_corp_mining_history = {
            "mining_log": data,
            "unknown_data": unknown_data,
            "unregistered_data": unregistered_data,
        }
        self.save()

    def get_admin_corp_mining_history(self):
        if self.admin_corp_mining_history is None:
            self.calc_admin_corp_mining_history()
        return self.admin_corp_mining_history

    def calc_leaderboards(self):
        characters = Character.objects.all()
        allentries = list(map(lambda x: x.get_monthly_mining(), characters))
        combined = {}
        for i, entries in enumerate(allentries):
            c = characters[i].main_character
            if c is None:
                logger.error(f"Missing main for {c}")
                continue
            for m in entries.keys():
                if m not in combined:
                    combined[m] = {}
                if c.character_name not in combined[m]:
                    combined[m][c.character_name] = 0.0
                combined[m][c.character_name] += entries[m]
        output = []
        for m in sorted(combined.keys()):
            users = sorted(combined[m], key=lambda x: -combined[m][x])
            table = []
            for i, u in enumerate(users):
                table.append({"rank": i + 1, "character": u, "amount": combined[m][u]})
            output.append({"month": str(m), "table": table})

        self.leaderboards = {"data": output}
        self.save()

    def get_leaderboards(self):
        if self.leaderboards is None:
            self.calc_leaderboards()
        return self.leaderboards

    def save(self, *args, **kwargs):
        self.pk = 1
        super(Stats, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
