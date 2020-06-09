#!/usr/share/ucs-test/runner python
## desc: Test the DNS SRV record replication.
## bugs: [34222, 38064, 39964]
## roles:
## - domaincontroller_master
## - domaincontroller_slave
## packages: [univention-s4-connector, univention-samba4]
## tags: [apptest,ucsschool,ucsschool_base1]
## exposure: dangerous
## versions:
##  3.2-5: skip
##  4.0-1: fixed
##  4.1-2: skip
# The test should be re-enabled after the reason for the failure is resolved.

import base64
import re
from os import path
from subprocess import PIPE
from sys import exit

from samba.dcerpc import dnsp
from samba.ndr import ndr_pack, ndr_unpack
from samba.provision.sambadns import SRVRecord

import univention.testing.utils as utils
from univention.testing.ucsschool.test_samba4 import TestSamba4

try:
    from cStringIO import StringIO  # a faster version
except ImportError:
    from StringIO import StringIO


class TestS4DNSSRVReplication(TestSamba4):
    def __init__(self):
        """
        Test class constructor.
        """
        super(TestS4DNSSRVReplication, self).__init__()

        self.ldap_base = ""
        self.domainname = ""
        self.server_role = ""

        self.sam_ldb_path = ""

        self.repl_should_work = False  # to distinguish test scenarios

    def get_dns_srv_location_via_udm(self, record_name):
        """
        Looks for a given DNS SRV 'record_name' via udm list.
        Returns the the respective record 'location' attributes.
        """
        cmd = (
            "udm",
            "dns/srv_record",
            "list",
            "--superordinate",
            "zoneName=%s,cn=dns,%s" % (self.domainname, self.ldap_base),  # needs a superordinate to work
            "--filter",
            "relativeDomainName=%s" % record_name,
        )

        stdout, stderr = self.create_and_run_process(cmd)
        if stderr:
            utils.fail(
                "An error occured while trying to get the DNS SRV record '%s' via UDM: '%s'. STDERR: '%s'"
                % (record_name, " ".join(cmd), stderr)
            )
        if not stdout.strip():
            utils.fail(
                "No output from 'udm': '%s', while the '%s' SRV record with attributes was expected"
                % (" ".join(cmd), record_name)
            )

        sed_stdout = self.sed_for_key(stdout, "^  location:")
        sed_stdout = sed_stdout.strip()
        if not sed_stdout:
            utils.fail("No 'location' attribute was found for DNS SRV '%s' record" % record_name)
        return sed_stdout.split()

    def get_samba4_dns_searchbase_for_record(self, record_name):
        if self.UCR.get("connector/s4/mapping/dns/position", "").lower() == "legacy":
            dns_searchbase = "CN=MicrosoftDNS,CN=System,%s" % (self.ldap_base,)
            zone_name = self.domainname
        else:
            if record_name.endswith("._msdcs"):
                partition = "ForestDnsZones"
                record_name = record_name[:-7]
                zone_name = "_msdcs.%s" % (self.domainname,)
            else:
                partition = "DomainDnsZones"
                zone_name = self.domainname
            dns_searchbase = "CN=MicrosoftDNS,DC=%s,%s" % (partition, self.ldap_base,)
        return (record_name, zone_name, dns_searchbase)

    def get_dns_srv_via_univention_s4search(self, record_name, dns_searchbase=None):
        """
        Returns the output of a decoded 'univention-s4search' with a query
        for a given DNS SRV 'record_name'.
        """
        cmd = ["univention-s4search", "DC=%s" % record_name, "dnsRecord"]
        if dns_searchbase:
            cmd.extend(["-b", dns_searchbase])

        stdout, stderr = self.create_and_run_process(cmd)
        if stderr:
            utils.fail(
                "An error occured while trying to get the '%s' DNS SRV record via 'univention-s4search': '%s', "
                "STDERR:\n %s" % (record_name, " ".join(cmd), stderr)
            )
        if not stdout.strip():
            utils.fail(
                "No output from 'univention-s4search', while the '%s' SRV record attributes were expected"
                % record_name
            )

        stdout, stderr = self.create_and_run_process("ldapsearch-wrapper", PIPE, stdout)
        return stdout

    def add_remove_srv_record_location_via_ldbmodify(self, record_name, action):
        """
        Modifies the given 'record_name' DNS SRV record using 'ldbmodify'
        tool with a test LDIF generated on the fly.
        """
        print (
            "\nModifying the DNS SRV '%s' record in Samba using 'ldbmodify', %s(-ing) a test value:"
            % (record_name, action)
        )

        if action not in ("add", "delete"):
            utils.fail(
                "The given action '%s' is not supported by the 'ldbmodify', only 'add' or 'delete' are allowed."
                % action
            )

        record_name, zone_name, dns_searchbase = self.get_samba4_dns_searchbase_for_record(record_name)
        samba_record_dn = "DC=%s,DC=%s,%s" % (record_name, zone_name, dns_searchbase)

        # prepare an LDIF to add/remove a test value to/from the SRV record:
        LDIFRecord = StringIO()
        LDIFRecord.write("dn: " + samba_record_dn + "\n")
        LDIFRecord.write("changetype: modify\n")
        LDIFRecord.write(action + ": dnsRecord\n")

        # unique test values set that was added to tested records in Samba
        (priority, weight, port, target) = (35, 888, 35512, "ucs_test_2.hostname.local")
        s = SRVRecord(target, port, priority, weight)
        base64.b64encode(ndr_pack(s))
        LDIFRecord.write("dnsRecord:: %s" % base64.b64encode(ndr_pack(s)))

        cmd = (
            "ldbmodify",
            "-H",
            self.sam_ldb_path,
            "--user=" + self.admin_username + "%" + self.admin_password,
            "-k",
            "no",  # do not use kerberos
        )

        stdout, stderr = self.create_and_run_process(cmd, PIPE, LDIFRecord.getvalue())
        LDIFRecord.close()

        if stderr:
            utils.fail(
                "An error occured while trying to modify the '%s' SRV record via 'ldbmodify': '%s'. STDERR:\n '%s'"
                % (record_name, " ".join(cmd), stderr)
            )
        if not stdout.strip():
            utils.fail(
                "No output from 'ldbmodify': '%s', while the '%s' SRV record modification confirmation was expected"
                % (" ".join(cmd), record_name)
            )
        print stdout

    def get_samba_srv_record_location(self, record_name):
        """
        Returns a () with four lists: priority; weight; port and host filled
        with respective location attribute values for the given 'record_name'.
        The first element in each list will be corresponding to a first record
        location values, the second to a second location, etc.
        """

        record_name, zone_name, dns_searchbase = self.get_samba4_dns_searchbase_for_record(record_name)
        zone_searchbase = "DC=%s,%s" % (zone_name, dns_searchbase)

        ldif = self.get_dns_srv_via_univention_s4search(record_name, zone_searchbase)
        dns_record_re = re.compile("^dnsRecord:: (.*)$", re.M)
        priority = []
        weight = []
        port = []
        host = []
        for dns_record_base64 in dns_record_re.findall(ldif):
            dns_record_ndr = base64.b64decode(dns_record_base64)
            dns_record = ndr_unpack(dnsp.DnssrvRpcRecord, dns_record_ndr)

            if dns_record.wType != dnsp.DNS_TYPE_SRV:
                continue

            priority.append(str(dns_record.data.wPriority))
            weight.append(str(dns_record.data.wWeight))
            port.append(str(dns_record.data.wPort))
            host.append(str(dns_record.data.nameTarget))

        if not all((priority, weight, port, host)):
            utils.fail(
                "Could not determine at least one of the location attribute values for the '%s' SRV record in Samba: "
                "priority=%s, weight=%s, port=%s, hostname=%s"
                % (record_name, priority, weight, port, host)
            )

        if len(priority) != len(weight) != len(port) != len(host):
            utils.fail(
                "The amount of values found for '%s' SRV record in Samba is different, not all the values were found: "
                "priority=%s, weight=%s, port=%s, hostname=%s"
                % (record_name, priority, weight, port, host)
            )
        return priority, weight, port, host

    def whereis_dns_edit(self):
        """
        Looks for a 'univention-directory-manager-tools' using 'whereis'
        to determine the path to 'univention-dnsedit'.
        Returns the absolute path string to 'univention-dnsedit'.
        """
        print "\nLooking for 'univention-dnsedit' using 'whereis'"
        cmd = ("whereis", "univention-directory-manager-tools")
        stdout, stderr = self.create_and_run_process(cmd)

        if stderr:
            utils.fail("An error occured while looking for 'univention-dnsedit'. STDERR: '%s'" % stderr)

        dns_edit_path = self.sed_for_key(stdout, "^univention-directory-manager-tools: ").strip()
        dns_edit_path += "/univention-dnsedit"

        if not path.exists(dns_edit_path):
            utils.fail(
                "The 'univention-dnsedit' or/and 'univention-directory-manager-tools' cannot be found"
            )
        return dns_edit_path

    def add_remove_record_location_via_dns_edit(self, records, action):
        """
        Adds or removes a test location values to each record in a given list
        of 'records' using 'univention-dnsedit' (i.e. to records in openLDAP).
        """
        if action not in ("add", "remove"):
            utils.fail(
                "The given '%s' action is not a supported option for use with 'univention-dnsedit'"
                % action
            )

        # test values that are added/(removed) to/(from) the 'records'
        # in a format: (priority, weight, port, hostname)
        test_location = ("53", "777", "63256", "ucs_test.hostname.local.")
        print (
            "\n%s(-ing) the test location values '%s' to/from each record in '%s'"
            % (action.upper(), test_location, records)
        )

        dns_edit_path = "/usr/share/univention-directory-manager-tools/" "univention-dnsedit"

        if not path.exists(dns_edit_path):
            print (
                "\nThe 'univention-dnsedit' cannot be found in the default location at '%s'. Trying to determine location."
                % dns_edit_path
            )
            dns_edit_path = self.whereis_dns_edit()

        cmd = (
            dns_edit_path,
            "--binddn=" + self.UCR.get("tests/domainadmin/account"),
            "--bindpwd=" + self.admin_password,
            self.domainname,
            action,
            "srv",
        )

        for record in records:
            print ("\n%s(-ing) the test location to/from the record '%s'" % (action.upper(), record))
            # making 'univention-dnsedit' cli-compatible record format:
            record = record.replace("_", "", 2)
            record = record.split(".", 1)

            record_cmd = tuple(record)
            record_cmd += test_location

            try:
                stdout, stderr = self.create_and_run_process(cmd + record_cmd)
            except IndexError as exc:  # some records in some setups do not exist
                pass  # workaround for Bug #38064
            if stderr:
                # ignore the 'Does not exist' messages
                if "Does not exist" not in stderr:
                    print (
                        "An error occured while executing command '%s', STDERR: '%s'"
                        % (" ".join(cmd + record_cmd), stderr)
                    )

    def check_srv_records_equal(self, dns_srv_records):
        """
        Checks that every record in the given list of DNS SRV records has
        the same location attribute values in the LDAP and Samba.
        Only applicable to DC-Master(s), as on DC-Slave the values
        are hardcoded.
        """
        if self.server_role == "domaincontroller_master":
            print (
                "\nChecking that all the DNS SRV records in LDAP and Samba have same attribute values (Priority, "
                "Weight, Port, Host):"
            )

            for record_name in dns_srv_records:
                print (
                    "\nChecking that DNS SRV '%s' record has the same attribute values in LDAP and Samba."
                    % record_name
                )

                ldap_attrs = self.get_dns_srv_location_via_udm(record_name)
                samba_attrs = self.get_samba_srv_record_location(record_name)

                for counter, attribute in enumerate(ldap_attrs):
                    if attribute.endswith("."):
                        # remove dots at the end of attributes from openLDAP:
                        ldap_attrs[counter] = attribute[:-1]

                for counter, samba_attr in enumerate(samba_attrs):
                    if ldap_attrs[counter::4] != samba_attr:
                        utils.fail(
                            "The '%s' record attributes in LDAP and Samba are different: '%s' vs. '%s'"
                            % (record_name, ldap_attrs, samba_attrs)
                        )

    def check_test_srv_record_replicated(self, record_name, to_samba):
        """
        Checks if the DNS SRV 'record_name' test values were replicated
        to Samba (if to_samba==True) or from samba (when to_samba==False).
        """
        replicated_values = []

        if to_samba:
            print (
                "\nChecking the DNS SRV '%s' record replication from openLDAP to Samba:" % record_name
            )

            # unique test values set that was added to the records in openLDAP:
            test_location = ("53", "777", "63256", "ucs_test.hostname.local")
            samba_attrs = self.get_samba_srv_record_location(record_name)

            for counter, samba_attr in enumerate(samba_attrs):
                if test_location[counter] in samba_attr:
                    # the value was replicated
                    replicated_values.append(test_location[counter])

            if replicated_values and not self.repl_should_work:
                utils.fail(
                    "The replication from openLDAP to Samba worked "
                    "in a case it should not have worked. Record '%s'. "
                    "Test recrod values: '%s', state in Samba '%s'. "
                    "The following values were replicated: '%s'"
                    % (record_name, test_location, samba_attrs, replicated_values)
                )

            if len(replicated_values) != 4 and self.repl_should_work:
                utils.fail(
                    "The replication from openLDAP to Samba did not "
                    "work in a case it should have worked. Record '%s'."
                    " Test record values: '%s', state in Samba '%s'. "
                    "The following values were replicated: '%s'"
                    % (record_name, test_location, samba_attrs, replicated_values)
                )
        else:
            # replication to openLDAP:
            print (
                "\nChecking the DNS SRV '%s' record replication from Samba to openLDAP:" % record_name
            )

            # unique test values set that was added to tested records in Samba
            test_location = ("35", "888", "35512", "ucs_test_2.hostname.local.")
            ldap_attrs = self.get_dns_srv_location_via_udm(record_name)

            for attr_value in test_location:
                if attr_value in ldap_attrs:
                    # the value was replicated
                    replicated_values.append(attr_value)

            if replicated_values and not self.repl_should_work:
                utils.fail(
                    "The replication from Samba to openLDAP worked, when it should not. Record '%s'. Test record "
                    "values: '%s', state in openLDAP '%s'." % (record_name, test_location, ldap_attrs)
                )

            if len(replicated_values) != 4 and self.repl_should_work:
                utils.fail(
                    "The replication from Samba to openLDAP did not work, when it should. Record '%s'. Test record "
                    "values: '%s', state in openLDAP '%s'." % (record_name, test_location, ldap_attrs)
                )

    def determine_test_scenario(self):
        """
        Determines the test scenario, i.e. whether the DNS SRV replication
        should work for a specific set of records:
        - if current role is DC-Master (Singlemaster): both ways should work;
        - if current role is DC-Master (multi-school): no way should work;
        - if current role is DC-Slave: (multi-school): no way should work.
        """
        self.server_role = self.UCR.get("server/role")
        print ("\nDetermining the test scenario, current DC role is '%s'" % self.server_role)
        if self.server_role == "domaincontroller_master":
            dc_slaves = self.sed_for_key(self.get_udm_list_dc_slaves_with_samba4(), "^  name: ").split()

            if dc_slaves:
                # multi-school domain with DC-Slave(s), no replication
                print (
                    "\nCurrent role is a DC-Master and there is(are) DC-Slave(s) %s in the domain, replication should "
                    "not work for specific DNS SRV records." % dc_slaves
                )
            else:
                # a Single-Master system setup, openLDAP -> SAMBA replication
                print (
                    "\nCurrent role is a DC-Master and it is the only DC in the domain, two-way replication should "
                    "work for tested DNS SRV records"
                )
                self.repl_should_work = True

        elif self.server_role == "domaincontroller_slave":
            # running on a DC-Slave, no replication
            print (
                "\nCurrent role is a DC-Slave, no replication should happen for a list of specific DNS SRV records."
            )

        else:
            print ("Current server role '%s' is not supported, skipping test.." % self.server_role)
            self.return_code_result_skip()

    def get_ucr_settings_for_test(self):
        """
        Writes all UCR variables needed for the test to the global vars.
        """
        self.get_ucr_test_credentials()
        try:
            self.ldap_master = self.UCR["ldap/master"]
            self.ldap_base = self.UCR["ldap/base"]
            self.domainname = self.UCR["domainname"]
        except KeyError as exc:
            print (
                "\nAn error occured while trying to get UCR settings for the test: %r. Skipping test."
                % exc
            )
            self.return_code_result_skip()

    def main(self):
        """
        Tests the DNS SRV records replication openLDAP <-> Samba4.
        Test scenario and cases are determined by the
        'determine_test_scenario' method.
        List of tested records is dns_srv_records.
        """
        self.get_ucr_settings_for_test()
        self.determine_test_scenario()
        self.sam_ldb_path = self.get_samba_sam_ldb_path()

        # DNS SRV records that have to be checked,
        # (determined by the 'ucs-school-metapackage/*.inst' scripts)
        dns_srv_records = (
            "_ldap._tcp",
            "_ldap._tcp.pdc._msdcs",
            "_ldap._tcp.dc._msdcs",
            "_ldap._tcp.gc._msdcs",
            "_gc._tcp",
            "_kerberos._tcp",
            "_kerberos._udp",
            "_kerberos-adm._tcp",
            "_kerberos._tcp.dc._msdcs",
            "_kpasswd._tcp",
            "_kpasswd._udp",
            "_kerberos._tcp.Default-First-Site-Name._sites.dc._msdcs",
            "_kerberos._tcp.Default-First-Site-Name._sites",
            # '_ldap._tcp.Default-First-Site-Name._sites.gc._msdcs',	# is not ignored by s4-connector
            "_ldap._tcp.Default-First-Site-Name._sites.dc._msdcs",
            "_ldap._tcp.Default-First-Site-Name._sites",
            "_gc._tcp.Default-First-Site-Name._sites",
        )

        try:
            # check that SRV record attribute values are the same in
            # openLDAP and Samba initially (DC-Master only):
            self.check_srv_records_equal(dns_srv_records)

            # case 1: modify values in openLDAP and check the state in Samba:
            print (
                "\n\nTest case 1: adding new DNS SRV record attribute values in openLDAP, checking their values in Samba:"
            )
            self.add_remove_record_location_via_dns_edit(dns_srv_records, "add")
            utils.wait_for_replication()
            utils.wait_for_connector_replication()

            print ("\nChecking if test values of the SRV records were replicated to Samba.")
            for srv_record in dns_srv_records:
                self.check_test_srv_record_replicated(srv_record, True)

            # restore to previous state in openLDAP by removing the test record
            self.add_remove_record_location_via_dns_edit(dns_srv_records, "remove")
            utils.wait_for_replication()
            utils.wait_for_connector_replication()

            # check that SRV record values are the same in openLDAP/Samba
            # at this point:
            self.check_srv_records_equal(dns_srv_records)

            # case 2: modify in Samba and check the state in openLDAP:
            print (
                "\n\nTest case 2: adding new DNS SRV record attribute values in Samba, checking their values in openLDAP:"
            )
            for srv_record in dns_srv_records:
                self.add_remove_srv_record_location_via_ldbmodify(srv_record, "add")
            utils.wait_for_connector_replication()
            utils.wait_for_replication()
            utils.wait_for_connector_replication()

            print ("\nChecking if test values of the SRV records were replicated to openLDAP.")
            for srv_record in dns_srv_records:
                self.check_test_srv_record_replicated(srv_record, False)

        finally:
            print "\nPerforming clean-up after the test:"  # in openldap
            self.add_remove_record_location_via_dns_edit(dns_srv_records, "remove")
            utils.wait_for_replication()
            utils.wait_for_connector_replication()

            for srv_record in dns_srv_records:  # and in samba
                self.add_remove_srv_record_location_via_ldbmodify(srv_record, "delete")
            utils.wait_for_connector_replication()
            utils.wait_for_replication()
            utils.wait_for_connector_replication()

            # check that SRV record values are the same after the clean-up:
            self.check_srv_records_equal(dns_srv_records)


if __name__ == "__main__":
    TestDNSSRVRecordsReplication = TestS4DNSSRVReplication()
    exit(TestDNSSRVRecordsReplication.main())
