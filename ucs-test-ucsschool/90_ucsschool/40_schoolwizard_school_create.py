#!/usr/share/ucs-test/runner pytest-3 -s -l -v
# -*- coding: utf-8 -*-
## desc: schoolwizards/school/create
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages:
##   - ucs-school-master | ucs-school-singlemaster

import pytest

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm
import univention.testing.utils as utils
from univention.testing.ucsschool.ucs_test_school import UCSTestSchool, get_ucsschool_logger
from univention.testing.umc import Client

ucr = ucr_test.UCSTestConfigRegistry()
ucr.load()


def schoolwizards_schools_create(ou_name, dc_name=None, dc_name_administrative=None):
    jsonargs = [{"object": {"display_name": ou_name, "name": ou_name}}]
    if dc_name:
        jsonargs[0]["object"]["dc_name"] = dc_name
    if dc_name_administrative:
        jsonargs[0]["object"]["dc_name_administrative"] = dc_name_administrative

    connection = Client.get_test_connection()
    assert (
        connection.umc_command("schoolwizards/schools/create", jsonargs, "schoolwizards/schools").result[
            0
        ]
        is True
    )


def test_schoolwizard_school_create():
    with UCSTestSchool() as testschool:
        logger = get_ucsschool_logger()
        msg = "new random OU, no DC specified"
        logger.info("---------------------------[%s]---------------------------", msg)
        ou_name = uts.random_string()
        dc_name = "dc%s" % ou_name
        testschool._cleanup_ou_names.add(ou_name)
        schoolwizards_schools_create(ou_name)
        dc_dn = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (dc_name, testschool.get_ou_base_dn(ou_name))
        if testschool.ucr.is_true("ucsschool/singlemaster", False):
            # on singlemaster systems a seperate DC should not be created
            utils.verify_ldap_object(
                dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=False
            )
        else:
            utils.verify_ldap_object(
                dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True
            )
            for grp_dn in (
                "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
                "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            ):
                grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
                utils.verify_ldap_object(
                    grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
                )

        msg = "new random OU, new random DC"
        logger.info("---------------------------[%s]---------------------------", msg)
        ou_name = uts.random_string()
        dc_name = uts.random_string()
        testschool._cleanup_ou_names.add(ou_name)
        schoolwizards_schools_create(ou_name, dc_name)
        dc_dn = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (dc_name, testschool.get_ou_base_dn(ou_name))
        utils.verify_ldap_object(dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True)
        for grp_dn in (
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
            )

        msg = "new random OU, existing DC in other OU"
        logger.info("---------------------------[%s]---------------------------", msg)
        ou_name = uts.random_string()
        testschool._cleanup_ou_names.add(ou_name)
        schoolwizards_schools_create(ou_name, dc_name)
        # reusing first DC
        utils.verify_ldap_object(dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True)
        for grp_dn in (
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
            )

        msg = "new random OU with existing DC in cn=computers,BASEDN"
        logger.info("---------------------------[%s]---------------------------", msg)
        with univention.testing.udm.UCSTestUDM() as udm:
            logger.info("*** Stopping existing UDM CLI server")
            udm.stop_cli_server()

            # create new DC
            dc_name = uts.random_string()
            dc_dn = udm.create_object(
                "computers/domaincontroller_slave",
                position="cn=computers,%s" % (ucr.get("ldap/base"),),
                name=dc_name,
            )
            utils.verify_ldap_object(
                dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True
            )

            ou_name = uts.random_string()
            testschool._cleanup_ou_names.add(ou_name)
            schoolwizards_schools_create(ou_name, dc_name)

            utils.verify_ldap_object(
                dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True
            )
            for grp_dn in (
                "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
                "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            ):
                grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
                utils.verify_ldap_object(
                    grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
                )

        msg = "new random OU, new random DC and then try to add a second new random DC"
        logger.info("---------------------------[%s]---------------------------", msg)
        ou_name = uts.random_string()
        dc_name = uts.random_string()
        testschool._cleanup_ou_names.add(ou_name)
        schoolwizards_schools_create(ou_name, dc_name)
        dc_dn = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (dc_name, testschool.get_ou_base_dn(ou_name))
        utils.verify_ldap_object(dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True)
        for grp_dn in (
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
            )

        dc_name = uts.random_string()
        with pytest.raises(AssertionError):
            schoolwizards_schools_create(ou_name, dc_name)
        dc_dn = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (dc_name, testschool.get_ou_base_dn(ou_name))
        utils.verify_ldap_object(dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True)
        for grp_dn in (
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
            )

        msg = "new random OU, new random administrative DC"
        logger.info("---------------------------[%s]---------------------------", msg)
        ou_name = uts.random_string()
        dc_name_administrative = uts.random_string()
        dc_name = uts.random_string()
        testschool._cleanup_ou_names.add(ou_name)
        schoolwizards_schools_create(ou_name, dc_name, dc_name_administrative)
        dc_dn = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (dc_name, testschool.get_ou_base_dn(ou_name))
        dc_dn_administrative = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (
            dc_name_administrative,
            testschool.get_ou_base_dn(ou_name),
        )
        utils.verify_ldap_object(
            dc_dn_administrative,
            expected_attr={"cn": [dc_name_administrative]},
            strict=True,
            should_exist=True,
        )
        for grp_dn in (
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
            )
        for grp_dn in (
            "cn=OU%(ou)s-DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn,
                expected_attr={"uniqueMember": [dc_dn_administrative]},
                strict=False,
                should_exist=True,
            )

        msg = (
            "new random OU, new random educational DC and then try to add a second new random "
            "administrative DC"
        )
        logger.info("---------------------------[%s]---------------------------", msg)
        ou_name = uts.random_string()
        dc_name = uts.random_string()
        testschool._cleanup_ou_names.add(ou_name)
        schoolwizards_schools_create(ou_name, dc_name)
        dc_dn = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (dc_name, testschool.get_ou_base_dn(ou_name))
        utils.verify_ldap_object(dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True)
        for grp_dn in (
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
            )

        dc_name_administrative = uts.random_string()
        with pytest.raises(AssertionError):
            schoolwizards_schools_create(ou_name, dc_name, dc_name_administrative)
        dc_dn_administrative = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (
            dc_name_administrative,
            testschool.get_ou_base_dn(ou_name),
        )
        utils.verify_ldap_object(
            dc_dn_administrative,
            expected_attr={"cn": [dc_name_administrative]},
            strict=True,
            should_exist=True,
        )
        for grp_dn in (
            "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
            )
        for grp_dn in (
            "cn=OU%(ou)s-DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
            "cn=DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
        ):
            grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
            utils.verify_ldap_object(
                grp_dn,
                expected_attr={"uniqueMember": [dc_dn_administrative]},
                strict=False,
                should_exist=True,
            )

        msg = "new random OU with existing administrative DC in cn=computers,BASEDN"
        logger.info("---------------------------[%s]---------------------------", msg)
        with univention.testing.udm.UCSTestUDM() as udm:
            logger.info("*** Stopping existing UDM CLI server")
            udm.stop_cli_server()

            # create new DC
            dc_name = uts.random_string()
            dc_name_administrative = uts.random_string()
            dc_dn_administrative = udm.create_object(
                "computers/domaincontroller_slave",
                position="cn=computers,%s" % (ucr.get("ldap/base"),),
                name=dc_name_administrative,
            )
            utils.verify_ldap_object(
                dc_dn_administrative,
                expected_attr={"cn": [dc_name_administrative]},
                strict=True,
                should_exist=True,
            )

            ou_name = uts.random_string()
            testschool._cleanup_ou_names.add(ou_name)
            schoolwizards_schools_create(ou_name, dc_name, dc_name_administrative)

            dc_dn = "cn=%s,cn=dc,cn=server,cn=computers,%s" % (
                dc_name,
                testschool.get_ou_base_dn(ou_name),
            )
            utils.verify_ldap_object(
                dc_dn, expected_attr={"cn": [dc_name]}, strict=True, should_exist=True
            )
            for grp_dn in (
                "cn=OU%(ou)s-DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
                "cn=DC-Edukativnetz,cn=ucsschool,cn=groups,%(basedn)s",
            ):
                grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
                utils.verify_ldap_object(
                    grp_dn, expected_attr={"uniqueMember": [dc_dn]}, strict=False, should_exist=True
                )
            for grp_dn in (
                "cn=OU%(ou)s-DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
                "cn=DC-Verwaltungsnetz,cn=ucsschool,cn=groups,%(basedn)s",
            ):
                grp_dn = grp_dn % {"ou": ou_name, "basedn": ucr.get("ldap/base")}
                utils.verify_ldap_object(
                    grp_dn,
                    expected_attr={"uniqueMember": [dc_dn_administrative]},
                    strict=False,
                    should_exist=True,
                )
