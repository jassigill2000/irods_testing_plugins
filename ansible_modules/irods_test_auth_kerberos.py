#!/usr/bin/python

import json
import os
import pwd
import shutil
import socket
import stat
import tempfile

def run_tests(module, result):
    install_testing_dependencies(module)
    install_plugin(module)
    module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test test_irods_auth_plugin_krb.Test_Authentication'], check_rc=True)

def install_testing_dependencies(module):
    add_shortname_to_etc_hosts()
    install_kerberos_packages(module)
    create_kerberos_realm(module)
    add_domain_to_krb5_conf()
    enable_kerberos_logging(module)
    restart_kerberos(module)
    create_privileged_principal(module)
    enable_admin_privileges()
    restart_kerberos(module)
    import time
    time.sleep(600) # 'kadmin: GSS-API (or Kerberos) error while initializing kadmin interface' seen without. possibly clock skew issue w/ VMs spawning from old template and updating clocks while krb system initializes
    create_unprivileged_principal('krb_user', module)
    create_unprivileged_principal('irods/icat.example.org', module)
    create_keytab(module)
    update_irods_server_config()
    restart_irods(module)
    create_ticket_granting_ticket(module)
    create_json_config_file_for_unit_test(module)

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

def install_kerberos_packages(module):
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
        module.run_command(['debconf-set-selections', f.name], check_rc=True)
    install_os_packages(['krb5-admin-server', 'krb5-kdc'])

def create_kerberos_realm(module):
    module.run_command(['krb5_newrealm'], data='krbtest\nkrbtest\n', check_rc=True)

def add_domain_to_krb5_conf():
    with tempfile.NamedTemporaryFile() as conf_copy:
        with open('/etc/krb5.conf') as conf:
            for l in conf:
                conf_copy.write(l)
                if '[domain_realm]' in l:
                    conf_copy.write('        .example.org = EXAMPLE.ORG\n')
                    conf_copy.write('        example.org = EXAMPLE.ORG\n')
        conf_copy.flush()
        shutil.copyfile(conf_copy.name, '/etc/krb5.conf')

def enable_kerberos_logging(module):
    conf_section = '''
[logging]
        kdc = FILE:/var/log/kerberos/krb5kdc.log
        admin_server = FILE:/var/log/kerberos/kadmin.log
        default = FILE:/var/log/kerberos/krb5lib.log
'''
    with open('/etc/krb5.conf', 'a') as conf:
        conf.write(conf_section)
    module.run_command(['mkdir', '/var/log/kerberos'], check_rc=True)
    module.run_command(['touch', '/var/log/kerberos/krb5kdc.log'], check_rc=True)
    module.run_command(['touch', '/var/log/kerberos/kadmin.log'], check_rc=True)
    module.run_command(['touch', '/var/log/kerberos/krb5lib.log'], check_rc=True)
    module.run_command(['chmod', '-R', '750', '/var/log/kerberos'], check_rc=True)

def restart_kerberos(module):
    module.run_command(['invoke-rc.d', 'krb5-admin-server', 'restart'], check_rc=True)
    module.run_command(['invoke-rc.d', 'krb5-kdc', 'restart'], check_rc=True)

def create_privileged_principal(module):
    stdin = '''addprinc root/admin
krbtest
krbtest
'''
    module.run_command(['kadmin.local'], data=stdin, check_rc=True)

def enable_admin_privileges():
    with open('/etc/krb5kdc/kadm5.acl', 'a') as f:
        f.write('*/admin *\n')

def create_unprivileged_principal(principal, module):
    stdin = '''krbtest
addprinc {0}
krbtest
krbtest
'''.format(principal)
    module.run_command(['kadmin', '-p', 'root/admin'], data=stdin, check_rc=True)

def create_keytab(module):
    stdin = '''krbtest
ktadd -k /var/lib/irods/irods.keytab irods/icat.example.org@EXAMPLE.ORG
'''
    module.run_command(['kadmin', '-p', 'root/admin'], data=stdin, check_rc=True)
    module.run_command(['chown', 'irods:irods', '/var/lib/irods/irods.keytab'], check_rc=True)

def update_irods_server_config():
    with open('/etc/irods/server_config.json') as f:
        d = json.load(f)
    d['KerberosServicePrincipal'] = 'irods/icat.example.org@EXAMPLE.ORG'
    d['KerberosKeytab'] = '/var/lib/irods/irods.keytab' # Not actually used, read from the environment variable
    d['environment_variables']['KRB5_KTNAME'] = '/var/lib/irods/irods.keytab'
    with open('/etc/irods/server_config.json', 'w') as f:
        json.dump(d, f, indent=4, sort_keys=True)

def restart_irods(module):
    module.run_command(['su', '-', 'irods', '-c', '/var/lib/irods/iRODS/irodsctl restart'], check_rc=True)

def create_ticket_granting_ticket(module):
    module.run_command(['kinit', 'krb_user'], data='krbtest\n', check_rc=True)

def create_json_config_file_for_unit_test(module):
    _, out, _ = module.run_command(['klist'], check_rc=True)
    first_line = out.split('\n')[0]
    ticket_cache = first_line.rpartition('Ticket cache: ')[2]
    d = {'client_user_principal': 'krb_user@EXAMPLE.ORG',
         'client_user_ticket_cache': ticket_cache}
    with open('/tmp/krb5_test_cfg.json', 'w') as f:
        json.dump(d, f, indent=4, sort_keys=True)
    os.chmod('/tmp/krb5_test_cfg.json', stat.S_IROTH)

    ticket_cache_file = ticket_cache.rpartition('FILE:')[2]
    module.run_command(['chmod', 'o+r', ticket_cache_file], check_rc=True)

def install_plugin(module):
    plugin_directory = os.path.join(module.params['plugin_root_directory'], get_irods_platform_string())
    plugin_basename = filter(lambda x:module.params['package_prefix']+'-' in x, os.listdir(plugin_directory))[0]
    package_name = os.path.join(plugin_directory, plugin_basename)
    install_os_packages_from_files([package_name])

def main():
    module = AnsibleModule(
        argument_spec = dict(
            plugin_root_directory=dict(type='str', required=True),
            package_prefix=dict(type='str', required=True),
            output_directory=dict(type='str', required=True),
        ),
        supports_check_mode=False,
    )

    result = {}
    run_tests(module, result)

    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
