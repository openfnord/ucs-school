#!/usr/share/ucs-test/runner python3
## desc: ucs-school-webproxy - pupilgroups listener updates UCRVs
## roles: [domaincontroller_slave]
## tags: [SKIP-UCSSCHOOL,apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-webproxy]
## bugs: [41749]


import univention.testing.strings as uts
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from ucsschool.lib.models.group import SchoolClass
from ucsschool.lib.models.school import School
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class Test(CLI_Import_v2_Tester):
    ou_A = None
    ou_B = None
    ou_C = None

    def create_ous(self, schoolenv):
        self.log.info("Creating OUs...")
        self.ou_A = utu.Bunch(name=None, dn=None)
        self.ou_B = utu.Bunch(name=None, dn=None)
        self.ou_A.name, self.ou_A.dn = schoolenv.create_ou(name_edudc=self.ucr.get("hostname"))
        # not using the cache, as it could return the same OU on singleserver systems.
        self.ou_B.name, self.ou_B.dn = schoolenv.create_ou(use_cache=False)
        self.log.info(
            "*** This host is responsible for OU %r, but not for OU %r.", self.ou_A.name, self.ou_B.name
        )
        all_local_schools = [school.dn for school in School.get_all(self.lo)]
        self.log.info("*** This hosts school OUs: %r\n\n", all_local_schools)
        if self.ou_B.name in all_local_schools:
            utils.fail("Found OU %r in local schools." % self.ou_B.name)

    def test(self):
        class_A_dn, class_A_name = self.udm.create_group(
            position=SchoolClass.get_container(self.ou_A.name),
            name="{}-{}".format(self.ou_A.name, uts.random_groupname()),
            check_for_drs_replication=False,
        )
        ucr_A = "proxy/filter/usergroup/%s" % class_A_name
        class_B_dn, class_B_name = self.udm.create_group(
            position=SchoolClass.get_container(self.ou_B.name),
            name="{}-{}".format(self.ou_B.name, uts.random_groupname()),
            check_for_drs_replication=False,
        )
        ucr_B = "proxy/filter/usergroup/%s" % class_B_name

        user_a_name, user_a_dn = self.schoolenv.create_user(self.ou_A.name, classes=class_A_name)
        user_b_name, user_b_dn = self.schoolenv.create_user(self.ou_B.name, classes=class_B_name)

        utils.wait_for_replication_and_postrun()
        self.ucr.load()

        sc_a = SchoolClass.from_dn(class_A_dn, None, self.lo)
        users_a = sc_a.get_udm_object(self.lo)["users"]
        if user_a_dn not in users_a:
            self.log.error("Users in %r: %r" % (class_A_name, users_a))
            utils.fail("User %r is not in school class %r." % (user_a_dn, sc_a))
        sc_b = SchoolClass.from_dn(class_B_dn, None, self.lo)
        users_b = sc_b.get_udm_object(self.lo)["users"]
        if user_b_dn not in users_b:
            self.log.error("Users in %r: %r" % (class_B_name, users_b))
            utils.fail("User %r is not in school class %r." % (user_b_dn, sc_b))

        if user_a_name not in self.ucr.get(ucr_A, "").split(","):
            utils.fail("Username %r not in UCRV %r." % (user_a_name, ucr_A))
        if self.ucr.get(ucr_B, ""):
            self.log.warning("*** UCRV %r exists: %r", ucr_B, self.ucr.get(ucr_B, ""))
        if user_b_name in self.ucr.get(ucr_B, "").split(","):
            utils.fail("Username %r in UCRV %r." % (user_b_name, ucr_B))


if __name__ == "__main__":
    Test().run()
