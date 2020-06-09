#!/usr/share/ucs-test/runner python
## desc: Delete computer deletes all related objects
## roles: [domaincontroller_master, domaincontroller_slave]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-umc-computerroom]

from ldap import NO_SUCH_OBJECT

import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.ucsschool.computerroom import UmcComputer
from univention.uldap import getMachineConnection

ucr = ucr_test.UCSTestConfigRegistry()
ucr.load()


def dns_forward():
    return "zoneName=%s,cn=dns,%s" % (ucr.get("domainname"), ucr.get("ldap/base"))


def dns_reverse(ip):
    return "zoneName=%s.in-addr.arpa,cn=dns,%s" % (
        ".".join(reversed(ip.split(".")[:3])),
        ucr.get("ldap/base"),
    )


def dhcp_dn(school, computer_name):
    return "cn=%s,cn=%s,cn=dhcp,ou=%s,%s" % (computer_name, school, school, ucr.get("ldap/base"))


def check_ldap(school, computers, should_exist):
    lo = getMachineConnection()
    for computer in computers:
        try:
            # Check DNS forward objects
            dns = dns_forward()
            found = lo.search(filter="(aRecord=%s)" % computer.ip_address, base=dns)
            if should_exist and not found:
                utils.fail("Object not found:(%r) aRecord=%s" % (dns, computer.ip_address))
            if not should_exist and found:
                utils.fail("Object unexpectedly found:(%r)" % found)

            computer_name = computer.name
            if computer_name[-1] == "$":
                computer_name = computer_name[:-1]
            # Check DNS reverse objects
            dns = dns_reverse(computer.ip_address)
            found = lo.search(
                filter="(pTRRecord=%s.%s.)" % (computer_name, ucr.get("domainname")), base=dns
            )
            if should_exist and not found:
                utils.fail(
                    "Object not found:(%r), pTRRecord=%s.%s."
                    % (dns, computer_name, ucr.get("domainname"))
                )
            if not should_exist and found:
                utils.fail("Object unexpectedly found:(%r)" % found)

            # Check DHCP objects
            dhcp = dhcp_dn(school, computer_name)
            found = lo.search(base=dhcp)
            if should_exist and not found:
                utils.fail("Object not found:(%r)" % dhcp)
            if not should_exist and found:
                utils.fail("Object unexpectedly found:(%r)" % dhcp)

        except NO_SUCH_OBJECT as ex:
            if should_exist:
                utils.fail(ex)


def main():
    with utu.UCSTestSchool() as schoolenv:
        school, oudn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))

        computers = []
        for computer_type in ["windows", "macos", "ipmanagedclient"]:
            computer = UmcComputer(school, computer_type)
            computer.create()
            computers.append(computer)

        check_ldap(school, computers, should_exist=True)

        for computer in computers:
            computer.remove()
        check_ldap(school, computers, should_exist=False)


if __name__ == "__main__":
    main()
