#!/usr/share/ucs-test/runner python
# -*- coding: utf-8 -*-
## desc: Check if school admins have at least the required LDAP permissions for UCS@school
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-ldap-acls-master]

from ldap.filter import filter_format

import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.udm as udm_test
from univention.testing.strings import random_string
from univention.testing.ucsschool.acl import Acl
from univention.testing.ucsschool.computerroom import Computers
from univention.testing.ucsschool.schoolroom import ComputerRoom


def main():
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            name_edudc = random_string(length=5)
            school, oudn = schoolenv.create_ou(name_edudc=name_edudc)
            school_admin, school_admin_dn = schoolenv.create_school_admin(
                school, is_staff=False, is_teacher=True
            )

            with udm_test.UCSTestUDM():
                replication_node_dn = "cn={},cn=dc,cn=server,cn=computers,ou={},{}".format(
                    name_edudc, school, ucr.get("ldap/base", "")
                )
                acl_replication_node = Acl(school, school_admin_dn, "DENIED")
                acl_replication_node.assert_acl(
                    replication_node_dn,
                    "write",
                    [
                        "krb5KeyVersionNumber",
                        "krb5KDCFlags",
                        "krb5Key",
                        "krb5PasswordEnd",
                        "sambaAcctFlags",
                        "sambaPwdLastSet",
                        "sambaLMPassword",
                        "sambaNTPassword",
                        "shadowLastChange",
                        "shadowMax",
                        "userPassword",
                        "pwhistory",
                        "sambaPwdCanChange",
                        "sambaPwdMustChange",
                        "sambaPasswordHistory",
                        "sambaBadPasswordCount",
                    ],
                )

            staff, staff_dn = schoolenv.create_staff(school)
            tea_staff, tea_staff_dn = schoolenv.create_teacher_and_staff(school)
            tea, tea_dn = schoolenv.create_teacher(school)
            stu, stu_dn = schoolenv.create_student(school)
            class_name, class_dn = schoolenv.create_school_class(school)

            open_ldap_co = schoolenv.open_ldap_connection()
            # importing 2 random computers
            computers = Computers(open_ldap_co, school, 1, 0, 0)
            created_computers = computers.create()
            computers_dns = computers.get_dns(created_computers)
            computers_hostnames = computers.get_hostnames(created_computers)
            computers_hostnames = [x[:-1] for x in computers_hostnames]

            room = ComputerRoom(school, host_members=computers_dns)
            room.add()

            acl = Acl(school, school_admin_dn, "ALLOWED")

            acl.assert_base_dn("read")

            # moved to "75_ldap_acls_specific_tests"
            # acl.assert_student(stu_dn, 'write')
            # acl.assert_user(tea_dn, 'write')
            # acl.assert_user(staff_dn, 'write')
            # acl.assert_user(tea_staff_dn, 'write')

            acl.assert_room(room.dn(), "write")

            acl.assert_teacher_group("write")
            acl.assert_student_group("write")

            shares_dn = "cn=shares,%s" % utu.UCSTestSchool().get_ou_base_dn(school)
            acl.assert_shares(shares_dn, "read")
            shares_dn = "cn=Marktplatz,cn=shares,%s" % utu.UCSTestSchool().get_ou_base_dn(school)
            acl.assert_shares(shares_dn, "read")
            shares_dn = "cn=klassen,cn=shares,%s" % utu.UCSTestSchool().get_ou_base_dn(school)
            acl.assert_shares(shares_dn, "read")

            acl.assert_temps("write")
            acl.assert_gid_temps("write")

            acl.assert_computers(computers_dns[0], "write")

            acl.assert_dhcp(computers_hostnames[0], "read")
            acl.assert_dhcp(computers_hostnames[0], "write", modify_only_attrs=True)

            #  Deactivated on purpose (Bug #42138)
            #  acl.assert_member_server("write")

            acl.assert_ou("read")

            acl.assert_global_containers("read")

            # Bug #41720
            share_dn = open_ldap_co.searchDn(
                filter=filter_format("(&(objectClass=univentionShare)(cn=%s))", (class_name,))
            )[0]
            acl.assert_share_object_access(share_dn, "read", "ALLOWED")
            acl.assert_share_object_access(share_dn, "write", "DENIED")
            # disabled on purpose - see Bug #42065
            # share_dn = 'cn=Marktplatz,cn=shares,%s' % (oudn,)
            # acl.assert_share_object_access(share_dn, 'read', 'ALLOWED')
            # acl.assert_share_object_access(share_dn, 'write', 'DENIED')


if __name__ == "__main__":
    main()
