#!/usr/share/ucs-test/runner python
## desc: ucs-school-reset-password-check
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-users]

from __future__ import print_function

import sys

import pytest

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.lib.umc import Forbidden, HTTPError
from univention.testing.umc import Client


def auth(host, username, password):
    try:
        client = Client(host)
        return client.authenticate(username, password)
    except HTTPError as exc:
        return exc.response


def test_pwd_reset(
    host,
    acting_user,
    flavor,
    target_user,
    target_userdn,
    chg_pwd_on_next_login,
    expected_reset_result,
    expected_auth_for_old_password,
    expected_auth_for_new_password,
    expect_password_expired=False,
):
    newpassword = uts.random_string()
    options = {"userDN": target_userdn, "newPassword": newpassword, "nextLogin": chg_pwd_on_next_login}
    client = Client(host, acting_user, "univention")

    def reset():
        try:
            return client.umc_command("schoolusers/password/reset", options, flavor).result
        finally:
            utils.wait_for_replication()
            utils.wait_for_connector_replication()

    if isinstance(expected_reset_result, type) and issubclass(expected_reset_result, Exception):
        with pytest.raises(expected_reset_result):
            reset()
    else:
        assert (
            reset() == expected_reset_result
        ), "umcp command schoolusers/password/reset was unexpectedly successful"

    # test if old password does NOT work
    auth_response = auth(host, target_user, "univention")
    if auth_response.status != expected_auth_for_old_password:
        utils.fail(
            "old password: unexpected authentication result=%s, expected=%s"
            % (auth_response.status, expected_auth_for_old_password)
        )

    # test if new password does work
    auth_response = auth(host, target_user, newpassword)
    if auth_response.status != expected_auth_for_new_password:
        utils.fail(
            "new password: unexpected authentication result=%s, expected=%s"
            % (auth_response.status, expected_auth_for_new_password)
        )

    if expect_password_expired:
        assert auth_response.result.get("password_expired"), "The password is not expired - as expected."


def main():
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()
    host = ucr.get("hostname")
    with utu.UCSTestSchool() as schoolenv:
        schoolName, oudn = schoolenv.create_ou(name_edudc=host)
        teachers = []
        teachersDn = []
        students = []
        studentsDn = []
        admins = []
        adminsDn = []
        for i in [0, 1, 2]:
            tea, teadn = schoolenv.create_user(schoolName, is_teacher=True)
            teachers.append(tea)
            teachersDn.append(teadn)
            stu, studn = schoolenv.create_user(schoolName)
            students.append(stu)
            studentsDn.append(studn)
            is_teacher = True if ucr.get("server/role") == "domaincontroller_slave" else None
            admin, admin_dn = schoolenv.create_school_admin(schoolName, is_teacher=is_teacher)
            admins.append(admin)
            adminsDn.append(admin_dn)

        utils.wait_for_replication_and_postrun()

        print("#1 test if teacher is unable to reset teacher password (chgPwdNextLogin=True)")
        test_pwd_reset(
            host, teachers[0], "teacher", teachers[1], teachersDn[1], True, Forbidden, 200, 401
        )

        print("#2 test if student is unable to reset teacher password (chgPwdNextLogin=True)")
        test_pwd_reset(
            host, students[0], "teacher", teachers[1], teachersDn[1], True, Forbidden, 200, 401
        )

        print("#3 test if student is unable to reset student password (chgPwdNextLogin=True)")
        test_pwd_reset(
            host, students[0], "student", students[1], studentsDn[1], True, Forbidden, 200, 401
        )

        print("#4 test if teacher is unable to reset teacher password (chgPwdNextLogin=False)")
        test_pwd_reset(
            host, teachers[0], "teacher", teachers[1], teachersDn[1], False, Forbidden, 200, 401
        )

        print("#5 test if student is unable to reset teacher password (chgPwdNextLogin=False)")
        test_pwd_reset(
            host, students[0], "teacher", teachers[1], teachersDn[1], False, Forbidden, 200, 401
        )

        print("#6 test if student is unable to reset student password (chgPwdNextLogin=False)")
        test_pwd_reset(
            host, students[0], "student", students[1], studentsDn[1], False, Forbidden, 200, 401
        )

        print("#7 test if teacher is able to reset student password (chgPwdNextLogin=True)")
        test_pwd_reset(
            host, teachers[0], "student", students[1], studentsDn[1], True, True, 401, 401, True
        )

        print("#8 test if teacher is able to reset student password (chgPwdNextLogin=False)")
        test_pwd_reset(host, teachers[0], "student", students[0], studentsDn[0], False, True, 401, 200)

        print("#9 test if schooladmin is able to reset student password (chgPwdNextLogin=False)")
        test_pwd_reset(host, admins[0], "student", students[0], studentsDn[0], False, True, 401, 200)

        print("#10 test if schooladmin is able to reset student password (chgPwdNextLogin=True)")
        test_pwd_reset(host, admins[0], "student", students[2], studentsDn[2], True, True, 401, 401)

        print("#11 test if schooladmin is able to reset teacher password (chgPwdNextLogin=False)")
        test_pwd_reset(host, admins[0], "student", teachers[0], teachersDn[0], False, True, 401, 200)

        print("#12 test if schooladmin is able to reset teacher password (chgPwdNextLogin=True)")
        test_pwd_reset(host, admins[0], "student", teachers[1], teachersDn[1], True, True, 401, 401)


# DISABLED DUE TO BUG 35447
# 		print '#13 test if schooladmin is able to reset admin password (chgPwdNextLogin=False)'
# 		test_pwd_reset(host, admins[0], 'student', admins[1], adminsDn[1], False, Forbidden, 200, 401)

# 		print '#14 test if schooladmin is able to reset admin password (chgPwdNextLogin=True)'
# 		test_pwd_reset(host, admins[0], 'student', admins[2], adminsDn[2], True, Forbidden, 200, 401)


if __name__ == "__main__":
    sys.exit(main())
