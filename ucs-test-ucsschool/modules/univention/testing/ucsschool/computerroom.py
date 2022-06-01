# -*- coding: utf-8 -*-
from __future__ import print_function

import copy
import datetime
import itertools
import os
import pipes
import re
import subprocess
import tempfile
import time
from functools import wraps

import univention.lib.atjobs as ula
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from ucsschool.lib.models.computer import (
    IPComputer as IPComputerLib,
    MacComputer as MacComputerLib,
    WindowsComputer as WindowsComputerLib,
)
from ucsschool.lib.models.utils import exec_cmd
from ucsschool.lib.roles import (
    create_ucsschool_role_string,
    role_ip_computer,
    role_mac_computer,
    role_win_computer,
)
from univention.lib.umc import ConnectionError
from univention.testing.decorators import SetTimeout
from univention.testing.ucsschool.importcomputers import (
    IPManagedClient,
    MacOS,
    Windows,
    random_ip,
    random_mac,
)
from univention.testing.ucsschool.internetrule import InternetRule
from univention.testing.ucsschool.simplecurl import SimpleCurl
from univention.testing.ucsschool.workgroup import Workgroup
from univention.testing.umc import Client


class CmdCheckFail(Exception):
    pass


def retry_cmd(func):
    #  retry to avoid errors due to slow replication
    @wraps(func)
    def decorated(*args, **kwargs):
        utils.retry_on_error(
            lambda: func(*args, **kwargs), exceptions=(CmdCheckFail), retry_count=8, delay=4
        )

    return decorated


class ComputerImport(object):
    def __init__(self, school=None, nr_windows=1, nr_macos=0, nr_ipmanagedclient=0):
        self.school = school if school else uts.random_name()
        self.windows = []
        for i in range(0, nr_windows):
            self.windows.append(Windows(self.school))
        self.macos = []
        for i in range(0, nr_macos):
            self.macos.append(MacOS(self.school))
        self.ipmanagedclients = []
        for i in range(0, nr_ipmanagedclient):
            self.ipmanagedclients.append(IPManagedClient(self.school))

    def run_import(self, open_ldap_co):
        def _set_kwargs(computer):
            kwargs = {
                "school": computer.school,
                "name": computer.name,
                "ip_address": computer.ip,
                "mac_address": computer.mac,
                "type_name": computer.ctype,
                "inventory_number": computer.inventorynumbers,
            }
            return kwargs

        for computer in self.windows:
            kwargs = _set_kwargs(computer)
            WindowsComputerLib(**kwargs).create(open_ldap_co)
        for computer in self.macos:
            kwargs = _set_kwargs(computer)
            MacComputerLib(**kwargs).create(open_ldap_co)
        for computer in self.ipmanagedclients:
            kwargs = _set_kwargs(computer)
            IPComputerLib(**kwargs).create(open_ldap_co)


class Room(object):
    def __init__(
        self, school, name=None, dn=None, description=None, host_members=None, teacher_computers=None
    ):
        self.school = school
        self.name = name if name else uts.random_name()
        self.dn = (
            dn
            if dn
            else "cn=%s-%s,cn=raeume,cn=groups,%s"
            % (school, self.name, utu.UCSTestSchool().get_ou_base_dn(school))
        )
        self.description = description if description else uts.random_name()
        self.host_members = host_members or []
        self.teacher_computers = teacher_computers or []

    def get_room_user(self, client):
        print("Executing command: computerroom/rooms in school:", self.school)
        reqResult = client.umc_command("computerroom/rooms", {"school": self.school}).result
        result = [x.get("user") for x in reqResult if x["label"] == self.name]
        return result[0] if result else None

    def check_room_user(self, client, expected_user):
        print("Checking computer room(%s) users.........." % self.name)
        current_user = self.get_room_user(client)
        print("Room %s is in use by user %r" % (self.name, current_user))
        if current_user:
            user_id = re.search(r"\((\w+)\)", current_user).group(1)
        else:
            user_id = current_user
        if expected_user != user_id:
            utils.fail("Room in use by user %r, expected: %r" % (user_id, expected_user))

    def aquire_room(self, client):
        print("Executing command: computerroom/room/acquire")
        return client.umc_command("computerroom/room/acquire", {"room": self.dn}).result

    def checK_room_aquire(self, client, expected_answer):
        print("Checking room aquire... (%s)" % self.name)
        answer = self.aquire_room(client)["message"]
        if answer == expected_answer:
            print("Room %s is %s" % (self.name, answer))
        else:
            utils.fail("Unexpected room aquire result: %s" % (answer,))

    def get_room_computers(self, client):
        print("Executing command: computerroom/query... (%s)" % self.name)
        reqResult = client.umc_command("computerroom/query", {"reload": False}).result
        return [x["name"] for x in reqResult]

    def check_room_computers(self, client, expected_computer_list):
        print("Checking room computers........... (%s)" % self.name)
        current_computers = self.get_room_computers(client)
        print("Current computers in room %s are %r" % (self.name, current_computers))
        for i, computer in enumerate(sorted(current_computers)):
            assert (
                computer in sorted(expected_computer_list)[i]
            ), "Computers found %r do not match the expected: %r" % (
                current_computers,
                expected_computer_list,
            )

    def set_room_settings(self, client, new_settings):
        print("Executing command: computerroom/settings/set")
        print("new_settings = %r" % (new_settings,))
        reqResult = client.umc_command("computerroom/settings/set", new_settings).result
        return reqResult

    def get_room_settings(self, client):
        print("Executing command: computerroom/settings/get")
        reqResult = client.umc_command("computerroom/settings/get").result
        return reqResult

    def check_room_settings(self, client, expected_settings):
        print("Checking computerroom (%s) settings ..........." % self.name)
        try:
            current_settings = self.get_room_settings(client)
            d = dict(expected_settings)  # copy dictionary
            d["period"] = current_settings["period"]
            d["customRule"] = current_settings["customRule"]  # TODO Bug 35258 remove
            assert current_settings == d, "Current settings (%r) do not match expected ones (%r)" % (
                current_settings,
                d,
            )
        except ConnectionError as exc:
            if "[Errno 4] " in str(exc):
                print("failed to check room (%s) settings, exception [Errno4]" % self.name)
            print("Exception: '%s' '%s' '%r'" % (str(exc), type(exc), exc))
            raise

    def get_internetRules(self, client):
        print("Executing command: computerroom/internetrules")
        reqResult = client.umc_command("computerroom/internetrules").result
        return reqResult

    def check_internetRules(self, client):
        """Check if the fetched internetrules match the already defined ones
        in define internet module.
        :param client: umc connection
        :type client: Client(uce.get('hostname'))
        """
        rule = InternetRule()
        current_rules = rule.allRules()
        internetRules = self.get_internetRules(client)
        assert sorted(current_rules) == sorted(
            internetRules
        ), "Fetched internetrules %r, do not match the existing ones %r" % (internetRules, current_rules)

    def check_atjobs(self, period, expected_existence):
        exist = False
        jobs = ula.list()
        for item in jobs:
            if period == datetime.time.strftime(item.execTime.time(), "%H:%M"):
                exist = True
                break
        print("Atjob result at(%r) existance: %r" % (period, exist))
        print(
            "\n".join(
                "Job %s: %s  owner=%s\n%s" % (i, item, item.owner, item.command)
                for i, item in enumerate(jobs)
            )
        )
        assert (
            exist == expected_existence
        ), "Atjob result at(%r) is unexpected (should_exist=%r  exists=%r)" % (
            period,
            expected_existence,
            exist,
        )

    def check_displayTime(self, client, period):
        displayed_period = self.get_room_settings(client)["period"][0:-3]
        print("Time displayed (%r) - Atjobs (%r)" % (displayed_period, period))
        assert (
            period == displayed_period
        ), "Time displayed (%r) is different from time at Atjobs (%r)" % (displayed_period, period)

    def test_time_settings(self, client):
        self.aquire_room(client)
        settings = self.get_room_settings(client)
        period = datetime.time.strftime(
            (datetime.datetime.now() + datetime.timedelta(0, 120)).time(), "%H:%M"
        )
        new_settings = {
            "customRule": "",
            "printMode": "none",
            "internetRule": "none",
            "shareMode": "home",
            "period": period,
        }

        ula_length = len(ula.list())
        time_out = 30  # seconds
        self.set_room_settings(client, new_settings)
        for i in range(time_out, 0, -1):
            print(i)
            if len(ula.list()) > ula_length:
                break
            else:
                time.sleep(1)
                continue

        # Checking Atjobs list
        self.check_atjobs(period, True)

        # TODO FAILS because of Bug #35195
        # self.check_displayTime(client, period)

        print("*** Waiting 2 mins for settings to expire.............")
        time.sleep(2 * 60 + 2)
        current_settings = self.get_room_settings(client)

        # Time field is not considered in the comparision
        current_settings["period"] = settings["period"]
        assert (
            current_settings == settings
        ), "Current settings (%r) are not reset back after the time out, expected (%r)" % (
            current_settings,
            settings,
        )

        # Checking Atjobs list
        self.check_atjobs(period, False)

    def check_home_read(self, user, ip_address, passwd="univention", expected_result=0):
        check_share_read(user, ip_address, share=user, passwd=passwd, expected_result=expected_result)

    def check_home_write(self, user, ip_address, passwd="univention", expected_result=0):
        check_share_write(user, ip_address, share=user, passwd=passwd, expected_result=expected_result)

    def check_marktplatz_read(self, user, ip_address, passwd="univention", expected_result=0):
        check_share_read(
            user, ip_address, share="Marktplatz", passwd=passwd, expected_result=expected_result
        )

    def check_marktplatz_write(self, user, ip_address, passwd="univention", expected_result=0):
        check_share_write(
            user, ip_address, share="Marktplatz", passwd=passwd, expected_result=expected_result
        )

    def check_share_access(self, user, ip_address, expected_home_result, expected_marktplatz_result):
        self.check_home_read(user, ip_address, expected_result=expected_home_result)
        self.check_home_write(user, ip_address, expected_result=expected_home_result)
        self.check_marktplatz_read(user, ip_address, expected_result=expected_marktplatz_result)
        self.check_marktplatz_write(user, ip_address, expected_result=expected_marktplatz_result)

    def check_share_behavior(self, user, ip_address, shareMode):
        if shareMode == "all":
            self.check_share_access(user, ip_address, 0, 0)
        elif shareMode == "home":
            self.check_share_access(user, ip_address, 0, 1)
        else:
            utils.fail("shareMode invalid value = (%s)" % shareMode)

    def test_share_access_settings(self, user, ip_address, client):
        self.aquire_room(client)
        print(self.get_room_settings(client))

        # generate all the possible combinations for (rule, printmode, sharemode)
        white_page = "univention.de"
        rules = ["none", "Kein Internet", "Unbeschränkt", "custom"]
        printmodes = ["default", "none"]
        sharemodes = ["all", "home"]
        settings = itertools.product(rules, printmodes, sharemodes)
        t = 600

        # Testing loop
        for i, (rule, printMode, shareMode) in enumerate(settings):
            period = datetime.time.strftime(
                (datetime.datetime.now() + datetime.timedelta(0, t)).time(), "%H:%M"
            )
            t += 300
            print()
            print(
                "*** %d -(internetRule, printMode, shareMode) = (%r, %r, %r) ----------"
                % (
                    i,
                    rule,
                    printMode,
                    shareMode,
                )
            )
            new_settings = {
                "customRule": white_page,
                "printMode": printMode,
                "internetRule": rule,
                "shareMode": shareMode,
                "period": period,
            }
            self.aquire_room(client)
            self.set_room_settings(client, new_settings)
            # check if displayed values match
            self.check_room_settings(client, new_settings)
            self.check_share_behavior(user, ip_address, shareMode)

    @retry_cmd
    def check_smb_print(self, ip, printer, user, expected_result):
        print("Checking print mode", "." * 40)
        # ensure cups is running, otherwise jobs are not rejected
        ucr = ucr_test.UCSTestConfigRegistry()
        ucr.load()
        cups_status = subprocess.check_output(
            ["lpstat", "-h", ucr.get("cups/server", ""), "-r"], env={"LC_ALL": "C"}
        ).decode("UTF-8")
        assert cups_status == "scheduler is running\n", 'CUPS status reported: "{}"'.format(cups_status)
        f = tempfile.NamedTemporaryFile(dir="/tmp")
        cmd_print = ["smbclient", "//%(ip)s/%(printer)s", "-U", "%(user)s", "-c", "print %(filename)s"]
        result = run_commands(
            [cmd_print],
            {
                "ip": ip,
                "printer": printer,
                "user": "{0}%{1}".format(user, "univention"),
                "filename": f.name,
            },
        )[0]
        f.close()
        if result != expected_result:
            print("FAIL .... smbclient print result (%r), expected (%r)" % (result, expected_result))
            raise CmdCheckFail("smbclient print result (%r), expected (%r)" % (result, expected_result))

    def check_print_behavior(self, user, ip_address, printer, printMode):
        if printMode == "none":
            self.check_smb_print(ip_address, printer, user, 1)
            self.check_smb_print(ip_address, "PDFDrucker", user, 1)
        elif printMode == "default":
            self.check_smb_print(ip_address, printer, user, 0)
            self.check_smb_print(ip_address, "PDFDrucker", user, 0)
        else:
            utils.fail("printMode invalid value = (%s)" % printMode)

    def test_printMode_settings(self, school, user, ip_address, client, ucr):
        ucr = ucr_test.UCSTestConfigRegistry()
        ucr.load()
        self.aquire_room(client)

        printer = uts.random_string()
        add_printer(printer, school, ucr.get("hostname"), ucr.get("domainname"), ucr.get("ldap/base"))
        try:
            # generate all the possible combinations for (rule, printmode, sharemode)
            white_page = "univention.de"
            rules = ["none", "Kein Internet", "Unbeschränkt", "custom"]
            printmodes = ["default", "none"]
            sharemodes = ["all", "home"]
            settings = itertools.product(rules, printmodes, sharemodes)
            settings_len = len(printmodes) * len(sharemodes) * len(rules)
            t = 600

            # Testing loop
            for i in range(settings_len):
                period = datetime.time.strftime(
                    (datetime.datetime.now() + datetime.timedelta(0, t)).time(), "%H:%M"
                )
                t += 300
                rule, printMode, shareMode = next(settings)
                print()
                print(
                    (
                        "***",
                        i,
                        "-(internetRule, printMode, shareMode) = (",
                        rule,
                        ",",
                        printMode,
                        ",",
                        shareMode,
                        ")",
                        "-" * 10,
                    )
                )
                new_settings = {
                    "customRule": white_page,
                    "printMode": printMode,
                    "internetRule": rule,
                    "shareMode": shareMode,
                    "period": period,
                }
                self.aquire_room(client)
                self.set_room_settings(client, new_settings)
                # check if displayed values match
                self.check_room_settings(client, new_settings)
                self.check_print_behavior(user, ip_address, printer, printMode)

        finally:
            remove_printer(printer, school, ucr.get("ldap/base"))

    def checK_internetrules(self, ucr, user, proxy, custom_domain, global_domains, expected_rule):
        # Getting the redirection page when blocked
        banPage = get_banpage(ucr)
        localCurl = SimpleCurl(proxy=proxy, username=user)

        rule_in_control = None
        if expected_rule == "Kein Internet" and localCurl.getPage("univention.de") == banPage:
            rule_in_control = expected_rule
        if expected_rule == "Unbeschränkt" and localCurl.getPage("gmx.de") != banPage:
            rule_in_control = expected_rule
        if expected_rule == "custom" and localCurl.getPage(custom_domain) != banPage:
            rule_in_control = expected_rule
        if expected_rule == "none":
            if all(localCurl.getPage(dom) != banPage for dom in global_domains):
                rule_in_control = expected_rule

        localCurl.close()
        print("RULE IN CONTROL = ", rule_in_control)
        assert (
            rule_in_control == expected_rule
        ), "rule in control (%s) does not match the expected one (%s)" % (rule_in_control, expected_rule)

    def test_internetrules_settings(self, school, user, user_dn, ip_address, ucr, client):
        # Create new workgroup and assign new internet rule to it
        group = Workgroup(school, members=[user_dn])
        group.create()
        try:
            global_domains = ["univention.de", "example.com"]
            rule = InternetRule(typ="whitelist", domains=global_domains)
            rule.define()
            rule.assign(school, group.name, "workgroup")

            self.check_internetRules(client)
            self.aquire_room(client)

            # generate all the possible combinations for (rule, printmode, sharemode)
            white_page = "univention.de"
            rules = ["none", "Kein Internet", "Unbeschränkt", "custom"]
            printmodes = ["default", "none"]
            sharemodes = ["all", "home"]
            settings = itertools.product(rules, printmodes, sharemodes)
            settings_len = len(printmodes) * len(sharemodes) * len(rules)
            t = 600

            # Testing loop
            for i in range(settings_len):
                period = datetime.time.strftime(
                    (datetime.datetime.now() + datetime.timedelta(0, t)).time(), "%H:%M"
                )
                t += 300
                rule, printMode, shareMode = next(settings)
                print()
                print(
                    (
                        "***",
                        i,
                        "-(internetRule, printMode, shareMode) = (",
                        rule,
                        ",",
                        printMode,
                        ",",
                        shareMode,
                        ")",
                        "-" * 10,
                    )
                )
                new_settings = {
                    "customRule": white_page,
                    "printMode": printMode,
                    "internetRule": rule,
                    "shareMode": shareMode,
                    "period": period,
                }
                self.aquire_room(client)
                self.set_room_settings(client, new_settings)
                # check if displayed values match
                self.check_room_settings(client, new_settings)
                self.checK_internetrules(ucr, user, ip_address, "univention.de", global_domains, rule)
        finally:
            group.remove()

    def test_settings(self, school, user, user_dn, ip_address, ucr, client):
        printer = uts.random_string()
        # Create new workgroup and assign new internet rule to it
        group = Workgroup(school, client, members=[user_dn])
        group.create()
        try:
            global_domains = ["univention.de", "example.com"]
            rule = InternetRule(typ="whitelist", domains=global_domains)
            rule.define()
            rule.assign(school, group.name, "workgroup")

            self.check_internetRules(client)

            # Add new hardware printer
            add_printer(
                printer, school, ucr.get("hostname"), ucr.get("domainname"), ucr.get("ldap/base")
            )

            # generate all the possible combinations for (rule, printmode, sharemode)
            white_page = "univention.de"
            rules = ["none", "Kein Internet", "Unbeschränkt", "custom"]
            printmodes = ["default", "none"]
            sharemodes = ["all", "home"]
            settings = itertools.product(rules, printmodes, sharemodes)
            t = 600

            utils.wait_for_replication()

            # Testing loop
            for i, (rule, printMode, shareMode) in enumerate(settings):
                period = datetime.time.strftime(
                    (datetime.datetime.now() + datetime.timedelta(0, t)).time(), "%H:%M"
                )
                print()
                print(
                    "*** %d -(internetRule, printMode, shareMode, period) = (%r, %r, %r, %r) "
                    "----------" % (i, rule, printMode, shareMode, period)
                )
                new_settings = {
                    "customRule": white_page,
                    "printMode": printMode,
                    "internetRule": rule,
                    "shareMode": shareMode,
                    "period": period,
                }
                self.aquire_room(client)
                old_settings = self.get_room_settings(client)
                self.set_room_settings(client, new_settings)

                utils.wait_for_replication_and_postrun()

                # give the CUPS and Samba server a little bit more time
                time.sleep(15)

                # check if displayed values match
                self.check_room_settings(client, new_settings)
                # old_period = old_settings['period']
                partial_old_settings = {
                    "period": old_settings["period"],
                    "printMode": old_settings["printMode"],
                    "shareMode": old_settings["shareMode"],
                    "internetRule": old_settings["internetRule"],
                }
                self.check_behavior(
                    partial_old_settings,
                    new_settings,
                    user,
                    ip_address,
                    printer,
                    white_page,
                    global_domains,
                    ucr,
                )
                t += 300
        finally:
            group.remove()
            remove_printer(printer, school, ucr.get("ldap/base"))

    def check_behavior(
        self,
        partial_old_settings,
        new_settings,
        user,
        ip_address,
        printer,
        white_page,
        global_domains,
        ucr,
    ):
        # extract the new_settings
        period = new_settings["period"]
        internetRule = new_settings["internetRule"]
        printMode = new_settings["printMode"]
        shareMode = new_settings["shareMode"]

        # check atjobs
        partial_new_settings = {
            # 'period': period,
            "printMode": printMode,
            "shareMode": shareMode,
            "internetRule": internetRule,
        }
        print()
        print("----------DEBUG-----------")
        print("old_period = %r" % (partial_old_settings.get("period"),))
        print("new_period = %r" % (period,))
        partial_old_settings = partial_old_settings.copy()
        partial_old_settings.pop("period")
        # if there is no change in settings, no atjob is added
        print("old=", partial_old_settings)
        print("new=", partial_new_settings)
        self.check_atjobs(period, partial_old_settings != partial_new_settings)

        # check internetrules
        self.checK_internetrules(ucr, user, ip_address, white_page, global_domains, internetRule)

        # check share access
        self.check_share_behavior(user, ip_address, shareMode)

        # check print mode
        self.check_print_behavior(user, ip_address, printer, printMode)


def get_banpage(ucr):
    # Getting the redirection page when blocked
    adminCurl = SimpleCurl(proxy=ucr.get("hostname"))
    redirUri = ucr.get("proxy/filter/redirecttarget")
    banPage = adminCurl.getPage(redirUri)
    adminCurl.close()
    return banPage


def clean_folder(path):
    print("Cleaning folder %r ....." % path)
    for root, _, filenames in os.walk(path):
        for f in filenames:
            file_path = os.path.join(root, f)
            os.remove(file_path)


def run_commands(cmdlist, argdict):
    """
    Start all commands in cmdlist and replace formatstrings with arguments in argdict.
    run_commands([['/bin/echo', '%(msg)s'], ['/bin/echo', 'World']], {'msg': 'Hello'})
    """
    result_list = []
    for cmd in cmdlist:
        cmd = copy.deepcopy(cmd)
        for i, val in enumerate(cmd):
            cmd[i] = val % argdict
        print("*** %r" % cmd)
        result = subprocess.call(cmd)
        result_list.append(result)
    return result_list


def add_printer(name, school, hostname, domainname, ldap_base):
    # account = utils.UCSTestDomainAdminCredentials()
    # adminuid = account.binddn
    # passwd = account.bindpw
    # adminuid = 'uid=Administrator,cn=users,dc=najjar,dc=local'
    # passwd = 'univention'

    cmd_add_printer = [
        "udm",
        "shares/printer",
        "create",
        "--position",
        "cn=printers,ou=%(school)s,%(ldap_base)s",
        "--set",
        "name=%(name)s",
        "--set",
        "spoolHost=%(hostname)s.%(domainname)s",
        "--set",
        "uri=file:// /tmp/%(name)s.printer",
        "--set",
        "model=None",
        "--binddn",
        "uid=Administrator,cn=users,%(ldap_base)s",
        "--bindpwd",
        "univention",
    ]
    print(
        run_commands(
            [cmd_add_printer],
            {
                "name": name,
                "school": school,
                "hostname": hostname,
                "domainname": domainname,
                "ldap_base": ldap_base,
            },
        )
    )

    utils.wait_for_replication_and_postrun()

    # give the CUPS and Samba server a little bit more time
    time.sleep(15)


def remove_printer(name, school, ldap_base):
    cmd_remove_printer = [
        "udm",
        "shares/printer",
        "remove",
        "--dn",
        "cn=%(name)s,cn=printers,ou=%(school)s,%(ldap_base)s",
    ]
    print(run_commands([cmd_remove_printer], {"name": name, "school": school, "ldap_base": ldap_base}))


class Computers(object):
    def __init__(self, open_ldap_co, school, nr_windows=1, nr_macos=0, nr_ipmanagedclient=0):
        self.open_ldap_co = open_ldap_co
        self.school = school
        self.nr_windows = nr_windows
        self.nr_macos = nr_macos
        self.nr_ipmanagedclient = nr_ipmanagedclient

    def create(self):
        computer_import = ComputerImport(
            self.school,
            nr_windows=self.nr_windows,
            nr_macos=self.nr_macos,
            nr_ipmanagedclient=self.nr_ipmanagedclient,
        )

        print("********** Create computers")
        computer_import.run_import(self.open_ldap_co)

        created_computers = []
        for computer in computer_import.windows:
            created_computers.append(computer)
        for computer in computer_import.macos:
            created_computers.append(computer)
        for computer in computer_import.ipmanagedclients:
            created_computers.append(computer)

        return sorted(created_computers, key=lambda x: x.name)

    def get_dns(self, computers):
        return [x.dn for x in computers]

    def get_ips(self, computers):
        return [x.ip for x in computers]

    def get_hostnames(self, computers):
        return ["%s$" % x.name for x in computers]


def set_windows_pc_password(dn, password):
    cmd = ["udm", "computers/windows", "modify", "--dn", "%(dn)s", "--set", "password=%(password)s"]
    read = run_commands([cmd], {"dn": dn, "password": password})
    return read


class UmcComputer(object):
    def __init__(
        self,
        school,
        typ,
        name=None,
        ip_address=None,
        subnet_mask=None,
        mac_address=None,
        inventory_number=None,
    ):
        self.school = school
        self.typ = typ
        self.name = name if name else uts.random_name()
        self.ip_address = ip_address if ip_address else random_ip()
        self.subnet_mask = subnet_mask if subnet_mask else "255.255.255.0"
        self.mac_address = mac_address.lower() if mac_address else random_mac()
        self.inventory_number = inventory_number if inventory_number else ""
        self.ucr = ucr_test.UCSTestConfigRegistry()
        self.ucr.load()
        host = self.ucr.get("ldap/master")
        self.client = Client(host)
        account = utils.UCSTestDomainAdminCredentials()
        admin = account.username
        passwd = account.bindpw
        self.client.authenticate(admin, passwd)

    def create(self, should_succeed=True, ignore_warning=True):
        """Creates object Computer"""
        flavor = "schoolwizards/computers"
        param = [
            {
                "object": {
                    "school": self.school,
                    "type": self.typ,
                    "name": self.name,
                    "ip_address": [self.ip_address],
                    "mac_address": [self.mac_address.lower()],
                    "subnet_mask": self.subnet_mask,
                    "inventory_number": self.inventory_number,
                    "ignore_warning": ignore_warning,
                },
                "options": None,
            }
        ]
        print("Creating Computer %s" % (self.name,))
        print("param = %s" % (param,))
        reqResult = self.client.umc_command("schoolwizards/computers/add", param, flavor).result
        if should_succeed and reqResult[0]["result"] is True:
            utils.wait_for_replication()
        elif not should_succeed and reqResult[0]["result"].get("error"):
            print(
                "Expected creation failed for computer (%r)\nReturn Message: %r"
                % (
                    self.name,
                    reqResult[0]["result"]["error"],
                )
            )
        else:
            assert False, "Unable to create computer (%r)\nRequest Result: %r" % (param, reqResult)

    def remove(self):
        """Remove computer"""
        flavor = "schoolwizards/computers"
        param = [{"object": {"$dn$": self.dn(), "school": self.school}, "options": None}]
        reqResult = self.client.umc_command("schoolwizards/computers/remove", param, flavor).result
        assert reqResult[0] is True, "Unable to remove computer (%s): %r" % (self.name, reqResult)
        utils.wait_for_replication()
        utils.wait_for_s4connector_replication()

    def dn(self):
        return "cn=%s,cn=computers,%s" % (self.name, utu.UCSTestSchool().get_ou_base_dn(self.school))

    def get(self):
        """Get Computer"""
        flavor = "schoolwizards/computers"
        param = [{"object": {"$dn$": self.dn(), "school": self.school}}]
        reqResult = self.client.umc_command("schoolwizards/computers/get", param, flavor).result
        assert reqResult[0], "Unable to get computer (%s): %r" % (self.name, reqResult)
        return reqResult[0]

    def check_get(self):
        typ2roles = {
            "windows": [create_ucsschool_role_string(role_win_computer, self.school)],
            "macos": [create_ucsschool_role_string(role_mac_computer, self.school)],
            "ipmanagedclient": [create_ucsschool_role_string(role_ip_computer, self.school)],
        }
        info = {
            "$dn$": self.dn(),
            "school": self.school,
            "type": self.typ,
            "name": self.name,
            "ip_address": [self.ip_address],
            "mac_address": [self.mac_address.lower()],
            "subnet_mask": self.subnet_mask,
            "inventory_number": self.inventory_number,
            "type_name": self.type_name(),
            "objectType": "computers/%s" % self.typ,
            "ucsschool_roles": typ2roles[self.typ],
        }
        get_result = self.get()
        if get_result != info:
            diff = set(x for x in get_result if get_result[x] != info[x])
        assert get_result == info, (
            "Failed get request for computer %s.\nReturned result: %r.\nExpected result: %r,\n"
            "Difference = %r" % (self.name, get_result, info, diff)
        )

    def type_name(self):
        if self.typ == "windows":
            return "Windows-System"
        elif self.typ == "macos":
            return "Mac OS X"
        elif self.typ == "ipmanagedclient":
            return "Gerät mit IP-Adresse"

    def edit(
        self, name=None, ip_address=None, subnet_mask=None, mac_address=None, inventory_number=None
    ):
        """Edit object computer"""
        flavor = "schoolwizards/computers"
        param = [
            {
                "object": {
                    "$dn$": self.dn(),
                    "name": self.name,
                    "school": self.school,
                    "type": self.typ,
                    "ip_address": [ip_address or self.ip_address],
                    "mac_address": [(mac_address or self.mac_address).lower()],
                    "subnet_mask": subnet_mask or self.subnet_mask,
                    "inventory_number": inventory_number or self.inventory_number,
                },
                "options": None,
            }
        ]
        print("Editing computer %s" % (self.name,))
        print("param = %s" % (param,))
        reqResult = self.client.umc_command("schoolwizards/computers/put", param, flavor).result
        assert reqResult[0] is True, "Unable to edit computer (%s) with the parameters (%r): %r" % (
            self.name,
            param,
            reqResult,
        )
        self.ip_address = ip_address
        self.mac_address = mac_address.lower() if mac_address else None
        self.subnet_mask = subnet_mask
        self.inventory_number = inventory_number
        utils.wait_for_replication()

    def query(self):
        """get the list of existing computer in the school"""
        flavor = "schoolwizards/computers"
        param = {"school": self.school, "filter": "", "type": "all"}
        reqResult = self.client.umc_command("schoolwizards/computers/query", param, flavor).result
        return reqResult

    def check_query(self, computer_names):
        reqResult = self.query()
        names_in_result = {x["name"] for x in reqResult}
        assert set(computer_names).issubset(
            names_in_result
        ), "computers from query do not contain the existing computers, found (%r), expected (%r)" % (
            names_in_result,
            computer_names,
        )

    def verify_ldap(self, should_exist):
        print("verifying computer %s" % self.name)
        utils.verify_ldap_object(self.dn(), should_exist=should_exist)


def create_homedirs(member_dn_list, open_ldap_co):
    for dn in member_dn_list:
        for home_dir in open_ldap_co.getAttr(dn, "homeDirectory"):
            home_dir = home_dir.decode("UTF-8")
            if not os.path.exists(home_dir):
                print("# Creating %r for %r" % (home_dir, dn))
                os.makedirs(home_dir)
            break
        else:
            assert False, "No homeDirectory attribute found for %r" % (dn,)


@SetTimeout
def check_create_share_folder(
    share, username, dir_name, samba_workstation=""
):  # type: (str, str, str, str) -> None
    """
    test if a user can create folders inside a given share, i.e. they have edit rights.
    """
    cmd = "smbclient -U {}%univention {} -c 'mkdir {}' ".format(
        pipes.quote(username), pipes.quote(share), dir_name
    )
    if samba_workstation:
        cmd += " --netbiosname={}".format(pipes.quote(samba_workstation))
    rv, stdout, stderr = exec_cmd(cmd, log=True, raise_exc=True, shell=True)
    assert (
        "NT_STATUS_ACCESS_DENIED" not in stdout
    ), "Failed to create folder, got NT_STATUS_ACCESS_DENIED: {}".format(stdout)


def check_change_permissions(
    filename, user_name, allowed, samba_workstation=""
):  # type: (str, str, bool, str) -> None
    """
    test if user can change the permissions a given file in a share folder.
    """
    new_acl = "ACL:Everyone:ALLOWED/OI|CI|I/FULL"
    cmd = "echo 'univention' | smbcacls {} --user={} --add '{}'".format(filename, user_name, new_acl)
    if samba_workstation:
        cmd += " --netbiosname='{}'".format(samba_workstation)
    rv, stdout, stderr = exec_cmd(cmd, log=True, raise_exc=False, shell=True)
    if not allowed and "NT_STATUS_ACCESS_DENIED" not in stdout:
        utils.fail(
            "Expected NT_STATUS_ACCESS_DENIED, user could change the permissions: {}".format(stdout)
        )
    elif allowed and "NT_STATUS_ACCESS_DENIED" in stdout:
        utils.fail(
            "Expected user to be able to change the permissions, got NT_STATUS_ACCESS_DENIED: {}".format(
                stdout
            )
        )


@retry_cmd
def check_share_read(user, ip_address, share, passwd="univention", filename="/*", expected_result=0):
    print(".... Check {} read ....".format(share))
    cmd_read_share = ["smbclient", "//%(ip)s/%(share)s", "-U", "%(user)s", "-c", "dir %(filename)s"]
    read = run_commands(
        [cmd_read_share],
        {"ip": ip_address, "share": share, "user": "{0}%{1}".format(user, passwd), "filename": filename},
    )
    assert read[0] == expected_result, "Read share (%r) result (%r), expected (%r)" % (
        share,
        read[0],
        expected_result,
    )


@retry_cmd
def check_share_write(
    user, ip_address, share, passwd="univention", remote_filename=None, expected_result=0
):
    print(".... Check {} write ....".format(share))
    f = tempfile.NamedTemporaryFile(dir="/tmp")
    if not remote_filename:
        remote_filename = os.path.basename(f.name)
    cmd_write_share = [
        "smbclient",
        "//%(ip)s/%(share)s",
        "-U",
        "%(user)s",
        "-c",
        "put %(filename)s %(remote_filename)s",
    ]
    write = run_commands(
        [cmd_write_share],
        {
            "ip": ip_address,
            "share": share,
            "user": "{0}%{1}".format(user, passwd),
            "filename": f.name,
            "remote_filename": remote_filename,
        },
    )
    f.close()
    assert write[0] == expected_result, "Write share (%r) result (%r), expected (%r)" % (
        share,
        write[0],
        expected_result,
    )
