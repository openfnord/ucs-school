#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Test UcsSchoolImportSkipImportRecord by raising it in a PyHook
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [47162]

import copy
import os
import os.path
import shutil

from ldap.filter import escape_filter_chars

import univention.testing.strings as uts
import univention.testing.utils as utils
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException

TESTHOOKSOURCE = os.path.join(os.path.dirname(__file__), "test236_skip_exception.pyhook")
TESTHOOKTARGET = "/usr/share/ucs-school-import/pyhooks/test236_skip_exception.py"


class Test(CLI_Import_v2_Tester):
    ou_C = None

    def pyhook_cleanup(self):
        for ext in ["", "c", "o"]:
            path = "{}{}".format(TESTHOOKTARGET, ext)
            try:
                os.remove(path)
                self.log.info("*** Deleted %s.", path)
            except OSError:
                self.log.warn("*** Could not delete %s.", path)

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
        config.update_entry("tolerate_errors", 0)

        self.log.info("Creating PyHook %r...", TESTHOOKTARGET)
        shutil.copy(TESTHOOKSOURCE, TESTHOOKTARGET)

        self.log.info(
            '*** Importing a user from each role, two with firstname starting with "M" should not be '
            "created..."
        )
        person_list = list()
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            person = Person(self.ou_A.name, role)
            person.update(record_uid="record_uid-{}".format(uts.random_string()), source_uid=source_uid)
            person_list.append(person)
        person_list[0].update(firstname="A{}".format(person_list[0].firstname[1:]))
        person_list[1].update(firstname="M{}".format(person_list[1].firstname[1:]))
        person_list[2].update(firstname="B{}".format(person_list[2].firstname[1:]))
        person_list[3].update(firstname="M{}".format(person_list[3].firstname[1:]))
        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(values=config)
        try:
            self.run_import(["-c", fn_config], fail_on_preexisting_pyhook=False)
        except ImportException:
            self.log.info("OK: import failed.")
        wait_for_drs_replication("cn={}".format(escape_filter_chars(person_list[2].username)))
        for person in (person_list[0], person_list[2]):
            utils.verify_ldap_object(person.dn, strict=False, should_exist=True)
        for person in (person_list[1], person_list[3]):
            utils.verify_ldap_object(person.dn, strict=False, should_exist=False)


if __name__ == "__main__":
    Test().run()
