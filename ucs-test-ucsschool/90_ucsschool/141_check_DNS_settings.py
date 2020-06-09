#!/usr/share/ucs-test/runner python
## bugs: [40470]
## desc: Check that school-servers (except master and backup) were not added to the DNS forward and reverse lookup zones.
## exposure: safe
## join: true
## roles:
##  - domaincontroller_slave
## tags: [apptest,ucsschool,ucsschool_base1]

from ldap.filter import filter_format

import univention.testing.utils as utils
from univention.testing.ucr import UCSTestConfigRegistry


def main():
    with UCSTestConfigRegistry() as ucr:
        lo = utils.get_ldap_connection()
        zone_name = "%s.%s." % (ucr.get("hostname"), ucr.get("domainname"))
        print "Searching for DNS zones with nsRecord=%r" % (zone_name,)
        zones = lo.search(filter_format("nSRecord=%s", (zone_name,)))

        assert not zones, "A school server is listed as DNS server, which it must not be: %r" % (zones,)


if __name__ == "__main__":
    main()
