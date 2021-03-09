#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# UCS@School Helpdesk
#  univention admin helpdesk module
#
# Copyright 2006-2021 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import univention.admin.filter
import univention.admin.handlers
import univention.admin.localization
import univention.admin.syntax
import univention.debug
from univention.admin.layout import Tab

translation = univention.admin.localization.translation("univention.admin.handlers.settings.helpdesk")
_ = translation.translate

module = "settings/console_helpdesk"
operations = ["add", "edit", "remove", "search", "move"]
superordinate = "settings/cn"

childs = 0
short_description = _("Settings: Console Helpdesk")
long_description = _("Settings for Univention Console Helpdesk Module")
options = {}

default_containers = ["cn=config,cn=console,cn=univention"]


property_descriptions = {
    "name": univention.admin.property(
        short_description=_("Name"),
        long_description=_("Name of Console-Helpdesk-Settings-Object"),
        syntax=univention.admin.syntax.string_numbers_letters_dots,
        multivalue=False,
        options=[],
        required=True,
        may_change=False,
        identifies=True,
    ),
    "description": univention.admin.property(
        short_description=_("Description"),
        long_description=_("Description"),
        syntax=univention.admin.syntax.string,
        multivalue=False,
        options=[],
        dontsearch=True,
        required=False,
        may_change=True,
        identifies=False,
    ),
    "category": univention.admin.property(
        short_description=_("Category"),
        long_description=_("Helpdesk Category"),
        syntax=univention.admin.syntax.string,
        multivalue=True,
        options=[],
        required=False,
        may_change=True,
        identifies=False,
    ),
}


layout = [
    Tab(_("General"), _("Basic Values"), layout=["description", "category",]),
]

mapping = univention.admin.mapping.mapping()

mapping.register("name", "cn", None, univention.admin.mapping.ListToString)
mapping.register("description", "description", None, univention.admin.mapping.ListToString)
mapping.register("category", "univentionUMCHelpdeskCategory")


class object(univention.admin.handlers.simpleLdap):
    module = module

    def __init__(self, co, lo, position, dn="", superordinate=None, attributes=[]):
        global mapping
        global property_descriptions

        self.co = co
        self.lo = lo
        self.dn = dn
        self.position = position
        self._exists = 0
        self.mapping = mapping
        self.descriptions = property_descriptions

        super(object, self).__init__(co, lo, position, dn, superordinate, attributes)

    def exists(self):
        return self._exists

    def _ldap_pre_create(self):
        self.dn = "%s=%s,%s" % (
            mapping.mapName("name"),
            mapping.mapValue("name", self.info["name"]),
            self.position.getDn(),
        )

    def _ldap_addlist(self):
        return [("objectClass", ["top", "univentionUMCHelpdeskClass"])]


def lookup(
    co,
    lo,
    filter_s,
    base="",
    superordinate=None,
    scope="sub",
    unique=False,
    required=False,
    timeout=-1,
    sizelimit=0,
):

    filter = univention.admin.filter.conjunction(
        "&", [univention.admin.filter.expression("objectClass", "univentionUMCHelpdeskClass")]
    )

    if filter_s:
        filter_p = univention.admin.filter.parse(filter_s)
        univention.admin.filter.walk(filter_p, univention.admin.mapping.mapRewrite, arg=mapping)
        filter.expressions.append(filter_p)

    res = []
    try:
        for dn in lo.searchDn(unicode(filter), base, scope, unique, required, timeout, sizelimit):
            res.append(object(co, lo, None, dn))
    except:
        pass
    return res


def identify(dn, attr, canonical=0):
    return "univentionUMCHelpdeskClass" in attr.get("objectClass", [])
