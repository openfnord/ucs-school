#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: UDM hook prevents creating and modifying user objects with forbidden option combinations
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [41351]

import univention.testing.strings as uts
import univention.testing.ucr
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.udm as udm_test
import univention.testing.utils as utils
from ucsschool.lib.models import ExamStudent, Staff, Student, Teacher, TeachersAndStaff
from ucsschool.lib.roles import create_ucsschool_role_string
from univention.admin.uexceptions import invalidOptions
from univention.testing.udm import UCSTestUDM_CreateUDMObjectFailed

blacklisted_option_combinations = {
    "ucsschoolAdministrator": {"ucsschoolExam", "ucsschoolStudent"},
    "ucsschoolExam": {"ucsschoolAdministrator", "ucsschoolStaff", "ucsschoolTeacher"},
    "ucsschoolStaff": {"ucsschoolExam", "ucsschoolStudent"},
    "ucsschoolStudent": {"ucsschoolAdministrator", "ucsschoolStaff", "ucsschoolTeacher"},
    "ucsschoolTeacher": {"ucsschoolExam", "ucsschoolStudent"},
}


def main():
    print("*** Testing creation...\n*")
    with univention.testing.ucr.UCSTestConfigRegistry() as ucr:
        with udm_test.UCSTestUDM() as udm:
            for kls, bad_options in blacklisted_option_combinations.items():
                for bad_option in bad_options:
                    try:
                        udm.create_user(options=[kls, bad_option])
                        utils.fail("Created {} with {}.".format(kls, bad_option))
                    except UCSTestUDM_CreateUDMObjectFailed as exc:
                        print("OK: caught expected exception: %s" % exc)

        print("*\n*** Testing modification...\n*")
        with utu.UCSTestSchool() as schoolenv:
            ou_name, ou_dn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))
            lo = schoolenv.open_ldap_connection(admin=True)
            for kls, ldap_cls in [
                (ExamStudent, "ucsschoolExam"),
                (Staff, "ucsschoolStaff"),
                (Student, "ucsschoolStudent"),
                (Teacher, "ucsschoolTeacher"),
                (TeachersAndStaff, "ucsschoolAdministrator"),
            ]:
                for bad_option in blacklisted_option_combinations[ldap_cls]:
                    print(
                        "*** Creating {} and trying to add option {}...".format(
                            kls.type_name, bad_option
                        )
                    )
                    user = kls(
                        name=uts.random_username(),
                        school=ou_name,
                        firstname=uts.random_name(),
                        lastname=uts.random_name(),
                    )
                    user.create(lo)
                    utils.verify_ldap_object(
                        user.dn,
                        expected_attr={
                            "uid": [user.name],
                            "ucsschoolRole": [
                                create_ucsschool_role_string(role, ou_name)
                                for role in user.default_roles
                            ],
                        },
                        strict=False,
                        should_exist=True,
                    )

                    udm_user = user.get_udm_object(lo)
                    udm_user.options.append(bad_option)
                    try:
                        udm_user.modify(lo)
                        utils.fail("Added {} to {}.".format(bad_option, kls.type_name))
                    except invalidOptions as exc:
                        print("OK: caught expected exception: %s" % exc)
                    user.remove(lo)

    print("*\n*** Test was successful.\n*")


if __name__ == "__main__":
    main()
