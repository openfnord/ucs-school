#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: test if it is possible to reuse an email address (Bug 41544)
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [41544]

import copy
import random

from ldap.filter import filter_format

import univention.testing.strings as uts
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):  # formally test_reuse_email_attribute()
        """
        Bug #41544: test if it is possible to reuse an email address (-> if
        users are removed before they are added)
        """
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config = copy.deepcopy(self.default_config)
        config.update_entry("source_uid", source_uid)
        config.update_entry("scheme:email", "<email>")
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)
        config.update_entry("deletion_grace_period:deletion", 0)
        person_list = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            record_uid = uts.random_name()
            person.update(
                record_uid=record_uid,
                source_uid=source_uid,
                mail="{}@{}".format(uts.random_name(), self.maildomain),
            )
            person_list.append(person)
        email_list = [p.mail for p in person_list]

        self.log.info("*** Importing users with email addresses %r...", email_list)
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config])
        wait_for_drs_replication(filter_format("cn=%s", (person_list[-1].username,)))
        self.check_new_and_removed_users(4, 0)
        for person in person_list:
            person.verify()

        random.shuffle(email_list)
        self.log.info(
            "*** Importing new users (and thus deleting previously imported users) with same "
            "email addresses %r ...",
            email_list,
        )
        person_list = []
        for num, role in enumerate(("student", "teacher", "staff", "teacher_and_staff")):
            person = Person(self.ou_A.name, role)
            record_uid = uts.random_name()
            person.update(record_uid=record_uid, source_uid=source_uid, mail=email_list[num])
            person_list.append(person)

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config])
        self.check_new_and_removed_users(4, 4)
        for person in person_list:
            person.verify()


if __name__ == "__main__":
    Test().run()
