#!/usr/share/ucs-test/runner python
## desc: Check NFS option of class shares
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-import, ucs-school-singlemaster]
## bugs: [38641]

from __future__ import print_function

import ldap
from ldap.filter import filter_format

import ucsschool.lib.models.utils
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.config_registry import handler_set, handler_unset


def verify_nfs_access(class_name, expected_nfs_option):
    try:
        attr = utils.get_ldap_connection().search(
            filter=filter_format("(&(objectClass=univentionShare)(cn=%s))", (class_name,)),
            attr=["objectClass"],
        )[0][1]
    except (ldap.NO_SUCH_OBJECT, IndexError):
        utils.fail("Share object for class %r not found!" % (class_name,))

    nfs_enabled = "univentionShareNFS" in attr.get("objectClass", [])
    print(
        "*** Share %r: NFS option enabled=%r   expected=%r"
        % (
            class_name,
            nfs_enabled,
            expected_nfs_option,
        )
    )
    if expected_nfs_option != nfs_enabled:
        utils.fail("Unexpected NFS option state!")


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with utu.UCSTestSchool() as schoolenv:
            school, oudn = schoolenv.create_ou(name_edudc=ucr.get("hostname"))

            print("--------YES------------------------------------------------------------")
            handler_set(["ucsschool/default/share/nfs=yes"])
            # workaround: manual reload of UCR instance in UCS@school lib:
            ucsschool.lib.models.utils.ucr.load()
            class_name, class_dn = schoolenv.create_school_class(school)
            verify_nfs_access(class_name, True)

            print("--------NO------------------------------------------------------------")
            handler_set(["ucsschool/default/share/nfs=no"])
            # workaround: manual reload of UCR instance in UCS@school lib:
            ucsschool.lib.models.utils.ucr.load()
            class_name, class_dn = schoolenv.create_school_class(school)
            verify_nfs_access(class_name, False)

            print("--------EMPTY------------------------------------------------------------")
            handler_unset(["ucsschool/default/share/nfs"])
            # workaround: manual reload of UCR instance in UCS@school lib:
            ucsschool.lib.models.utils.ucr.load()
            class_name, class_dn = schoolenv.create_school_class(school)
            verify_nfs_access(class_name, False)


if __name__ == "__main__":
    main()
