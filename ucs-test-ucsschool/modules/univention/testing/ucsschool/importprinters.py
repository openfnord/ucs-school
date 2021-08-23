# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import subprocess
import tempfile

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.ucsschool.importou import get_school_base

HOOK_BASEDIR = "/usr/share/ucs-school-import/hooks"


class PrinterHookResult(Exception):
    pass


configRegistry = univention.config_registry.ConfigRegistry()
configRegistry.load()


class Printer:
    def __init__(self, school):
        self.name = uts.random_name()
        self.spool_host = uts.random_name()
        self.uri = "parallel:/dev/lp0"
        self.model = "foomatic-ppds/Apple/Apple-12_640ps-Postscript.ppd.gz"
        self.school = school
        self.mode = "A"

        self.school_base = get_school_base(self.school)

        self.dn = "cn=%s,cn=printers,%s" % (self.name, self.school_base)

    def set_mode_to_modify(self):
        self.mode = "M"

    def set_mode_to_delete(self):
        self.mode = "D"

    def __str__(self):
        delimiter = "\t"
        line = self.mode
        line += delimiter
        line += self.school
        line += delimiter
        line += self.spool_host
        line += delimiter
        line += self.name
        line += delimiter
        line += self.uri
        line += delimiter
        if self.model:
            line += self.model
        return line

    def expected_attributes(self):
        attr = {}
        attr["cn"] = [self.name]
        attr["univentionPrinterSpoolHost"] = [
            "%s.%s" % (self.spool_host, configRegistry.get("domainname"))
        ]
        attr["univentionPrinterURI"] = [self.uri]
        if self.model:
            attr["univentionPrinterModel"] = [self.model]
        else:
            attr["univentionPrinterModel"] = ["None"]
        attr["univentionPrinterACLtype"] = ["allow all"]
        attr["univentionObjectType"] = ["shares/printer"]
        return attr

    def verify(self):
        print("verify printer: %s" % self.name)

        if self.mode == "D":
            utils.verify_ldap_object(self.dn, should_exist=False)
            return

        utils.verify_ldap_object(self.dn, expected_attr=self.expected_attributes(), should_exist=True)


class ImportFile:
    def __init__(self, use_cli_api, use_python_api):
        self.use_cli_api = use_cli_api
        self.use_python_api = use_python_api
        self.import_fd, self.import_file = tempfile.mkstemp()
        os.close(self.import_fd)

    def write_import(self, data):
        self.import_fd = os.open(self.import_file, os.O_RDWR | os.O_CREAT)
        os.write(self.import_fd, data.encode("utf-8"))
        os.close(self.import_fd)

    def run_import(self, data):
        hooks = PrinterHooks()
        try:
            self.write_import(data)
            if self.use_cli_api:
                self._run_import_via_cli()
            elif self.use_python_api:
                self._run_import_via_python_api()
            pre_result = hooks.get_pre_result()
            post_result = hooks.get_post_result()
            print("PRE  HOOK result: %s" % pre_result)
            print("POST HOOK result: %s" % post_result)
            print("SCHOOL DATA     : %s" % data)
            if pre_result != post_result != data:
                raise PrinterHookResult(pre_result, post_result, data)
        finally:
            hooks.cleanup()
            os.remove(self.import_file)

    def _run_import_via_cli(self):
        cmd_block = ["/usr/share/ucs-school-import/scripts/import_printer", self.import_file]

        print("cmd_block: %r" % cmd_block)
        subprocess.check_call(cmd_block)

    def _run_import_via_python_api(self):
        raise NotImplementedError()


class PrinterHooks:
    def __init__(self):
        fd, self.pre_hook_result = tempfile.mkstemp()
        os.close(fd)

        fd, self.post_hook_result = tempfile.mkstemp()
        os.close(fd)

        self.create_hooks()

    def get_pre_result(self):
        return open(self.pre_hook_result, "r").read()

    def get_post_result(self):
        return open(self.post_hook_result, "r").read()

    def create_hooks(self):
        self.pre_hooks = [
            os.path.join(os.path.join(HOOK_BASEDIR, "printer_create_pre.d"), uts.random_name()),
            os.path.join(os.path.join(HOOK_BASEDIR, "printer_remove_pre.d"), uts.random_name()),
            os.path.join(os.path.join(HOOK_BASEDIR, "printer_modify_pre.d"), uts.random_name()),
        ]

        self.post_hooks = [
            os.path.join(os.path.join(HOOK_BASEDIR, "printer_create_post.d"), uts.random_name()),
            os.path.join(os.path.join(HOOK_BASEDIR, "printer_modify_post.d"), uts.random_name()),
            os.path.join(os.path.join(HOOK_BASEDIR, "printer_remove_post.d"), uts.random_name()),
        ]

        for pre_hook in self.pre_hooks:
            with open(pre_hook, "w+") as fd:
                fd.write(
                    """#!/bin/sh
set -x
test $# = 1 || exit 1
cat $1 >>%(pre_hook_result)s
exit 0
"""
                    % {"pre_hook_result": self.pre_hook_result}
                )
            os.chmod(pre_hook, 0o755)

        for post_hook in self.post_hooks:
            with open(post_hook, "w+") as fd:
                fd.write(
                    """#!/bin/sh
set -x
dn="$2"
name="$(cat $1 | awk -F '\t' '{print $4}')"
mode="$(cat $1 | awk -F '\t' '{print $1}')"
if [ "$mode" != D ]; then
    ldap_dn="$(univention-ldapsearch "(&(objectClass=univentionPrinter)(cn=$name))" | \
    ldapsearch-wrapper | sed -ne 's|dn: ||p')"
    test "$dn" = "$ldap_dn" || exit 1
fi
cat $1 >>%(post_hook_result)s
exit 0
"""
                    % {"post_hook_result": self.post_hook_result}
                )
            os.chmod(post_hook, 0o755)

    def cleanup(self):
        for pre_hook in self.pre_hooks:
            os.remove(pre_hook)
        for post_hook in self.post_hooks:
            os.remove(post_hook)
        os.remove(self.pre_hook_result)
        os.remove(self.post_hook_result)


class PrinterImport:
    def __init__(self, ou_name, nr_printers=20):
        assert nr_printers > 3

        self.school = ou_name

        self.printers = []
        for i in range(0, nr_printers):
            self.printers.append(Printer(self.school))
        self.printers[0].model = None
        self.printers[1].uri = "file:/dev/null"

    def __str__(self):
        lines = []

        for printer in self.printers:
            lines.append(str(printer))

        return "\n".join(lines)

    def verify(self):
        for printer in self.printers:
            printer.verify()

    def modify(self):
        for printer in self.printers:
            printer.set_mode_to_modify()
        self.printers[1].model = None
        self.printers[2].uri = "file:/dev/null"
        self.printers[0].spool_host = uts.random_name()

    def delete(self):
        for printer in self.printers:
            printer.set_mode_to_delete()


def create_and_verify_printers(use_cli_api=True, use_python_api=False, nr_printers=5):
    assert use_cli_api != use_python_api

    with utu.UCSTestSchool() as schoolenv:
        ou_name, ou_dn = schoolenv.create_ou(name_edudc=schoolenv.ucr.get("hostname"))

        print("********** Generate school data")
        printer_import = PrinterImport(ou_name, nr_printers=nr_printers)
        print(printer_import)
        import_file = ImportFile(use_cli_api, use_python_api)

        print("********** Create printers")
        import_file.run_import(str(printer_import))
        printer_import.verify()

        print("********** Modify printers")
        printer_import.modify()
        import_file.run_import(str(printer_import))
        printer_import.verify()

        print("********** Delete printers")
        printer_import.delete()
        import_file.run_import(str(printer_import))
        printer_import.verify()


def import_printers_basics(use_cli_api=True, use_python_api=False):
    create_and_verify_printers(use_cli_api, use_python_api, 10)
