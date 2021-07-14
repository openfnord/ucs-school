#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: set OU display name
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import

from __future__ import print_function

import random

import univention.testing.strings as uts
import univention.testing.ucr
import univention.testing.udm
import univention.testing.utils as utils

ucr = univention.testing.ucr.UCSTestConfigRegistry()
ucr.load()

# multiple whitespaces to increase chance to get several words
charset = uts.STR_ALPHANUMDOTDASH + uts.STR_ALPHA.upper() + '()[]/,;:_#"+*@<>~ßöäüÖÄÜ$%&!     '


def main():
    with univention.testing.udm.UCSTestUDM() as udm:
        print("*** Stopping existing UDM CLI server")
        udm.stop_cli_server()

        print("*** Creating OU and set random display name without UCS@school option")
        ou_name = uts.random_name()
        ou_displayName = uts.random_string(length=random.randint(5, 50), charset=charset)
        dn = udm.create_object(
            "container/ou", position=ucr.get("ldap/base"), name=ou_name, displayName=ou_displayName
        )
        utils.verify_ldap_object(
            dn,
            expected_attr={"ou": [ou_name], "displayName": [ou_displayName]},
            strict=True,
            should_exist=True,
        )

        print("*** Creating OU and set random display name with UCS@school option")
        ou_name = uts.random_name()
        ou_displayName = uts.random_string(length=random.randint(5, 50), charset=charset)
        dn = udm.create_object(
            "container/ou",
            position=ucr.get("ldap/base"),
            name=ou_name,
            displayName=ou_displayName,
            options=["UCSschool-School-OU"],
        )
        utils.verify_ldap_object(
            dn,
            expected_attr={"ou": [ou_name], "displayName": [ou_displayName]},
            strict=True,
            should_exist=True,
        )

        print("*** Change displayName to new random value")
        ou_displayName = uts.random_string(length=random.randint(5, 50), charset=charset)
        dn = udm.modify_object("container/ou", dn=dn, displayName=ou_displayName)
        utils.verify_ldap_object(
            dn,
            expected_attr={"ou": [ou_name], "displayName": [ou_displayName]},
            strict=True,
            should_exist=True,
        )


if __name__ == "__main__":
    main()
