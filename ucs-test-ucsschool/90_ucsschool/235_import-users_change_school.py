#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Check user moving between schools
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [45379]

import copy

import univention.testing.strings as uts
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    def test(self):
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config = copy.deepcopy(self.default_config)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)

        self.log.info("*** 1. Importing (create in %r) new users of each role....", self.ou_A.name)
        person_list = list()
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(record_uid="record_uid-{}".format(uts.random_string()), source_uid=source_uid)
            person_list.append(person)

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])

        for person in person_list:
            person.verify()
        self.log.info("OK: import (create) succeeded.")

        self.log.info(
            "*** 2. Importing (move %r -> %r) of existing users of each role....",
            self.ou_A.name,
            self.ou_B.name,
        )
        for person in person_list:
            person.old_school = person.school
            person.update(school=self.ou_B.name)

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])
        for person in person_list:
            person.verify()
        self.log.info("OK: import (move 1) succeeded.")

        self.log.info(
            "*** 3. Importing (move %r -> %r) of existing users of each role...",
            self.ou_B.name,
            self.ou_C.name,
        )
        for person in person_list:
            person.old_school = person.school
            person.update(school=self.ou_C.name)

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])
        for person in person_list:
            person.verify()
        self.log.info("OK: import (move 2) succeeded.")


if __name__ == "__main__":
    Test().run()
