#!/usr/bin/python

import abc
import json
import os
import shutil

class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplemented_error()

    def build(self):
        self.unimplemented_error()

    def unimplemented_error(self):
        platform = get_platform()
        distribution = get_distribution()
        if distribution is not None:
            msg_platform = '{0} ({1})'.format(platform, distribution)
        else:
            msg_platform = platform
        self.module.fail_json(msg='irods_build_plugin module cannot be used on platform {0}'.format(msg_platform))

class Builder(object):
    platform = 'Generic'
    distribution = None
    strategy_class = UnimplementedStrategy
    def __new__(cls, *args, **kwargs):
        return load_platform_subclass(Builder, args, kwargs)

    def __init__(self, module):
        self.strategy = self.strategy_class(module)

    def build(self):
        return self.strategy.build()

class GenericStrategy(object):
    __metaclass__ = abc.ABCMeta
    def __init__(self, module):
        self.module = module
        self.output_root_directory = module.params['output_root_directory']
        self.irods_packages_root_directory = module.params['irods_packages_root_directory']
        self.git_repository = module.params['git_repository']
        self.git_commitish = module.params['git_commitish']
        self.local_plugin_dir = os.path.expanduser('~/irods_build_local_plugin_dir')

    @abc.abstractproperty
    def building_dependencies(self):
        pass

    @property
    def irods_packages_directory(self):
        return os.path.join(self.irods_packages_root_directory, get_irods_platform_string())

    @property
    def output_directory(self):
        return os.path.join(self.output_root_directory, get_irods_platform_string())

    def install_dev_and_runtime_packages(self):
        dev_package_basename = filter(lambda x:'irods-dev-' in x, os.listdir(self.irods_packages_directory))[0]
        dev_package = os.path.join(self.irods_packages_directory, dev_package_basename)
        install_os_packages_from_files([dev_package])
        runtime_package_basename = filter(lambda x:'irods-runtime-' in x, os.listdir(self.irods_packages_directory))[0]
        runtime_package = os.path.join(self.irods_packages_directory, runtime_package_basename)
        install_os_packages_from_files([runtime_package])

    def build(self):
        self.install_building_dependencies()
        self.prepare_git_repository()
        self.build_plugin_package()
        self.copy_build_output()

    def install_building_dependencies(self):
        install_os_packages(self.building_dependencies)
        self.install_dev_and_runtime_packages()
        self.install_plugin_specific_building_dependencies()

    def install_plugin_specific_building_dependencies(self):
        pass

    def prepare_git_repository(self):
        self.module.run_command('git clone --recursive {0} {1}'.format(self.git_repository, self.local_plugin_dir), check_rc=True)
        self.module.run_command('git checkout {0}'.format(self.git_commitish), cwd=self.local_plugin_dir, check_rc=True)

    def build_plugin_package(self):
        os.makedirs(os.path.join(self.local_plugin_dir, 'build'))
        self.module.run_command(['sudo', 'su', '-c', './packaging/build.sh -r 2>&1 | tee ./build/build_plugin_output.log; exit $PIPESTATUS'], cwd=self.local_plugin_dir, check_rc=True)

    def copy_build_output(self):
        shutil.copytree(os.path.join(self.local_plugin_dir, 'build'), self.output_directory)

class RedHatStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        gsi_dependencies = ['globus-proxy-utils', 'globus-gssapi-gsi-devel']
        return ['python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'curl-devel', 'bzip2-devel', 'zlib-devel', 'pam-devel', 'openssl-devel', 'libxml2-devel', 'krb5-devel', 'unixODBC-devel', 'perl-JSON'] + gsi_dependencies

    def install_plugin_specific_building_dependencies(self):
        # hpss
        hpss_packages = ['/projects/irods/vsphere-testing/externals/hpss/hpss-lib-7.4.3.2-0.el6.x86_64.rpm',
                         '/projects/irods/vsphere-testing/externals/hpss/hpss-lib-devel-7.4.3.2-0.el6.x86_64.rpm',
                         '/projects/irods/vsphere-testing/externals/hpss/hpss-clnt-7.4.3.2-0.el6.x86_64.rpm']
        install_os_packages_from_files(hpss_packages)
        self.module.run_command(['sudo', 'ln', '-s', '/hpss_src/hpss-7.4.3.2-0.el6', '/opt/hpss'], check_rc=True)

        # gsi
        install_command = ['sudo', 'ln', '-s', '/usr/lib64/libglobus_callout.so.0', '/usr/lib64/libglobus_callout.so']
        self.module.run_command(install_command, check_rc=True)
        install_command = ['sudo', 'ln', '-s', '/usr/lib64/libglobus_gss_assist.so.3', '/usr/lib64/libglobus_gss_assist.so']
        self.module.run_command(install_command, check_rc=True)

class DebianStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        gsi_dependencies = ['globus-proxy-utils', 'libglobus-gssapi-gsi-dev']
        return ['git', 'g++', 'make', 'python-dev', 'help2man', 'unixodbc', 'libfuse-dev', 'libcurl4-gnutls-dev', 'libbz2-dev', 'zlib1g-dev', 'libpam0g-dev', 'libssl-dev', 'libxml2-dev', 'libkrb5-dev', 'unixodbc-dev', 'libjson-perl'] + gsi_dependencies

    def install_plugin_specific_building_dependencies(self):
        # gsi
        # Ubuntu_12
        install_command = ['sudo', 'ln', '-s', '/usr/lib/libglobus_callout.so.0', '/usr/lib/libglobus_callout.so']
        self.module.run_command(install_command, check_rc=True)
        install_command = ['sudo', 'ln', '-s', '/usr/lib/libglobus_gss_assist.so.3', '/usr/lib/libglobus_gss_assist.so']
        self.module.run_command(install_command, check_rc=True)
        # Ubuntu_14
        install_command = ['sudo', 'ln', '-s', '/usr/lib/x86_64-linux-gnu/libglobus_callout.so.0', '/usr/lib/x86_64-linux-gnu/libglobus_callout.so']
        self.module.run_command(install_command, check_rc=True)
        install_command = ['sudo', 'ln', '-s', '/usr/lib/x86_64-linux-gnu/libglobus_gss_assist.so.3', '/usr/lib/x86_64-linux-gnu/libglobus_gss_assist.so']
        self.module.run_command(install_command, check_rc=True)

class SuseStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'libcurl-devel', 'libbz2-devel', 'libopenssl-devel', 'libxml2-devel', 'krb5-devel', 'perl-JSON', 'unixODBC-devel']

class CentOS6Builder(Builder):
    platform = 'Linux'
    distribution = 'Centos'
    strategy_class = RedHatStrategy

class CentOS7Builder(Builder):
    platform = 'Linux'
    distribution = 'Centos linux'
    strategy_class = RedHatStrategy

class UbuntuBuilder(Builder):
    platform = 'Linux'
    distribution = 'Ubuntu'
    strategy_class = DebianStrategy

class OpenSuseBuilder(Builder):
    platform = 'Linux'
    distribution = 'Opensuse '
    strategy_class = SuseStrategy

def main():
    module = AnsibleModule(
        argument_spec = dict(
            output_root_directory=dict(type='str', required=True),
            irods_packages_root_directory=dict(type='str', required=True),
            git_repository=dict(type='str', required=True),
            git_commitish=dict(type='str', required=True),
            debug_build=dict(type='bool', required=True),
        ),
        supports_check_mode=False,
    )

    builder = Builder(module)
    builder.build()

    result = {
        'changed': True,
        'complex_args': module.params,
        'irods_platform_string': get_irods_platform_string(),
    }
    module.exit_json(**result)

from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
