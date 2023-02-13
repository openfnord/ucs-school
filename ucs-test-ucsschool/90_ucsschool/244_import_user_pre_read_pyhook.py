#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Test PreReadPyHook
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [48188]

import copy
import os
import os.path
import shutil

import pytest
from ldap.filter import escape_filter_chars

import univention.testing.strings as uts
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException

TESTHOOKSOURCE = "/usr/share/ucs-school-import/pyhooks-available/pre_read_modify_csv_header.py"
TESTHOOKTARGET = "/usr/share/ucs-school-import/pyhooks/test244_pre_read_modify_csv_header.py"


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
        config.update_entry("csv:mapping:recordUID", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)

        roles = ("staff", "student", "teacher", "teacher_and_staff")
        person_list = []
        for role in roles:
            person = Person(self.ou_A.name, role)
            person.update(record_uid="recordUID-{}".format(uts.random_string()), source_uid=source_uid)
            person_list.append(person)
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        with open(fn_csv) as fp:
            self.log.info("Header of created CSV: %r", fp.readline())

        del config["csv"]["mapping"]["OUs"]
        config.update_entry("csv:mapping:Grundschulen", "schools")
        config.update_entry("csv:header_swap", {"OUs": "Grundschulen", "Foo": "Bar"})

        self.log.info("*** Importing users without Pre-Read PyHook (should fail)...")
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        with pytest.raises(ImportException):
            self.run_import(["-c", fn_config])
        self.log.info("OK: import failed.")

        self.log.info("*** Importing users with Pre-Read PyHook...")
        self.log.info("Creating PyHook %r...", TESTHOOKTARGET)
        shutil.copy(TESTHOOKSOURCE, TESTHOOKTARGET)

        self.run_import(["-c", fn_config], fail_on_preexisting_pyhook=False)
        wait_for_drs_replication("cn={}".format(escape_filter_chars(person_list[-1].username)))
        for person in person_list:
            person.verify()
        self.log.info("OK: import succeeded.")


if __name__ == "__main__":
    Test().run()
