#!/usr/share/ucs-test/runner python
## desc: http-proxy-basic-auth-check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-webproxy]

from __future__ import print_function

import time

import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.ucsschool.internetrule import InternetRule
from univention.testing.ucsschool.klasse import Klasse
from univention.testing.ucsschool.simplecurl import SimpleCurl
from univention.testing.ucsschool.workgroup import Workgroup
from univention.testing.umc import Client

# Checks a list of rules defined and return the active rule
# for a specific user


def ruleInControl(user, ruleList, host, banPage):
    inCtrl = []
    localCurl = SimpleCurl(proxy=host, username=user)
    ruleList = [rule for rule in ruleList if rule is not None]
    for rule in ruleList:
        if rule.typ == "blacklist":
            if all(localCurl.getPage(dom) == banPage for dom in rule.domains):
                inCtrl.append(rule)
        elif rule.typ == "whitelist":
            if all(localCurl.getPage(dom) != banPage for dom in rule.domains):
                inCtrl.append(rule)
    localCurl.close()
    # return the bigger rule
    # in case one rule is contained in another
    result = [x.name for x in inCtrl if len(x.domains) == max(len(y.domains) for y in inCtrl)]
    print("Rule in control =", result)
    return result[0]


def printHeader(comment):
    print("-" * 80)
    print(comment)
    print("-" * 80)


# Perform the whole check steps for a user and two rules


def doCheck(host, banPage, user, rulesType, ruleWithHigherPrio, ruleWithLowerPrio=None):
    ruleInCtrl = ruleInControl(user, [ruleWithLowerPrio, ruleWithHigherPrio], host, banPage)
    if ruleInCtrl != ruleWithHigherPrio.name:
        utils.fail(
            "rule in Ctrl for user (%s): expected (%s), current (%s)"
            % (user, ruleWithHigherPrio.name, ruleInCtrl)
        )
    else:
        print("TEST PASSED: rule in Ctrl for user (%s) is (%s)" % (user, ruleInCtrl))


def main():
    with utu.UCSTestSchool() as schoolenv:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            host = ucr.get("hostname")

            # create ou
            school, oudn = schoolenv.create_ou(name_edudc=host)
            # create class
            newClass = Klasse(school, ucr=ucr)
            newClass.create()

            # create user in that class student/teacher
            tea, teadn = schoolenv.create_user(
                school, classes="%s-%s" % (school, newClass.name), is_teacher=True
            )
            stu, studn = schoolenv.create_user(school, classes="%s-%s" % (school, newClass.name))

            # Getting the redirection page when blocked
            adminCurl = SimpleCurl(proxy=host)
            redirUri = ucr.get("proxy/filter/redirecttarget")
            banPage = adminCurl.getPage(redirUri)
            adminCurl.close()

            client = Client.get_test_connection(host)

            # define whitelist internet rule
            rule1 = InternetRule(
                ucr=ucr, connection=client, typ="whitelist", domains=["univention.de"], priority=3
            )
            rule1.define()

            # assign whitelist rule1 to the class
            rule1.assign(school, newClass.name, "class")

            utils.wait_for_replication_and_postrun()
            printHeader("Check for whitelist and student for one rule")
            doCheck(host, banPage, stu, "whitelist", rule1)
            printHeader("Check for whitelist and teacher for one rule")
            doCheck(host, banPage, tea, "whitelist", rule1)

            # create a workgroup
            newWorkgroup = Workgroup(school, ucr=ucr, members=[teadn, studn])
            newWorkgroup.create()

            # define different rule with higher priority
            rule2 = InternetRule(
                ucr=ucr, connection=client, typ="whitelist", domains=["google.de", "gmx.net"], priority=4
            )
            rule2.define()

            # Assign whitelist rule to the new Workgroup
            rule2.assign(school, newWorkgroup.name, "workgroup")
            utils.wait_for_replication_and_postrun()

            printHeader("Check for whitelist and student for two rules with different priorities")
            doCheck(host, banPage, stu, "whitelist", rule2, rule1)

            printHeader("Check for whitelist and teacher for two rules with different priorities")
            doCheck(host, banPage, tea, "whitelist", rule2, rule1)

            # switch rule1 to be 'blacklist' with higher proirity
            rule1.put(new_type="blacklist", new_priority=5)
            time.sleep(17)  # wait for reload of squid/squidguard - limited to 1 reload every 15 seconds

            printHeader("Check for blacklist and student for one rule")
            doCheck(host, banPage, stu, "blacklist", rule1)

            printHeader("Check for blacklist and teacher for one rule")
            doCheck(host, banPage, tea, "blacklist", rule1)

            # switch rule2 to be 'blacklist' with higher proirity
            rule2.put(new_type="blacklist", new_priority=6)
            time.sleep(17)  # wait for reload of squid/squidguard - limited to 1 reload every 15 seconds

            printHeader("Check for blacklist and student for two rules with different priorities")
            doCheck(host, banPage, stu, "blacklist", rule2, rule1)

            printHeader("Check for blacklist and teacher for two rules with different priorities")
            doCheck(host, banPage, tea, "blacklist", rule2, rule1)


if __name__ == "__main__":
    main()
