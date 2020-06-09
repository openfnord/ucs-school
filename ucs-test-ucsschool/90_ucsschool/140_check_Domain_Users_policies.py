#!/usr/share/ucs-test/runner python
## bugs: [40471]
## desc: Check that the group "Domain Users $SCHOOL" is connected to the policy "default-umc-users"
## exposure: dangerous
## roles:
##  - domaincontroller_master
##  - domaincontroller_slave
## tags: [apptest,ucsschool,ucsschool_base1]

import univention.testing.utils as utils
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.ucsschool.ucs_test_school import UCSTestSchool


def main():
    lo = utils.get_ldap_connection()

    with UCSTestSchool() as env, UCSTestConfigRegistry() as ucr:
        policy_dn = "cn=default-umc-users,cn=UMC,cn=policies,%s" % (ucr.get("ldap/base"),)
        school, _ = env.create_ou(name_edudc=ucr.get("hostname"))

        domain_users = lo.get(
            "cn=Domain Users %s,cn=groups,ou=%s,%s" % (school, school, ucr.get("ldap/base"),)
        )
        assert policy_dn in domain_users.get("univentionPolicyReference", []), (
            "The policy %r is not connected to the 'Domain Users %s' group, but should be."
            % (policy_dn, school)
        )


if __name__ == "__main__":
    main()
