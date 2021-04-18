#!/usr/share/ucs-test/runner python
## desc: ucs-school-define-internet-rules-check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: careful
## packages: [ucs-school-umc-internetrules]

import univention.testing.utils as utils
from univention.testing.ucsschool.internetrule import InternetRule


def main():

    with InternetRule() as rule:

        # Fetch the currently defined internet rules
        definedRules = rule.allRules()

        # Defining rule
        rule.define()
        definedRules.append(rule.name)

        # check internetrules/get
        rule.get(should_exist=True)
        # check ucr
        rule.checkUcr(should_match=True)

        # Fetch the currently existing internet rules
        definedRules2 = rule.allRules()

        # check if the existing internet rules are correct
        if definedRules2 != sorted(definedRules):
            utils.fail(
                "Existing rules (%r) do not match the actual ones (%r)" % (definedRules2, definedRules)
            )

        # New rule values (hard coded)
        name = rule.name
        new_type = "blacklist"
        priority = 8
        wlan = True
        domains = sorted(["asda.de", "kjnasd.sy", "nmxcvbl.gp"])

        # Modifying the rule
        rule.put(name, new_type, domains, wlan, priority)

        # check internetrules/get
        rule.get(should_exist=True)
        # check ucr
        rule.checkUcr(should_match=True)

        # Removing the rule
        rule.remove()
        definedRules.remove(rule.name)

        # check internetrules/get
        rule.get(should_exist=False)
        # check ucr
        rule.checkUcr(should_match=False)

        # Fetch the currently existing internet rules
        definedRules2 = rule.allRules()

        # check if the existing internet rules are correct
        if definedRules2 != sorted(definedRules):
            utils.fail(
                "Existing rules (%r) do not match the actual ones (%r)" % (definedRules2, definedRules)
            )


if __name__ == "__main__":
    main()
