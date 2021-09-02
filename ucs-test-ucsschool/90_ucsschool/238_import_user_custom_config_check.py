#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Test UcsSchoolImportSkipImportRecord by raising it in a PyHook
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [47448]

import copy
import os
import os.path
import random
import shutil

import pytest
from ldap.filter import escape_filter_chars

import univention.testing.strings as uts
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException

TESTHOOKSOURCE = os.path.join(os.path.dirname(__file__), "test238_custom_conf_check.pycheck")
TESTHOOKTARGET = "/usr/share/ucs-school-import/checks/test238_custom_conf_check.py"


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def pyhook_cleanup(self):
        for ext in ["", "c", "o"]:
            path = "{}{}".format(TESTHOOKTARGET, ext)
            try:
                os.remove(path)
                self.log.info("*** Deleted %s.", path)
            except OSError:
                self.log.warning("*** Could not delete %s.", path)

    def cleanup(self):
        self.pyhook_cleanup()
        super(Test, self).cleanup()

    def test(self):
        source_uid = "source_uid-{}".format(uts.random_string())
        config = copy.deepcopy(self.default_config)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)

        self.log.info("Creating custom configuration test %r...", TESTHOOKTARGET)
        shutil.copy(TESTHOOKSOURCE, TESTHOOKTARGET)

        role = random.choice(("student", "teacher", "staff", "teacher_and_staff"))

        person = Person(self.ou_A.name, role)
        person.update(record_uid="record_uid-{}".format(uts.random_string()), source_uid=source_uid)

        self.log.info(
            "*** Importing a %r, no configuration test, no birthday mapping -> no exception...", role
        )
        fn_csv = self.create_csv_file(person_list=[person], mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        self.run_import(["-c", fn_config], fail_on_preexisting_pyhook=False)
        wait_for_drs_replication("cn={}".format(escape_filter_chars(person.username)))
        person.verify()
        self.log.info("*** OK: import ran.")

        self.log.info(
            "*** Importing same %r, activating check, no birthday mapping -> no exception...", role
        )
        config.update_entry("configuration_checks", ["defaults", "test238_custom_conf_check"])
        fn_csv = self.create_csv_file(person_list=[person], mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        self.run_import(["-c", fn_config], fail_on_preexisting_pyhook=False)
        wait_for_drs_replication("cn={}".format(escape_filter_chars(person.username)))
        person.verify()
        self.log.info("*** OK: import ran.")

        self.log.info(
            "*** Importing same %r, activating check, configuration test should raise an exception...",
            role,
        )
        config.update_entry("csv:mapping:birthday", "birthday")
        person.set_random_birthday()
        fn_csv = self.create_csv_file(person_list=[person], mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        with pytest.raises(ImportException):
            self.run_import(["-c", fn_config], fail_on_preexisting_pyhook=False)
        self.log.info("*** OK: import failed.")


if __name__ == "__main__":
    Test().run()
