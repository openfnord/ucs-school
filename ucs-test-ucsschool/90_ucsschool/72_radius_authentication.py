#!/usr/share/ucs-test/runner pytest-3 -s -l -v
## -*- coding: utf-8 -*-
## desc: Computers(schools) module
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-radius-802.1x]

from __future__ import print_function

import random

from ldap.filter import filter_format

import univention.testing.utils as utils
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.internetrule import InternetRule
from univention.testing.ucsschool.radius import test_peap_auth as _test_peap_auth
from univention.testing.ucsschool.workgroup import Workgroup


def random_case(txt):  # type: (str) -> str
    """
    Try up to 1000 times to randomize given string by using upper/lowercase variants of its characters.
    """
    assert txt, "Given string should not be empty!"
    result = []
    for i in range(1000):
        for c in txt:
            if random.randint(0, 1):
                result.append(c.upper())
            else:
                result.append(c.lower())
        if "".join(result) != txt:
            break
        result = []
    return "".join(result)


def test_radius_authentication(schoolenv, ucr):
            school, oudn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))

            tea, tea_dn = schoolenv.create_user(school, is_teacher=True)
            tea2, tea2_dn = schoolenv.create_user(school, is_teacher=True)
            stu, stu_dn = schoolenv.create_user(school)
            stu2, stu2_dn = schoolenv.create_user(school)

            group = Workgroup(school, members=[tea_dn, stu_dn])
            group.create()
            rule = InternetRule(wlan=True)
            rule.define()

            group2 = Workgroup(school, members=[tea2_dn, stu2_dn])
            group2.create()
            rule2 = InternetRule(wlan=False)
            rule2.define()

            utils.wait_for_replication_and_postrun()

            rule.assign(school, group.name, "workgroup")
            rule2.assign(school, group2.name, "workgroup")

            utils.wait_for_replication_and_postrun()
            print("Wait until users are replicated into S4...")
            for name in [tea, tea2, stu, stu2]:
                wait_for_drs_replication(filter_format("cn=%s", (name,)))

            radius_secret = "testing123"  # parameter set in  /etc/freeradius/clients.conf
            password = "univention"

            test_couples = []

            def add_test_couples(username, expected_success):
                test_couples.extend(
                    [
                        (username, expected_success),  # original case
                        (username.lower(), expected_success),  # all lowercase
                        (username.upper(), expected_success),  # all uppercase
                        (random_case(username), expected_success),  # all random case
                    ]
                )

            add_test_couples(tea, True)
            add_test_couples(stu, True)
            add_test_couples(tea2, False)
            add_test_couples(stu2, False)

            # Testing loop
            for username, should_succeed in test_couples:
                _test_peap_auth(username, password, radius_secret, should_succeed=should_succeed)
