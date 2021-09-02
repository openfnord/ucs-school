#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: test diffent username lengths
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [45577, 47222]

import copy
import random

from ldap.filter import filter_format

import univention.config_registry
import univention.testing.strings as uts
from ucsschool.lib.models.utils import ucr_username_max_length
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester, ImportException


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):
        """
        Bug #45577, #47222: allow import with usernames longer than 15 characters
        """
        source_uid = "source_uid-{}".format(uts.random_string())
        config = copy.deepcopy(self.default_config)
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("scheme:username:default", "<:umlauts><firstname:lower><lastname:lower>"),
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)
        del config["csv"]["mapping"]["E-Mail"]

        def test_default_settings():
            self.log.info("*** 1/4 Importing a user from each role (default settings)...")

            if self.ucr.get("ucsschool/username/max_length") is not None:
                univention.config_registry.handler_unset(["ucsschool/username/max_length"])

            person_list = []
            for role in ("student", "teacher", "staff", "teacher_and_staff"):
                person = Person(self.ou_A.name, role)
                record_uid = "record_uid-%s" % (uts.random_string(),)
                person.update(
                    record_uid=record_uid,
                    source_uid=source_uid,
                    firstname=uts.random_username(),
                    lastname=uts.random_username(),
                    username=None,  # let the import generate the attributes value
                    mail=None,  # let the import generate the attributes value
                )
                person_list.append(person)
            fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
            config.update_entry("input:filename", fn_csv)
            fn_config = self.create_config_json(values=config)
            self.save_ldap_status()
            self.run_import(["-c", fn_config])
            self.check_new_and_removed_users(4, 0)

            filter_src = filter_format(
                "(objectClass=ucsschoolType)(ucsschoolSourceUID=%s)", (source_uid,)
            )
            for person in person_list:
                filter_s = "(&{}{})".format(
                    filter_src, filter_format("(ucsschoolRecordUID=%s)", (person.record_uid,))
                )
                res = self.lo.search(filter=filter_s)
                if len(res) != 1:
                    self.fail(
                        "Search with filter={!r} did not return 1 result:\n{}".format(
                            filter_s, "\n".join(repr(res))
                        )
                    )
                dn = res[0][0]
                username = res[0][1]["uid"][0].decode("UTF-8")
                self.log.debug(
                    "*** role=%r username=%r len(username)=%r dn=%r",
                    person.role,
                    username,
                    len(username),
                    dn,
                )
                # default configuration
                if person.role == "student":
                    exp_len = ucr_username_max_length - 5
                else:
                    exp_len = ucr_username_max_length

                if len(username) != exp_len:
                    self.fail(
                        "Length of username {!r} of {!r} is {}, expected {} (dn={!r}).".format(
                            username, person.role, len(username), exp_len, dn
                        )
                    )
                else:
                    self.log.info(
                        "*** OK: Username %r of %r has expected length %r.",
                        username,
                        person.role,
                        exp_len,
                    )

            self.log.info("*** OK 1/4: All %r users were created correctly.", len(person_list))

        def test_custom_settings():
            self.log.info(
                "*** 2/4: Importing a user from each role (custom username:max_length settings)..."
            )

            if self.ucr.get("ucsschool/username/max_length") is not None:
                univention.config_registry.handler_unset(["ucsschool/username/max_length"])

            username_lengths = {
                "student": random.randint(5, 15),  # keep in legal range
                "teacher": random.randint(5, 20),
                "staff": random.randint(5, 20),
                "teacher_and_staff": random.randint(5, 20),
            }
            # use default values for two roles
            for _ in range(2):
                role_uses_default = random.choice(list(username_lengths.keys()))
                del username_lengths[role_uses_default]
            # min length is 4, if student is unset and default is used, it must be at least
            # 4 + len('exam-') = 9
            username_lengths["default"] = random.randint(9, 20)
            self.log.info("*** username_lengths=%r", username_lengths)
            for k, v in username_lengths.items():
                config.update_entry("username:max_length:{}".format(k), v)
            source_uid = "source_uid-{}".format(uts.random_string())
            config.update_entry("source_uid", source_uid)

            person_list = list()
            for role in ("student", "teacher", "staff", "teacher_and_staff"):
                person = Person(self.ou_A.name, role)
                record_uid = "record_uid-%s" % (uts.random_string(),)
                person.update(
                    record_uid=record_uid,
                    source_uid=source_uid,
                    firstname=uts.random_username(20),
                    lastname=uts.random_username(20),
                    username=None,
                    mail=None,
                )
                person_list.append(person)
            fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
            config.update_entry("input:filename", fn_csv)
            fn_config = self.create_config_json(values=config)
            self.save_ldap_status()
            self.run_import(["-c", fn_config])
            self.check_new_and_removed_users(4, 0)

            filter_src = filter_format(
                "(objectClass=ucsschoolType)(ucsschoolSourceUID=%s)", (source_uid,)
            )
            for person in person_list:
                filter_s = "(&{}{})".format(
                    filter_src, filter_format("(ucsschoolRecordUID=%s)", (person.record_uid,))
                )
                res = self.lo.search(filter=filter_s)
                if len(res) != 1:
                    self.fail(
                        "Search with filter={!r} did not return 1 result:\n{}".format(
                            filter_s, "\n".join(repr(res))
                        )
                    )
                dn = res[0][0]
                username = res[0][1]["uid"][0].decode("UTF-8")
                self.log.debug(
                    "*** role=%r username=%r len(username)=%r dn=%r",
                    person.role,
                    username,
                    len(username),
                    dn,
                )
                # special configuration with lower max_length
                try:
                    exp_len = username_lengths[person.role]
                except KeyError:
                    exp_len = username_lengths["default"]
                    if person.role == "student":
                        exp_len -= 5

                if len(username) != exp_len:
                    self.fail(
                        "Length of username {!r} of {!r} is {}, expected {} (dn={!r}).".format(
                            username, person.role, len(username), exp_len, dn
                        )
                    )
                else:
                    self.log.info(
                        "*** OK: Username %r of %r has expected length %r.",
                        username,
                        person.role,
                        exp_len,
                    )

            self.log.info("*** OK 2/4: All %r users were created correctly.", len(person_list))

        def test_settings_higher_than_20(set_ucr, counter):
            self.log.info(
                "*** %s: Importing a user from each role (custom username:max_length settings higher "
                "than 20) and UCR is%s set...",
                counter,
                "" if set_ucr else " NOT",
            )

            username_lengths = {
                "student": random.randint(31, 55),
                "teacher": random.randint(31, 55),
                "staff": random.randint(31, 55),
                "teacher_and_staff": random.randint(31, 55),
            }
            # use default values for two roles
            for _ in range(2):
                role_uses_default = random.choice(list(username_lengths.keys()))
                del username_lengths[role_uses_default]
                try:
                    del config["username"]["max_length"][role_uses_default]
                except KeyError:
                    pass
            username_lengths["default"] = random.randint(21, 30)
            self.log.info("*** username_lengths=%r", username_lengths)
            for k, v in username_lengths.items():
                config.update_entry("username:max_length:{}".format(k), v)
            source_uid = "source_uid-{}".format(uts.random_string())
            config.update_entry("source_uid", source_uid)

            person_list = []
            for role in ("student", "teacher", "staff", "teacher_and_staff"):
                person = Person(self.ou_A.name, role)
                record_uid = "record_uid-%s" % (uts.random_string(),)
                person.update(
                    record_uid=record_uid,
                    source_uid=source_uid,
                    firstname=uts.random_username(30),
                    lastname=uts.random_username(30),
                    username=None,
                    mail=None,
                )
                person_list.append(person)
            fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
            config.update_entry("input:filename", fn_csv)
            if set_ucr:
                univention.config_registry.handler_set(["ucsschool/username/max_length=60"])
            else:
                if self.ucr.get("ucsschool/username/max_length") is not None:
                    univention.config_registry.handler_unset(["ucsschool/username/max_length"])
            ucr_username_max_length = int(self.ucr.get("ucsschool/username/max_length", 20))
            self.log.info(
                "*** UCRV ucsschool/username/max_length = %r",
                self.ucr.get("ucsschool/username/max_length"),
            )
            self.log.info("*** ucr_username_max_length = %r", ucr_username_max_length)
            fn_config = self.create_config_json(values=config)
            self.save_ldap_status()
            try:
                self.run_import(["-c", fn_config])
                if not set_ucr:
                    self.fail(
                        "Import should have failed, because UCRV was not set and username:max_length:* "
                        "to high."
                    )
            except ImportException:
                if not set_ucr:
                    self.log.info("OK: Import failed as expected.")
                    return
            self.check_new_and_removed_users(4, 0)

            filter_src = filter_format(
                "(objectClass=ucsschoolType)(ucsschoolSourceUID=%s)", (source_uid,)
            )
            for person in person_list:
                filter_s = "(&{}{})".format(
                    filter_src, filter_format("(ucsschoolRecordUID=%s)", (person.record_uid,))
                )
                res = self.lo.search(filter=filter_s)
                if len(res) != 1:
                    self.fail(
                        "Search with filter={!r} did not return 1 result:\n{}".format(
                            filter_s, "\n".join(repr(res))
                        )
                    )
                dn = res[0][0]
                username = res[0][1]["uid"][0].decode("UTF-8")
                self.log.debug(
                    "*** role=%r username=%r len(username)=%r dn=%r",
                    person.role,
                    username,
                    len(username),
                    dn,
                )
                try:
                    exp_len = username_lengths[person.role]
                except KeyError:
                    exp_len = username_lengths["default"]
                    if person.role == "student":
                        exp_len -= 5

                if len(username) != exp_len:
                    self.fail(
                        "Length of username {!r} of {!r} is {}, expected {} (dn={!r}).".format(
                            username, person.role, len(username), exp_len, dn
                        )
                    )
                else:
                    self.log.info(
                        "*** OK: Username %r of %r has expected length %r.",
                        username,
                        person.role,
                        exp_len,
                    )

            self.log.info("*** OK %s: All %r users were created correctly.", counter, len(person_list))

        test_default_settings()
        test_custom_settings()
        test_settings_higher_than_20(
            False, "3/4"
        )  # without setting the UCRV, settings > 20 should be ignored
        test_settings_higher_than_20(True, "4/4")


if __name__ == "__main__":
    Test().run()
