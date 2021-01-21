#!/usr/share/ucs-test/runner python
## desc: Test the DC Locator (DNS) with Samba4.
## bugs: [34223, 37698]
## roles:
## - domaincontroller_master
## - domaincontroller_backup
## - domaincontroller_slave
## packages: [univention-samba4]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: careful
## versions:
##  4.0-0: skip
##  4.0-1: skip
##  3.2-5: skip
##  4.1-2: skip

from sys import exit
from time import sleep

import univention.testing.utils as utils
from univention.testing.ucsschool.test_samba4 import TestSamba4


class TestS4DCLocatorDNS(TestSamba4):
    def __init__(self):
        """
        Test class constructor
        """
        super(TestS4DCLocatorDNS, self).__init__()

        self.site_dcs = []  # stores DCs located at the same school site/branch

    def check_dc_location(self):
        """
        Performs the lookup and checks results.
        Possible fail cases:
         No DCs located, but at least one correct option exists;
         No correct options exist, but a DC was located;
         Located DC does not fit the list of correct options.
        Possible success cases:
         No DCs located and no DC options are available;
         Located DC is in the list of DC options.
        """
        print ("\nChecking if a right DC was located, correct options are: %s" % self.site_dcs)
        located_dc = self.get_dc_names()

        if self.site_dcs and not located_dc:
            utils.fail("No DCs were located while there is at least one correct option exists.")

        if not self.site_dcs and not located_dc:
            print ("\nNo DCs are in the list of correct options and no DCs were located.")
            return

        for correct_dc in self.site_dcs:
            if correct_dc in located_dc:
                return

        utils.fail(
            "None of the correct DC options were found among the located DC:\n%s" % located_dc.strip()
        )

    def get_dc_names(self):
        """
        Uses 'net ads lookup' to find and return located Domain Controller.
        """
        cmd = ("net", "ads", "lookup")

        stdout, stderr = self.create_and_run_process(cmd)
        if stderr:
            print (
                "\nThe following message occured during '%s' command execution, STDERR:\n%s"
                % (" ".join(cmd), stderr.strip())
            )

        grep_stdout = self.grep_for_key(stdout, "Domain Controller:")
        grep_stdout = grep_stdout.strip()

        if not grep_stdout:
            print (
                "The 'Domain Controller:' line was not found in the output from 'net ads lookup', i.e. "
                "no Domain Controllers were located."
            )
        return grep_stdout

    def populate_list_of_site_dcs(self):
        """
        Detects if current DC is in the School branch site or in the central
        School department. Populates the list with all DCs running Samba 4
        located in the branch or central department respectively via UDM list.
        """
        if self.is_a_school_branch_site(self.UCR.get("ldap/hostdn")):
            # in a branch site (looks for DC-Slaves)
            branch_dcs = self.sed_for_key(self.get_udm_list_dc_slaves_with_samba4(), "^  fqdn: ")

            self.site_dcs.extend(branch_dcs.split())
            print ("\nThe following DCs are located in the current School branch site:\n%s" % branch_dcs)

        else:
            # in a central department site (looks for DC-Master and DC-Backup)
            central_dcs = self.sed_for_key(self.get_udm_list_dcs("domaincontroller_master"), "^  fqdn: ")
            central_dcs += " "
            central_dcs += self.sed_for_key(
                self.get_udm_list_dcs("domaincontroller_backup"), "^  fqdn: "
            )
            self.site_dcs.extend(central_dcs.split())
            print (
                "\nThe following DCs are located in the current central School department:\n%s"
                % central_dcs
            )

    def main(self):
        """
        Tests the Domain Controller location process as done by the
        'net ads lookup'.
        Correct DC location behavior:
         for DC-Slave -> itself or other DC-Slave within the same branch;
         for DC-Backup -> itself or DC-Master in a central department;
         for DC-Master -> itself or DC-Backup in a central department;
        """
        try:
            self.UCR.load()
            self.populate_list_of_site_dcs()  # get all site DCs with Samba4

            # case 1: samba running and any current site DC can be
            # located including the local (current) DC itself
            print ("\nForcing the 'samba' service start to ensure it runs:")
            self.start_stop_service("samba", "start")
            sleep(30)  # wait to ensure that 'samba' works
            self.check_dc_location()

            # case 2: samba stopped and current DC should not be located,
            # other DCs in a current site can be located (if there are any)
            print ("\nForcing the 'samba' service stop to ensure it is stopped:")
            self.start_stop_service("samba", "stop")
            sleep(30)  # give the environment some seconds Bug #34223
            try:
                self.site_dcs.remove(self.UCR.get("ldap/server/name"))
            except ValueError as exc:
                utils.fail(
                    "An error occured while trying to remove the current DC name from the list of site "
                    "DCs that can be discovered: %r. Current DC should be present in this list." % exc
                )

            self.check_dc_location()
        finally:
            print "\nForcing the 'samba' service (re-)start:"
            self.start_stop_service("samba", "restart")
            sleep(30)  # wait to ensure that 'samba' works


if __name__ == "__main__":
    TestDCLocatorDNS = TestS4DCLocatorDNS()
    exit(TestDCLocatorDNS.main())
