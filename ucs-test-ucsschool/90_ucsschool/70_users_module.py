#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Users(schools) module
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-wizards]

from copy import deepcopy

from ldap.filter import filter_format

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.decorators import SetTimeout
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.klasse import Klasse
from univention.testing.ucsschool.user import User
from univention.testing.umc import Client

# this test fails every now and then, lets see if more waiting helps
utils.verify_ldap_object = SetTimeout(utils.verify_ldap_object_orig, 50)


def test(student_classes, teacher_classes, schools, ucr, remove_from_school=None, connection=None):
    print("\n>>>> Creating 4 users...\n")
    users = []

    user = User(
        school=schools[0],
        role="student",
        school_classes=deepcopy(student_classes),
        schools=schools,
        connection=connection,
    )
    user.create()
    user.verify()
    user.check_get()
    users.append(user)

    user = User(
        school=schools[0],
        role="teacher",
        school_classes=deepcopy(teacher_classes),
        schools=schools,
        connection=connection,
    )
    user.create()
    user.verify()
    user.check_get()
    users.append(user)

    user = User(
        school=schools[0], role="staff", school_classes={}, schools=schools, connection=connection
    )
    user.create()
    user.verify()
    user.check_get()
    users.append(user)

    user = User(
        school=schools[0],
        role="teacher_staff",
        school_classes=deepcopy(teacher_classes),
        schools=schools,
        connection=connection,
    )
    user.create()
    user.verify()
    user.check_get()
    users.append(user)

    users[0].check_query([users[0].dn, users[1].dn])

    print("\n>>>> Editing and removing (remove_from_school=%r) 4 users...\n" % (remove_from_school,))
    for num, user in enumerate(users):
        new_attrs = {
            "email": "%s@%s" % (uts.random_name(), ucr.get("domainname")),
            "firstname": "first_name%d" % num,
            "lastname": "last_name%d" % num,
        }
        user.edit(new_attrs)
        wait_for_drs_replication(filter_format("cn=%s", (user.username,)))
        user.check_get(expected_attrs=new_attrs)
        user.verify()
        school_classes = deepcopy(user.school_classes)
        try:
            school_classes.pop(remove_from_school)
        except KeyError:
            pass
        user.remove(remove_from_school)
        # importusers expects that the class groups are moved as well as the user during a school change
        # schoolwizard does not do that -> reset the school classes that got modified during the school move
        # see bug #47208
        user.school_classes = school_classes
        utils.wait_for_replication()
        user.verify()

    return users


def main():
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            umc_connection = Client.get_test_connection(ucr.get("ldap/master"))
            (ou, oudn), (ou2, oudn2) = schoolenv.create_multiple_ous(2, name_edudc=ucr.get("hostname"))
            class_01 = Klasse(school=ou, connection=umc_connection)
            class_01.create()
            class_01.verify()
            class_02 = Klasse(school=ou, connection=umc_connection)
            class_02.create()
            class_02.verify()
            student_classes = {ou: ["%s-%s" % (ou, class_01.name)]}
            teacher_classes = {ou: ["%s-%s" % (ou, class_01.name), "%s-%s" % (ou, class_02.name)]}

            print("\n>>>> Testing module with users in 1 OU ({}).\n".format(ou))
            test(student_classes, teacher_classes, [ou], ucr, ou, connection=umc_connection)

            class_03 = Klasse(school=ou2, connection=umc_connection)
            class_03.create()
            class_03.verify()
            student_classes = {
                ou: ["%s-%s" % (ou, class_01.name)],
                ou2: ["%s-%s" % (ou2, class_03.name)],
            }
            teacher_classes = {
                ou: ["%s-%s" % (ou, class_01.name), "%s-%s" % (ou, class_02.name)],
                ou2: ["%s-%s" % (ou2, class_03.name)],
            }

            print(
                "\n>>>> Testing module with users in 2 OUs (primary: {} secondary: {}).".format(ou, ou2)
            )
            print(">>>> Removing user from primary OU first.\n")
            users = test(student_classes, teacher_classes, [ou, ou2], ucr, ou, connection=umc_connection)

            for user in users:
                print(user.username, user.role, user.school, user.schools)
                wait_for_drs_replication(filter_format("cn=%s", (user.username,)))
                user.get()
                user.verify()
                user.remove()
                wait_for_drs_replication(filter_format("cn=%s", (user.username,)), should_exist=False)
                utils.wait_for_replication()
                user.verify()

            print(
                "\n>>>> Testing module with users in 2 OUs (primary: {} secondary: {}).".format(ou, ou2)
            )
            print(">>>> Removing user from secondary OU first.\n")
            users = test(
                student_classes, teacher_classes, [ou, ou2], ucr, ou2, connection=umc_connection
            )

            for user in users:
                wait_for_drs_replication(filter_format("cn=%s", (user.username,)))
                user.get()
                user.verify()
                user.remove()
                utils.wait_for_replication()
                wait_for_drs_replication(filter_format("cn=%s", (user.username,)), should_exist=False)
                user.verify()


if __name__ == "__main__":
    main()
