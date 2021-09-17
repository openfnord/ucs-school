#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Import deactived user
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [42913]


import copy

from ldap.filter import filter_format

import univention.admin.uldap
import univention.testing.strings as uts
from ucsschool.lib.models.user import User
from univention.admin.uexceptions import authFail
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config = copy.deepcopy(self.default_config)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:password", "password")
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)
        config.update_entry("activate_new_users:default", False)

        self.log.info("*** Importing new, deactivated users of all roles...")
        person_list = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(
                record_uid="record_uid-{}".format(uts.random_string()),
                source_uid=source_uid,
                password=uts.random_string(20),
            )
            person_list.append(person)
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config])
        wait_for_drs_replication(filter_format("cn=%s", (person_list[-1].username,)))
        self.check_new_and_removed_users(4, 0)
        for person in person_list:
            person.set_inactive()
            person.verify()

            udm_user = User.from_dn(person.dn, None, self.lo).get_udm_object(self.lo)
            self.log.info("disabled: %r", udm_user.get("disabled"))
            self.log.info("locked: %r", udm_user.get("locked"))
            self.log.info("userexpiry: %r", udm_user.get("userexpiry"))

            try:
                univention.admin.uldap.access(binddn=person.dn, bindpw=person.password)
                self.fail("Deactivated user can bind to LDAP server.")
            except authFail:
                self.log.info("OK: deactivated user cannot bind to LDAP server.")

        self.log.info("*** Importing deactivated users, activating them...")
        for person in person_list:
            person.set_active()
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config])
        wait_for_drs_replication(filter_format("cn=%s", (person_list[-1].username,)))
        for person in person_list:
            person.verify()
            udm_user = User.from_dn(person.dn, None, self.lo).get_udm_object(self.lo)
            self.log.info("disabled: %r", udm_user.get("disabled"))
            self.log.info("locked: %r", udm_user.get("locked"))
            self.log.info("userexpiry: %r", udm_user.get("userexpiry"))
            try:
                univention.admin.uldap.access(binddn=person.dn, bindpw=person.password)
                self.log.info("OK: reactivated user can bind to LDAP server.")
            except authFail:
                self.fail("Reactivated user cannot bind to LDAP server.")


if __name__ == "__main__":
    Test().run()
