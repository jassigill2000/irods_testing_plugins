#!/usr/bin/python

import glob
import json
import os
import pwd
import shutil
import socket
import subprocess

def run_tests(module):
    install_testing_dependencies(module)
    if get_irods_version() >= (4, 2):
        pass
        module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd scripts; python run_tests.py --xml_output --run_specific_test {0}'.format(module.params['python_test_module_to_run'])], check_rc=True)
    else:
        module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test {0}'.format(module.params['python_test_module_to_run'])], check_rc=True)

def install_testing_dependencies(module):
    install_hpss_plugin(module)
    configure_hpss(module)

def install_hpss_plugin(module):
    plugin_directory = os.path.join(module.params['plugin_package_root_directory'],get_irods_platform_string())
    plugin_basename = filter(lambda x:module.params['plugin_package_prefix'] in x, os.listdir(plugin_directory))[0]
    package_name = os.path.join(plugin_directory, plugin_basename)
    module.run_command(['sudo', 'rpm', '-i', '--nodeps', package_name], check_rc=True)
    #install_os_packages_from_files(['--skip-broken', package_name])

def add_LD_PRELOAD_to_server_config():
    with open('/etc/irods/server_config.json') as f:
        d = json.load(f)
    d['environment_variables']['LD_PRELOAD'] = '/lib64/libtirpc.so'
    with open('/etc/irods/server_config.json', 'w') as f:
        json.dump(d, f, sort_keys=True, indent=4)

def configure_hpss(module):
    module.run_command(['passwd', 'irods'], data='notasecret\nnotasecret\n', check_rc=True)
    module.run_command(['sed', '-i', '/hpss743.example.org/ s/$/ hpss743/', '/etc/hosts'], check_rc=True)
    module.run_command(['ln', '-s', '/lib64/libtirpc.so.1', '/lib64/libtirpc.so'], check_rc=True)
    add_LD_PRELOAD_to_server_config()
    module.run_command(['sed', '-i', '/^ALL:.*DENY$/d', '/etc/hosts.allow'], check_rc=True)
    module.run_command(['/etc/init.d/rpcbind', 'restart'], check_rc=True)
    module.run_command(['/opt/hpss/bin/rc.hpss', 'start'], check_rc=True)
    module.run_command(['/opt/hpss/bin/hpssadm.pl', '-U', 'hpssssm', '-A', 'unix', '-a', '/var/hpss/etc/hpss.unix.keytab'], data='server start -all\nquit\n', check_rc=True)
    pwnam = pwd.getpwnam('irods')
    module.run_command(['/opt/hpss/bin/hpssuser', '-add', 'irods', '-unix', '-gid', str(pwnam.pw_gid), '-uid', str(pwnam.pw_uid), '-group', 'irods', '-fullname', '"irods"', '-home', '/var/lib/irods', '-unixkeytab', '/var/hpss/etc/irods.keytab', '-shell', '/bin/bash', '-hpsshome', '/opt/hpss', '-password', 'notasecret'], check_rc=True)
    prepare_hpss_string = '''
unlink /irodsVault recurse top
mkdir /irodsVault
chown /irodsVault {0}
chgrp /irodsVault {1}
quit
'''.format(pwnam.pw_uid, pwnam.pw_gid)
    module.run_command(['/opt/hpss/bin/scrub', '-a', 'unix', '-k', '-t', '/var/hpss/etc/root.unix.keytab', '-p', 'root'], data=prepare_hpss_string, check_rc=True)
    module.run_command(['service', 'irods', 'restart'])

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

    run_tests(module)

    result = {
        'changed': True,
        'complex_args': module.params,
    }

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
