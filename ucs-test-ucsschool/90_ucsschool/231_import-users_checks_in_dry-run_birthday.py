#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Verify that checks of birthday format are executed in dry-run
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [46571, 46572]

import copy
import time

import univention.testing.strings as uts
import univention.testing.utils as utils
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException


class Test(CLI_Import_v2_Tester):
    def test(self):
        source_uid_success = "source_uid-%s" % (uts.random_string(),)
        config = copy.deepcopy(self.default_config)
        config.update_entry("source_uid", source_uid_success)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:birthday", "birthday")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)

        self.log.info(
            "*** 1.1 Importing (create) a new user of each role with birthday in correct format."
        )
        self.log.info("*** 1.1 should not fail for non-dry-run..")
        config.update_entry("dry_run", False)
        person_list_success = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.set_random_birthday()
            person.update(record_uid=person.username, source_uid=source_uid_success)
            person_list_success.append(person)

        fn_csv = self.create_csv_file(person_list=person_list_success, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])
        for person in person_list_success:
            person.verify()
        self.log.info("OK: import succeeded.")

        self.log.info(
            "*** 1.2 Importing (create) a new user of each role with birthday in correct format."
        )
        self.log.info("*** 1.2 should not fail for dry-run..")
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config.update_entry("source_uid", source_uid)
        config.update_entry("dry_run", True)
        person_list = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(
                record_uid=person.username, source_uid=source_uid, birthday=time.strftime("%Y-%m-%d")
            )
            person_list.append(person)

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])
        for person in person_list:
            utils.verify_ldap_object(person.dn, strict=False, should_exist=False)
        self.log.info("OK: dry-run succeeded.")

        self.log.info("*** 2.1 Importing (create) a new user of each role with birthday in bad format.")
        self.log.info("*** 2.1 should fail for non-dry-run..")
        config.update_entry("dry_run", False)
        person_list = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(
                record_uid=person.username, source_uid=source_uid, birthday=time.strftime("%Y%m%d")
            )
            person_list.append(person)

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        try:
            self.run_import(["-c", fn_config, "-i", fn_csv])
            self.fail("Import did not fail.")
        except ImportException:
            self.log.info("OK: import failed.")

        for person in person_list:
            utils.verify_ldap_object(person.dn, strict=False, should_exist=False)

        self.log.info("*** 2.2 Importing (create) a new user of each role with birthday in bad format.")
        self.log.info("*** 2.2 should also fail for dry-run..")
        config.update_entry("dry_run", True)
        fn_config = self.create_config_json(config=config)
        try:
            self.run_import(["-c", fn_config, "-i", fn_csv])
            self.fail("Dry-run did not fail.")
        except ImportException:
            self.log.info("OK: dry-run failed.")

        for person in person_list:
            utils.verify_ldap_object(person.dn, strict=False, should_exist=False)

        self.log.info(
            "*** 3.1 Importing (modify) of existing users of each role with birthday in bad format."
        )
        self.log.info("*** 3.1 should fail for non-dry-run..")
        config.update_entry("dry_run", False)
        config.update_entry("source_uid", source_uid_success)
        for person in person_list_success:
            person.old_birthday = person.birthday
            person.update(birthday="19870606")

        fn_csv = self.create_csv_file(person_list=person_list_success, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        try:
            self.run_import(["-c", fn_config, "-i", fn_csv])
            self.fail("Import did not fail.")
        except ImportException:
            self.log.info("OK: import failed.")

        for person in person_list_success:
            person.update(birthday=person.old_birthday)
            person.verify()

        self.log.info(
            "*** 3.2 Importing (modify) of existing users of each role with birthday in bad format."
        )
        self.log.info("*** 3.2 should fail for dry-run..")
        config.update_entry("dry_run", True)
        for person in person_list_success:
            person.old_birthday = person.birthday
            person.update(birthday="19760504")

        fn_csv = self.create_csv_file(person_list=person_list_success, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        try:
            self.run_import(["-c", fn_config, "-i", fn_csv])
            self.fail("Dry-run did not fail.")
        except ImportException:
            self.log.info("OK: dry-run failed.")

        for person in person_list_success:
            person.update(birthday=person.old_birthday)
            person.verify()

        self.log.info(
            "*** 4.1 Importing (move %r -> %r) of existing users of each role with birthday in bad "
            "format.",
            self.ou_A.name,
            self.ou_B.name,
        )
        self.log.info("*** 4.1 should fail for non-dry-run..")
        config.update_entry("dry_run", False)
        for person in person_list_success:
            person.old_birthday = person.birthday
            person.old_school = person.school
            person.update(school=self.ou_B.name, birthday="18160402")

        fn_csv = self.create_csv_file(person_list=person_list_success, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        try:
            self.run_import(["-c", fn_config, "-i", fn_csv])
            self.fail("Import did not fail.")
        except ImportException:
            self.log.info("OK: import failed.")

        # Import aborted after 1st person, others didn't change school.
        for person in person_list_success[1:]:
            person.update(school=person.old_school)

        for person in person_list_success:
            person.update(
                birthday=person.old_birthday, school_classes={}
            )  # As the import aborts, school classes may
            # not have been created in the new school, but old ones may have been removed already.
            # So lets ignore them.
            person.verify()

        self.log.info(
            "*** 4.2 Importing (move %r/%r -> %r) of existing users of each role with birthday in bad "
            "format.",
            self.ou_A.name,
            self.ou_B.name,
            self.ou_C.name,
        )
        self.log.info("*** 4.2 should fail for dry-run..")
        config.update_entry("dry_run", True)
        for person in person_list_success:
            person.old_birthday = person.birthday
            person.old_school = person.school
            person.update(school=self.ou_C.name, birthday="19010203")

        fn_csv = self.create_csv_file(person_list=person_list_success, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        try:
            self.run_import(["-c", fn_config, "-i", fn_csv])
            self.fail("Import did not fail.")
        except ImportException:
            self.log.info("OK: import failed.")

        for person in person_list_success:
            person.update(school=person.old_school, birthday=person.old_birthday)
            person.verify()


if __name__ == "__main__":
    Test().run()
