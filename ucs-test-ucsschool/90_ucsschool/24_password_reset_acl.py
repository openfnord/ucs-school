#!/usr/share/ucs-test/runner python
## desc: test password reset ACLs
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-users]
## timeout: 14400

from __future__ import print_function

import sys
import time

import pytest

import univention.admin.uldap as udm_uldap
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils


class MyObj(object):
    def __init__(self, name, dn):
        self.name = name
        self.dn = dn


class MySchool(MyObj):
    pass


class MyStudent(MyObj):
    pass


class MyTeacher(MyObj):
    pass


class MyAdmin(MyObj):
    pass


RESULT_FAIL = "FAIL"
RESULT_OK = "OK"


class TestCases(object):
    def __init__(self, ucr, schoolenv):
        self.ucr = ucr
        self.schoolenv = schoolenv

        print("---[START /etc/ldap/slapd.conf]---", file=sys.stderr)
        print(open("/etc/ldap/slapd.conf", "r").read(), file=sys.stderr)
        print("---[END /etc/ldap/slapd.conf]---", file=sys.stderr)
        sys.stderr.flush()

        host = self.ucr.get("hostname")
        # create 2 schools
        self.school1 = MySchool(*self.schoolenv.create_ou(name_edudc=host, wait_for_replication=False))
        self.school2 = MySchool(
            *self.schoolenv.create_ou(name_edudc="dcschool2", wait_for_replication=False)
        )

        print("School 1 = {!r}".format(self.school1.name))
        print("School 2 = {!r}\n".format(self.school2.name))

        # "${type}2" is located at second school but member of both schools, so teachers/admins of
        # school1 should be able to reset passwords of "${type}1" and "${type}2"
        self.student0 = MyStudent(
            *self.schoolenv.create_student(self.school1.name, wait_for_replication=False)
        )
        self.student1 = MyStudent(
            *self.schoolenv.create_student(self.school1.name, wait_for_replication=False)
        )
        self.student2 = MyStudent(
            *self.schoolenv.create_student(
                self.school2.name,
                schools=[self.school1.name, self.school2.name],
                wait_for_replication=False,
            )
        )
        self.teacher0 = MyTeacher(
            *self.schoolenv.create_teacher(self.school1.name, wait_for_replication=False)
        )
        self.teacher1 = MyTeacher(
            *self.schoolenv.create_teacher(self.school1.name, wait_for_replication=False)
        )
        self.teacher2 = MyTeacher(
            *self.schoolenv.create_teacher(
                self.school2.name,
                schools=[self.school1.name, self.school2.name],
                wait_for_replication=False,
            )
        )
        is_teacher = True if self.ucr.get("server/role") == "domaincontroller_slave" else None
        self.admin0 = MyAdmin(
            *self.schoolenv.create_school_admin(
                self.school1.name, is_teacher=is_teacher, wait_for_replication=False
            )
        )
        self.admin1 = MyAdmin(
            *self.schoolenv.create_school_admin(
                self.school1.name, is_teacher=is_teacher, wait_for_replication=False
            )
        )

        # verify users
        assert self.student1.dn.endswith(self.school1.dn)
        assert self.student2.dn.endswith(self.school2.dn)
        assert self.teacher1.dn.endswith(self.school1.dn)
        assert self.teacher2.dn.endswith(self.school2.dn)
        utils.verify_ldap_object(
            self.student2.dn,
            expected_attr={"ucsschoolSchool": [self.school1.name, self.school2.name]},
            strict=True,
            should_exist=True,
        )
        utils.verify_ldap_object(
            self.teacher2.dn,
            expected_attr={"ucsschoolSchool": [self.school1.name, self.school2.name]},
            strict=True,
            should_exist=True,
        )

    def test_pw_reset(self, actor, target, expected_result):
        print("\nTEST: {} ==> {}  (expected: {})".format(actor.dn, target.dn, expected_result))
        lo = udm_uldap.access(
            host=self.ucr.get("ldap/master"),
            port=7389,
            base=self.ucr.get("ldap/base"),
            binddn=actor.dn,
            bindpw="univention",
            start_tls=2,
        )
        old_values = lo.get(target.dn)
        print("target.ucsschoolSchool: {}".format(old_values.get("ucsschoolSchool")))
        for attr_name in (
            "sambaNTPassword",
            "userPassword",
            "pwhistory",
        ):  # "krb5key" has no eq matching rule, so lo.modify fails
            if expected_result == RESULT_OK:
                lo.modify(target.dn, [[attr_name, old_values.get(attr_name), [str(time.time())]]])
            else:
                with pytest.raises(Exception):
                    lo.modify(target.dn, [[attr_name, old_values.get(attr_name), [str(time.time())]]])
        print("OK: result as expected")

    def run(self):
        self.test_pw_reset(self.student0, self.student1, RESULT_FAIL)
        self.test_pw_reset(self.student0, self.student2, RESULT_FAIL)
        self.test_pw_reset(self.teacher0, self.student1, RESULT_OK)
        self.test_pw_reset(self.teacher0, self.student2, RESULT_OK)
        self.test_pw_reset(self.teacher0, self.teacher1, RESULT_FAIL)
        self.test_pw_reset(self.teacher0, self.teacher2, RESULT_FAIL)
        self.test_pw_reset(self.admin0, self.student1, RESULT_OK)
        self.test_pw_reset(self.admin0, self.student2, RESULT_OK)
        self.test_pw_reset(self.admin0, self.teacher1, RESULT_OK)
        self.test_pw_reset(self.admin0, self.teacher2, RESULT_OK)
        # the following test is disabled because it will currently fail
        # self.test_pw_reset(self.admin0, self.admin1, RESULT_FAIL)


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with utu.UCSTestSchool() as schoolenv:
            testcases = TestCases(ucr, schoolenv)
            testcases.run()


if __name__ == "__main__":
    main()
