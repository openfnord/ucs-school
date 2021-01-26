#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Check if the --no-delete option works as expected (Bug #41775, #41350)
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [41350, 41775]

import copy

import univention.testing.strings as uts
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):  # formerly test_create_modify_only()
        """
        Bug #41775, #41350: check if the --no-delete option works as expected
        """
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config = copy.deepcopy(self.default_config)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("scheme:record_uid", "<username>")
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)

        person_list_a = []
        person_list_b = []
        self.log.info("*** Add/modify without delete...")
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(record_uid=person.username, source_uid=source_uid)
            person_list_a.append(person)
            person = Person(self.ou_A.name, role)
            person.update(record_uid=person.username, source_uid=source_uid)
            person_list_b.append(person)

        self.log.info("Adding users A: %r", [_person.username for _person in person_list_a])
        fn_csv = self.create_csv_file(person_list=person_list_a, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv, "--no-delete"])
        self.check_new_and_removed_users(4, 0)
        for person in person_list_a:
            person.verify()

        self.log.info("Adding users B: %r", [person.username for person in person_list_b])
        fn_csv = self.create_csv_file(person_list=person_list_b, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv, "--no-delete"])
        self.check_new_and_removed_users(4, 0)
        for person in person_list_a:
            person.verify()
        for person in person_list_b:
            person.verify()

        self.log.info("Modifying users A: %r", [person.username for person in person_list_a])
        for person in person_list_a:
            person.lastname = uts.random_name()
        config.update_entry("no_delete", "True")
        fn_csv = self.create_csv_file(person_list=person_list_a, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        # '--no-delete'  is not specified on purpose -> using config option "no_delete"
        self.run_import(["-c", fn_config, "-i", fn_csv])
        self.check_new_and_removed_users(0, 0)
        for person in person_list_a:
            person.verify()
        for person in person_list_b:
            person.verify()


if __name__ == "__main__":
    Test().run()
