"""
.. module:: Workgroup
    :platform: Unix

.. moduleauthor:: Ammar Najjar <najjar@univention.de>
"""
from __future__ import print_function

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
from univention.testing import utils
import univention.uldap as uu
from ucsschool.lib.roles import create_ucsschool_role_string, role_workgroup
from univention.lib.umc import HTTPError
from univention.testing.ucsschool.ucs_test_school import UCSTestSchool
from univention.testing.umc import Client


class Workgroup(object):
    """
    Contains the needed functionality for workgroups in an already created OU,
    By default they are randomly formed except the OU, should be provided\n
    :param school: name of the ou
    :type school: str
    :param connection:
    :type connection: UMC connection object
    :param ucr:
    :type ucr: UCR object
    :param name: name of the class to be created later
    :type name: str
    :param description: description of the class to be created later
    :type description: str
    :param members: list of dns of members
    :type members: [str=memberdn]
    """

    def __init__(
        self,
        school,
        connection=None,
        ulConnection=None,
        ucr=None,
        name=None,
        description=None,
        members=None,
        create_share=True,
        create_email=False,
        email="",
        allowed_email_senders_groups=[],
        allowed_email_senders_users=[],
    ):
        self.school = school
        self.name = name if name else uts.random_string()
        self.create_share = create_share
        self.email = email
        self.create_email = create_email
        self.allowed_email_senders_groups = allowed_email_senders_groups
        self.allowed_email_senders_users = allowed_email_senders_users
        self.description = description if description else uts.random_string()
        self.members = members if members else []
        self.ucr = ucr if ucr else ucr_test.UCSTestConfigRegistry()
        self.ucr.load()
        if ulConnection:
            self.ulConnection = ulConnection
        else:
            self.ulConnection = uu.getMachineConnection(ldap_master=False)
        if connection:
            self.client = connection
        else:
            self.client = Client.get_test_connection()

    def __enter__(self):
        return self

    def __exit__(self, type, value, trace_back):
        self.ucr.revert_to_original_registry()

    def create(self, expect_creation_fails_due_to_duplicated_name=False):
        """
        Creates object workgroup\n
        :param expect_creation_fails_due_to_duplicated_name: if user allow duplicate names no exception
            is raised, no group is created either
        :type expect_creation_fails_due_to_duplicated_name: bool
        """
        try:
            createResult = self._create()
            if createResult and expect_creation_fails_due_to_duplicated_name:
                utils.fail(
                    "Workgroup %s already exists, though a new workgroup is created with a the same name"
                    % self.name
                )
            utils.wait_for_replication()
        except HTTPError as exc:
            group_fullname = "%s-%s" % (self.school, self.name)
            exception_strings = [
                "The groupname is already in use as groupname or as username",
                "Der Gruppenname wird bereits als Gruppenname oder als Benutzername verwendet",
                "Die Arbeitsgruppe '%s' existiert bereits!" % group_fullname,
                "The workgroup '%s' already exists!" % group_fullname,
                "Die Arbeitsgruppe u'%s' existiert bereits!" % group_fullname,
                "The workgroup u'%s' already exists!" % group_fullname,
            ]
            for entry in exception_strings:
                if expect_creation_fails_due_to_duplicated_name and entry in str(exc.message):
                    print("Fail : %s" % (exc))
                    break
            else:
                print("Exception: '%s' '%s' '%r'" % (str(exc), type(exc), exc))
                raise

    def _create(self):
        print("Creating workgroup %s in school %s" % (self.name, self.school))
        flavor = "workgroup-admin"
        param = [
            {
                "object": {
                    "name": self.name,
                    "school": self.school,
                    "members": self.members,
                    "description": self.description,
                    "create_share": self.create_share,
                    "create_email": self.create_email,
                    "allowed_email_senders_users": self.allowed_email_senders_users,
                    "allowed_email_senders_groups": self.allowed_email_senders_groups,
                    "email": self.email,
                }
            }
        ]
        requestResult = self.client.umc_command("schoolgroups/add", param, flavor).result
        assert requestResult, "Unable to add workgroup (%r)" % (param,)
        return requestResult

    def remove(self, options=None):
        """Removing a Workgroup from ldap"""
        print("Removing group %s from ldap" % (self.name))
        groupdn = self.dn()
        flavor = "workgroup-admin"
        removingParam = [{"object": [groupdn], "options": options}]
        requestResult = self.client.umc_command("schoolgroups/remove", removingParam, flavor).result
        assert requestResult, "Group %s failed to be removed" % self.name
        utils.wait_for_replication()

    def addMembers(self, memberListdn, options=None):
        """
        Add members to workgroup\n
        :param memberListdn: list of the new members
        :type memberListdn: list
        :param options:
        :type options: None
        """
        print("Adding members  %r to group %s" % (memberListdn, self.name))
        groupdn = self.dn()
        currentMembers = sorted(
            x.decode("UTF-8") for x in self.ulConnection.getAttr(groupdn, "uniqueMember")
        )
        for member in memberListdn:
            if member not in currentMembers:
                currentMembers.append(member)
            else:
                print("member", member, "already exist in the group")
        self.set_members(currentMembers)

    def removeMembers(self, memberListdn, options=None):
        """
        Remove members from workgroup\n
        :param memberListdn: list of the removed members
        :type memberListdn: list
        :param options:
        :type options: None
        """
        print("Removing members  %r from group %s" % (memberListdn, self.name))
        groupdn = self.dn()
        currentMembers = sorted(
            x.decode("UTF-8") for x in self.ulConnection.getAttr(groupdn, "uniqueMember")
        )
        for member in memberListdn:
            if member in currentMembers:
                currentMembers.remove(member)
        self.set_members(currentMembers)

    def deactivate_email(self):
        """Deactivates the email address for the workgroup via UMC"""
        print("Deactivating email for the workgroup {}".format(self.dn()))
        flavor = "workgroup-admin"
        group_dn = self.dn()
        self.create_email = False
        creationParam = [
            {
                "object": {
                    "$dn$": group_dn,
                    "school": self.school,
                    "create_email": self.create_email,
                    "email": self.email,
                    "allowed_email_senders_users": self.allowed_email_senders_users,
                    "allowed_email_senders_groups": self.allowed_email_senders_groups,
                    "name": self.name,
                    "description": self.description,
                    "members": self.members,
                },
            }
        ]
        requestResult = self.client.umc_command("schoolgroups/put", creationParam, flavor).result
        assert requestResult, "Email address failed to be deactivated"
        self.email = ""
        self.allowed_email_senders_groups = []
        self.allowed_email_senders_users = []
        utils.wait_for_replication()

    def set_members(self, new_members, options=None):
        """
        Set members for workgroup\n
        :param new_members: list of the new members
        :type new_members: list
        """
        print("Setting members %r from group %s" % (new_members, self.name))
        flavor = "workgroup-admin"
        groupdn = self.dn()
        creationParam = [
            {
                "object": {
                    "$dn$": groupdn,
                    "school": self.school,
                    "create_email": self.create_email,
                    "email": self.email,
                    "allowed_email_senders_users": self.allowed_email_senders_users,
                    "allowed_email_senders_groups": self.allowed_email_senders_groups,
                    "name": self.name,
                    "description": self.description,
                    "members": new_members,
                },
                "options": options,
            }
        ]
        requestResult = self.client.umc_command("schoolgroups/put", creationParam, flavor).result
        assert requestResult, "Members %s failed to be set" % new_members
        self.members = new_members
        utils.wait_for_replication()

    def verify_ldap_attributes(self):
        """checking group attributes in ldap"""
        print("Checking the attributes for group %s in ldap" % (self.name,))
        members = []
        if self.members:
            for member in self.members:
                m = member.split(",")[0][4:]
                members.append(m)
        expected_attr = {
            "memberUid": members,
            "description": [self.description],
            "ucsschoolRole": [create_ucsschool_role_string(role_workgroup, self.school)],
            "mailPrimaryAddress": [self.email] if self.create_email else [],
            "univentionAllowedEmailUsers": self.allowed_email_senders_users if self.create_email else [],
            "univentionAllowedEmailGroups": self.allowed_email_senders_groups
            if self.create_email
            else [],
        }
        utils.verify_ldap_object(self.dn(), expected_attr=expected_attr)

    def verify_exists(self, group_should_exist, share_should_exist):
        """check for group and file share objects existance in ldap"""
        print("Checking if group %s and its share object exist in ldap" % (self.name,))
        groupdn = self.dn()
        utils.verify_ldap_object(groupdn, should_exist=group_should_exist)
        ucsschool = UCSTestSchool()
        sharedn = "cn=%s-%s,cn=shares,%s" % (
            self.school,
            self.name,
            ucsschool.get_ou_base_dn(self.school),
        )
        utils.verify_ldap_object(sharedn, should_exist=share_should_exist)

    def dn(self):
        ucsschool = UCSTestSchool()
        groupdn = ucsschool.get_workinggroup_dn(self.school, self.name)
        return groupdn
