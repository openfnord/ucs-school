#!/usr/share/ucs-test/runner python3
## desc: Fix broken domaincontroller slave objects via fix_ucsschool_slaves
## roles: [domaincontroller_master]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## packages: [ucs-school-import,ucs-school-master]

from __future__ import absolute_import, print_function

import subprocess
import sys

import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils


def main():
    with utu.UCSTestSchool() as schoolenv:
        school, oudn = schoolenv.create_ou()

        lo = schoolenv.open_ldap_connection()
        result = lo.search(base=oudn, attr=["ucsschoolHomeShareFileServer"])
        try:
            dcdn = result[0][1].get("ucsschoolHomeShareFileServer", [None])[0]
        except IndexError:
            dcdn = None
        assert dcdn is not None, "Cannot determine DN of school server"

        result = lo.search(base=dcdn)
        attrs = result[0][1]
        if "univentionWindows" in attrs.get("objectClass", []) or "ucsschoolComputer" in attrs.get(
            "objectClass", []
        ):
            print("WARNING: domaincontroller_slave's objectclass already broken!")
        for value in attrs.get("ucsschoolRole", []):
            if value.startswith("win_computer:school:"):
                print(
                    "WARNING: domaincontroller_slave's ucschoolRole already broken! {!r}".format(value)
                )

        lo.modify(
            dcdn,
            [
                [
                    "objectClass",
                    attrs.get("objectClass", []),
                    list(
                        set(attrs.get("objectClass", []))
                        | {"univentionWindows", "ucsschoolComputer"}
                    ),
                ],
                [
                    "ucsschoolRole",
                    attrs.get("ucsschoolRole", []),
                    list(
                        set(attrs.get("ucsschoolRole", []))
                        | {"win_computer:school:{}".format(school)}
                    ),
                ],
            ],
        )

        print("Starting fix_ucschool_slaves...")
        sys.stdout.flush()
        sys.stderr.flush()
        subprocess.call(["/usr/share/ucs-school-import/scripts/fix_ucsschool_slaves", "--verbose"])

        broken = False
        result = lo.search(base=dcdn)
        if "univentionWindows" in result[0][1].get("objectClass", []) or "ucsschoolComputer" in result[
            0
        ][1].get("objectClass", []):
            print("ERROR: domaincontroller_slave's objectclass is not fixed!")
            broken = True
        for value in result[0][1].get("ucsschoolRole", []):
            if value.startswith("win_computer:school:"):
                print("ERROR: domaincontroller_slave's ucschoolRole is not fixed! {!r}".format(value))
                broken = True
        if broken:
            utils.fail("At least one attribute is not fixed!")


if __name__ == "__main__":
    main()
