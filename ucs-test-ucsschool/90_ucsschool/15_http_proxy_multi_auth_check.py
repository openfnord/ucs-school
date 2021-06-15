#!/usr/share/ucs-test/runner python
## desc: http-proxy-multi-auth-check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave, memberserver]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [univention-samba4, ucs-school-webproxy]
## bugs: [44252, 44287]

from __future__ import print_function

import itertools
import subprocess

import pycurl

import univention.testing.ucr as ucr_test
import univention.testing.utils as utils
from univention.config_registry import handler_set, handler_unset
from univention.testing.ucsschool.simplecurl import SimpleCurl


def checkAuths(host, passwd, url, basic, ntlm, gneg, expect_wrong_password):
    # in case all auth are disabled, all return 200
    http_basic, http_ntlm, http_gneg = (200, 200, 200)
    if basic or ntlm or gneg:
        http_basic = 200 if (basic and not expect_wrong_password) else 407
        http_ntlm = 200 if (ntlm and not expect_wrong_password) else 407
        # in Gssnegotiate case kinit is called with the password
        # if passwd is wrong it fails setting the auth up but returns 200
        http_gneg = 200 if (gneg) else 407
    checkBasic(host, passwd, url, http_basic)
    checkNTLM(host, passwd, url, http_ntlm)
    checkGssnegotiate(host, passwd, url, http_gneg, expect_wrong_password)


def checkBasic(host, passwd, url, http_code):
    print("Performing Basic proxy auth check")
    curl = SimpleCurl(proxy=host, password=passwd, auth=pycurl.HTTPAUTH_BASIC)
    result = curl.response(url)
    if http_code != result:
        utils.fail("Basic proxy auth check failed, http_code = %r, expected = %r" % (result, http_code))


def checkNTLM(host, passwd, url, http_code):
    print("Performing NTLM proxy auth check")
    curl = SimpleCurl(proxy=host, password=passwd, auth=pycurl.HTTPAUTH_NTLM)
    result = curl.response(url)
    if http_code != result:
        utils.fail("NTLM proxy auth check failed, http_code = %r, expected = %r" % (result, http_code))


def checkGssnegotiate(host, passwd, url, http_code, expect_wrong_password):
    print("Performing Gssnegotiate proxy auth check")
    curl = SimpleCurl(proxy=host, password=passwd, auth=pycurl.HTTPAUTH_GSSNEGOTIATE)
    account = utils.UCSTestDomainAdminCredentials()
    admin = account.username
    pop = subprocess.Popen(["kinit", "--password-file=STDIN", admin], stdin=subprocess.PIPE)
    pop.communicate(passwd)
    subprocess.call(["klist"])
    result = curl.response(url)
    if http_code != result:
        utils.fail(
            "Gssnegotiate proxy auth check failed, http_code = %r, expected = %r" % (result, http_code)
        )
    else:
        if not expect_wrong_password and pop.returncode != 0:
            utils.fail("kinit: correct Password used but did not work")


def setAuthVariables(basic, ntlm, gneg):
    """set ucr variables according to the auth states, and restart Squid"""
    if basic:
        handler_set(["squid/basicauth=yes"])
    else:
        handler_unset(["squid/basicauth"])
    if ntlm:
        handler_set(["squid/ntlmauth=yes"])
    else:
        handler_unset(["squid/ntlmauth"])
    if gneg:
        handler_set(["squid/krb5auth=yes", "squid/krb5auth/keepalive=yes"])
    else:
        handler_unset(["squid/krb5auth", "squid/krb5auth/keepalive"])
    subprocess.Popen(["/etc/init.d/squid", "restart"], stdin=subprocess.PIPE).communicate()


def printHeader(state, passwd, expect_wrong_password):
    print("-" * 40)
    print("(Basic, NTLM, Gssnegotiate) = %s" % (state,))
    print("Password used: %s, expect_wrong_password: %s" % (passwd, expect_wrong_password))


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        # url = ucr.get('proxy/filter/redirecttarget')
        url = "http://download.univention.de/"
        host = "%s.%s" % (ucr.get("hostname"), ucr.get("domainname"))

        # list of tuples (passwd, expect_wrong_password) used in the test
        passwords = [("univention", False), ("wrong_passwd", True)]

        # Generate all the possibilities for the auth states
        # [(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1),
        #  (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)]
        authStates = list(itertools.product([0, 1], repeat=3))

        for passwd, expect_wrong_password in passwords:
            for basic, ntlm, gneg in authStates:
                printHeader((basic, ntlm, gneg), passwd, expect_wrong_password)

                # set ucr variables according to the auth states
                setAuthVariables(basic, ntlm, gneg)

                # Perform the checks
                checkAuths(host, passwd, url, basic, ntlm, gneg, expect_wrong_password)


if __name__ == "__main__":
    main()
