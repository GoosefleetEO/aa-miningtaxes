from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from . import urls


class MiningTaxesMenuItem(MenuItemHook):
    """This class ensures only authorized users will see the menu entry"""

    def __init__(self):
        # setup menu entry for sidebar
        MenuItemHook.__init__(
            self,
            _("Mining Taxes"),
            "fas fa-cube fa-fw",
            "miningtaxes:index",
            navactive=["miningtaxes:"],
        )

    def render(self, request):
        if request.user.has_perm("miningtaxes.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return MiningTaxesMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "miningtaxes", r"^miningtaxes/")
