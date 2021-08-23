#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Check if a new group gets a domain sid
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

        # create a group which is ignored by the connector
        position = "cn=univention,%s" % ucr.get("ldap/base")
        group_dn, groupname = udm.create_group(position=position, check_for_drs_replication=False)

        lo = uldap.getMachineConnection()
        group_sid = lo.get(group_dn)["sambaSID"][0]
        if not group_sid.startswith(b"S-1-5-21-"):
            raise WrongSID()
