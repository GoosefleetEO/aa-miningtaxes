from eveuniverse.models import EveType


class PriceGroups:
    moon_ore_groups = (
        1923,  # R64 Moon ores
        1922,  # R32 Moon ores
        1921,  # R16 Moon ores
        1920,  # R8 Moon ores
        1884,  # R4 Moon ores
    )

    groups = (
        711,  # Gasses
        1923,  # R64 Moon ores
        1922,  # R32 Moon ores
        1921,  # R16 Moon ores
        1920,  # R8 Moon ores
        1884,  # R4 Moon ores
        427,  # Moon materials
        465,  # Ice
        423,  # Ice materials
        18,  # Ore materials
        468,  # Mercoxit
        450,  # Arkonor
        4031,  # Bezdnacine
        451,  # Bistot
        452,  # Crokite
        453,  # Dark Ochre
        467,  # Gneiss
        454,  # Hedbergite
        455,  # Hemorphite
        456,  # Jaspet
        457,  # Kernite
        469,  # Omber
        458,  # Plagioclase
        459,  # Pyroxeres
        4030,  # Rakovene
        460,  # Scordite
        461,  # Spodumain
        4029,  # Talassonite
        462,  # Veldspar
    )

    taxgroups = {
        711: "Gasses",
        1923: "R64",
        1922: "R32",
        1921: "R16",
        1920: "R8",
        1884: "R4",
        465: "Ice",
        468: "Mercoxit",
        450: "Ores",
        4031: "Ores",
        451: "Ores",
        452: "Ores",
        453: "Ores",
        467: "Ores",
        454: "Ores",
        455: "Ores",
        529: "Ores",
        457: "Ores",
        526: "Ores",
        516: "Ores",
        459: "Ores",
        4030: "Ores",
        460: "Ores",
        461: "Ores",
        4029: "Ores",
        462: "Ores",
    }

    def __init__(self):
        self.items = []
        added = set()
        for grp in self.groups:
            g = EveType.objects.filter(eve_group_id=grp)
            for it in g:
                if it.id in added:
                    continue
                added.add(it.id)
                self.items.append(it)
        self.taxable_groups = set()
        for k in self.taxgroups.keys():
            self.taxable_groups.add(self.taxgroups[k])
