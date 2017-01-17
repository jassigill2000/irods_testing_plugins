#!/usr/bin/python

import abc
import json
import os
import pwd


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
        self.module.fail_json(msg='irods_test_auth_gsi module cannot be used on platform {0}'.format(msg_platform))

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

    @abc.abstractproperty
    def globus_toolkit_package_name(self):
        pass

    def run_tests(self):
        self.install_testing_dependencies()
        self.install_plugin()
        self.do_globus_config()
        if get_irods_version() >= (4, 2):
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd scripts; python run_tests.py --xml_output --run_specific_test {0}'.format(self.module.params['python_test_module_to_run'])], check_rc=True)
        else:
            self.module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test {0}'.format(self.module.params['python_test_module_to_run'])], check_rc=True)

    def install_testing_dependencies(self):
        self.module.run_command(['wget', 'http://toolkit.globus.org/ftppub/gt6/installers/repo/{0}'.format(self.globus_toolkit_package_name)], check_rc=True)
        install_os_packages_from_files([self.globus_toolkit_package_name])
        install_os_packages(['globus-gsi'])

    def install_plugin(self):
        plugin_directory = os.path.join(self.module.params['plugin_package_root_directory'], get_irods_platform_string())
        plugin_basename = filter(lambda x:self.module.params['plugin_package_prefix'] in x, os.listdir(plugin_directory))[0]
        package_name = os.path.join(plugin_directory, plugin_basename)
        install_os_packages_from_files([package_name])

    def do_globus_config(self):
        self.module.run_command(['chmod', 'o+rx', '/home/irodsbuild'], check_rc=True) # so user simpleca can read ~irodsbuild/.globus/usercert_request.pem
        irodsbuild_password = self.create_irodsbuild_certificate()
        self.create_irods_certificate()
        self.generate_proxy('irodsbuild', irodsbuild_password)
        self.generate_proxy('irods', None)
        irodsbuild_proxy_copy = self.make_irods_readable_copy_of_irodsbuild_proxy()
        irodsbuild_distinguished_name = self.get_irodsbuild_distinguished_name()
        self.create_test_configuration_json(irodsbuild_proxy_copy, irodsbuild_distinguished_name)

    def create_irodsbuild_certificate(self):
        self.module.run_command(['sudo', 'su', '-', 'irodsbuild', '-c', 'grid-cert-request -nopw -force -cn gsi_client_user'], check_rc=True)
        self.module.run_command(['chmod', 'u+w', '~irodsbuild/.globus/userkey.pem'], check_rc=True)
        private_key_password = 'gsitest'
        self.module.run_command(['openssl', 'rsa', '-in', '.globus/userkey.pem', '-out', '~irodsbuild/.globus/userkey.pem', '-des3', '-passout', 'pass:{0}'.format(private_key_password)], check_rc=True)
        self.module.run_command(['chmod', '400', '~irodsbuild/.globus/userkey.pem'], check_rc=True)

        temporary_certificate_location = '/tmp/gsicert'
        self.module.run_command(['sudo', 'su', '-s', '/bin/bash', '-c', 'grid-ca-sign -in ~irodsbuild/.globus/usercert_request.pem -out {0}'.format(temporary_certificate_location), 'simpleca'], check_rc=True)

        self.module.run_command(['cp', temporary_certificate_location, '.globus/usercert.pem'], check_rc=True)
        self.module.run_command(['sudo', 'rm', temporary_certificate_location], check_rc=True)
        return private_key_password

    def create_irods_certificate(self):
        self.module.run_command(['sudo', 'su', '-', 'irods', '-c', 'grid-cert-request -nopw -force -cn irods_service'], check_rc=True)

        temporary_certificate_location = '/tmp/gsicert'
        self.module.run_command(['sudo', 'su', '-s', '/bin/bash', '-c', 'grid-ca-sign -in ~irods/.globus/usercert_request.pem -out {0}'.format(temporary_certificate_location), 'simpleca'], check_rc=True)

        self.module.run_command(['sudo', 'cp', temporary_certificate_location, '~irods/.globus/usercert.pem'], check_rc=True)
        self.module.run_command(['sudo', 'rm', temporary_certificate_location], check_rc=True)

    def generate_proxy(self, username, password):
        if password:
            self.module.run_command(['sudo', 'su', '-', username, '-c' 'echo {0} | grid-proxy-init -pwstdin'.format(password)], check_rc=True)
        else:
            self.module.run_command(['sudo', 'su', '-', username, '-c' 'grid-proxy-init'], check_rc=True)

    def make_irods_readable_copy_of_irodsbuild_proxy(self):
        uid = pwd.getpwnam('irodsbuild').pw_uid
        proxy_file = '/tmp/x509up_u' + str(uid)
        irods_copy_of_proxy = '/tmp/irods_copy_of_irodsbuild_gsi_proxy'
        self.module.run_command(['sudo', 'cp', proxy_file, irods_copy_of_proxy], check_rc=True)
        self.module.run_command(['sudo', 'chown', 'irods:irods', irods_copy_of_proxy], check_rc=True)
        return irods_copy_of_proxy

    def get_irodsbuild_distinguished_name(self):
        _, name, _ = self.module.run_command(['su', '-', 'irodsbuild', '-c', 'grid-cert-info -subject'], check_rc=True)
        return name.strip()

    def create_test_configuration_json(self, irodsbuild_proxy_copy, irodsbuild_distinguished_name):
        config = {'client_user_proxy': irodsbuild_proxy_copy,
                  'client_user_DN': irodsbuild_distinguished_name}
        config_file = '/tmp/gsi_test_cfg.json'
        with open(config_file, 'w') as f:
            json.dump(config, f)
        self.module.run_command(['sudo', 'chmod', '777', config_file], check_rc=True)

class DebianStrategy(GenericStrategy):
    @property
    def globus_toolkit_package_name(self):
        return 'globus-toolkit-repo_latest_all.deb'

class RedHatStrategy(GenericStrategy):
    @property
    def globus_toolkit_package_name(self):
        return 'globus-toolkit-repo-latest.noarch.rpm'

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
