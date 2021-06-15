#!/usr/share/ucs-test/runner python
# -*- coding: utf-8 -*-
## desc: check number of squid helper process children
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master,domaincontroller_slave]
## bugs: [40092]
## exposure: safe
## packages:
##   - ucs-school-webproxy

from __future__ import print_function

import univention.testing.ucr
import univention.testing.utils as utils


def main():
    ucr = univention.testing.ucr.UCSTestConfigRegistry()
    ucr.load()

    for key, value in {
        "squid/basicauth/children": "50",
        "squid/krb5auth/children": "50",
        "squid/ntlmauth/children": "50",
        "squid/rewrite/children": "20",
    }.items():
        if ucr.get(key) != value:
            utils.fail(
                "Expected UCR variable %r to be set to %r but current value is %r"
                % (key, value, ucr.get(key))
            )
        else:
            print("UCR variable: %s=%r" % (key, value))


if __name__ == "__main__":
    main()
