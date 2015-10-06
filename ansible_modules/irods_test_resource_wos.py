#!/usr/bin/python

import glob
import json
import os
import pwd
import shutil
import socket
import subprocess

def run_tests(module, result):
    install_testing_dependencies(module)
    module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test test_irods_resource_plugin_wos'], check_rc=True)

def install_testing_dependencies(module):
    module.run_command('sudo apt-get update', check_rc=True)
    # dependencies
    packages = ['git']
    install_command = ['sudo', 'apt-get', 'install', '-y'] + packages
    module.run_command(install_command, check_rc=True)
    # plugin package
    plugin_directory = os.path.join(module.params['plugin_root_directory'],get_irods_platform_string())
    plugin_basename = filter(lambda x:module.params['package_prefix']+'-' in x, os.listdir(plugin_directory))[0]
    package_name = os.path.join(plugin_directory, plugin_basename)
    install_command = ['sudo', 'dpkg', '-i'] + [package_name]
    module.run_command(install_command, check_rc=True)

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
