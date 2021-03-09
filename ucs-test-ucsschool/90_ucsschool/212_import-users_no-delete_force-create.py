#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: test --no-delete option and force mode=D (Bug 41775, 41350)
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

    def test(self):  # formally test_no_delete_option()
        """
        Bug #41775, #41350: test --no-delete option:
        - with[out] --no-delete
        - with[out] explicit mode=D  -> should delete even when --no-delete is on
        """
        config = copy.deepcopy(self.default_config)
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)
        roles = ("student", "teacher", "staff", "teacher_and_staff")

        self.log.info('*** Testing "--no-delete" option...')
        person_list = [Person(self.ou_A.name, role) for role in roles]
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.log.info("*** Importing a user")
        self.run_import(["-c", fn_config, "-i", fn_csv])
        self.check_new_and_removed_users(4, 0)

        self.log.info('*** Importing new user, NOT deleting previous users (running with "--no-delete")')
        person_list = [Person(self.ou_A.name, role) for role in roles]
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv, "--no-delete"])
        self.check_new_and_removed_users(4, 0)

        self.log.info('*** Importing users, deleting previous users (running without "--no-delete")')
        person_list = [Person(self.ou_A.name, role) for role in roles]
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv])
        self.check_new_and_removed_users(4, 8)

        self.log.info("*** Importing users, deleting previous users")
        person_list = [Person(self.ou_A.name, role) for role in roles]
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv])
        self.check_new_and_removed_users(4, 4)

        self.log.info('*** Importing same users and running with "--no-delete"')
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv, "--no-delete"])
        self.check_new_and_removed_users(0, 0)

        self.log.info('*** Importing same users with action="D" and running with "--no-delete"')
        for person in person_list:
            person.set_mode_to_delete()
        config_d = copy.deepcopy(config)
        config_d.update_entry("csv:mapping:Aktion", "__action")
        fn_config_d = self.create_config_json(config=config_d)
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config_d["csv"]["mapping"])
        self.save_ldap_status()
        self.run_import(["-c", fn_config_d, "-i", fn_csv, "--no-delete"])
        self.check_new_and_removed_users(0, 4)


if __name__ == "__main__":
    Test().run()
