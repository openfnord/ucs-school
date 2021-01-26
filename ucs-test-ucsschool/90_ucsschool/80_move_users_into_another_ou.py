#!/usr/share/ucs-test/runner python3
## desc: move user into another school
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool,ucsschool_base1]
## bugs: [40870, 41601, 41609, 41620, 41910]
## exposure: dangerous

from __future__ import print_function

import functools
import os.path

import univention.config_registry
import univention.testing.strings as uts
from ucsschool.lib.models import SchoolClass, User, WorkGroup
from univention.testing import utils
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.ucsschool.ucs_test_school import UCSTestSchool, get_ucsschool_logger
from univention.testing.udm import UCSTestUDM

logger = get_ucsschool_logger()


def verify_user_move(lo, b, user, attrs, workgroup_dn, groups, oldinfo, grp1_name, grp2_name):
    user = User.from_dn(user.dn, None, lo)
    print("*** Groups {} is in: {}".format(user, user.get_udm_object(lo)["groups"]))
    workgroup = WorkGroup.from_dn(workgroup_dn, None, lo)
    if user.dn in workgroup.users:
        print("*** Users in workgroup {}: {}".format(workgroup.name, workgroup.users))
        utils.fail("User %r was not removed from workgroup." % user)
    try:
        utils.verify_ldap_object(
            user.dn, expected_attr=attrs, strict=True, should_exist=True, retry_count=0
        )
    except utils.LDAPObjectValueMissing:
        info = user.get_udm_object(lo).info
        print("FAIL1: %r;\noldinfo=%r\ninfo=%r" % (user.dn, oldinfo, info))
        print("FAIL2: %r; attrs=%r" % (user.dn, lo.get(user.dn)))
        raise

    assert set(groups) == set(
        user.get_udm_object(lo)["groups"]
    ), "Moving the user %r failed... Expected groups %r != %r" % (
        user,
        groups,
        user.get_udm_object(lo)["groups"],
    )
    assert "{}-{}".format(b, grp1_name) not in [
        sc.name for sc in SchoolClass.get_all(lo, b)
    ], 'Old school class "{}" was created in target school.'.format(grp1_name)
    assert "{}-{}".format(b, grp2_name) not in [
        sc.name for sc in SchoolClass.get_all(lo, b)
    ], 'Old school class "{}" was created in target school.'.format(grp2_name)


def main():
    if not hasattr(User, "change_school"):
        utils.fail("ERROR: moving users to another school OU is not supported by ucs-school-lib")

    with UCSTestSchool() as env, UCSTestConfigRegistry() as ucr, UCSTestUDM() as udm:
        # make sure that nonedu containers are created
        univention.config_registry.handler_set(["ucsschool/ldap/noneducational/create/objects=yes"])

        (a, a_dn), (b, b_dn) = env.create_multiple_ous(2, name_edudc=ucr.get("hostname"))

        # TODO: add exam user
        # TODO: change school and uid at once!
        # TODO: user without classes

        base = ucr["ldap/base"]
        domain_users_school = "cn=Domain Users %s,cn=groups,ou=%s,%s" % (b, b, base)
        teacher_group = "cn=lehrer-%s,cn=groups,ou=%s,%s" % (b, b, base)
        staff_group = "cn=mitarbeiter-%s,cn=groups,ou=%s,%s" % (b, b, base)
        students_group = "cn=schueler-%s,cn=groups,ou=%s,%s" % (b, b, base)
        grp1_name = uts.random_username()
        grp2_name = uts.random_username()
        two_klasses = "{0}-{1},{0}-{2}".format(a, grp1_name, grp2_name)
        group_name = "{}-{}".format(a, uts.random_username())
        workgroup_dn, workgroup_name = udm.create_group(
            position="cn=schueler,cn=groups,%s" % (a_dn,), name=group_name
        )
        global_group_dn, global_group_name = udm.create_group()

        users = [
            (
                env.create_user(a, classes=two_klasses),
                "schueler",
                [students_group, domain_users_school, global_group_dn],
            ),
            (
                env.create_user(a, is_teacher=True, classes=two_klasses),
                "lehrer",
                [domain_users_school, teacher_group, global_group_dn],
            ),
            (
                env.create_user(a, is_staff=True),
                "mitarbeiter",
                [domain_users_school, staff_group, global_group_dn],
            ),
            (
                env.create_user(a, is_teacher=True, is_staff=True, classes=two_klasses),
                "lehrer",
                [domain_users_school, teacher_group, staff_group, global_group_dn],
            ),
        ]
        lo = env.open_ldap_connection()
        workgroup = WorkGroup.from_dn(workgroup_dn, None, lo)
        users_dns = [dn for (user, dn), roleshare_path, groups in users]
        udm.modify_object("groups/group", dn=global_group_dn, append={"users": users_dns})
        workgroup.users.extend(users_dns)
        workgroup.modify(lo)
        workgroup = WorkGroup.from_dn(workgroup_dn, None, lo)
        print("*** Users in workgroup {}: {}".format(workgroup.name, workgroup.users))

        for (user, dn), roleshare_path, groups in users:
            user = User.from_dn(dn, None, lo)
            print("*** Groups {} is in: {}".format(user, user.get_udm_object(lo)["groups"]))

            print("################################")
            print("#### moving user at", dn, "to", b)
            print("################################")

            attrs = {
                "homeDirectory": [os.path.join("/home", b, roleshare_path, user.name)],
                "ucsschoolSchool": [b],
                "departmentNumber": [b],
                # TODO: add sambaHomeDrive sambaHomePath sambaLogonScript sambaProfilePath
            }
            oldinfo = user.get_udm_object(lo).info
            if oldinfo.get("departmentNumber") != [a]:
                attrs.pop("departmentNumber")

            user.change_school(b, lo)
            assert user.dn != dn
            assert b in user.dn
            udm.wait_for("users/user", user.dn, everything=True)
            udm.wait_for("groups/group", global_group_dn, everything=True)
            utils.retry_on_error(
                functools.partial(
                    verify_user_move,
                    lo,
                    b,
                    user,
                    attrs,
                    workgroup_dn,
                    groups,
                    oldinfo,
                    grp1_name,
                    grp2_name,
                ),
                exceptions=(Exception,),
                retry_count=50,
                delay=4,
            )


if __name__ == "__main__":
    main()
