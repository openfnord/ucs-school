#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: set OU display name
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import

from __future__ import print_function

import random
import subprocess

import univention.testing.strings as uts
import univention.testing.ucr
import univention.testing.ucsschool.ucs_test_school as ut_school
import univention.testing.utils as utils

ucr = univention.testing.ucr.UCSTestConfigRegistry()
ucr.load()

# multiple whitespaces to increase chance to get several words
charset = uts.STR_ALPHANUMDOTDASH + uts.STR_ALPHA.upper() + '()[]/,;:_#"+*@<>~ßöäüÖÄÜ$%&!     '


def setRandomDisplayNameViaCreateOU(ou_name):
    """ Tries to set an optional display name while creating/updating the given OU """
    ou_displayName = uts.random_string(length=random.randint(5, 50), charset=charset)
    # create new ou with display name
    cmd = [
        "/usr/share/ucs-school-import/scripts/create_ou",
        "--verbose",
        "--displayName",
        ou_displayName,
        ou_name,
    ]
    print("Calling following command: %r" % cmd)
    retval = subprocess.call(cmd)
    if retval:
        utils.fail("create_ou failed with exitcode %s" % retval)

    ou_dn = "ou=%s,%s" % (ou_name, ucr.get("ldap/base"))
    utils.verify_ldap_object(
        ou_dn,
        expected_attr={"ou": [ou_name], "displayName": [ou_displayName]},
        strict=True,
        should_exist=True,
    )


def main():
    # create short OU name
    ou_name = uts.random_name()
    try:
        print("*** Creating OU and set random display name")
        setRandomDisplayNameViaCreateOU(ou_name)
        print("*** Change displayName to new random value")
        setRandomDisplayNameViaCreateOU(ou_name)
    finally:
        school_tester = ut_school.UCSTestSchool()
        school_tester.cleanup_ou(ou_name)


if __name__ == "__main__":
    main()
