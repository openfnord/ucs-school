#!/usr/share/ucs-test/runner python3
## desc: Test user creation denial on Replica Directory Node with Samba4.
## bugs: [34217, 37700]
## roles: [domaincontroller_slave]
## packages: [univention-samba4]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: careful
## versions:
##  4.0-0: skip
##  4.0-1: skip
##  3.2-5: skip
##  4.1-2: fixed

from __future__ import print_function

from re import compile as regex_compile, search
from sys import exit

import workaround
import univention.testing.utils as utils
from univention.testing.strings import random_string
from univention.testing.ucsschool.test_samba4 import TestSamba4


class TestS4SlaveUserCreationDenied(TestSamba4):
    def __init__(self):
        """
        Test class constructor.
        """
        super(TestS4SlaveUserCreationDenied, self).__init__()

        self.credentials = []  # for use with 'samba-tool'
        self.remove_user = ""  # in case user is created, will store username
        self.fail_pattern = regex_compile("univention_samaccountname_ldap_check:.* is disabled")

    def delete_samba4_user(self):
        """
        Tries to remove the user with username 'self.remove_user'
        using 'samba-tool'.
        """
        print("\nAttempting to remove a user with a username '%s' using 'samba-tool'" % self.remove_user)

        cmd = ["samba-tool", "user", "delete", self.remove_user]
        cmd.extend(self.credentials)

        stdout, stderr = self.create_and_run_process(cmd)
        if stderr:
            print("An error occured during '%s' user deletion: '%s'" % (self.remove_user, stderr))
        if stdout:
            print("The 'samba-tool' has produced the following output: '%s'" % stdout.rstrip())

    def create_samba4_user(self, creation_options):
        """
        Tries to create a user with a random username and a list of given
        'creation_options'. Fails the test if user creation succeeds or if
        the message printed to STDERR does not match the 'self.fail_pattern'.
        """
        username = "ucs_test_school_user_" + random_string(8)
        print(
            "\nAttempting to create a user with a username '%s' and options: %s"
            % (username, creation_options)
        )

        cmd = ["samba-tool", "user", "create", username]
        cmd.extend(creation_options)
        cmd.extend(self.credentials)

        stdout, stderr = self.create_and_run_process(cmd)
        if stdout:
            print(("The 'samba-tool' produced the following output to STDOUT:", stdout))

            if bool(search(".*User .* created successfully.*", stdout)):
                self.remove_user = username
                utils.fail(
                    "The creation of user '%s' succeded, while should be disabled on Replica Directory Node with "
                    "Samba4" % username
                )
        stderr = workaround.filter_deprecated(stderr)
        if not stderr.strip():
            utils.fail(
                "Expecting the user creation to fail, however, the 'samba-tool' did not produce any "
                "output to STDERR."
            )


        if not bool(self.fail_pattern.match(stderr)):
            utils.fail(
                "The 'samba-tool' output produced to STDERR does not match the '%s' pattern. STDERR: "
                "'%s'" % (self.fail_pattern.pattern, stderr)
            )

    def main(self):
        """
        Test that user objects creation is blocked on S4 Replica Directory Node.
        """
        try:
            self.get_ucr_test_credentials()
            self.credentials = ["--username=" + self.admin_username, "--password=" + self.admin_password]

            self.create_samba4_user(["Foo1" + random_string()])  # gen-d pass
            self.create_samba4_user(["--random-password"])  # tool's random
        finally:
            if self.remove_user:
                self.delete_samba4_user()


if __name__ == "__main__":
    TestUserCreationDenied = TestS4SlaveUserCreationDenied()
    exit(TestUserCreationDenied.main())
