#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: test recursion detection in dependency solver for formatting ImportUser properties
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [42137]

import copy
import random

import pytest

import univention.testing.strings as uts
import univention.testing.utils as utils
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException

username_max_length = {"default": 20, "student": 15}


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):
        source_uid = "{}-{:02}-{:02}".format(
            random.randint(1900, 2016), random.randint(1, 12), random.randint(1, 27)
        )
        config = copy.deepcopy(self.default_config)
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)

        self.log.info("*** 1 Importing (create) a new user of each role.")
        person_list_success = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(record_uid=person.username, source_uid=source_uid)
            person_list_success.append(person)
        fn_csv = self.create_csv_file(person_list=person_list_success, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])
        for person in person_list_success:
            person.verify()
        self.log.info("OK: import succeeded.")

        self.log.info(
            "*** 2 Importing a user from each role with same source_uid but a recursion in scheme..."
        )

        config = copy.deepcopy(self.default_config)
        del config["csv"]["mapping"]
        config.update_entry("csv:mapping:Nach", "lastname")
        config.update_entry("csv:mapping:OUs", "schools")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("scheme:birthday", "<source_uid>")
        config.update_entry("scheme:record_uid", "<email>.<name>[0:4]"),
        config.update_entry("scheme:email", "<firstname:lower>.<lastname:lower>@<maildomain><:strip>"),
        config.update_entry("scheme:username:default", "<firstname:lower>.<phone>"),
        config.update_entry("scheme:firstname", "fn-<email>[1:6]"),  # recursion!
        config.update_entry("scheme:street", "<:lower><firstname>-<roomNumber>"),
        config.update_entry("scheme:phone", "<birthday>"),
        config.update_entry("scheme:roomNumber", "<street>-<email>[0:5]"),  # recursion!
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)

        person_list = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(
                source_uid=source_uid,
                lastname=uts.random_username(),
                birthday=None,  # emtpy, so that it will be generated from scheme
                record_uid=None,
                mail=None,
                username=None,
                firstname=None,
                school_classes={},  # no mapping for auto generated classes
            )
            person_list.append(person)
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        with pytest.raises(ImportException):
            self.run_import(["-c", fn_config])
        self.log.info("*** OK: import failed.")

        # import must fail before creating or deleting any users
        for person in person_list:
            utils.verify_ldap_object(person.dn, strict=False, should_exist=False)
        for person in person_list_success:
            utils.verify_ldap_object(person.dn, strict=False, should_exist=True)


if __name__ == "__main__":
    Test().run()
