#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Imported users found using record_uid
## tags: [apptest,ucsschool,ucsschool_import1,logging]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: []

import copy
import os.path

from ldap.filter import filter_format

import univention.testing.strings as uts
import univention.testing.utils as utils
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, PyHooks


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def __init__(self):
        super(Test, self).__init__()
        self.hooks = PyHooks()
        self.hooks.create_hooks()

    def assert_and_print(self, exists, fn):
        status = os.path.exists(os.path.join(self.hooks.tmpdir, fn))
        self.log.debug("Hook touch file %r exists = %r" % (fn, status))
        assert exists == status, "Unexpected status of hook touch file: exists=%s  expected=%s" % (
            status,
            exists,
        )

    def test(
        self,
    ):  # formerly test_create_modify_delete_user_with_username_and_record_uid_and_UDM_property()
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config = copy.deepcopy(self.default_config)
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:DBID", "record_uid")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)

        person_list = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person_a = Person(self.ou_A.name, role)
            person_b = Person(self.ou_A.name, role)
            person_a.update(
                record_uid=uts.random_name(), source_uid=source_uid, description=uts.random_name()
            )
            person_b.update(
                record_uid=uts.random_name(), source_uid=source_uid, description=uts.random_name()
            )
            person_list.append(person_a)
            person_list.append(person_b)

        self.log.info("*** Importing two users of each role...")
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv], fail_on_preexisting_pyhook=False)
        wait_for_drs_replication(filter_format("cn=%s", (person_list[-1].username,)))

        self.check_new_and_removed_users(8, 0)

        for person in person_list:
            person.verify()
            utils.verify_ldap_object(
                person.dn,
                expected_attr={"street": [",pre-create,post-create"]},
                strict=True,
                should_exist=True,
            )

        for fn in ("pre-create", "post-create"):
            self.assert_and_print(True, fn)
        for fn in ("pre-modify", "post-modify", "pre-remove", "post-remove"):
            self.assert_and_print(False, fn)

        self.log.info("*** Modifying both users username and record_uid...")
        person_list_pairs = zip(person_list[::2], person_list[1::2])
        for person_a, person_b in person_list_pairs:
            self.log.info(
                "Changing firstname of %r and lastname of %r.", person_a.username, person_b.username
            )
            person_a.firstname = uts.random_name()
            person_b.lastname = uts.random_name()

        self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"], fn_csv=fn_csv)
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv], fail_on_preexisting_pyhook=False)
        wait_for_drs_replication(filter_format("cn=%s", (person_list[-1].username,)))
        self.check_new_and_removed_users(0, 0)

        for person in person_list:
            person.verify()
            utils.verify_ldap_object(
                person.dn,
                expected_attr={"street": [",pre-create,post-create,pre-modify,post-modify"]},
                strict=True,
                should_exist=True,
            )
        for fn in ("pre-create", "post-create", "pre-modify", "post-modify"):
            self.assert_and_print(True, fn)
        for fn in ("pre-remove", "post-remove"):
            self.assert_and_print(False, fn)

        self.log.info("*** Remove users %r...", person_list[::2])
        # mark first person as removed
        for person_a, person_b in person_list_pairs:
            person_a.set_mode_to_delete()
        # import only second person
        self.create_csv_file(
            person_list=person_list[1::2], mapping=config["csv"]["mapping"], fn_csv=fn_csv
        )
        fn_config = self.create_config_json(values=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv], fail_on_preexisting_pyhook=False)
        self.check_new_and_removed_users(0, 4)

        for person in person_list:
            person.verify()
        for fn in (
            "pre-create",
            "post-create",
            "pre-modify",
            "post-modify",
            "pre-remove",
            "post-remove",
        ):
            self.assert_and_print(True, fn)

    def cleanup(self):
        self.hooks.cleanup()
        super(Test, self).cleanup()


if __name__ == "__main__":
    Test().run()
