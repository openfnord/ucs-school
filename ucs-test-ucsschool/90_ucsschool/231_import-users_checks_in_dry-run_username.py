#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Verify that checks on existing usernames are executed in dry-run
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [45715]

import copy
import random

import pytest

import univention.testing.strings as uts
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config = copy.deepcopy(self.default_config)
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)

        role, func = random.choice(
            (
                ("staff", self.schoolenv.create_staff),
                ("student", self.schoolenv.create_student),
                ("teacher", self.schoolenv.create_teacher),
                ("teacher_and_staff", self.schoolenv.create_teacher_and_staff),
            )
        )

        username, user_dn = func(self.ou_A.name, schools=None)
        self.log.info("*** Created a new %r with username %r.", role, username)

        self.log.info(
            "*** Importing same %r with username %r with dry-run (should fail)...", role, username
        )
        config.update_entry("dry_run", True)
        person = Person(self.ou_A.name, role)
        person.update(record_uid=person.username, source_uid=source_uid, username=username)
        fn_csv = self.create_csv_file(person_list=[person], mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        with pytest.raises(ImportException):
            self.run_import(["-c", fn_config, "-i", fn_csv])
        self.log.info("OK: import failed.")

        self.log.info("*** Importing (create) a new user of role %r and different username...", role)
        config.update_entry("dry_run", False)
        person = Person(self.ou_A.name, role)
        person.update(record_uid=person.username, source_uid=source_uid)
        fn_csv = self.create_csv_file(person_list=[person], mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])
        person.verify()

        self.log.info(
            "*** Importing (modify) same user (%r) but changing its username to %r in dry-run (should "
            "fail)...",
            person.username,
            role,
            username,
        )
        config.update_entry("dry_run", True)
        person.update(username=username)
        fn_csv = self.create_csv_file(person_list=[person], mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        with pytest.raises(ImportException):
            self.run_import(["-c", fn_config, "-i", fn_csv])
        self.log.info("OK: import failed.")


if __name__ == "__main__":
    Test().run()
