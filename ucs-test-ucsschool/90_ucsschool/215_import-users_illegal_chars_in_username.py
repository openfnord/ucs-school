#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: remove illegal characters from username (Bug 42313)
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [42313]

import copy
import random
import string
import time

from ldap.filter import filter_format

import univention.testing.strings as uts
from ucsschool.importer.exceptions import FormatError
from ucsschool.importer.utils.username_handler import UsernameHandler
from ucsschool.lib.models.utils import ucr_username_max_length
from univention.testing import utils
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import UniqueObjectTester


class Test(UniqueObjectTester):
    def __init__(self):
        super(Test, self).__init__()
        self.ou_B = None
        self.ou_C = None

    def remove_bad_chars(self, name):
        allowed_chars = string.ascii_letters + string.digits + "."
        bad_chars = "".join(set(name).difference(set(allowed_chars)))
        if bad_chars:
            self.log.warning(
                "Removing disallowed characters %r from username %r.", "".join(sorted(bad_chars)), name
            )
        if name.startswith(".") or name.endswith("."):
            self.log.warning("Removing disallowed dot from start and end of username %r.", name)
            name = name.strip(".")
        if str is bytes:  # Py 2
            return name.translate(None, bad_chars)
        return name.translate(str.maketrans("", "", bad_chars))

    def test(self):  # formally test_create_with_illegal_chars_in_username()
        """
        Bug #42313: remove illegal characters from username
        * "Username must only contain numbers, letters and dots, and may not be 'admin'!"
        * but no dot at beginning
        """
        self.import_test1()
        self.import_test2()
        self.unit_tests()

    def import_test1(self):
        config = copy.deepcopy(self.default_config)
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("scheme:username:default", "<lastname>[ALWAYSCOUNTER]")
        config.update_entry("user_role", None)

        persons = []
        names = {}
        lastnames = []
        for role in ("student", "teacher", "teacher_and_staff"):
            random_puncts = list(string.punctuation)
            random.shuffle(random_puncts)
            lastnames_role = [
                "{}{}{}".format(uts.random_username(5), x, uts.random_username(5))
                for x in random_puncts[:4]
            ]
            lastnames_role.append(".{}".format(uts.random_username()))
            lastnames_role.append(".{}.{}.".format(uts.random_username(4), uts.random_username(4)))
            lastnames_role.append(
                "{}[{}]{}".format(uts.random_username(3), uts.random_username(3), uts.random_username(3))
            )
            lastnames_role.append(uts.random_username(40))
            self.unique_basenames_to_remove.extend(lastnames_role)
            self.log.info(
                "*** Importing new users with role %r and the following lastnames:\n%r",
                role,
                lastnames_role,
            )

            for lastname in lastnames_role:
                record_uid = uts.random_name()
                person = Person(self.ou_A.name, role)
                person.update(record_uid=record_uid, source_uid=source_uid, lastname=lastname)
                persons.append(person)
                names[person] = lastname
            lastnames.extend(lastnames_role)

        fn_csv = self.create_csv_file(person_list=persons, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv])
        utils.wait_for_replication()
        self.check_new_and_removed_users(len(persons), 0)

        # check usernames
        for person, lastname in names.items():
            if person.role == "student":
                username_length_length = ucr_username_max_length - 5
            else:
                username_length_length = ucr_username_max_length
            person.update(
                username=self.remove_bad_chars("{}1".format(lastname[: username_length_length - 3]))
            )
            utils.verify_ldap_object(
                person.dn, expected_attr={"uid": [person.username]}, strict=False, should_exist=True
            )
            # wait for creation before deletion:
            wait_for_drs_replication(filter_format("cn=%s", (person.username,)))

        # delete users
        self.log.info("*** Deleting all users...")
        fn_csv = self.create_csv_file(person_list=[], mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv])
        utils.wait_for_replication()
        timeout = 5
        while True:
            try:
                self.check_new_and_removed_users(0, len(persons))
                break
            except SystemExit:
                if timeout > 0:
                    self.log.error("Failed, sleeping 30s...")
                    time.sleep(30)
                    timeout -= 1
                else:
                    raise

        # recreate users, but move position of COUNTER variable
        self.log.info(
            "*** Importing users with the same lastnames, but move position of COUNTER variable..."
        )
        config.update_entry("scheme:username:default", "[ALWAYSCOUNTER]<lastname>")
        for person in persons:
            # Prevent 'The email address is already taken by another user. Please change the email
            # address.' because of slow s4 replication. Username is the same, so it doesn't change
            # what's tested.
            person.mail = "{}{}".format(uts.random_username(4), person.mail)
        fn_csv = self.create_csv_file(person_list=persons, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv])
        utils.wait_for_replication()
        for person, lastname in names.items():
            if person.role == "student":
                username_length_length = ucr_username_max_length - 5
            else:
                username_length_length = ucr_username_max_length
            person.update(
                username=self.remove_bad_chars("2{}".format(lastname[: username_length_length - 3]))
            )
            utils.verify_ldap_object(
                person.dn, expected_attr={"uid": [person.username]}, strict=False, should_exist=True
            )
        self.log.info("*** OK import_test1")

    def import_test2(self):
        """check username:allowed_special_chars (Bug #49259 / Bug #49260)"""
        self.log.info('*** Importing with username:allowed_special_chars="-+" (no dot)')

        config = copy.deepcopy(self.default_config)
        source_uid = "source_uid-%s" % (uts.random_string(),)
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("user_role", None)
        config.update_entry("username:allowed_special_chars", "-_")
        config.update_entry("scheme:username:default", "<firstname><lastname><:umlauts>")

        persons = []
        for role, schar in (
            ("teacher", "-"),
            ("student", "."),
            ("staff", "-"),
            ("teacher_and_staff", "_"),
        ):
            person = Person(self.ou_A.name, role)
            if role == "staff":
                firstname = schar + uts.random_name(random.randint(4, 8))
                lastname = uts.random_name(4) + schar
            else:
                firstname = (
                    uts.random_name(random.randint(2, 4)) + schar + uts.random_name(random.randint(2, 4))
                )
                lastname = uts.random_name(4)
            person.update(
                record_uid=uts.random_name(),
                source_uid=source_uid,
                username=None,
                firstname=firstname,
                lastname=lastname,
            )
            persons.append(person)
            self.log.info("*** Importing %r with firstname=%r lastname=%r", role, firstname, lastname)

        fn_csv = self.create_csv_file(person_list=persons, mapping=config["csv"]["mapping"])
        config.update_entry("input:filename", fn_csv)
        fn_config = self.create_config_json(config=config)
        self.save_ldap_status()
        self.run_import(["-c", fn_config, "-i", fn_csv])
        utils.wait_for_replication()
        self.check_new_and_removed_users(len(persons), 0)
        for person in persons:
            if person.role == "staff":
                person.update(username="{}{}".format(person.firstname, person.lastname).strip("-"))
                utils.verify_ldap_object(
                    person.dn, expected_attr={"uid": [person.username]}, strict=False, should_exist=True
                )
            elif person.role == "student":
                person.update(username="{}{}".format(person.firstname.replace(".", ""), person.lastname))
                utils.verify_ldap_object(
                    person.dn, expected_attr={"uid": [person.username]}, strict=False, should_exist=True
                )
            elif person.role in ("teacher", "teacher_and_staff"):
                person.update(username="{}{}".format(person.firstname, person.lastname))
                utils.verify_ldap_object(
                    person.dn, expected_attr={"uid": [person.username]}, strict=False, should_exist=True
                )
        self.log.info("*** OK import_test2")

    def unit_tests(self):
        self.log.info("*** Starting unit test for UsernameHandler.format_username() (1/5)")
        # prevent "InitialisationError: Configuration not yet loaded."
        from ucsschool.importer.utils.shell import config as _config

        assert _config

        unh = UsernameHandler(15)  # 20 - len("exam-")
        name12 = uts.random_username(12)  # 15 - 3
        usernames = {
            ".abc.def.": "abc.def",
            "...abc...def...": "abc...def",
            "": "",
            "..[ALWAYSCOUNTER]..": "",
            "[ALWAYSCOUNTER]": "",
            "[FOObar]": "FOObar",
            "{}.[COUNTER2]".format(name12): name12,
            ".": "",
            "M" * 14 + "." + "A": "M" * 14,
        }
        for input_name, expected in usernames.items():
            try:
                out = unh.format_username(input_name)
                self.unique_basenames_to_remove.append(expected)
                if out != expected:
                    self.fail(
                        "UsernameHandler.format_username(%r) returned %r, expected %r."
                        % (input_name, out, expected)
                    )
            except FormatError:
                if expected is not None:
                    self.fail(
                        "UsernameHandler.format_username(%r) raise a FormatError, expected it to return "
                        "%r." % (input_name, expected)
                    )
                continue
        self.log.info("*** Starting unit test for UsernameHandler.format_username() (2/5)")
        for _i in range(1000):
            name = uts.random_username(15)
            self.unique_basenames_to_remove.append(name)
            out = unh.format_username(name)
            if out != name:
                self.fail("UsernameHandler.format_username(%r) returned %r." % (name, out))
        self.log.info("*** Starting unit test for UsernameHandler.format_username() (3/5)")
        for _i in range(1000):
            name = uts.random_name(20)
            self.unique_basenames_to_remove.append(name)
            out = unh.format_username(name)
            if out.startswith(".") or out.endswith(".") or len(out) > 15:
                self.fail("UsernameHandler.format_username(%r) returned %r." % (name, out))
        self.log.info("*** Starting unit test for UsernameHandler.format_username() (4/5)")
        for _i in range(1000):
            name = uts.random_name_special_characters(20)
            if str is bytes:  # Py 2
                name = name.translate(None, "[]")
            else:
                name = name.translate(str.maketrans("", "", "[]"))  # those are reserved for counter vars
            self.unique_basenames_to_remove.append(name)
            out = unh.format_username(name)
            if out.startswith(".") or out.endswith(".") or len(out) > 15:
                self.fail("UsernameHandler.format_username(%r) returned %r." % (name, out))
        self.log.info("*** Starting unit test for UsernameHandler.format_username() (5/5)")
        usernames = [
            ("Max[ALWAYSCOUNTER].Mustermann", "Max1.Mustermann"),
            ("Max[ALWAYSCOUNTER].Mustermann", "Max2.Mustermann"),
            ("Max[ALWAYSCOUNTER].Mustermann", "Max3.Mustermann"),
            ("Max[ALWAYSCOUNTER].Mustermann", "Max4.Mustermann"),
            ("Maria[ALWAYSCOUNTER].Musterfrau", "Maria1.Musterfrau"),
            ("Moritz[COUNTER2]", "Moritz"),
            ("Moritz[COUNTER2]", "Moritz2"),
        ]
        self.unique_basenames_to_remove.extend(["Max.Mustermann", "Maria.Musterfrau", "Moritz"])
        unh = UsernameHandler(20)
        for input_name, expected in usernames:
            out = unh.format_username(input_name)
            if out != expected:
                self.fail(
                    "UsernameHandler.format_username(%r) returned %r, expected %r."
                    % (input_name, out, expected)
                )


def main():
    tester = Test()
    try:
        tester.run()
    finally:
        tester.cleanup()


if __name__ == "__main__":
    main()
