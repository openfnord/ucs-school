#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Check if a new user gets a domain sid
## tags: [apptest,ucsschool,ucsschool_base1]
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup,
##  - domaincontroller_slave,
##  - memberserver
## exposure: dangerous
## bugs: [33677]

import univention.config_registry as config_registry
import univention.testing.udm as udm_test
import univention.uldap as uldap


class WrongSID(Exception):
    pass


if __name__ == "__main__":
    with udm_test.UCSTestUDM() as udm:
        ucr = config_registry.ConfigRegistry()
        ucr.load()

        # create an user who is ignored by the connector
        position = "cn=univention,%s" % ucr.get("ldap/base")
        user_dn, username = udm.create_user(
            position=position, check_for_drs_replication=False, wait_for=False
        )

        lo = uldap.getMachineConnection()
        user_sid = lo.get(user_dn)["sambaSID"][0]
        if not user_sid.startswith("S-1-5-21-"):
            raise WrongSID()
