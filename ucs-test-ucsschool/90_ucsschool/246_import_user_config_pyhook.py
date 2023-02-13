#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Test ExtendConfigByRole hook
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [49265, 49267]

import copy
import json
import os
import os.path
import random
import shutil
import tempfile

import univention.testing.strings as uts
from univention.testing import utils
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester

TESTHOOKSOURCE = "/usr/share/ucs-school-import/pyhooks-available/ext_config_dep_on_role.py"
TESTHOOKTARGET = "/usr/share/ucs-school-import/pyhooks/test246_config_modification.py"


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def __init__(self, *args, **kwargs):
        super(Test, self).__init__(*args, **kwargs)
        _fd, self.student_conf_path = tempfile.mkstemp()
        _fd, self.teacher_conf_path = tempfile.mkstemp()

    def pyhook_cleanup(self):
        paths = [self.student_conf_path, self.teacher_conf_path]
        paths.extend("{}{}".format(TESTHOOKTARGET, ext) for ext in ["", "c", "o"])
        for path in paths:
            try:
                os.remove(path)
                self.log.info("*** Deleted %s.", path)
            except OSError:
                self.log.warning("*** Could not delete %s.", path)

    def cleanup(self):
        self.pyhook_cleanup()
        super(Test, self).cleanup()

    def test(self):
        shutil.copy(TESTHOOKSOURCE, TESTHOOKTARGET)
        student_conf = {
            "username": {
                "max_length": {
                    "default": 20,
                    "student": random.randint(4, 6),
                    "teacher": random.randint(7, 10),
                }
            }
        }
        teacher_conf = {
            "username": {
                "max_length": {
                    "default": 20,
                    "student": random.randint(11, 14),
                    "teacher": random.randint(15, 18),
                }
            }
        }
        with open(self.student_conf_path, "w") as fp:
            json.dump(student_conf, fp, indent=4)
        with open(self.teacher_conf_path, "w") as fp:
            json.dump(teacher_conf, fp, indent=4)

        source_uid = "source_uid-{}".format(uts.random_string())
        config = copy.deepcopy(self.default_config)
        config.update_entry("csv:mapping:recordUID", "record_uid")
        config.update_entry("source_uid", source_uid)
        config.update_entry("scheme:username:default", "<:umlauts><firstname><lastname>")
        config.update_entry("include:by_role:student", self.student_conf_path)
        config.update_entry("include:by_role:teacher", self.teacher_conf_path)

        for role, un_len in (
            ("staff", 20),
            ("student", student_conf["username"]["max_length"]["student"]),
            ("teacher", teacher_conf["username"]["max_length"]["teacher"]),
            ("teacher_and_staff", 20),
        ):
            self.log.info(
                "*** Importing user with role %s, should have username length %d...", role, un_len
            )

            config.update_entry("user_role", role)
            person = Person(self.ou_A.name, role)
            person.update(
                record_uid="recordUID-{}".format(uts.random_string()),
                source_uid=source_uid,
                username=None,
                firstname=uts.random_name(10),
                lastname=uts.random_name(10),
            )
            fn_csv = self.create_csv_file(person_list=[person], mapping=config["csv"]["mapping"])
            config.update_entry("input:filename", fn_csv)
            fn_config = self.create_config_json(values=config)
            self.run_import(["-c", fn_config], fail_on_preexisting_pyhook=False)
            person.update(username="{}{}".format(person.firstname, person.lastname)[:un_len])
            utils.verify_ldap_object(
                person.dn, expected_attr={"uid": [person.username]}, strict=False, should_exist=True
            )
            self.log.info("*** OK: username %r", person.username)

        self.log.info("OK: import succeeded.")


if __name__ == "__main__":
    Test().run()
