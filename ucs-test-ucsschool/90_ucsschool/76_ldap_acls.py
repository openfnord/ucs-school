#!/usr/share/ucs-test/runner pytest-3 -s -l -v
# -*- coding: utf-8 -*-
## desc: ucs-school-ldap-acls
## roles: [domaincontroller_master]
## versions:
##  4.0-0: skip
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-ldap-acls-master]

from __future__ import print_function

from univention.testing.ucsschool.acl import run_commands
from univention.testing.ucsschool.computer import Computers
from univention.testing.ucsschool.schoolroom import ComputerRoom
from univention.uldap import getMachineConnection


class Attributes(object):
    base = [
        "entry",
        "children",
        "dc",
        "univentionObjectType",
        "krb5RealmName",
        "nisDomain",
        "associatedDomain",
        "univentionPolicyReference",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "objectClass",
        "msGPOLink",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    container = [
        "children",
        "entry",
    ]
    room = [
        "entry",
        "children",
        "sambaGroupType",
        "cn",
        "objectClass",
        "univentionObjectType",
        "gidNumber",
        "sambaSID",
        "univentionGroupType",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
        "hasSubordinates",
        "entryDN",
        "subschemaSubentry",
    ]
    tea_stu_groups = [
        "objectClass",
        "univentionObjectType",
        "cn",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    tea_stu_groups_tree = [
        "entry",
        "children",
        "objectClass",
        "univentionObjectType",
        "cn",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    tea_stu = [
        "sambaGroupType",
        "cn",
        "description",
        "objectClass",
        "memberUid",
        "univentionObjectType",
        "gidNumber",
        "sambaSID",
        "uniqueMember",
        "univentionGroupType",
    ]
    gid_temp = ["children", "entry", "univentionLastUsedValue"]
    temp_tree = [
        "children",
        "entry",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
        "entryDN",
        "subschemaSubentry",
        "hasSubordinates",
    ]
    temp = [
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
        "entryDN",
        "subschemaSubentry",
        "hasSubordinates",
    ]
    ou = [
        "entry",
        "children",
        "ou",
        "displayName",
        "univentionObjectType",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "ucsschoolHomeShareFileServer",
        "ucsschoolClassShareFileServer",
        "univentionPolicyReference",
        "objectClass",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    global_containers = [
        "objectClass",
        "univentionObjectType",
        "description",
        "cn",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    global_containers_tree = [
        "entry",
        "children",
        "objectClass",
        "univentionObjectType",
        "description",
        "cn",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    computer = ["macAddress", "sambaNTPassword"]
    user = [
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
    ]
    shares = [
        "objectClass",
        "univentionObjectType",
        "cn",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    dhcp = [
        "entry",
        "children",
        "objectClass",
        "univentionObjectType",
        "dhcpOption",
        "cn",
        "structuralObjectClass",
        "entryUUID",
        "creatorsName",
        "createTimestamp",
        "entryCSN",
        "modifiersName",
        "modifyTimestamp",
    ]
    member_server = [
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
    ]


class Access(object):
    Read = "read"
    Write = "write"
    none = "none"
    Allowed = "ALLOWED"
    Denied = "DENIED"


class LDAPACLTestMatrix(object):
    def __init__(self, auth_dn, default):
        self.auth_dn = auth_dn
        self.default = default
        self.matrix = {}

    def assert_acl(self, target_dn, access, attr, access_allowance=None):
        """
        Test ACL rule:\n
        :param target_dn: Target dn to test access to
        :type target_dn: ldap object dn
        :param attrs: names of the attributes to test acl against
        :type attrs: list of str
        :param access: type of access
        :type access: str=Access.Read Access.Write or Access.none
        """
        access_allowance = access_allowance if access_allowance else Access.Allowed
        # print('\n * Authdn = %s\n * Targetdn = %s\n * Attribute = %s\n * Access = %s' % (
        #       self.auth_dn, target_dn, attr, access))
        cmd = [
            "slapacl",
            "-f",
            "/etc/ldap/slapd.conf",
            "-D",
            "%(auth_dn)s",
            "-b",
            "%(target_dn)s",
            "%(attr)s/%(access)s",
            "-d",
            "0",
        ]
        argdict = {"auth_dn": self.auth_dn, "target_dn": target_dn, "access": access, "attr": attr}
        out, err = run_commands([cmd], argdict)[0]
        if err:
            result = [x for x in err.split("\n") if (Access.Allowed in x or Access.Denied in x)][0]
            if result:
                if access_allowance not in result:
                    return False
                else:
                    return True
        else:
            assert False, "command %r was not executed successfully" % cmd

    def walkThroughContainer(self, base):
        lo = getMachineConnection()
        for container in lo.search(base=base, attr=["*", "+"]):
            yield container

    def get_all_attributes_as_dict(self, base):
        """
        return {
            dn1: [attibute1, attribute2, ..],
            dn2: [attibute1, attribute2, ..],
            ..
        }
        """
        containers = list(self.walkThroughContainer(base))
        return dict([(y, [k for k in x]) for y, x in containers])

    def gather_attributes_as_set(self, base_list):
        result = {"children", "entry"}
        for base in base_list:
            containers = list(self.walkThroughContainer(base))
            s = set([u for x, y in containers for u in y])
            result = result | s
        return result

    def run(self, base_list):
        attrs = self.gather_attributes_as_set(base_list)
        for base in base_list:
            containers = self.walkThroughContainer(base)
            for target_dn, _ in containers:
                for attr in attrs:
                    access = Access.none
                    if self.assert_acl(target_dn, Access.Write, attr):
                        access = Access.Write
                    elif self.assert_acl(target_dn, Access.Read, attr):
                        access = Access.Read
                    expected_access = self.get_attribute_access(target_dn, attr)
                    if access != expected_access:
                        print(
                            '\nDIFFER= User="%s", tried to access Object="%s", Attr="%s",'
                            ' expected="%s", result="%s"'
                            % (self.auth_dn, target_dn, attr, expected_access, access)
                        )
                    else:
                        print(
                            'SAME= User="%s", tried to access Object="%s", Attr="%s", expected="%s",'
                            ' result="%s"' % (self.auth_dn, target_dn, attr, expected_access, access)
                        )

    def get_attribute_access(self, target_dn, attr):
        if target_dn in self.matrix:
            return self.matrix[target_dn].get(attr, self.default)
        else:
            return self.default

    def addDn(self, target_dn, attrs, access=Access.none):
        print("adding target_dn= %s" % (target_dn,))
        for attr in attrs:
            print("\tattr= %s,\taccess= %s" % (attr, access))
            self.matrix.setdefault(target_dn, {})[attr] = access
        print()

    def addSubtree(self, container, attrs, access=Access.none):
        for target_dn, _ in self.walkThroughContainer(container):
            self.addDn(target_dn, attrs, access)

    def add_staff_target_dns(self, dn_access_list):
        for (add_type, dn, attrs, access) in dn_access_list:
            if add_type == 0:
                self.addDn(dn, attrs, access)
            else:
                self.addSubtree(dn, attrs, access)


def test_ldap_acls(schoolenv, ucr):
    base_dn = ucr.get("ldap/base")
    school, school_dn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))

    tea, tea_dn = schoolenv.create_user(school, is_teacher=True)
    schoolenv.create_user(school, is_teacher=True, is_staff=True)
    schoolenv.create_user(school, is_staff=True)
    stu, stu_dn = schoolenv.create_user(school)
    schoolenv.create_school_admin(school)

    open_ldap_co = schoolenv.open_ldap_connection()
    # importing 2 random computers
    computers = Computers(open_ldap_co, school, 1, 0, 0)
    created_computers = computers.create()
    computers_dns = computers.get_dns(created_computers)
    room = ComputerRoom(school, host_members=computers_dns)
    room.add()

    room_container_dn = "cn=raeume,cn=groups,%s" % school_dn
    gid_temp_dn = "cn=gid,cn=temporary,cn=univention,%s" % base_dn
    gidNumber_temp_dn = "cn=gidNumber,cn=temporary,cn=univention,%s" % base_dn
    sid_temp_dn = "cn=sid,cn=temporary,cn=univention,%s" % base_dn
    groupName_temp_dn = "cn=groupName,cn=temporary,cn=univention,%s" % base_dn
    mac_temp_dn = "cn=mac,cn=temporary,cn=univention,%s" % base_dn

    global_univention_dn = "cn=univention,%s" % base_dn
    global_policies_dn = "cn=policies,%s" % base_dn
    global_dns_dn = "cn=dns,%s" % base_dn
    global_groups_dn = "cn=groups,%s" % base_dn

    staff_dn_access_list = [
        # 0 for base, 1 for subtree
        (0, stu_dn, Attributes.user, Access.Write),
        (0, room_container_dn, Attributes.container, Access.Write),
        (0, room.dn(), Attributes.room, Access.Write),
        (1, gid_temp_dn, Attributes.temp_tree, Access.Write),
        (1, gidNumber_temp_dn, Attributes.temp_tree, Access.Write),
        (1, sid_temp_dn, Attributes.temp_tree, Access.Write),
        (1, groupName_temp_dn, Attributes.temp_tree, Access.Write),
        (1, mac_temp_dn, Attributes.temp_tree, Access.Write),
        (0, gid_temp_dn, Attributes.temp, Access.Read),
        (0, gidNumber_temp_dn, Attributes.temp, Access.Read),
        (0, sid_temp_dn, Attributes.temp, Access.Read),
        (0, groupName_temp_dn, Attributes.temp, Access.Read),
        (0, mac_temp_dn, Attributes.temp, Access.Read),
        (0, gidNumber_temp_dn, Attributes.gid_temp, Access.Write),
        (1, global_univention_dn, Attributes.global_containers, Access.Write),
        (1, global_policies_dn, Attributes.global_containers, Access.Write),
        (1, global_dns_dn, Attributes.global_containers, Access.Write),
        (1, global_groups_dn, Attributes.global_containers, Access.Write),
        (1, global_univention_dn, Attributes.global_containers, Access.Read),
        (1, global_policies_dn, Attributes.global_containers, Access.Read),
        (1, global_dns_dn, Attributes.global_containers, Access.Read),
        (1, global_groups_dn, Attributes.global_containers, Access.Read),
    ]
    mat = LDAPACLTestMatrix(tea_dn, Access.Read)
    mat.add_staff_target_dns(staff_dn_access_list)
    mat.run(
        [
            school_dn,
            global_univention_dn,
            global_policies_dn,
            global_dns_dn,
            global_groups_dn,
            gid_temp_dn,
            gidNumber_temp_dn,
            sid_temp_dn,
            groupName_temp_dn,
            mac_temp_dn,
        ]
    )
