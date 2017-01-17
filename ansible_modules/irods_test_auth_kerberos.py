#!/usr/bin/python

import abc
import json
import os
import pwd
import shutil
import socket
import stat
import tempfile


class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplmented_error()

    def run_tests(self):
        self.unimplmented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_test_auth_kerberos module cannot be used on platform {0}'.format(msg_platform))

class TestRunner(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(TestRunner, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def run_tests(self):
        return self.strategy.run_tests()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.kdc_database_master_key = 'krbtest'
        self.unprivileged_principal_password = 'krbtest'

    @abc.abstractmethod
    def install_kerberos_packages(self):
        pass

    @abc.abstractmethod
    def configure_realm_and_domain(self):
        pass

    @abc.abstractmethod
    def enable_admin_privileges(self):
        pass

    def run_tests(self):
        self.install_testing_dependencies()
        self.install_plugin()
        if get_irods_version() >= (4, 2):
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd scripts; python run_tests.py --xml_output --run_specific_test {0}'.format(self.module.params['python_test_module_to_run'])], check_rc=True)
        else:
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test {0}'.format(self.module.params['python_test_module_to_run'])], check_rc=True)

    def install_testing_dependencies(self):
        add_shortname_to_etc_hosts()
        self.install_kerberos_packages()
        self.configure_realm_and_domain()
        self.restart_kerberos()
        self.create_privileged_principal()
        self.enable_admin_privileges()
        self.restart_kerberos()
        import time; time.sleep(600) # On Ubuntu 14: 'kadmin: GSS-API (or Kerberos) error while initializing kadmin interface' seen without. possibly clock skew issue w/ VMs spawning from old template and updating clocks while krb system initializes
        self.create_unprivileged_principal('krb_user')
        self.create_unprivileged_principal('irods/icat.example.org')
        self.create_keytab()
        update_irods_server_config()
        self.restart_irods()
        self.create_ticket_granting_ticket()
        self.create_json_config_file_for_unit_test()

    def create_privileged_principal(self):
        stdin = '''addprinc root/admin
krbtest
krbtest
'''
        self.module.run_command(['kadmin.local'], data=stdin, check_rc=True)

    def create_unprivileged_principal(self, principal):
        stdin = '''{0}
addprinc {1}
{2}
{2}
'''.format(self.kdc_database_master_key, principal, self.unprivileged_principal_password)
        self.module.run_command(['kadmin', '-p', 'root/admin'], data=stdin, check_rc=True)

    def create_keytab(self):
        stdin = '''krbtest
ktadd -k /var/lib/irods/irods.keytab irods/icat.example.org@EXAMPLE.ORG
'''
        self.module.run_command(['kadmin', '-p', 'root/admin'], data=stdin, check_rc=True)
        self.module.run_command(['chown', 'irods:irods', '/var/lib/irods/irods.keytab'], check_rc=True)

    def restart_irods(self):
        if get_irods_version() >= (4, 2):
            self.module.run_command(['su', '-', 'irods', '-c', '/var/lib/irods/irodsctl restart'], check_rc=True)
        else:
            self.module.run_command(['su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl restart'], check_rc=True)

    def create_ticket_granting_ticket(self):
        self.module.run_command(['kinit', 'krb_user'], data='{0}\n'.format(self.unprivileged_principal_password), check_rc=True)

    def create_json_config_file_for_unit_test(self):
        _, out, _ = self.module.run_command(['klist'], check_rc=True)
        first_line = out.split('\n')[0]
        ticket_cache = first_line.rpartition('Ticket cache: ')[2]
        d = {'client_user_principal': 'krb_user@EXAMPLE.ORG',
             'client_user_ticket_cache': ticket_cache}
        with euid_and_egid_set('irods'):
            with open('/tmp/krb5_test_cfg.json', 'w') as f:
                json.dump(d, f, indent=4, sort_keys=True)

        ticket_cache_file = ticket_cache.rpartition('FILE:')[2]
        self.module.run_command(['chmod', 'o+r', ticket_cache_file], check_rc=True)

    def install_plugin(self):
        plugin_directory = os.path.join(self.module.params['plugin_package_root_directory'], get_irods_platform_string())
        plugin_basename = filter(lambda x:self.module.params['plugin_package_prefix'] in x, os.listdir(plugin_directory))[0]
        package_name = os.path.join(plugin_directory, plugin_basename)
        install_os_packages_from_files([package_name])

class DebianStrategy(GenericStrategy):
    def install_kerberos_packages(self):
        debconf_settings = '''
krb5-config	krb5-config/read_conf	boolean	true
krb5-admin-server	krb5-admin-server/newrealm	note
krb5-kdc	krb5-kdc/debconf	boolean	true
krb5-admin-server	krb5-admin-server/kadmind	boolean	true
krb5-kdc	krb5-kdc/purge_data_too	boolean	false
krb5-config	krb5-config/add_servers	boolean	true
krb5-config	krb5-config/add_servers_realm	string	EXAMPLE.ORG
krb5-config	krb5-config/default_realm	string	EXAMPLE.ORG
krb5-config	krb5-config/admin_server	string	icat.example.org
krb5-config	krb5-config/kerberos_servers	string	icat.example.org
'''
        with tempfile.NamedTemporaryFile() as f:
            f.write(debconf_settings)
            f.flush()
            self.module.run_command(['debconf-set-selections', f.name], check_rc=True)
        install_os_packages(['krb5-admin-server', 'krb5-kdc'])

    def configure_realm_and_domain(self):
        self.create_kerberos_realm()
        self.add_domain_to_krb5_conf()
        self.enable_kerberos_logging()

    def create_kerberos_realm(self):
        self.module.run_command(['krb5_newrealm'], data='krbtest\nkrbtest\n', check_rc=True)

    def add_domain_to_krb5_conf(self):
        with tempfile.NamedTemporaryFile() as conf_copy:
            with open('/etc/krb5.conf') as conf:
                for l in conf:
                    conf_copy.write(l)
                    if '[domain_realm]' in l:
                        conf_copy.write('        .example.org = EXAMPLE.ORG\n')
                        conf_copy.write('        example.org = EXAMPLE.ORG\n')
            conf_copy.flush()
            shutil.copyfile(conf_copy.name, '/etc/krb5.conf')

    def enable_kerberos_logging(self):
        conf_section = '''
[logging]
        kdc = FILE:/var/log/kerberos/krb5kdc.log
        admin_server = FILE:/var/log/kerberos/kadmin.log
        default = FILE:/var/log/kerberos/krb5lib.log
'''
        with open('/etc/krb5.conf', 'a') as conf:
            conf.write(conf_section)
        self.module.run_command(['mkdir', '/var/log/kerberos'], check_rc=True)
        self.module.run_command(['touch', '/var/log/kerberos/krb5kdc.log'], check_rc=True)
        self.module.run_command(['touch', '/var/log/kerberos/kadmin.log'], check_rc=True)
        self.module.run_command(['touch', '/var/log/kerberos/krb5lib.log'], check_rc=True)
        self.module.run_command(['chmod', '-R', '750', '/var/log/kerberos'], check_rc=True)

    def restart_kerberos(self):
        self.module.run_command(['invoke-rc.d', 'krb5-admin-server', 'restart'], check_rc=True)
        self.module.run_command(['invoke-rc.d', 'krb5-kdc', 'restart'], check_rc=True)

    def enable_admin_privileges(self):
        with open('/etc/krb5kdc/kadm5.acl', 'a') as f:
            f.write('*/admin *\n')

class RedHatStrategy(GenericStrategy):
    def install_kerberos_packages(self):
        install_os_packages(['krb5-server', 'krb5-libs', 'krb5-auth-dialog', 'krb5-workstation'])

    def configure_realm_and_domain(self):
        krb5_conf_contents = '''\
[logging]
 default = FILE:/var/log/krb5libs.log
 kdc = FILE:/var/log/krb5kdc.log
 admin_server = FILE:/var/log/kadmind.log

[libdefaults]
 default_realm = EXAMPLE.ORG
 dns_lookup_realm = false
 dns_lookup_kdc = false
 ticket_lifetime = 24h
 renew_lifetime = 7d
 forwardable = true

[realms]
 EXAMPLE.ORG = {
  kdc = icat.example.org
  admin_server = icat.example.org
 }

[domain_realm]
 .example.org = EXAMPLE.ORG
 example.org = EXAMPLE.ORG
'''
        with open('/etc/krb5.conf', 'w') as f:
            f.write(krb5_conf_contents)

        kdc_conf_contents = '''\
[kdcdefaults]
 kdc_ports = 88
 kdc_tcp_ports = 88

[realms]
 EXAMPLE.ORG = {
  #master_key_type = aes256-cts
  acl_file = /var/kerberos/krb5kdc/kadm5.acl
  dict_file = /usr/share/dict/words
  admin_keytab = /var/kerberos/krb5kdc/kadm5.keytab
  supported_enctypes = aes256-cts:normal aes128-cts:normal des3-hmac-sha1:normal arcfour-hmac:normal des-hmac-sha1:normal des-cbc-md5:normal des-cbc-crc:normal
 }
'''
        with open('/var/kerberos/krb5kdc/kdc.conf', 'w') as f:
            f.write(kdc_conf_contents)

        self.module.run_command(['kdb5_util', 'create', '-r', 'EXAMPLE.ORG', '-s', '-W'], data='{0}\n{0}\n'.format(self.kdc_database_master_key), check_rc=True)

    def restart_kerberos(self):
        if get_distribution_version_major() == '6':
            self.module.run_command(['/etc/init.d/krb5kdc', 'restart'], check_rc=True)
            self.module.run_command(['/etc/init.d/kadmin', 'restart'], check_rc=True)
            self.module.run_command(['chkconfig', 'krb5kdc', 'on'], check_rc=True)
            self.module.run_command(['chkconfig', 'kadmin', 'on'], check_rc=True)
        elif get_distribution_version_major() == '7':
            self.module.run_command(['systemctl', 'restart', 'krb5kdc.service'], check_rc=True)
            self.module.run_command(['systemctl', 'restart', 'kadmin.service'], check_rc=True)
            self.module.run_command(['systemctl', 'enable', 'krb5kdc.service'], check_rc=True)
            self.module.run_command(['systemctl', 'enable', 'kadmin.service'], check_rc=True)
        else:
            assert False, 'OS unsupported: ' + get_irods_platform_string()

    def enable_admin_privileges(self):
        with open('/var/kerberos/krb5kdc/kadm5.acl', 'w') as f:
            f.write('*/admin@EXAMPLE.ORG *\n')

def add_shortname_to_etc_hosts():
    fullname = socket.gethostname()
    shortname = fullname.partition('.')[0]
    with tempfile.NamedTemporaryFile() as hosts_copy:
        with open('/etc/hosts') as hosts_file:
            for l in hosts_file:
                if fullname in l:
                    hosts_copy.write(l.strip() + ' ' + shortname + '\n')
                else:
                    hosts_copy.write(l)
        hosts_copy.flush()
        shutil.copyfile(hosts_copy.name, '/etc/hosts')

def update_irods_server_config():
    with open('/etc/irods/server_config.json') as f:
        d = json.load(f)
    d['KerberosServicePrincipal'] = 'irods/icat.example.org@EXAMPLE.ORG'
    d['KerberosKeytab'] = '/var/lib/irods/irods.keytab' # Not actually used, read from the environment variable
    d['environment_variables']['KRB5_KTNAME'] = '/var/lib/irods/irods.keytab'
    with open('/etc/irods/server_config.json', 'w') as f:
        json.dump(d, f, indent=4, sort_keys=True)

class CentOS6TestRunner(TestRunner):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = RedHatStrategy

class CentOS7TestRunner(TestRunner):
    platform = 'Linux'
    distribution = 'Centos linux'
    strategy_class = RedHatStrategy

class UbuntuTestRunner(TestRunner):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = DebianStrategy

#class OpenSUSETestRunner(TestRunner):
#    platform = 'Linux'
#    distribution = 'Opensuse '
#    strategy_class = SuseStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            plugin_package_root_directory=dict(type='str', required=True),
            plugin_package_prefix=dict(type='str', required=True),
            python_test_module_to_run=dict(type='str', required=True),
            output_directory=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    test_runner = TestRunner(module)
    test_runner.run_tests()

    result = {
        'changed': True,
        'complex_args': module.params,
    }

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
