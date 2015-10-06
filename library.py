import imp
import os
import yaml

import ansible.constants
ansible.constants.HOST_KEY_CHECKING = False
import ansible.inventory
import ansible.runner

import configuration


module_tuple = imp.find_module('irods_testing_zone_bundle', [configuration.irods_testing_zone_bundle_module_path])
imp.load_module('irods_testing_zone_bundle', *module_tuple)
import irods_testing_zone_bundle
from irods_testing_zone_bundle.gather import gather
from irods_testing_zone_bundle.deploy import deploy
from irods_testing_zone_bundle.destroy import deployed_zone_bundle_manager
from irods_testing_zone_bundle.library import deploy_vm_return_ip
from irods_testing_zone_bundle.library import destroy_vm
from irods_testing_zone_bundle.library import format_ansible_output
from irods_testing_zone_bundle.library import register_log_handlers
from irods_testing_zone_bundle.library import convert_sigterm_to_exception

def get_ansible_modules_directory():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ansible_modules')

def run_ansible(*args, **kwargs):
    return irods_testing_zone_bundle.library.run_ansible(*args, additional_modules_directories=[get_ansible_modules_directory()], **kwargs)
