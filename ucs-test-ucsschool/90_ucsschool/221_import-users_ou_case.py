#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Import users via CLI v2 with a OU name in wrong upper/lower case
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [42456]

import random
import string

import pytest

import univention.testing.strings as uts
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException


class Test(CLI_Import_v2_Tester):
    def test(self):
        for ori_ou in (self.ou_A, self.ou_B, self.ou_C):
            while not any(c in string.ascii_letters for c in ori_ou.name):
                # test won't work: only digits -> upper case == lower case
                self.log.warning("OU does not contain any letters, creating new one.")
                ori_ou.name, ori_ou.dn = self.schoolenv.create_ou(
                    name_edudc=self.ucr.get("hostname"), use_cache=False
                )

            role = random.choice(("student", "teacher", "staff", "teacher_and_staff"))
            self.log.info(
                "*** Importing a new single user with role %r and ori_ou=(%r, %r)",
                role,
                ori_ou.name,
                ori_ou.dn,
            )

            person = Person(ori_ou.name, role)
            fn_csv = self.create_csv_file(person_list=[person])
            source_uid = "source_uid-%s" % (uts.random_string(),)
            record_uid = "%s;%s;%s" % (person.firstname, person.lastname, person.mail)
            config = {
                "source_uid": source_uid,
                "input:filename": fn_csv,
                "user_role": role,
            }
            fn_config = self.create_config_json(values=config)
            self.save_ldap_status()
            self.run_import(["-c", fn_config])
            self.check_new_and_removed_users(1, 0)
            new_users = [x for x in self.diff_ldap_status().new if x.startswith("uid=")]
            person.update(dn=new_users[0], record_uid=record_uid, source_uid=source_uid)
            person.verify()
            self.log.info("*** OK - import is functional. Trying with bad OU name now.")

            ou = ori_ou.name
            while ou == ori_ou.name:
                index = random.choice(range(len(ou)))
                func = random.choice((str.lower, str.upper))
                ou = list(ou)
                ou[index] = func(ou[index])
                ou = "".join(ou)
            self.log.info("*** original OU=%r modified OU=%r", ori_ou.name, ou)

            person = Person(ou, role)
            fn_csv = self.create_csv_file(person_list=[person])
            source_uid = "source_uid-%s" % (uts.random_string(),)
            config = {
                "source_uid": source_uid,
                "input:filename": fn_csv,
                "user_role": role,
            }
            fn_config = self.create_config_json(values=config)
            with pytest.raises(ImportException):
                self.run_import(["-c", fn_config])
            self.log.info("*** OK - import stopped.")


if __name__ == "__main__":
    Test().run()
