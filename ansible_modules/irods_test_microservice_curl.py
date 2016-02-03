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
    module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test test_irods_microservice_plugins_curl'], check_rc=True)

def install_plugin_package(module):
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

    run_tests(module)

    result = {
        'changed': True,
        'complex_args': module.params,
    }

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
