#!/usr/share/ucs-test/runner pytest-3 -s -l -v
# -*- coding: utf-8 -*-
## desc: Check if edu slaves have at least the required LDAP permissions for UCS@school
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-ldap-acls-master]
## bugs: [41818,48924]

import attr
from ldap.filter import filter_format

from univention.testing.ucsschool.acl import Acl


@attr.s
class DCObj(object):
    name = attr.ib()
    dn = attr.ib()


@attr.s
class OUObj(object):
    name = attr.ib()
    dn = attr.ib()
    edu_server = attr.ib()
    admin_server = attr.ib()


def test_ldap_acls_edu_server(schoolenv, ucr):
            schools = []
            for i in range(2):
                name_edudc = "e-myschool{}".format(i)
                name_admindc = "a-myschool{}".format(i)
                name, dn = schoolenv.create_ou(
                    ou_name="myschool{}".format(i), name_edudc=name_edudc, name_admindc=name_admindc
                )
                school = OUObj(name, dn, None, None)
                school.edu_server = DCObj(
                    name_edudc, "cn={},cn=dc,cn=server,cn=computers,{}".format(name_edudc, school.dn)
                )
                school.admin_server = DCObj(
                    name_admindc, "cn={},cn=dc,cn=server,cn=computers,{}".format(name_admindc, school.dn)
                )
                schools.append(school)

            staff_dn = schoolenv.create_user(
                ou_name=schools[0].name, schools=[schools[0].name, schools[1].name], is_staff=True
            )[1]
            teastaff_dn = schoolenv.create_user(
                ou_name=schools[0].name,
                schools=[schools[0].name, schools[1].name],
                is_teacher=True,
                is_staff=True,
            )[1]
            tea_dn = schoolenv.create_user(
                ou_name=schools[0].name, schools=[schools[0].name, schools[1].name], is_teacher=True
            )[1]
            stu_dn = schoolenv.create_user(
                ou_name=schools[0].name, schools=[schools[0].name, schools[1].name]
            )[1]
            lo = schoolenv.open_ldap_connection()

            # check if DC on school DC is correct
            for school in schools:
                try:
                    dn = lo.searchDn(
                        filter=filter_format(
                            "(&(objectClass=univentionHost)(cn=%s))", (school.edu_server.name,)
                        )
                    )[0]
                except IndexError:
                    print(
                        "\n\nERROR: Looks like the edu domaincontroller {} does not exist in "
                        "LDAP\n\n".format(school.edu_server.dn)
                    )
                    raise
                if school.edu_server.dn != dn:
                    raise Exception(
                        "Looks like the edu domaincontroller dn {} does not match expected DN "
                        "{}\n\n".format(dn, school.edu_server.dn)
                    )

                # Bug 41818: administrative school server can only replicate staff users and
                # teacher-staff users
                acl = Acl(school.name, school.edu_server.dn, "ALLOWED")
                # following attribute list is incomplete, but gives a rough idea if replication of this
                # user is allowed
                attr_list = [
                    "uid",
                    "givenName",
                    "sn",
                    "uidNumber",
                    "userPassword",
                    "sambaHomePath",
                    "gidNumber",
                    "krb5Key",
                    "sambaSID",
                ]
                for user_dn, allowance in (
                    (staff_dn, "DENIED"),
                    (teastaff_dn, "ALLOWED"),
                    (tea_dn, "ALLOWED"),
                    (stu_dn, "ALLOWED"),
                ):
                    acl.assert_acl(user_dn, "read", attr_list, allowance)
