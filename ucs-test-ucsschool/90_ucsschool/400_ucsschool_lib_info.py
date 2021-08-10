#!/usr/share/ucs-test/runner pytest-3 -s -l -v
## -*- coding: utf-8 -*-
## desc: Test python module ucsschool.lib.info
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages:
##   - python3-ucsschool-lib
## bugs: [47966]

import pytest

import ucsschool.lib.info as uli
import univention.testing.strings as uts


def test_ucsschool_lib_info(udm_session, schoolenv, ucr):
                udm = udm_session
                name_edudc = uts.random_string()
                name_admindc = uts.random_string()
                name_centraldc = uts.random_string()
                name_backup = uts.random_string()
                name_centralmemberserver = uts.random_string()

                # create central dc slave, edu school slave and admin school slave
                dn_centraldc = udm.create_object(
                    "computers/domaincontroller_slave",
                    position="cn=dc,cn=computers,{}".format(ucr.get("ldap/base")),
                    name=name_centraldc,
                )
                school, oudn = schoolenv.create_ou(
                    name_edudc=name_edudc, name_admindc=name_admindc, use_cache=False
                )
                # create dc backup and memberserver
                dn_memberserver = udm.create_object(
                    "computers/memberserver",
                    position="cn=computers,{}".format(ucr.get("ldap/base")),
                    name=name_centralmemberserver,
                )
                dn_backup = udm.create_object(
                    "computers/domaincontroller_backup",
                    position="cn=dc,cn=computers,{}".format(ucr.get("ldap/base")),
                    name=name_backup,
                )

                # get DNs of school slaves
                lo = schoolenv.open_ldap_connection()
                dn_edudc = lo.searchDn(
                    filter="(&(univentionObjectType=computers/domaincontroller_slave)(cn={}))".format(
                        name_edudc
                    ),
                    base=oudn,
                )[0]
                dn_admindc = lo.searchDn(
                    filter="(&(univentionObjectType=computers/domaincontroller_slave)(cn={}))".format(
                        name_admindc
                    ),
                    base=oudn,
                )[0]
                dn_master = lo.searchDn(
                    filter="(univentionObjectType=computers/domaincontroller_master)"
                )[0]

                # check is_school_slave()
                assert uli.is_school_slave(lo, dn_edudc), "{} should be a school slave".format(dn_edudc)
                assert uli.is_school_slave(lo, dn_admindc), "{} should be a school slave".format(
                    dn_admindc
                )
                assert not (
                    uli.is_school_slave(lo, dn_centraldc)
                ), "{} should NOT be a school slave".format(dn_centraldc)
                with pytest.raises(
                    ValueError,
                    match="Given computer DN does not refer to a computers/domaincontroller_slave "
                    "object",
                ):  # match will be evaluated as of pytest 3.1+
                    uli.is_school_slave(lo, dn_backup)

                assert not (
                    uli.is_central_computer(lo, dn_edudc)
                ), "{} should NOT be a central slave".format(dn_edudc)
                assert not (
                    uli.is_central_computer(lo, dn_admindc)
                ), "{} should NOT be a central slave".format(dn_admindc)
                assert uli.is_central_computer(lo, dn_centraldc), "{} should be a central slave".format(
                    dn_centraldc
                )
                assert uli.is_central_computer(
                    lo, dn_memberserver
                ), "{} should be a central memberserver".format(dn_memberserver)
                assert uli.is_central_computer(lo, dn_backup), "{} should be a central backup".format(
                    dn_backup
                )
                assert uli.is_central_computer(lo, dn_master), "{} should be a central master".format(
                    dn_master
                )

                assert uli.get_school_membership_type(lo, dn_edudc) == (
                    True,
                    False,
                ), "get_school_membership_type() returned unexpected result for edu dc"
                assert uli.get_school_membership_type(lo, dn_admindc) == (
                    False,
                    True,
                ), "get_school_membership_type() returned unexpected result for admin dc"
                assert uli.get_school_membership_type(lo, dn_centraldc) == (
                    False,
                    False,
                ), "get_school_membership_type() returned unexpected result for central dc"
