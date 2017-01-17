#!/usr/bin/python

import glob
import json
import os
import pwd
import shutil
import socket
import subprocess

def run_tests(module):
    install_plugin_package(module)
    module.run_command(['sudo', '-E', 'pip2', 'install', '--upgrade', 'boto3'], check_rc=True) # antoine
    if get_irods_version() >= (4, 2):
        module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd scripts; python run_tests.py --xml_output --run_specific_test {0}'.format(module.params['python_test_module_to_run'])], check_rc=True)
    else:
        module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test {0} > /var/lib/irods/tests/pydevtest/test_output.txt'.format(module.params['python_test_module_to_run'])], check_rc=True)

def install_plugin_package(module):
    plugin_directory = os.path.join(module.params['plugin_package_root_directory'], get_irods_platform_string())
    plugin_basename = filter(lambda x:module.params['plugin_package_prefix'] in x, os.listdir(plugin_directory))[0]
    package_name = os.path.join(plugin_directory, plugin_basename)
    install_os_packages_from_files([package_name])

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
