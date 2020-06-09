#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: test diffent username lengths
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [45577, 47222]

import copy

import univention.config_registry
import univention.testing.strings as uts
from ucsschool.importer.utils.configuration_checks import run_configuration_checks
from ucsschool.importer.utils.shell import ImportStudent, ImportTeacher
from ucsschool.lib.models.utils import ucr_username_max_length
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def __init__(self):
        super(Test, self).__init__()
        self.usernames = list()

    def test(self):
        """
        Bug #45577, #47222: allow import with usernames longer than 15 characters
        """
        if self.ucr.get("ucsschool/username/max_length") is not None:
            univention.config_registry.handler_unset(["ucsschool/username/max_length"])

        self.log.info("*** checking installed configuration")
        assert ImportStudent().username_max_length <= ucr_username_max_length - 5
        assert ImportTeacher().username_max_length == ucr_username_max_length

        config = copy.deepcopy(ImportStudent().config)
        config["dry_run"] = True
        config["scheme"] = {
            "username": {"default": "<:umlauts><firstname>[0].<lastname><:lower>[ALWAYSCOUNTER]"}
        }
        config["username"] = {
            "max_length": {"default": ucr_username_max_length, "student": ucr_username_max_length - 5}
        }
        run_configuration_checks(config)
        self.log.info("*** OK: default configuration: %r", config)
        cursor = 0

        for exam_prefix_length in range(3, 10):
            exam_prefix = "{}-".format(uts.random_username(exam_prefix_length - 1))
            self.log.info("*** exam_prefix_length=%r exam_prefix=%r", exam_prefix_length, exam_prefix)
            assert exam_prefix_length == len(exam_prefix)
            univention.config_registry.handler_set(
                ["ucsschool/ldap/default/userprefix/exam={}".format(exam_prefix)]
            )
            max_length_default_range = [None]
            max_length_default_range.extend(range(5, 21))
            for max_length_default in max_length_default_range:
                max_length_student_range = [None]
                max_length_student_range.extend(range(5, 16))
                for max_length_student in max_length_student_range:
                    if max_length_default:
                        config["username"]["max_length"]["default"] = max_length_default
                    if max_length_student:
                        config["username"]["max_length"]["student"] = max_length_student
                    self.log.debug(
                        '***   config["username"]["max_length"]=%r', config["username"]["max_length"]
                    )
                    run_configuration_checks(config)
                    ImportStudent.config = config
                    ImportTeacher.config = config
                    for firstname_length in range(3, 21):
                        firstname = uts.random_username(firstname_length)
                        assert len(firstname) == firstname_length
                        # self.log.debug('***   firstname_length=%r firstname=%r', firstname_length, firstname)
                        for lastname_length in range(3, 21):
                            lastname = uts.random_username(lastname_length)
                            assert len(lastname) == lastname_length
                            student = ImportStudent(
                                name="name", school="school", firstname=firstname, lastname=lastname
                            )
                            student.name = ""
                            student.config = config
                            student.make_username()
                            # self.log.debug(
                            # 	'***   lastname_length=%r lastname=%r student.name=%r len(student.name)=%r',
                            # 	lastname_length, lastname, student.name, len(student.name)
                            # )
                            self.usernames.append(student.name)
                            if len(student.name) > ucr_username_max_length - 5:
                                self.fail(
                                    "Username {!r} of student has length {}.".format(
                                        student.name, len(student.name)
                                    )
                                )
                            firstname = uts.random_username(firstname_length)
                            assert len(firstname) == firstname_length
                            lastname = uts.random_username(lastname_length)
                            assert len(lastname) == lastname_length
                            # self.log.debug('***   firstname_length=%r firstname=%r', firstname_length, firstname)
                            teacher = ImportTeacher(
                                name="name", school="school", firstname=firstname, lastname=lastname
                            )
                            teacher.name = ""
                            teacher.config = config
                            teacher.make_username()
                            # self.log.debug(
                            # 	'***   lastname_length=%r lastname=%r teacher.name=%r len(teacher.name)=%r',
                            # 	lastname_length, lastname, teacher.name, len(teacher.name)
                            # )
                            self.usernames.append(teacher.name)
                            if len(teacher.name) > ucr_username_max_length:
                                self.fail(
                                    "Username {!r} of teacher has length {}.".format(
                                        teacher.name, len(teacher.name)
                                    )
                                )
            self.log.info(
                "*** Tested %d usernames for exam_prefix_length %d...",
                len(self.usernames) - cursor,
                exam_prefix_length,
            )
            cursor = len(self.usernames)
        self.log.info("*** No errors.")
        self.log.info("*** Tested a total of %d usernames.", len(self.usernames))
        self.log.info("*** There were %d duplicates.", len(self.usernames) - len(set(self.usernames)))


if __name__ == "__main__":
    Test().run()
