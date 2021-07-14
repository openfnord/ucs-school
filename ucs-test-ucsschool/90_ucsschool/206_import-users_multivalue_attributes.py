#!/usr/share/ucs-test/runner python
## -*- coding: utf-8 -*-
## desc: Test creation of multi-value fields (Bug #41471)
## tags: [apptest,ucsschool,ucsschool_import1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [41471]

import copy
import pprint

import univention.testing.strings as uts
from univention.testing.ucsschool.importusers import Person
from univention.testing.ucsschool.importusers_cli_v2 import CLI_Import_v2_Tester


class MultiPerson(Person):
    def __init__(self, school, role):
        Person.__init__(self, school, role)
        self.mailAlternativeAddress = "%s@example.com;%s@example.com;%s@example.com" % (
            uts.random_name(),
            uts.random_name(),
            uts.random_name(),
        )

    def map_to_dict(self, value_map):
        result = Person.map_to_dict(self, value_map)
        result[value_map.get("mailAlternativeAddress", "__EMPTY__")] = self.mailAlternativeAddress
        return result

    def expected_attributes(self):
        result = Person.expected_attributes(self)
        result["mailAlternativeAddress"] = self.mailAlternativeAddress.split(",")


class Test(CLI_Import_v2_Tester):
    ou_B = None
    ou_C = None

    def test(self):  # formally test_multivalue_attributes()
        """
        Test creation of multi-value fields (Bug #41471).
        - mailAlternativeAddress is filled with multiple strings
        """
        source_uid = "source_uid-%s" % (uts.random_string(),)

        config = copy.deepcopy(self.default_config)
        config.update_entry("source_uid", source_uid)
        config.update_entry("csv:incell-delimiter:default", ";")
        config.update_entry("csv:mapping:Benutzername", "name")
        config.update_entry("csv:mapping:record_uid", "record_uid")
        config.update_entry("csv:mapping:mailAlternativeAddress", "mailAlternativeAddress")
        config.update_entry("csv:mapping:role", "__role")
        config.update_entry("source_uid", source_uid)
        config.update_entry("user_role", None)

        self.log.info("*** Importing a new user of each role role with multivalue attributes...")
        person_list = []
        for role in ("student", "teacher", "staff", "teacher_and_staff"):
            # create person with 3 alternative mail addresses
            person = MultiPerson(self.ou_A.name, role)
            person.update(record_uid=person.username, source_uid=source_uid)
            person_list.append(person)

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])

        for person in person_list:
            self.log.debug(
                "User object %r:\n%s",
                person.dn,
                pprint.PrettyPrinter(indent=2).pformat(self.lo.get(person.dn)),
            )
            person.verify()
            # modify person and set 1 alternative mail address
            person.update(mailAlternativeAddress="%s@example.com" % (uts.random_name(),))

        fn_csv = self.create_csv_file(person_list=person_list, mapping=config["csv"]["mapping"])
        fn_config = self.create_config_json(config=config)
        self.run_import(["-c", fn_config, "-i", fn_csv])

        for person in person_list:
            self.log.debug(
                "User object %r:\n%s",
                person.dn,
                pprint.PrettyPrinter(indent=2).pformat(self.lo.get(person.dn)),
            )
            person.verify()


if __name__ == "__main__":
    Test().run()
