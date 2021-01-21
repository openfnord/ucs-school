#!/usr/share/ucs-test/runner python
## desc: Check if an internet rule may be assigned to 2 rooms
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave]
## bugs: [32544]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages:  [ucs-school-webproxy]

import re

import univention.config_registry as uc
import univention.testing.ucr as ucr_test
import univention.testing.utils as utils


# copied from ucs-school-webproxy.py
def quote(string):
    "Replace every unsafe byte with hex value"
    if type(string) is unicode:
        string = string.encode("utf-8")
    newstring = ""
    for byte in string:
        if byte in quote.safeBytes:
            newstring += byte
        else:
            newstring += "-" + byte.encode("hex")
    return newstring


quote.safeBytes = set("abcdefghijklmnopqrstuvwxyz012345679ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def prepare_UCR_setup(ucr):
    changes = [
        "proxy/filter/redirecttarget=http://%s.%s/blocked-by-squid.html"
        % (ucr.get("hostname"), ucr.get("domainname")),
        "proxy/filter/room/Raum1/ip=10.200.18.250 10.200.18.251",
        "proxy/filter/room/Raum1/rule=Some Rule",
        "proxy/filter/room/Raum2/ip=10.200.18.252",
        "proxy/filter/room/Raum2/rule=Another Rule",
        "proxy/filter/room/Raum-Drei/ip=10.200.18.253",
        "proxy/filter/room/Raum-Drei/rule=Special Rule",
        "proxy/filter/setting/Nur Wikipedia/domain/whitelisted/1=wikipedia.de",
        "proxy/filter/setting/Nur Wikipedia/filtertype=whitelist-block",
        "proxy/filter/setting/Nur Wikipedia/priority=5",
        "proxy/filter/setting/Nur Wikipedia/wlan=false",
        "proxy/filter/setting/Nur-Univention/domain/whitelisted/1=univention.de",
        "proxy/filter/setting/Nur-Univention/filtertype=whitelist-block",
        "proxy/filter/setting/Nur-Univention/priority=7",
        "proxy/filter/setting/Nur-Univention/wlan=false",
    ]
    uc.handler_set(changes)


def test_ruleset(ucr, test_settings):
    print "*** Testing with following test settings: %r" % test_settings

    # assign different rules to each room
    changes = []
    for room, rule in test_settings.items():
        changes.append("proxy/filter/room/%s/rule=%s" % (room, rule))
    uc.handler_set(changes)
    ucr.load()

    # read and normalize content of squidGuard.conf
    content = open("/etc/squidguard/squidGuard.conf", "r").read()
    content = re.sub("[ \t]+", " ", content)  # merge whitespaces
    content = re.sub("\n +", "\n", content)  # remove leading whitespace
    content = re.sub(" +\n", "\n", content)  # remove trailing whitespace

    for room, rule in test_settings.items():
        # do a rough check if all required lines are present
        expected_strings = [
            "\ndest blacklist-%s {\ndomainlist blacklisted-domain-%s\nurllist blacklisted-url-%s"
            % (quote(rule), quote(rule), quote(rule)),
            "\ndest whitelist-%s {\ndomainlist whitelisted-domain-%s\nurllist whitelisted-url-%s"
            % (quote(rule), quote(rule), quote(rule)),
        ]

        if ucr.is_true("proxy/filter/global/blacklists/forced"):
            expected_strings.append(
                "\nroom-%s {\npass !global-blacklist whitelist-%s none" % (quote(room), quote(rule))
            )
        else:
            expected_strings.append("\nroom-%s {\npass whitelist-%s none" % (quote(room), quote(rule)))

        addr_list = ucr.get("proxy/filter/room/%s/ip" % room).split()
        if addr_list:
            expected_strings.append("src room-%s {\nip %s" % (quote(room), "\nip ".join(addr_list)))

        for line in expected_strings:
            if line not in content:
                # print '---[expected strings]----------------------------------------------------------'
                # print expected_strings
                # print '---[/etc/squidguard/squidGuard.conf]-------------------------------------------'
                # print content
                # print '-------------------------------------------------------------------------------'
                utils.fail("Cannot find string %r in squidGuard.conf" % line)


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        # setup filter rules for squidguard
        prepare_UCR_setup(ucr)

        # test with different rules for each room
        test_ruleset(ucr, {"Raum1": "Nur Wikipedia", "Raum2": "Nur-Univention"})
        # test with the same rule for both rooms
        test_ruleset(ucr, {"Raum1": "Nur Wikipedia", "Raum2": "Nur Wikipedia"})
        # test with the same rule for both rooms
        test_ruleset(ucr, {"Raum1": "Nur-Univention", "Raum2": "Nur-Univention"})
        # test with the same rule for three rooms
        test_ruleset(
            ucr, {"Raum1": "Nur-Univention", "Raum2": "Nur-Univention", "Raum-Drei": "Nur-Univention"}
        )
        test_ruleset(
            ucr, {"Raum1": "Nur Wikipedia", "Raum2": "Nur Wikipedia", "Raum-Drei": "Nur Wikipedia"}
        )


if __name__ == "__main__":
    main()
