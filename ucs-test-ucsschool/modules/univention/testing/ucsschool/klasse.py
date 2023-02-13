"""
.. module:: Klasse
    :platform: Unix

.. moduleauthor:: Ammar Najjar <najjar@univention.de>
"""
from __future__ import print_function

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
from ucsschool.lib.roles import create_ucsschool_role_string, role_school_class, role_school_class_share
from univention.testing import utils
from univention.testing.ucsschool.ucs_test_school import UCSTestSchool
from univention.testing.umc import Client


class Klasse(object):
    """
    Contains the needed functionality for classes in an already created OU,
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
    """

    def __init__(self, school, connection=None, ucr=None, name=None, users=None, description=None):
        self.school = school
        self.users = users or []
        self.name = name if name else uts.random_string()
        self.description = description if description else uts.random_string()
        self.ucr = ucr if ucr else ucr_test.UCSTestConfigRegistry()
        self.ucr.load()
        if connection:
            self.client = connection
        else:
            self.client = Client.get_test_connection(self.ucr.get("ldap/master"))

    def __enter__(self):
        return self

    def __exit__(self, type, value, trace_back):
        self.ucr.revert_to_original_registry()

    def create(self):
        """Creates object class"""
        flavor = "schoolwizards/classes"
        param = [
            {
                "object": {"name": self.name, "school": self.school, "description": self.description},
                "options": None,
            }
        ]
        print("Creating class %s in school %s" % (self.name, self.school))
        print("param = %s" % (param,))
        reqResult = self.client.umc_command("schoolwizards/classes/add", param, flavor).result
        assert reqResult[0], "Unable to create class (%r)" % (param,)

    def query(self):
        """get the list of existing classes in the school"""
        flavor = "schoolwizards/classes"
        param = {"school": self.school, "filter": ""}
        reqResult = self.client.umc_command("schoolwizards/classes/query", param, flavor).result
        return reqResult

    def check_query(self, classes_names):
        q = self.query()
        k = [x["name"] for x in q]
        assert set(classes_names) == set(
            k
        ), "Classes from query do not match existing ones\nfound (%r)\nexpected (%r)" % (
            k,
            classes_names,
        )

    def dn(self):
        return "cn=%s-%s,cn=klassen,cn=schueler,cn=groups,%s" % (
            self.school,
            self.name,
            UCSTestSchool().get_ou_base_dn(self.school),
        )

    @property
    def share_dn(self):
        return "cn=%s-%s,cn=klassen,cn=shares,%s" % (
            self.school,
            self.name,
            UCSTestSchool().get_ou_base_dn(self.school),
        )

    def get(self):
        """Get class"""
        flavor = "schoolwizards/classes"
        param = [{"object": {"$dn$": self.dn(), "school": self.school}}]
        reqResult = self.client.umc_command("schoolwizards/classes/get", param, flavor).result
        assert reqResult[0], "Unable to get class (%s)" % self.name
        return reqResult[0]

    def check_get(self):
        info = {
            "$dn$": self.dn(),
            "school": self.school,
            "description": self.description,
            "name": self.name,
            "users": self.users,
            "objectType": "groups/group",
            "ucsschool_roles": [create_ucsschool_role_string(role_school_class, self.school)],
        }
        get_result = self.get()
        assert (
            get_result == info
        ), "Failed get request for class %s. Returned result: %r. Expected result: %r" % (
            self.name,
            get_result,
            info,
        )

    def remove(self):
        """Remove class"""
        flavor = "schoolwizards/classes"
        param = [{"object": {"$dn$": self.dn(), "school": self.school}, "options": None}]
        reqResult = self.client.umc_command("schoolwizards/classes/remove", param, flavor).result

        assert reqResult[0], "Unable to remove class (%s)" % self.name

    def edit(self, new_attributes):
        """Edit object class"""
        flavor = "schoolwizards/classes"
        param = [
            {
                "object": {
                    "$dn$": self.dn(),
                    "name": new_attributes["name"],
                    "school": self.school,
                    "description": new_attributes["description"],
                },
                "options": None,
            }
        ]
        print("Editing class %s in school %s" % (self.name, self.school))
        print("param = %s" % (param,))
        reqResult = self.client.umc_command("schoolwizards/classes/put", param, flavor).result
        assert reqResult[0], "Unable to edit class (%s) with the parameters (%r)" % (self.name, param)
        self.name = new_attributes["name"]
        self.description = new_attributes["description"]

    def check_existence(self, should_exist):
        utils.verify_ldap_object(self.dn(), should_exist=should_exist)

    def verify(self):
        # TODO: check all attributes
        utils.verify_ldap_object(
            self.dn(),
            expected_attr={
                "ucsschoolRole": [create_ucsschool_role_string(role_school_class, self.school)]
            },
            should_exist=True,
        )
        utils.verify_ldap_object(
            self.share_dn,
            expected_attr={
                "ucsschoolRole": [create_ucsschool_role_string(role_school_class_share, self.school)]
            },
            should_exist=True,
        )
