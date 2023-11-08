#!/usr/share/ucs-test/runner python3
## -*- coding: utf-8 -*-
## desc: Test configurability feature of import factory
## tags: [apptest,ucsschool,ucsschool_base1]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - ucs-school-import
## bugs: [41469]

import json
import os.path
import random
import shutil
import subprocess
import sys
import tempfile
import time
from csv import QUOTE_ALL, DictReader, DictWriter, excel, reader as csvreader

import pytest

import univention.testing.strings as uts
from ucsschool.importer.utils.test_user_creator import TestUserCreator as _TestUserCreator
from ucsschool.importer.writer.test_user_csv_exporter import TestUserCsvExporter as _TestUserCsvExporter
from univention.admin.uldap import explodeDn
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.ucsschool.ucs_test_school import UCSTestSchool, get_ucsschool_logger
from univention.testing.udm import UCSTestUDM

CONFIG = os.path.join(os.path.dirname(__file__), "factoryconftest.json")


class Bunch(object):
    def __init__(self, **kwds):
        self.__dict__.update(kwds)


class Test_FactoryConf(object):
    @pytest.fixture(scope="class", autouse=True)
    def _setup(self, request):
        self = request.cls
        self.tmpdir = tempfile.mkdtemp(prefix="113factest.", dir="/tmp")
        self.ldap_status = None
        self.ou_name = None
        self.ou_dn = None
        self.ou_name2 = None
        self.ou_dn2 = None
        self.lo = None
        self.logger = get_ucsschool_logger()
        self.test_user_exporter = _TestUserCsvExporter()
        self._test_user_creator = None
        try:
            with UCSTestConfigRegistry() as ucr, UCSTestSchool() as schoolenv, UCSTestUDM() as udm:
                if not ucr.get("mail/hosteddomains"):
                    self.logger.info("\n\n*** Creating mail domain...\n")
                    udm.create_object(
                        "mail/domain",
                        position="cn=domain,cn=mail,{}".format(ucr["ldap/base"]),
                        name="{}.{}.{}".format(uts.random_name(), uts.random_name(), uts.random_name()),
                    )

                self.logger.info("\n\n*** Creating OUs...\n")
                (self.ou_name, self.ou_dn), (self.ou_name2, self.ou_dn2) = schoolenv.create_multiple_ous(
                    2, name_edudc=ucr.get("hostname")
                )
                self.lo = schoolenv.open_ldap_connection(admin=True)
                self._test_user_creator = _TestUserCreator(
                    [self.ou_name, self.ou_name2],
                    staff=2,
                    students=2,
                    teachers=2,
                    staffteachers=2,
                    classes=2,
                    inclasses=2,
                    schools=2,
                )
                self._test_user_creator.make_classes()
                yield
        finally:
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    def save_ldap_status(self):
        self.logger.debug("Saving LDAP status...")
        self.ldap_status = set(self.lo.searchDn())

    def diff_ldap_status(self):
        self.logger.debug("Reading LDAP status for check differences...")
        new_ldap_status = set(self.lo.searchDn())
        new_objects = new_ldap_status - self.ldap_status
        removed_objects = self.ldap_status - new_ldap_status
        self.logger.debug("LDAP status diffed.")
        self.logger.debug("New objects: %r", new_objects)
        self.logger.debug("Removed objects: %r", removed_objects)
        return Bunch(new=new_objects, removed=removed_objects)

    def check_new_and_removed_users(self, exp_new, exp_removed):
        ldap_diff = self.diff_ldap_status()
        new_users = [x for x in ldap_diff.new if x.startswith("uid=")]
        if len(new_users) != exp_new:
            self.logger.error(
                "Invalid number of new users (expected %d, found %d)! Found new objects: %r",
                exp_new,
                len(new_users),
                new_users,
            )
        assert len(new_users) == exp_new
        removed_users = [x for x in ldap_diff.removed if x.startswith("uid=")]
        if len(removed_users) != exp_removed:
            self.logger.error(
                "Invalid number of removed users (expected %d, found %d)! Removed objects: %r",
                exp_removed,
                len(removed_users),
                removed_users,
            )
        assert len(removed_users) == exp_removed

    def run_import(self, args, fail_on_error=True):
        cmd = ["/usr/share/ucs-school-import/scripts/ucs-school-user-import"] + args
        self.logger.info("Starting import: %r", cmd)
        sys.stdout.flush()
        sys.stderr.flush()
        exitcode = subprocess.call(cmd)
        self.logger.info("Import process exited with exit code %r", exitcode)
        if fail_on_error and exitcode:
            self.logger.error("As requested raising an exception due to non-zero exit code")
            raise Exception("Non-zero exit code %r" % (exitcode,))
        return exitcode

    def create_csv(self):
        csvfile = tempfile.NamedTemporaryFile("w+", dir=self.tmpdir)
        self.logger.info("*** Writing user information to CSV file '%s'...", csvfile.name)
        users = list(self._test_user_creator.make_users())
        self.test_user_exporter.dump(users, csvfile.name)
        return users, csvfile

    def test_mass_importer(self):
        self.logger.info("\n\n*** Starting import with mass_importer=NullImport...\n")
        users, csvfile = self.create_csv()
        self.save_ldap_status()
        self.run_import(
            [
                "-c",
                CONFIG,
                "-i",
                csvfile.name,
                "--source_uid",
                "source_uid-{}".format(uts.random_string()),
                "--set",
                "classes:mass_importer="
                "univention.testing.ucsschool.import_factory_test_classes.NullImport",
            ]
        )
        self.check_new_and_removed_users(0, 0)
        self.logger.info("\n\n*** OK: No users imported.\n\n")

    def test_password_exporter(self):
        self.logger.info(
            "\n\n*** Starting import with password_exporter=UniventionPasswordExporter...\n"
        )
        users, csvfile = self.create_csv()
        outfile = tempfile.NamedTemporaryFile("w+", dir=self.tmpdir)
        self.save_ldap_status()
        self.run_import(
            [
                "-c",
                CONFIG,
                "-i",
                csvfile.name,
                "--source_uid",
                "source_uid-{}".format(uts.random_string()),
                "--set",
                "classes:password_exporter="
                "univention.testing.ucsschool.import_factory_test_classes.UniventionPasswordExporter",
                "output:new_user_passwords={}".format(outfile.name),
            ]
        )
        self.check_new_and_removed_users(8, 0)
        outfile.seek(0)
        dialect = excel()
        dialect.doublequote = True
        dialect.quoting = QUOTE_ALL
        myreader = csvreader(outfile, dialect=dialect)
        for num, row in enumerate(myreader):
            if num == 0:
                # header
                continue
            assert row[1] == "univention", "Password should be 'univention', is %r. Line %d: %r" % (
                row[1],
                num,
                row,
            )
        self.logger.info("\n\n*** OK: passwords are 'univention'.\n\n")

    def test_result_exporter(self):
        self.logger.info("\n\n*** Starting import with result_exporter=AnonymizeResultExporter...\n\n")
        users, csvfile = self.create_csv()
        outfile = tempfile.NamedTemporaryFile("w+", dir=self.tmpdir)
        self.save_ldap_status()
        self.run_import(
            [
                "-c",
                CONFIG,
                "-i",
                csvfile.name,
                "--source_uid",
                "source_uid-{}".format(uts.random_string()),
                "--set",
                "classes:result_exporter="
                "univention.testing.ucsschool.import_factory_test_classes.AnonymizeResultExporter",
                "output:user_import_summary={}".format(outfile.name),
            ]
        )
        self.check_new_and_removed_users(8, 0)
        outfile.seek(0)
        dialect = excel()
        dialect.doublequote = True
        dialect.quoting = QUOTE_ALL
        field_names = (
            "line",
            "success",
            "error",
            "action",
            "role",
            "username",
            "schools",
            "firstname",
            "lastname",
            "birthday",
            "email",
            "disabled",
            "classes",
            "source_uid",
            "record_uid",
            "error_msg",
        )  # from UserImportCsvResultExporter
        myreader = DictReader(outfile, dialect=dialect, fieldnames=field_names)
        expected = {"firstname": "s3cr31", "lastname": "S3cr3t", "birthday": "1970-01-01"}
        for num, row in enumerate(myreader):
            if num == 0:
                # header
                continue
            found = {
                "firstname": row["firstname"],
                "lastname": row["lastname"],
                "birthday": row["birthday"],
            }
            assert expected == found, "Output not as expected: expected=%r found=%r" % (expected, found)
        self.logger.info("\n\n*** OK: result is anonymized.\n\n")

    def test_user_importer(self):
        self.logger.info("\n\n*** Starting import with user_importer=BirthdayUserImport...\n\n")
        csvfile = tempfile.NamedTemporaryFile("w+", dir=self.tmpdir)
        self.logger.info("*** Writing user information to CSV file '%s'...", csvfile.name)
        users = list(self._test_user_creator.make_users())
        today_birthday_users = []
        random_birthday_users = []
        today = time.strftime("%Y-%m-%d")
        for user in users:
            if random.choice([True, False]):
                user["Geburtstag"] = today
                today_birthday_users.append(user)
            else:
                user["Geburtstag"] = "{}-{:>02}-{:>02}".format(
                    uts.random_int(1900, 2000), uts.random_int(1, 12), uts.random_int(1, 27)
                )
                random_birthday_users.append(user)
        test_user_exporter_with_birthday = _TestUserCsvExporter()
        field_names = list(test_user_exporter_with_birthday.field_names)
        field_names.append("Geburtstag")
        test_user_exporter_with_birthday.field_names = field_names
        test_user_exporter_with_birthday.dump(users, csvfile.name)
        self.save_ldap_status()
        source_uid = "source_uid-{}".format(uts.random_string())
        self.run_import(
            [
                "-c",
                CONFIG,
                "-i",
                csvfile.name,
                "--source_uid",
                source_uid,
                "--set",
                "classes:user_importer="
                "univention.testing.ucsschool.import_factory_test_classes.BirthdayUserImport",
                "csv:mapping:Geburtstag=birthday",
            ]
        )
        self.check_new_and_removed_users(8, 0)

        self.logger.info(
            "\n\n*** OK: imported 8 users. Will delete them now (except whose with birthday=today)\n\n"
        )
        # create empty CSV file
        with tempfile.NamedTemporaryFile("w+", dir=self.tmpdir, delete=False) as csvfile:
            dialect = excel()
            dialect.doublequote = True
            dialect.quoting = QUOTE_ALL
            writer = DictWriter(csvfile, fieldnames=field_names, dialect=dialect)
            writer.writeheader()
            csvfile_name = csvfile.name
        self.save_ldap_status()
        self.run_import(
            [
                "-c",
                CONFIG,
                "-i",
                csvfile_name,
                "--source_uid",
                source_uid,
                "--set",
                "classes:user_importer="
                "univention.testing.ucsschool.import_factory_test_classes.BirthdayUserImport",
            ]
        )
        self.check_new_and_removed_users(0, len(random_birthday_users))
        try:
            os.remove(csvfile_name)
        except OSError as exc:
            self.logger.warning("Could not delete %r: %s", csvfile_name, exc)
        self.logger.info("*** OK: only %d users were deleted.\n", len(random_birthday_users))

    def test_username_handler(self):
        self.logger.info("\n\n*** Starting import with username_handler=FooUsernameHandler...\n\n")
        users, csvfile = self.create_csv()
        outfile = tempfile.NamedTemporaryFile("w+", dir=self.tmpdir)
        self.save_ldap_status()
        self.run_import(
            [
                "-c",
                CONFIG,
                "-i",
                csvfile.name,
                "--source_uid",
                "source_uid-{}".format(uts.random_string()),
                "--set",
                "classes:username_handler="
                "univention.testing.ucsschool.import_factory_test_classes.FooUsernameHandler",
                "output:user_import_summary={}".format(outfile.name),
                "scheme:username:default=<:umlauts><firstname>.<lastname><:lower>[FOO]",
            ]
        )
        self.check_new_and_removed_users(8, 0)
        ldap_diff = self.diff_ldap_status()
        new_users = [x for x in ldap_diff.new if x.startswith("uid=")]
        self.logger.debug("new_users=%r", new_users)
        assert all(
            explodeDn(user)[0].endswith("foo") for user in new_users
        ), "Not all usernames end with 'foo': %r" % (new_users,)
        self.logger.info("\n\n*** OK: all usernames end with 'foo'.\n\n")

    def test_json_writer(self):
        self.logger.info("\n\n*** Starting import with user_writer=JsonWriter...\n")
        users, csvfile = self.create_csv()
        outfile = tempfile.NamedTemporaryFile("w+", dir=self.tmpdir)
        self.save_ldap_status()
        self.run_import(
            [
                "-c",
                CONFIG,
                "-i",
                csvfile.name,
                "--source_uid",
                "source_uid-{}".format(uts.random_string()),
                "--set",
                "classes:user_writer="
                "univention.testing.ucsschool.import_factory_test_classes.JsonWriter",
                "output:user_import_summary={}".format(outfile.name),
            ]
        )
        self.check_new_and_removed_users(8, 0)
        try:
            outfile.seek(0)
            jsout = json.load(outfile)
        except ValueError:
            self.logger.exception(repr(open(outfile.name).read()))
            raise

        assert len(jsout) == 8, "Expected %d objects in export, found %d." % (8, len(jsout))
        vn_in = {x["Vorname"] for x in users}
        vn_out = {x["firstname"].encode("utf-8") if str is bytes else x["firstname"] for x in jsout}
        assert not vn_in.difference(
            vn_out
        ), "Input and output does not match:\nvn_in=%r\nvn_out=%r\nvn_in.difference(vn_out)=%r" % (
            vn_in,
            vn_out,
            vn_in.difference(vn_out),
        )
        self.logger.info("\n\n*** OK: JSON output.\n\n")
