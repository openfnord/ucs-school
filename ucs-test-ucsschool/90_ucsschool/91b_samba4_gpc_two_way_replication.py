#!/usr/share/ucs-test/runner python
## desc: Test the Samba4 GPC objects and links replication from DC-Master to DC-Slave or vice versa.
## bugs: [34214, 34216]
## roles: [domaincontroller_master, domaincontroller_slave]
## packages: [univention-samba4, ucs-school-slave|ucs-school-master]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous

from __future__ import print_function

from re import search
from sys import exit
from time import sleep

import ldap

import ucsschool.lib.models
import univention.testing.utils as utils
from univention.admin.uldap import getMachineConnection
from univention.testing.strings import random_username
from univention.testing.ucsschool.test_samba4 import TestSamba4


class TestGPCReplicationTwoWays(TestSamba4):
    def __init__(self):
        """
        Test class constructor
        """
        super(TestGPCReplicationTwoWays, self).__init__()

        self.host_or_ip = ""
        self.remote_host = ""
        self.local_ip = ""

    def check_gpo_replicated_locally(self):
        """
        Using 'samba-tool' looks for created GPO to check if it was replicated
        from the remote host to the localhost.
        """
        print("\nChecking if GPO '%s' was replicated to the current DC" % self.gpo_reference)
        sleep(30)  # wait for replication to happen

        cmd = (
            "samba-tool",
            "gpo",
            "show",
            self.gpo_reference,
            "--ipaddress=" + self.local_ip,
            "--username",
            self.admin_username,
            "--password",
            self.admin_password,
        )
        stdout, stderr = self.create_and_run_process(cmd)

        if stderr:
            print("\nExecuting cmd:", cmd)
            utils.fail("The 'samba-tool' produced the following output to STDERR: '%s'" % stderr)
        if not stdout:
            utils.fail(
                "The 'samba-tool' did not produce any output to STDOUT, while GPO info was expected"
            )

        gpo_dn = "CN=%s,CN=Policies,CN=System" % self.gpo_reference
        if gpo_dn not in stdout:
            utils.fail(
                "The 'samba-tool' did not list the replicated test GPO in the 'dn', STDOUT: '%s'"
                % stdout
            )

    def find_school_ou(self):
        (lo, _pos) = getMachineConnection(ldap_master=True)
        schools = ucsschool.lib.models.School.get_all(lo)

        server_role = self.UCR.get("server/role")
        if server_role == "domaincontroller_master":
            slave_filter = "(&(aRecord=%s)(objectClass=univentionDomainController))"
            filter_string = ldap.filter.filter_format(slave_filter, (self.remote_host,))
            host_dn  = lo.searchDn(filter=filter_string, attr=["dn"])[0]

            def get_names(school):
                for s in school.get_administrative_server_names(lo):
                    yield s.lower()
                for s in school.get_educational_server_names(lo):
                    yield s.lower()

            schools = [s for s in schools if host_dn.lower() in get_names(s)]

        if not schools:
            utils.fail("Could not find the a School-OU")
        return schools[0].dn

    def create_gpo_on_remote_host(self):
        """
        Using samba-tool creates a GPO on 'self.remote_host' (can be hostname
        or an IP address with respective 'self.host_or_ip').
        """
        display_name = "ucs_test_school_gpo_" + random_username(8)

        print(
            "\nCreating a Group Policy Object (GPO) on the host '%s' with a display name '%s' using "
            "'samba-tool'" % (self.remote_host, display_name)
        )

        cmd = (
            "samba-tool",
            "gpo",
            "create",
            display_name,
            self.host_or_ip,
            self.remote_host,
            "-k",
            "no",
            "--username",
            self.admin_username,
            "--password",
            self.admin_password,
        )

        stdout, stderr = self.create_and_run_process(cmd)
        if stderr:
            print("\nExecuting cmd:", cmd)
            print(
                "\nAn error message while creating a GPO using 'samba-tool' on the remote host '%s'. "
                "STDERR:\n%s" % (self.remote_host, stderr)
            )
        if not stdout:
            utils.fail(
                "The 'samba-tool' did not produce any output to STDOUT, while a GPO reference was "
                "expected"
            )

        stdout = stdout.rstrip()
        print("\nSamba-tool produced the following output:", stdout)

        try:
            # extracting the GPO reference from the stdout:
            self.gpo_reference = "{" + search("{(.+?)}", stdout).group(1) + "}"
        except AttributeError as exc:
            utils.fail(
                "Could not find the GPO reference in the STDOUT '%s' of the 'samba-tool', error: '%s'"
                % (stdout, exc)
            )

    def create_gpo_link_on_remote_host(self, container_dn):
        """
        Creates a GPO link to a given 'container_dn' for 'self.gpo_reference'
        on the 'self.remote_host' using 'samba-tool'.
        """
        print(
            "\nLinking '%s' container and '%s' GPO on the remote host '%s' using 'samba-tool'"
            % (container_dn, self.gpo_reference, self.remote_host)
        )

        cmd = (
            "samba-tool",
            "gpo",
            "setlink",
            container_dn,
            self.gpo_reference,
            self.host_or_ip,
            self.remote_host,
            "-k",
            "no",
            "--username",
            self.admin_username,
            "--password",
            self.admin_password,
        )

        stdout, stderr = self.create_and_run_process(cmd)
        if stderr:
            print("\nExecuting cmd:", cmd)
            print(
                "\nAn error message while creating a GPO link using 'samba-tool' on the remote host "
                "'%s'. STDERR:\n%s" % (self.remote_host, stderr)
            )

        if not stdout:
            utils.fail(
                "The 'samba-tool' did not produce any output to STDOUT, while a GPO link confirmation "
                "was expected"
            )
        if container_dn not in stdout:
            utils.fail("The linked School OU (Container) was not referenced in the 'samba-tool' output")
        if self.gpo_reference not in stdout:
            utils.fail("The linked GPO was not referenced in the 'samba-tool' output")

        print("\nSamba-tool produced the following output:\n", stdout)

    def check_gpo_link_replicated_locally(self, container_dn):
        """
        Checks if previously created GPO link was replicated from the
        remote host to the localhost using 'samba-tool'.
        """
        print(
            "\nChecking the GPO links for the container '%s' using 'samba-tool' locally" % container_dn
        )
        sleep(30)  # wait for replication to happen

        cmd = (
            "samba-tool",
            "gpo",
            "getlink",
            container_dn,
            "--ipaddress=" + self.local_ip,
            "--username",
            self.admin_username,
            "--password",
            self.admin_password,
        )
        stdout, stderr = self.create_and_run_process(cmd)

        if stderr:
            print("\nExecuting cmd:", cmd)
            utils.fail(
                "An error occured while getting the GPO link using 'samba-tool', STDERR: '%s'" % stderr
            )
        if not stdout:
            utils.fail(
                "The 'samba-tool' did not produce any output to the STDOUT, while GPO list was expected"
            )

        if container_dn not in stdout:
            utils.fail(
                "The linked School OU (Container) was not referenced in the 'samba-tool' output, "
                "possibly the link was not replicated"
            )
        if self.gpo_reference not in stdout:
            utils.fail(
                "The linked GPO was not referenced in the 'samba-tool output, possibly link was not "
                "replicated"
            )

        print("\nSamba-tool produced the following output:\n", stdout)

    def find_slave_in_domain(self):
        """
        Using 'udm list' looks for any DC-Slave in the domain to test the
        replication from.
        """
        print("\nCurrent server role is DC-Master, trying to find a DC-Slave in the domain for the test")
        udm_stdout = self.get_udm_list_dc_slaves_with_samba4(with_ucsschool=True)

        if "serverRole: slave" not in udm_stdout.strip():
            print(
                "\nThe udm list to did not produce any ouptut with slave(s)to STDOUT, assuming there "
                "are no DC-Slave(s) in the domain. Skipping test..."
            )
            self.return_code_result_skip()
        else:
            sed_stdout = self.sed_for_key(udm_stdout, "^  ip: ")
            if not sed_stdout:
                utils.fail(
                    "Could not find at least one IP address of the DC-Slave in the output of the udm "
                    "list command"
                )

            slave_ips = sed_stdout.split()
            print(
                "\nThe DC-Slave(s) with the following IP address(-es) were found in the domain: '%s'"
                % slave_ips
            )
            self.remote_host = slave_ips[0]
            self.host_or_ip = "--ipaddress"  # use ip address with samba-tool

    def select_remote_host(self):
        """
        Depending on the current server role (DC-Master or DC-Slave) selects
        the remote server where from the GPC obj replication will be tested.
        (If test runs on DC-Slave the replication from the DC-Master will
        be tested and v.v.) Test skipped if there are no DC-Slave found or
        when the DC-Master has no Samba4.
        """
        server_role = self.UCR.get("server/role")
        self.ldap_master = self.UCR.get("ldap/master")

        if server_role == "domaincontroller_master":
            self.find_slave_in_domain()
            print(
                "\nThe following DC-Slave '%s' will be selected as the remote host for the test"
                % self.remote_host
            )

        elif server_role == "domaincontroller_slave":
            # check first if DC-Master has Samba4:
            if not self.dc_master_has_samba4():
                print(
                    "The DC-Master '%s' has no Samba4, thus remote check not possible, skipping the "
                    "test." % self.ldap_master
                )
                self.return_code_result_skip()

            self.remote_host = "ldap://" + self.ldap_master
            self.host_or_ip = "-H"  # to use hostname as an arg for samba-tool
            print(
                "\nCurrent server role is DC-Slave, the DC-Master '%s' will be selected as the "
                "remote host for the test" % self.remote_host
            )
        else:
            print(
                "\nThe test not inteded to run on servers other than DC-Slave or DC-Master, current "
                "role is '%s'. Skipping test..." % server_role
            )
            self.return_code_result_skip()

    def main(self):
        """
        Tests the Samba4 GPC objects (and GPO links) replication from
        DC-Master to DC-Slave and vise versa: from DC-Slave to DC-Master.
        Which direction to test is determined by the current server role
        (and thus the self.remote_host is being selected).
        """
        try:
            # Get UCR vars, select the test case (replication direction):
            self.get_ucr_test_credentials()
            self.select_remote_host()
            self.local_ip = self.UCR.get("interfaces/eth0/address")

            # Create GPO remotely and check replication:
            self.create_gpo_on_remote_host()
            self.check_gpo_replicated_locally()

            # Create remotely GPO link to School OU and check replication:
            school_ou_dn = self.find_school_ou()
            self.create_gpo_link_on_remote_host(school_ou_dn)
            self.check_gpo_link_replicated_locally(school_ou_dn)
        finally:
            if self.gpo_reference:
                sleep(30)  # wait before deleting (for LDAP entries)
                self.delete_samba_gpo()


if __name__ == "__main__":
    TestGPCReplication = TestGPCReplicationTwoWays()
    exit(TestGPCReplication.main())
