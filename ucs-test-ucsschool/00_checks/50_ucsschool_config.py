#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Check ucs config in ucs@school
## tags: [ucsschool]
## exposure: safe

import sys

from six import iteritems

import univention.config_registry
import univention.testing.utils as utils

ucr = univention.config_registry.ConfigRegistry()
ucr.load()


def check_setting(setting, value):
    if ucr[setting] != value:
        utils.fail(
            "{} not correctly configured (is {}, should be {})".format(setting, value, ucr[setting])
        )


settings_connector = {
    "connector/s4/mapping/sid_to_s4": "yes",
    "connector/s4/mapping/sid_to_ucs": "no",
    "connector/s4/mapping/syncmode": "sync",
    "connector/s4/mapping/msprintconnectionpolicy": "yes",
    "connector/s4/mapping/msgpwl": "yes",
    "connector/s4/mapping/msgpipsec": "yes",
    "connector/s4/mapping/msgpsi": "yes",
    "connector/s4/mapping/wmifilter": "yes",
    "connector/s4/mapping/gpo": "true",
    "connector/s4/mapping/dns/ignorelist": "_ldap._tcp.Default-First-Site-Name._site",
}

settings_samba = {
    "samba4/ldb/sam/module/prepend": "univention_samaccountname_ldap_check",
}

settings_school_slave = {
    "connector/s4/mapping/user/ignorelist": "root,ucs-s4sync,krbtgt,Guest",
    "connector/s4/allow/secondary": "true",
}


if utils.package_installed("univention-samba4"):
    for setting, value in iteritems(settings_samba):
        if setting == "samba4/ldb/sam/module/prepend" and not any(
            (
                utils.package_installed("ucs-school-singlemaster"),
                utils.package_installed("ucs-school-slave"),
                utils.package_installed("ucs-school-nonedu-slave"),
            )
        ):
            # Bug #49726: test only on slave / singlemaster
            continue
        check_setting(setting, value)

if utils.package_installed("univention-s4-connector"):
    for setting, value in iteritems(settings_connector):
        check_setting(setting, value)

if utils.package_installed("ucs-school-slave"):
    for setting, value in iteritems(settings_school_slave):
        check_setting(setting, value)

sys.exit(0)
