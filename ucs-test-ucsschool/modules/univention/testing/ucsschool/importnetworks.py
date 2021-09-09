# -*- coding: utf-8 -*-

from __future__ import print_function

import difflib
import ipaddress
import os
import random
import subprocess
import tempfile

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucsschool.ucs_test_school as utu
import univention.testing.utils as utils
from univention.testing.ucsschool.importcomputers import random_ip
from univention.testing.ucsschool.importou import get_school_base

HOOK_BASEDIR = "/usr/share/ucs-school-import/hooks"


configRegistry = univention.config_registry.ConfigRegistry()
configRegistry.load()


def get_reverse_net(network, netmask):
    p = subprocess.Popen(
        [
            "/usr/bin/univention-ipcalc",
            "--ip",
            network,
            "--netmask",
            netmask,
            "--output",
            "reverse",
            "--calcdns",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (stdout, stderr) = p.communicate()

    output = stdout.decode("UTF-8").strip().split(".")
    output.reverse()

    return ".".join(output)


class Network:
    def __init__(self, school, prefixlen):
        assert prefixlen > 7
        assert prefixlen < 25

        self._net = ipaddress.IPv4Interface(u"%s/%s" % (random_ip(), prefixlen))
        self.network = str(self._net.network)
        self.iprange = "%s-%s" % (
            self._net.network.network_address + 1,
            self._net.network.network_address + 10,
        )
        self.defaultrouter = self._net.network.network_address + 1
        self.nameserver = self._net.network.network_address + 2
        self.netbiosserver = self._net.network.network_address + 8

        self.router_mode = False
        self.school = school
        self.name = "%s-%s" % (self.school, self._net.network.network_address)

        self.school_base = get_school_base(self.school)

        self.dn = "cn=%s,cn=networks,%s" % (self.name, self.school_base)

        self.dhcp_zone = "cn=%s,cn=dhcp,%s" % (self.school, self.school_base)
        self.dns_forward_zone = "zoneName=%s,cn=dns,%s" % (
            configRegistry.get("domainname"),
            configRegistry.get("ldap/base"),
        )
        reverse_subnet = get_reverse_net(
            str(self._net.network.network_address), str(self._net.network.netmask)
        )
        self.dns_reverse_zone = "zoneName=%s.in-addr.arpa,cn=dns,%s" % (
            reverse_subnet,
            configRegistry.get("ldap/base"),
        )

    def __str__(self):
        delimiter = "\t"
        line = self.school
        line += delimiter
        line += self.network
        line += delimiter
        if self.iprange:
            line += self.iprange
        line += delimiter
        line += str(self.defaultrouter)
        line += delimiter
        line += str(self.nameserver)
        line += delimiter
        line += str(self.netbiosserver)
        return line

    def expected_attributes(self):
        attr = {}
        attr["cn"] = [self.name]
        attr["univentionNetmask"] = [str(self._net.network.prefixlen)]
        attr["univentionNetwork"] = [str(self._net.network.network_address)]
        if self.iprange:
            attr["univentionIpRange"] = [self.iprange.replace("-", " ")]
        attr["univentionDnsForwardZone"] = [self.dns_forward_zone]
        attr["univentionDnsReverseZone"] = [self.dns_reverse_zone]
        return attr

    def verify(self):
        print("verify network: %s" % self.network)

        utils.verify_ldap_object(self.dn, expected_attr=self.expected_attributes(), should_exist=True)
        utils.verify_ldap_object(self.dns_forward_zone, should_exist=True)
        utils.verify_ldap_object(self.dns_reverse_zone, should_exist=True)
        utils.verify_ldap_object(self.dhcp_zone, should_exist=True)

        lo = univention.uldap.getMachineConnection()
        search_filter = (
            "(&(cn=%s)(objectClass=univentionDhcpSubnet))" % self._net.network.network_address
        )
        subnet_dn = lo.searchDn(
            base=self.dhcp_zone,
            filter=search_filter,
            unique=True,
            required=True,
        )[0]

        if self.defaultrouter:
            defaultrouter_policy_dn = "cn=%s,cn=routing,cn=dhcp,cn=policies,%s" % (
                self.name,
                self.school_base,
            )
            utils.verify_ldap_object(
                defaultrouter_policy_dn,
                expected_attr={"univentionDhcpRouters": [str(self.defaultrouter)]},
                should_exist=True,
            )
            utils.verify_ldap_object(
                subnet_dn,
                expected_attr={"univentionPolicyReference": [defaultrouter_policy_dn]},
                strict=False,
                should_exist=True,
            )
        if self.nameserver and not self.router_mode:
            nameserver_policy_dn = "cn=%s,cn=dns,cn=dhcp,cn=policies,%s" % (self.name, self.school_base)
            utils.verify_ldap_object(
                nameserver_policy_dn,
                expected_attr={
                    "univentionDhcpDomainName": [configRegistry.get("domainname")],
                    "univentionDhcpDomainNameServers": [str(self.nameserver)],
                },
                should_exist=True,
            )
            utils.verify_ldap_object(
                subnet_dn,
                expected_attr={"univentionPolicyReference": [nameserver_policy_dn]},
                strict=False,
                should_exist=True,
            )
        if self.netbiosserver and not self.router_mode:
            netbios_policy_dn = "cn=%s,cn=netbios,cn=dhcp,cn=policies,%s" % (self.name, self.school_base)
            utils.verify_ldap_object(
                netbios_policy_dn,
                expected_attr={
                    "univentionDhcpNetbiosNodeType": ["8"],
                    "univentionDhcpNetbiosNameServers": [str(self.netbiosserver)],
                },
                should_exist=True,
            )
            utils.verify_ldap_object(
                subnet_dn,
                expected_attr={"univentionPolicyReference": [netbios_policy_dn]},
                strict=False,
                should_exist=True,
            )

    def set_mode_to_router(self):
        self.router_mode = True


class ImportFile:
    def __init__(self, use_cli_api, use_python_api):
        self.router_mode = False
        self.use_cli_api = use_cli_api
        self.use_python_api = use_python_api
        self.import_fd, self.import_file = tempfile.mkstemp()
        os.close(self.import_fd)

    def write_import(self, data):
        self.import_fd = os.open(self.import_file, os.O_RDWR | os.O_CREAT)
        os.write(self.import_fd, data.encode("utf-8"))
        os.close(self.import_fd)

    def run_import(self, data):
        hooks = NetworkHooks(self.router_mode)
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
            diff_pre = "".join(difflib.unified_diff(data.splitlines(), pre_result.splitlines()))
            diff_post = "".join(difflib.unified_diff(data.splitlines(), post_result.splitlines()))
            assert data == pre_result.strip(), (data, pre_result, diff_pre)
            assert data == post_result.strip(), (data, post_result, diff_post)
        finally:
            hooks.cleanup()
            os.remove(self.import_file)

    def _run_import_via_cli(self):
        if self.router_mode:
            cmd_block = ["/usr/share/ucs-school-import/scripts/import_router", self.import_file]
        else:
            cmd_block = ["/usr/share/ucs-school-import/scripts/import_networks", self.import_file]

        print("cmd_block: %r" % cmd_block)
        subprocess.check_call(cmd_block)

    def _run_import_via_python_api(self):
        raise NotImplementedError()

    def set_mode_to_router(self):
        self.router_mode = True


class NetworkHooks:
    def __init__(self, router_mode):
        fd, self.pre_hook_result = tempfile.mkstemp()
        os.close(fd)

        fd, self.post_hook_result = tempfile.mkstemp()
        os.close(fd)

        self.router_mode = router_mode
        self.pre_hooks = []
        self.post_hooks = []

        self.create_hooks()

    def get_pre_result(self):
        return open(self.pre_hook_result, "r").read()

    def get_post_result(self):
        return open(self.post_hook_result, "r").read()

    def create_hooks(self):
        self.pre_hooks = [
            os.path.join(os.path.join(HOOK_BASEDIR, "network_create_pre.d"), uts.random_name()),
            os.path.join(os.path.join(HOOK_BASEDIR, "router_create_pre.d"), uts.random_name()),
        ]

        self.post_hooks = [
            os.path.join(os.path.join(HOOK_BASEDIR, "network_create_post.d"), uts.random_name()),
            os.path.join(os.path.join(HOOK_BASEDIR, "router_create_post.d"), uts.random_name()),
        ]

        if self.router_mode:
            search_object_class = "univentionPolicyDhcpRouting"
        else:
            search_object_class = "univentionNetworkClass"

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
debug_exit() {
    echo "Hook failed: filter=(&(objectClass=%(search_object_class)s)(cn=$school-$network))" >>%(post_hook_result)s
    echo "Expected DN: $dn" >>%(post_hook_result)s
    echo "Found DN: $ldap_dn" >>%(post_hook_result)s
    echo "Found similar objects" >>%(post_hook_result)s
    univention-ldapsearch -LLL "objectClass=%(search_object_class)s" dn >>%(post_hook_result)s
    exit "$@"
}
set -x
dn="$2"
network="$(cat $1 | awk -F '\t' '{print $2}' | sed -e 's|/.*||')"
school="$(cat $1 | awk -F '\t' '{print $1}')"
ldap_dn="$(univention-ldapsearch -LLL "(&(objectClass=%(search_object_class)s)(cn=$school-$network))" dn | \
ldapsearch-wrapper | sed -ne 's|dn: ||p')"
test "$dn" = "$ldap_dn" || debug_exit 1
cat $1 >>%(post_hook_result)s
exit 0
"""
                    % {
                        "post_hook_result": self.post_hook_result,
                        "search_object_class": search_object_class,
                    }
                )
            os.chmod(post_hook, 0o755)

    def cleanup(self):
        for pre_hook in self.pre_hooks:
            os.remove(pre_hook)
        for post_hook in self.post_hooks:
            os.remove(post_hook)
        os.remove(self.pre_hook_result)
        os.remove(self.post_hook_result)


class NetworkImport:
    def __init__(self, ou_name, nr_networks=5):
        assert nr_networks > 3

        self.school = ou_name

        self.networks = []
        for i in range(0, nr_networks):
            self.networks.append(Network(self.school, prefixlen=random.randint(8, 24)))
        self.networks[1].iprange = None

    def __str__(self):
        lines = []

        for network in self.networks:
            lines.append(str(network))

        return "\n".join(lines)

    def verify(self):
        for network in self.networks:
            network.verify()

    def set_mode_to_router(self):
        for network in self.networks:
            network.set_mode_to_router()

    def modify(self):
        self.networks[0].defaultrouter += 2
        # self.networks[1].defaultrouter = ''
        self.networks[2].nameserver += 3
        self.networks[3].defaultrouter += 3
        self.networks[3].netbiosserver += 3


def create_and_verify_networks(use_cli_api=True, use_python_api=False, nr_networks=5):
    assert use_cli_api != use_python_api

    with utu.UCSTestSchool() as schoolenv:
        ou_name, ou_dn = schoolenv.create_ou(name_edudc=schoolenv.ucr.get("hostname"))

        print("********** Generate school data")
        network_import = NetworkImport(ou_name, nr_networks=nr_networks)
        print(network_import)
        import_file = ImportFile(use_cli_api, use_python_api)

        print("********** Create networks")
        import_file.run_import(str(network_import))
        network_import.verify()

        print("********** Create routers")
        network_import.set_mode_to_router()
        import_file.set_mode_to_router()
        network_import.modify()
        import_file.run_import(str(network_import))
        network_import.verify()


def import_networks_basics(use_cli_api=True, use_python_api=False):
    create_and_verify_networks(use_cli_api, use_python_api, 10)
