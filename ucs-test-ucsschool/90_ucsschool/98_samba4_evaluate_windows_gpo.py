#!/usr/share/ucs-test/runner python
## desc: Test if GPOs filtered for a native Windows Server work in exam mode
## exposure: dangerous
## packages: [univention-samba4, ucs-school-umc-computerroom, ucs-school-umc-exam, ucs-windows-tools]
## tags: [apptest,ucsschool, windows_gpo_test, native_win_client,ucsschool_base1]
## bugs: [37568,41571]
## roles:
## - domaincontroller_master
## - domaincontroller_slave

import glob
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from os import path
from subprocess import PIPE, STDOUT, Popen
from sys import exit

import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.udm
import univention.testing.utils as utils
import univention.winexe
from ucsschool.lib.models import School
from ucsschool.lib.schoolldap import SchoolSearchBase
from univention.config_registry import ConfigRegistry
from univention.testing.codes import TestCodes
from univention.testing.strings import random_username
from univention.testing.ucs_samba import force_drs_replication, get_available_s4connector_dc
from univention.testing.ucsschool.computerroom import Room
from univention.testing.ucsschool.exam import Exam

ucr = ConfigRegistry()


def run_cmd(cmd, stdout=PIPE, stdin=None, std_in=None):
    """
    Creates a process as a Popen instance with a given 'cmd'
    and 'communicates' with it.
    """
    proc = Popen(cmd, stdout=stdout, stderr=PIPE, stdin=stdin)
    return proc.communicate(std_in)


def remove_samba_warnings(input_str):
    """
    Removes the Samba Warning/Note from the given input_str.
    """
    # ignoring following messages (Bug #37362):
    input_str = input_str.replace("WARNING: No path in service IPC$ - making it unavailable!", "")
    return input_str.replace("NOTE: Service IPC$ is flagged unavailable.", "").strip()


def run_samba_tool(cmd, stdout=PIPE):
    """
    Creates a process as a Popen instance with a given 'cmd'
    and 'communicates' with it. Adds samba credintials to cmd.
    Returns (stdout, stderr).
    """
    cmd += samba_credentials
    stdout, stderr = run_cmd(cmd)

    if stderr:
        stderr = remove_samba_warnings(stderr)
    if stdout:
        stdout = remove_samba_warnings(stdout)
    return stdout, stderr


def print_domain_ips():
    domainname = ucr.get("domainname")
    dig_sources = []
    for source in ["nameserver1", "nameserver2", "nameserver3"]:
        if source in ucr:
            dig_sources.append("@%s" % ucr[source])

    for dig_source in dig_sources:
        try:
            cmd = ["dig", dig_source, domainname, "+search", "+short"]
            p1 = Popen(cmd, close_fds=True, stdout=PIPE, stderr=STDOUT)
            stdout, stderr = p1.communicate()
            print "IPs for %s: %s" % (domainname, stdout.strip())
        except OSError as ex:
            print "\n%s failed: %s" % (cmd, ex.args[1])


def windows_create_gpo(gpo_name, gpo_comment, server=""):
    """
    Creates a GPO with a given 'gpo_name' and 'gpo_comment' via
    winexe running the powershell script on the Windows host.
    """
    print "\nCreating GPO for the test with a name:", gpo_name
    try:
        ret_code, stdout, stderr = Win.create_gpo(gpo_name, gpo_comment, server)
        if ret_code != 0:
            utils.fail(
                "The creation of the GPO on the Windows host returned code '%s' when 0 is expected. "
                "STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr)
            )
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occured while creating GPO remotely: %r" % exc)


def windows_link_gpo(gpo_name, container, server=""):
    """
    Links a given 'gpo_name' to a container using powershell script
    on Windows Host via winexe.
    """
    print "\nLinking GPO '%s' to a '%s'" % (gpo_name, container)
    try:
        ret_code, stdout, stderr = Win.link_gpo(gpo_name, 1, container, server)
        if ret_code != 0:
            utils.fail(
                "The linking of the GPO on the Windows host returned code '%s' when 0 is expected. "
                "STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr)
            )
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occured while linking a GPO remotely: %r" % exc)


def windows_force_gpo_update():
    print "Forcing GPO update on Windows:"
    try:
        ret_code, stdout, stderr = Win.force_gpo_update()
        if stdout:
            print stdout
        if stderr:
            print stderr
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occured while linking a GPO remotely: %r" % exc)


def windows_set_gpo_security_filter(
    gpo_name, permission_level, target_name, target_type, replace="False", server=""
):
    """
    Applies the 'gpo_name' GPO to the 'target_name' of the 'target_type'
    by executing a powershell script on Windows host via winexe.
    """
    if permission_level not in ("GpoRead", "GpoApply", "GpoEdit", "GpoEditDeleteModifySecurity", "None"):
        utils.fail("Set-GPPermissions: unsupported permission_level: %s" % permission_level)

    if target_type not in ("Computer", "User", "Group"):
        utils.fail("Set-GPPermissions: unsupported target_type: %s" % target_type)

    print (
        "\nSet-GPPermissions on '%s' for '%s' '%s' to '%s'"
        % (gpo_name, target_name, target_type, permission_level)
    )
    try:
        ret_code, stdout, stderr = Win.Set_GPPermissions(
            gpo_name, permission_level, target_name, target_type, replace, server
        )
        if ret_code != 0:
            utils.fail(
                "Set-GPPermissions on the Windows host returned status '%s' when 0 is expected. STDOUT: "
                "%s STDERR: %s" % (ret_code, stdout, stderr)
            )
    except univention.winexe.WinExeFailed as exc:
        utils.fail("Exception during Set-GPPermissions: %r" % exc)


def windows_check_registry_key(reg_key, subkey, expected_value):
    print (
        "\nGet-ItemProperty for '%s' check subkey '%s' value '%s'" % (reg_key, subkey, expected_value)
    )

    if reg_key.startswith("HKCU\\"):
        item = "HKCU:" + reg_key[4:]
    elif reg_key.startswith("HKLM\\"):
        item = "HKLM:" + reg_key[4:]
    else:
        utils.fail("The given registry key '%s' should be either HKCU or HKLM" % reg_key)

    try:
        ret_code, stdout, stderr = Win.Get_ItemProperty(item)
        if ret_code != 0:
            utils.fail(
                "Get-ItemProperty on the Windows host returned status '%s' when 0 is expected. "
                "STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr)
            )
        print "stdout:", stdout
    except univention.winexe.WinExeFailed as exc:
        # print("Exception during Get-ItemProperty: %r\n" % exc)
        # print("Continue?\n")
        # raw_input()
        utils.fail("Exception during Get-ItemProperty: %r" % exc)

    reg_key_pattern = re.compile("^%s +: (.*)$" % subkey, re.M)
    m = reg_key_pattern.search(stdout)
    if m and m.group(1).strip() == expected_value:
        return True
    utils.fail(
        "Get-ItemProperty for %s did not return expected value (%s) for subkey %s"
        % (reg_key, expected_value, subkey)
    )


def samba_check_gpo_exists(gpo_name):
    """
    Checks that GPO with 'gpo_name' exists via samba-tool.
    """
    print "\nChecking that GPO '%s' exists." % gpo_name
    cmd = ("samba-tool", "gpo", "listall")

    stdout, stderr = run_samba_tool(cmd)
    if not stdout:
        utils.fail("The samba-tool did not produce any output when list of all GPOs is expected.")
    if gpo_name not in stdout:
        print "Output of %s: %s" % (cmd, stdout.strip())
        gpo_dirs = glob.glob("/var/lib/samba/sysvol/*/Policies/*")
        print "Files in sysvol: %s" % (gpo_dirs,)
        utils.fail("The GPO '%s' was not found in the list of all GPOs." % gpo_name)


def windows_set_gpo_registry_value(gpo_name, reg_key, value_name, value, value_type, server=""):
    """
    Sets the 'value_name', 'value' and 'value_type' for 'gpo_name' Registry Key
    """
    print "\nModifying the '%s' GPO '%s' registry key " % (gpo_name, reg_key)
    try:
        ret_code, stdout, stderr = Win.Set_GPRegistryValue(
            gpo_name, reg_key, value_name, value, value_type, server
        )
        if ret_code != 0:
            utils.fail(
                "The modification of the GPO on the Windows host returned code '%s' when 0 is expected. "
                "STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr)
            )
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occured while modifying GPO remotely: %r" % exc)


def samba_get_gpo_uid_by_name(gpo_name):
    """
    Returns the {GPO UID} for the given gpo_name using samba-tool.
    """
    stdout, stderr = run_samba_tool(("samba-tool", "gpo", "listall"))
    if not stdout:
        utils.fail("The samba-tool did not produce any output when list of all GPOs is expected.")
    if stderr:
        print "Samba-tool STDERR:", stderr

    stdout = stdout.split("\n\n")  # separate GPOs
    for gpo in stdout:
        if gpo_name in gpo:
            return "{" + re.search("{(.+?)}", gpo).group(1) + "}"


def windows_check_gpo_report(gpo_name, identity_name, server=""):
    """
    Gets the XML GPOreport for the 'gpo_name' from the remote Windows Host
    via winexe. Checks that 'identity_name' has 'gpo_name' applied.
    """
    print "\nCollecting and checking the GPOreport for %s:" % gpo_name
    try:
        ret_code, stdout, stderr = Win.get_gpo_report(gpo_name, server)
        if ret_code != 0:
            utils.fail(
                "The collection of the GPO report on the Windows host returned code '%s' when 0 is "
                "expected. STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr)
            )
        if not stdout:
            utils.fail("The GPOreport STDOUT from the remote Windows Host is empty.")
        if stderr:
            print "\nGET-GPOreport STDERR:", stderr
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occured while collecting GPO report remotely: %r" % exc)

    # Recode to match encoding specified in XML header
    gporeport_unicode = stdout.decode("cp850")
    gporeport_utf16 = gporeport_unicode.encode("utf-16")

    gpo_root = ET.fromstring(gporeport_utf16)
    gpo_types = "http://www.microsoft.com/GroupPolicy/Types"

    # find the 'TrusteePermissions' tags in xml:
    for trust_perm in gpo_root.iter("{%s/Security}TrusteePermissions" % gpo_types):

        # check name tag of the 'Trustee':
        for name in trust_perm.iter("{%s}Name" % gpo_types):
            trustee = name.text.split("\\", 1)[-1]  # cut off netbios domain prefix
            if identity_name == trustee:
                print "Found GPO test identity '%s'." % identity_name

                # check GPO is applied to user/computer:
                for access in trust_perm.iter("{%s/Security}GPOGroupedAccessEnum" % gpo_types):
                    if "Apply Group Policy" in access.text:
                        print ("Confirmed '%s' GPO application to '%s'." % (gpo_name, identity_name))
                        return True

    print "\nUnexpected GPOreport:\n"
    print gporeport_unicode
    utils.fail("\nCould not confirm that GPO '%s' is applied to '%s'" % (gpo_name, identity_name))


def sysvol_sync():
    stdout, stderr = run_cmd(("/usr/share/univention-samba4/scripts/sysvol-sync.sh"))
    print stdout
    if stderr:
        print "\nAn Error occured during sysvol sync:", stderr


def sysvol_check_gpo_registry_value(gpo_name, reg_key, value_name, value):
    """
    Checks that GPO exists on the filesystem level in sysvol;
    Checks the Registry.pol contents has test values.
    """
    print "\nChecking '%s' GPO registry key value in Samba" % gpo_name
    gpo_uid = samba_get_gpo_uid_by_name(gpo_name)  # get GPO UID to determine path

    gpo_path = "/var/lib/samba/sysvol/%s/Policies/%s" % (domainname, gpo_uid)
    if not path.exists(gpo_path):
        utils.fail("The location of '%s' GPO cannot be found at '%s'" % (gpo_name, gpo_path))

    if not path.exists(gpo_path + "/Machine") or not path.exists(gpo_path + "/User"):
        # both folders should exist
        utils.fail("The '%s' GPO has no Machine or User folder at '%s'" % (gpo_name, gpo_path))

    if reg_key.startswith("HKCU"):
        reg_pol_file = gpo_path + "/User/Registry.pol"
    elif reg_key.startswith("HKLM"):
        reg_pol_file = gpo_path + "/Machine/Registry.pol"
    else:
        utils.fail("The given registry key '%s' should be either HKCU or HKLM" % reg_key)

    if not path.exists(reg_pol_file):
        utils.fail("The Registry.pol file cannot be found at '%s'" % reg_pol_file)

    try:
        reg_policy = open(reg_pol_file)
        # skip first 8 bytes (signature and file version):
        # https://msdn.microsoft.com/en-us/library/aa374407%28v=vs.85%29.aspx
        reg_policy_text = reg_policy.read()[8:].decode(encoding="utf-16")
        reg_policy.close()
    except (IOError, OSError) as exc:
        utils.fail("An Error occured while opening '%s' file: %r" % (reg_pol_file, exc))

    reg_key = reg_key[5:]  # the 'HKCU\' or 'HKLM\' are not included:
    if reg_key not in reg_policy_text:
        utils.fail("Could not find '%s' Registry key in '%s' GPO Registry.pol" % (reg_key, gpo_name))

    if value_name not in reg_policy_text:
        utils.fail("Could not find '%s' ValueName in '%s' GPO Registry.pol" % (value_name, gpo_name))

    if value not in reg_policy_text:
        utils.fail("Could not find '%s' Value in '%s' GPO Registry.pol" % (value, gpo_name))


def samba_check_gpo_application_listed(gpo_name, username):
    """
    Checks if the 'gpo_name' GPO is listen in GPOs for
    'username' via samba-tool.
    """
    print "\nChecking that GPO '%s' is applied to %s" % (gpo_name, username)
    stdout, stderr = run_samba_tool(("samba-tool", "gpo", "list", username))
    if stdout:
        print stdout
    if stderr:
        print stderr

    if not stdout:
        utils.fail(
            "The samba-tool did not produce any output when list of all user/computer GPOs is expected."
        )
    if gpo_name not in stdout:
        utils.fail("The GPO '%s' was not found in the list of all user/computer GPOs." % gpo_name)


def dns_get_host_ip(host_name, all=False):
    """
    Lookup host_name;
    """
    print "\nLooking for '%s' host ip address:" % host_name

    ips = []
    dig_sources = []
    for source in ["nameserver1", "nameserver2", "nameserver3"]:
        if source in ucr:
            dig_sources.append("@%s" % ucr[source])

    for dig_source in dig_sources:
        try:
            cmd = ["dig", dig_source, host_name, "+search", "+short"]
            p1 = Popen(cmd, close_fds=True, stdout=PIPE, stderr=PIPE)
            stdout, stderr = p1.communicate()
            if p1.returncode == 0:
                for i in stdout.split("\n"):
                    if i:
                        ips.append(i)
            if ips:
                break
        except OSError as ex:
            print "\n%s failed: %s" % (cmd, ex.args[1])

    if not ips:
        utils.fail("Could not resolve '%s' via DNS." % host_name)
    else:
        if all:
            print "Host IPs are: %s" % (ips,)
            return ips
        else:
            print "Host IP is: %s" % (ips[0],)
            return ips[0]


def udm_get_windows_computer():
    """
    Using UDM looks for 'computers/windows' hostname of the joined
    Windows Host (Assuming there is only one).
    """
    stdout, stderr = run_cmd(("udm", "computers/windows", "list"))
    if stderr:
        print "\nAn Error occured while looking for Windows Server hostname:", stderr

    sed_stdout, stderr = run_cmd(("sed", "-n", "s/^DN: //p"), stdin=PIPE, std_in=stdout)
    if not sed_stdout:
        print (
            "SKIP: failed to find any Windows Host DN via UDM. Perhaps host not joined as a "
            "memberserver or does not exist in this setup."
        )
        exit(TestCodes.REASON_INSTALL)

    return {"hostdn": sed_stdout, "hostname": sed_stdout.split(",")[0][3:]}


def windows_check_domain():
    """
    Runs powershell script via Winexe to check Windows Host domain is correct.
    """
    print "Trying to check Windows host '%s' domain" % Win.client
    try:
        Win.winexec("check-domain", domainname)
    except univention.winexe.WinExeFailed as exc:
        utils.fail("Failed to check that Windows host domain is correct: %r" % exc)


def windows_remove_test_gpo(gpo_name, server=""):
    """
    Removes the GPO with a given 'gpo_name' via
    winexe running the powershell script on the Windows host.
    """
    print "\nRemoving GPOs created for the test:", gpo_name
    try:
        ret_code, stdout, stderr = Win.remove_gpo(gpo_name, server)
        if ret_code != 0:
            print (
                "The removal of the GPO on the Windows host returned code '%s' when 0 is expected. "
                "STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr)
            )
    except (univention.winexe.WinExeFailed, NameError) as exc:
        print ("An Error occured while removing GPO remotely: %r" % exc)


class GPO_Test(object):
    def __init__(self, school_dn, student_name, student_pwd, windows_hostname, security_filter_group):
        self.school_dn = school_dn
        self.student_name = student_name
        self.student_pwd = student_pwd
        self.windows_hostname = windows_hostname
        self.security_filter_group = security_filter_group
        random_gpo_suffix = random_username(4)
        self.test_user_gpo = "test_user_gpo_" + random_gpo_suffix
        self.test_machine_gpo = "test_machine_gpo_" + random_gpo_suffix
        self.test_user_gpo_value = random_username(4)
        self.test_machine_gpo_value = random_username(4)

    def __enter__(self):
        print "\nGPOTest.__enter__"
        # case 1: checks with user GPO
        gpo_name = self.test_user_gpo

        ## START test case debugging:
        print_domain_ips()
        print "get_available_s4connector_dc: %s" % (get_available_s4connector_dc(),)
        ## END test case debugging

        windows_create_gpo(
            gpo_name, "GPO for %s Group %s" % (self.student_name, self.security_filter_group)
        )
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_exists(gpo_name)

        windows_set_gpo_registry_value(
            gpo_name,
            r"HKCU\Software\Policies\Microsoft\UCSTestKey",
            "TestUserValueOne",
            self.test_user_gpo_value,
            "String",
        )
        force_drs_replication()
        force_drs_replication(direction="out")
        sysvol_sync()
        sysvol_check_gpo_registry_value(
            gpo_name,
            r"HKCU\Software\Policies\Microsoft\UCSTestKey",
            "TestUserValueOne",
            self.test_user_gpo_value,
        )

        windows_link_gpo(gpo_name, self.school_dn)
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_application_listed(gpo_name, self.student_name)

        windows_set_gpo_security_filter(gpo_name, "GpoRead", "Authenticated Users", "Group", "True")
        if ucr.is_true("connector/s4/mapping/gpo/ntsd", False):
            # Workaround for Bug #35336
            utils.wait_for_connector_replication()
            utils.wait_for_replication()
            utils.wait_for_connector_replication()
        windows_set_gpo_security_filter(gpo_name, "GpoApply", self.security_filter_group, "Group")
        force_drs_replication()
        force_drs_replication(direction="out")
        # windows_force_gpo_update()
        windows_check_gpo_report(gpo_name, self.security_filter_group)

        # case 2: checks with computer GPO
        gpo_name = self.test_machine_gpo
        windows_create_gpo(gpo_name, "GPO for %s Windows host" % self.windows_hostname)
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_exists(gpo_name)

        windows_set_gpo_registry_value(
            gpo_name,
            r"HKLM\Software\Policies\Microsoft\UCSTestKey",
            "TestComputerValueTwo",
            self.test_machine_gpo_value,
            "String",
        )
        force_drs_replication()
        force_drs_replication(direction="out")
        sysvol_sync()
        sysvol_check_gpo_registry_value(
            gpo_name,
            r"HKLM\Software\Policies\Microsoft\UCSTestKey",
            "TestComputerValueTwo",
            self.test_machine_gpo_value,
        )

        # windows_link_gpo(gpo_name, self.school_dn) ## doesn't work: Bug #40435
        windows_link_gpo(gpo_name, ldap_base)
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_application_listed(gpo_name, self.windows_hostname)

        windows_set_gpo_security_filter(gpo_name, "GpoRead", "Authenticated Users", "Group", "True")
        if ucr.is_true("connector/s4/mapping/gpo/ntsd", False):
            # Workaround for Bug #35336
            utils.wait_for_connector_replication()
            utils.wait_for_replication()
            utils.wait_for_connector_replication()
        windows_set_gpo_security_filter(gpo_name, "GpoApply", self.security_filter_group, "Group")
        force_drs_replication()
        force_drs_replication(direction="out")
        # windows_force_gpo_update()
        windows_check_gpo_report(gpo_name, self.security_filter_group)

        print "\nGPOTest.__enter__ return"
        return self

    def __exit__(self, exc_type, exc_value, etraceback):
        print "\nGPOTest.__exit__"
        windows_remove_test_gpo(self.test_user_gpo)
        windows_remove_test_gpo(self.test_machine_gpo)

    def check(self):
        print "\nGPOTest.check"
        windows_force_gpo_update()  # seems to be necessary even for machine GPO after reboot

        # case 1: checks with user GPO
        # TODO: Doesn't work as Admin, needs to be checked with the student-account!
        # windows_check_registry_key("HKCU\Software\Policies\Microsoft\UCSTestKey",
        # "TestUserValueOne", self.test_user_gpo_value)

        # case 2: checks with computer GPO
        windows_check_registry_key(
            r"HKLM\Software\Policies\Microsoft\UCSTestKey",
            "TestComputerValueTwo",
            self.test_machine_gpo_value,
        )


def test_exam_gpo(ucr, udm, schoolenv, windows_client):

    school = SchoolSearchBase.getOU(ucr["ldap/hostdn"])
    school_search_base = School.get_search_base(school)
    school_dn = school_search_base.schoolDN
    exam_group_name = school_search_base.examGroupName

    schoolclassname = "%s-AA1" % school
    klasse_dn = udm.create_object(
        "groups/group", name=schoolclassname, position="cn=klassen,cn=schueler,cn=groups,%s" % school_dn
    )

    student_pwd = "univention"
    student_name, student_dn = schoolenv.create_user(school, password=student_pwd)
    udm.modify_object("groups/group", dn=klasse_dn, append={"users": [student_dn]})

    # set 2 computer rooms to contain the windows client
    room = Room(school, host_members=windows_client["hostdn"])
    schoolenv.create_computerroom(
        school, name=room.name, description=room.description, host_members=room.host_members
    )

    # Set an exam and start it
    current_time = datetime.now()
    chosen_time = current_time + timedelta(hours=2)
    exam = Exam(
        school=school,
        room=room.dn,
        examEndTime=chosen_time.strftime("%H:%M"),  # in format "HH:mm"
        recipients=[klasse_dn],
    )

    with GPO_Test(
        school_dn, student_name, student_pwd, windows_client["hostname"], exam_group_name
    ) as gpo_test:

        exam.start()
        try:
            Win.reboot_remote_win_host()
            Win.wait_until_client_is_gone(timeout=120)
            Win.wait_for_client(timeout=120)
            gpo_test.check()
        finally:
            exam.finish()


if __name__ == "__main__":
    """
    IMPORTANT: Windows Host should be joined to the domain prior test run!

    Finds Windows hostname and ip;
    Configures Winexe and checks win domain;
    Creates a User via samba-tool;
    Creates a GPO on the remote Windows Host (joined into Domain);
    Checks created GPO exist via samba-tool;
    Applies the GPO to the User and modifies GPO registry values;
    Checks GPO is listed by samba-tool for the User;
    Checks GPO registry values in the samba sysvol;
    Gets GPO report from Windows Host and verifies GPO application.

    Performs similar checks for Machine GPO using Windows host account.

    GPOs are applied using 'Security Filtering',
    'Authenticated Users' are set to have only GpoRead permissions.
    """
    ucr.load()

    domain_admin_dn = ucr.get("tests/domainadmin/account")
    domain_admin_password = ucr.get("tests/domainadmin/pwd")
    windows_admin = ucr.get("tests/windowsadmin/account", "Administrator")
    windows_admin_password = ucr.get("tests/windowsadmin/pwd", "univention")
    domainname = ucr.get("domainname")
    hostname = ucr.get("hostname")
    ldap_base = ucr.get("ldap/base")

    if not all((domain_admin_dn, domain_admin_password, domainname, hostname, ldap_base)):
        print ("\nFailed to obtain settings for the test from UCR. Skipping the test.")
        exit(TestCodes.REASON_INSTALL)

    domain_admin = domain_admin_dn.split(",")[0][len("uid=") :]
    samba_credentials = ("--username=" + domain_admin, "--password=" + domain_admin_password)

    windows_client = udm_get_windows_computer()

    # setup winexe:
    Win = univention.winexe.WinExe(
        domainname,
        domain_admin,
        domain_admin_password,
        windows_admin,
        windows_admin_password,
        445,
        dns_get_host_ip(windows_client["hostname"]),
        loglevel=0,
    )
    windows_check_domain()

    with univention.testing.udm.UCSTestUDM() as udm:
        with utu.UCSTestSchool() as schoolenv:
            test_exam_gpo(ucr, udm, schoolenv, windows_client)
