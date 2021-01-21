#!/usr/share/ucs-test/runner python
## desc: Test the Samba SYSVOL replication with multi-school domain setup
## bugs: [34225]
## roles: [domaincontroller_slave, domaincontroller_backup]
## packages: [univention-samba4]
## tags: [SKIP-UCSSCHOOL,apptest,ucsschool,ucsschool_base1]
## exposure: dangerous

from os import path
from re import IGNORECASE, match, search
from subprocess import PIPE
from sys import exit
from time import sleep

import univention.testing.utils as utils
from univention.testing.strings import random_username
from univention.testing.ucsschool.test_samba4 import TestSamba4


class TestSYSVOLReplicationMultiSchool(TestSamba4):
    def execute_cmd_on_host(self, host, command_line):
        """
        Logs into the given remote 'host' using 'univention-ssh' and test
        admin credentials and executes there the given 'command_line'.
        Returns the stdout produced on the remote 'host'.
        """
        print ("\nAccessing the remote host '%s' using the test administrator credentials" % host)

        # '/dev/stdin' used to avoid creation of a file with a password:
        cmd = (
            "univention-ssh",
            "-timeout",
            "120",
            "/dev/stdin",
            self.admin_username + "@" + host,
            command_line,
        )

        stdout, stderr = self.create_and_run_process(cmd, PIPE, self.admin_password)
        if stderr:
            # ignore warnings (both lower/UPPER case)
            # ("Permanently added to the list of known hosts", etc.):
            if bool(match("Warning|Warnung", stderr, IGNORECASE)):
                print "Ignoring the following warning message:", stderr
            else:
                utils.fail(
                    "An error occured while connecting to the remote host '%s' via ssh or executing the"
                    " command: '%s'" % (host, stderr)
                )
        if stdout:
            stdout = stdout.strip()
            print (
                "\nThe output of the command '%s' executed on the remote host '%s' is: '%s'"
                % (command_line, host, stdout)
            )
            return stdout

    def check_sysvol_replication(self, host):
        """
        Executes the command on the given 'host' to check the presence of
        a test GPO folder in Samba sysvol.
        """
        print "\nChecking SYSVOL replication to host '%s':" % host

        sysvol_path = "/var/lib/samba/sysvol/%s/Policies/%s/" % (
            self.UCR["domainname"],
            self.gpo_reference,
        )

        # command should return 'True' if folder exists and 'False' otherwise:
        command_line = "[ -d %s ] && echo 'True' || echo 'False'" % sysvol_path

        print "\nWaiting for SYSVOL synchronisation to happen (up to 370 sec.)"
        remote_stdout = ""

        for attempt in range(37):
            remote_stdout = self.execute_cmd_on_host(host, command_line)
            if remote_stdout == "True":
                # folder created, replication works
                return
            print "Waiting 10 more seconds before next check..."
            sleep(10)  # wait up to 5 (+1) mins (cron job schedule)

        if not remote_stdout:
            utils.fail(
                "The command '%s' executed on the remote host '%s' produced no output to 'stdout'"
                % (command_line, host)
            )
        if remote_stdout != "True":
            if remote_stdout == "False":
                utils.fail(
                    "The command to check the sysvol replication on a remote host '%s' reported that "
                    "'%s' GPO folder "
                    "does not exist. (Replication did not work)." % (host, self.gpo_reference)
                )

            utils.fail(
                "The command to check the sysvol replication on a remote host '%s' did not report that "
                "'%s' GPO folder exists. Command's stdout from the remote host: '%s'"
                % (host, self.gpo_reference, remote_stdout)
            )

    def run_local_sysvol_replication(self):
        """
        Triggers 'sysvol-sync.sh' locally.
        """
        repl_script = "/usr/share/univention-samba4/scripts/sysvol-sync.sh"

        print "\nLocally executing the replication script '%s'" % repl_script
        if not path.exists(repl_script):
            utils.fail("The replication script '%s' file cannot be found." % repl_script)

        stdout, stderr = self.create_and_run_process(repl_script)
        if stderr:
            utils.fail(
                "An error occured while running the replication script '%s': '%s'"
                % (repl_script, stderr)
            )

    def get_other_hostnames_from_search(self, search_results):
        """
        Returns the list of other hostnames in search_results
        except for the local hostname and the DC-Master.
        """
        sysvol_sync_host = self.UCR.get("samba4/sysvol/sync/host")
        try:
            other_hostnames = search_results.split()

            # DC-Master might not be in a list if it has no Samba4.
            if sysvol_sync_host in other_hostnames:
                # remove the DC Master as it is added to the first place:
                other_hostnames.remove(sysvol_sync_host)

            # remove local DC hostname:
            other_hostnames.remove(self.UCR.get("hostname"))
        except ValueError as exc:
            utils.fail(
                "An error occured while trying to remove local DC hostname from the list of DCs to be "
                "checked. Probably current DC was not in the search results of DCs with Samba-4. "
                "Exception: '%s'" % exc
            )
        return other_hostnames

    def get_other_dc_hostnames(self):
        """
        Invokes the 'univention-ldapsearch' with 'ldap_master' as LDAP
        server to get the hostnames of other DC instances in the domain that
        have S4 running; Excludes the local hostname and returns the list with
        a DC-Master hostname plus all other DC hostnames in the domain.
        """
        print ("\nGenerating the list of other DCs in the domain to check the SYSVOL replication:")

        ldap_master = self.UCR.get("ldap/master")
        search_pattern = "univentionService=Samba 4"  # pick those with Samba4
        search_attribute = "displayName"

        cmd = (
            "univention-ldapsearch",
            "-h",
            ldap_master,
            "-p",
            self.UCR.get("ldap/master/port"),
            "-D",
            self.UCR.get("tests/domainadmin/account"),
            "-w",
            self.admin_password,
            search_pattern,
            search_attribute,
        )

        search_stdout, search_stderr = self.create_and_run_process(cmd)
        if search_stderr:
            print (
                "An error message while executing 'univention-ldapsearch' on the '%s' with pattern '%s':"
                " '%s'" % (ldap_master, search_pattern, search_stderr)
            )

        # reduce the LDAP search results to only 'displayName' fields:
        stdout, stderr = self.create_and_run_process(
            ("sed", "-n", "s/^%s: //p" % search_attribute), PIPE, search_stdout
        )
        if stderr:
            utils.fail(
                "An error occured while trying to sed through the LDAP search results from the "
                "DC-Master: '%s'. sed input was: '%s'" % (stderr, search_stdout)
            )
        if not stdout.strip():
            utils.fail(
                "No output from sed process, possibly an error occured during the LDAP search on "
                "DC-Master or while trying to connect to DC-Master. sed input "
                "was: '%s'" % (search_stdout,)
            )

        # DC-Master should be the first node to check the replication to:
        hosts = [ldap_master] + self.get_other_hostnames_from_search(stdout)
        print "The following hosts will be checked:", hosts
        return hosts

    def create_samba_gpo(self):
        """
        Creates a Group Policy Object for the test by executing
        'samba-tool gpo create'; saves the GPO reference to
        'self.gpo_reference'.
        """
        display_name = "ucs_test_school_gpo_" + random_username(8)
        print (
            "\nCreating Group Policy Object (GPO) for the test with a name '%s' using 'samba-tool'"
            % display_name
        )

        # define localhost explicitly:
        host = "ldap://" + self.UCR.get("hostname") + "." + self.UCR.get("domainname")

        cmd = (
            "samba-tool",
            "gpo",
            "create",
            display_name,
            "-H",
            host,
            "--username=" + self.admin_username,
            "--password=" + self.admin_password,
        )

        stdout, stderr = self.create_and_run_process(cmd)
        if stderr:
            utils.fail("An error occured while creating a GPO using 'samba-tool': '%s'" % stderr)
        if not stdout:
            utils.fail(
                "The 'samba-tool' did not produce any output to stdout, while a GPO reference was "
                "expected"
            )

        stdout = stdout.rstrip()
        print "\nSamba-tool produced the following output:", stdout
        try:
            # extracting the GPO reference from the stdout:
            self.gpo_reference = "{" + search("{(.+?)}", stdout).group(1) + "}"
        except AttributeError as exc:
            utils.fail(
                "Could not find the GPO reference in the stdout '%s' of the 'samba-tool', error: '%s'"
                % (stdout, exc)
            )

    def main(self):
        """
        Tests the replication of the Samba SYSVOL with multi-school
        domain setup (DC-Master + [optionally DC-Backup] +
        any number of DC-Slaves).
        """
        try:
            self.get_ucr_test_credentials()
            self.create_samba_gpo()

            self.run_local_sysvol_replication()

            for host in self.get_other_dc_hostnames():
                self.check_sysvol_replication(host)  # check remote replication
        finally:
            if self.gpo_reference:
                self.delete_samba_gpo()


if __name__ == "__main__":
    TestSYSVOLReplication = TestSYSVOLReplicationMultiSchool()
    exit(TestSYSVOLReplication.main())
