#!/usr/bin/python

import abc
import json
import os
import shutil

class UnimplementedStrategy(object):
    def __init__(self, module):
        self.module = module
        self.unimplmented_error()

    def build(self):
        self.unimplmented_error()

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
        self.plugin_name = module.params['plugin_name']
        self.local_plugin_dir = os.path.expanduser('~/'+self.plugin_name)

    @abc.abstractproperty
    def building_dependencies(self):
        pass

    @abc.abstractmethod
    def install_packages(self, packages):
        pass

    @abc.abstractmethod
    def install_packages_from_file(self, packages):
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
        self.install_packages_from_file([dev_package])
        runtime_package_basename = filter(lambda x:'irods-runtime-' in x, os.listdir(self.irods_packages_directory))[0]
        runtime_package = os.path.join(self.irods_packages_directory, runtime_package_basename)
        self.install_packages_from_file([runtime_package])

    def build(self):
        self.install_building_dependencies()
        self.prepare_git_repository()
        self.build_plugin_package()
        self.copy_build_output()

    def install_building_dependencies(self):
        self.install_packages(self.building_dependencies)
        self.install_dev_and_runtime_packages()

    def prepare_git_repository(self):
        self.module.run_command('git clone --recursive {0} {1}'.format(self.git_repository, self.local_plugin_dir), check_rc=True)
        self.module.run_command('git checkout {0}'.format(self.git_commitish), cwd=self.local_plugin_dir, check_rc=True)

    def build_plugin_package(self):
        os.makedirs(os.path.join(self.local_plugin_dir, 'build'))
#        self.module.run_command('sudo ./packaging/build.sh -r > ./build/build_plugin_output.log 2>&1', cwd=self.local_plugin_dir, use_unsafe_shell=True, check_rc=True)
        self.module.run_command('sudo ./packaging/build.sh -r > "/projects/irods/terrell/build-{0}.log" 2>&1'.format(get_irods_platform_string()), cwd=self.local_plugin_dir, use_unsafe_shell=True, check_rc=True)

    def copy_build_output(self):
        shutil.copytree(os.path.join(self.local_plugin_dir, 'build'), self.output_directory)

class RedHatStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'curl-devel', 'bzip2-devel', 'zlib-devel', 'pam-devel', 'openssl-devel', 'libxml2-devel', 'krb5-devel', 'unixODBC-devel', 'perl-JSON', 'globus-proxy-utils', 'globus-gssapi-gsi-devel']

    def install_packages(self, packages):
        install_command = 'sudo yum install -y {0}'.format(' '.join(packages))
        self.module.run_command(install_command, check_rc=True)
        # install hpss build dependencies
        args = ['sudo', 'rpm', '-i', '/projects/irods/vsphere-testing/externals/hpss/hpss-lib-7.4.3.2-0.el6.x86_64.rpm']
        self.module.run_command(args, check_rc=True)
        args = ['sudo', 'rpm', '-i', '/projects/irods/vsphere-testing/externals/hpss/hpss-lib-devel-7.4.3.2-0.el6.x86_64.rpm']
        self.module.run_command(args, check_rc=True)
        args = ['sudo', 'rpm', '-i', '/projects/irods/vsphere-testing/externals/hpss/hpss-clnt-7.4.3.2-0.el6.x86_64.rpm']
        self.module.run_command(args, check_rc=True)
        # install hpss symlink
        install_command = ['sudo', 'ln', '-s', '/hpss_src/hpss-7.4.3.2-0.el6', '/opt/hpss']
        self.module.run_command(install_command, check_rc=True)
        # fix gsi symlinks
        # Centos_6
        install_command = ['sudo', 'ln', '-s', '/usr/lib64/libglobus_callout.so.0', '/usr/lib64/libglobus_callout.so']
        self.module.run_command(install_command, check_rc=True)
        install_command = ['sudo', 'ln', '-s', '/usr/lib64/libglobus_gss_assist.so.3', '/usr/lib64/libglobus_gss_assist.so']
        self.module.run_command(install_command, check_rc=True)

    def install_packages_from_file(self, packages):
        args = ['sudo', 'yum', 'localinstall', '-y', '--nogpgcheck'] + packages
        self.module.run_command(args, check_rc=True)

class DebianStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['git', 'g++', 'make', 'python-dev', 'help2man', 'unixodbc', 'libfuse-dev', 'libcurl4-gnutls-dev', 'libbz2-dev', 'zlib1g-dev', 'libpam0g-dev', 'libssl-dev', 'libxml2-dev', 'libkrb5-dev', 'unixodbc-dev', 'libjson-perl', 'globus-proxy-utils', 'libglobus-gssapi-gsi-dev']

    def install_packages(self, packages):
        self.module.run_command('sudo apt-get update', check_rc=True)
        install_command = 'sudo apt-get install -y {0}'.format(' '.join(packages))
        self.module.run_command(install_command, check_rc=True)
        # fix gsi symlinks
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

    def install_packages_from_file(self, packages):
        args = ['sudo', 'dpkg', '-i'] + packages
        self.module.run_command(args) # no check_rc, missing deps return code 1
        self.module.run_command('sudo apt-get update', check_rc=True)
        self.module.run_command('sudo apt-get install -yf')

class SuseStrategy(GenericStrategy):
    @property
    def building_dependencies(self):
        return ['python-devel', 'help2man', 'unixODBC', 'fuse-devel', 'libcurl-devel', 'libbz2-devel', 'libopenssl-devel', 'libxml2-devel', 'krb5-devel', 'perl-JSON', 'unixODBC-devel']

    def install_packages(self, packages):
        args = ['sudo', 'zypper', '--non-interactive', 'install'] + packages
        self.module.run_command(args, check_rc=True)

    def install_packages_from_file(self, packages):
        self.install_packages(packages)

class CentOSBuilder(Builder):
    platform = 'Linux'
    distribution = 'Centos'
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
            plugin_name=dict(type='str', required=True),
            target_os_list=dict(type='list', required=True),
            git_repository=dict(type='str', required=True),
            git_commitish=dict(type='str', required=True),
            debug_build=dict(type='bool', required=True),
        ),
        supports_check_mode=False,
    )

    builder = Builder(module)
    builder.build()

    result = {}
    result['changed'] = True
    result['complex_args'] = module.params

    module.exit_json(**result)


from ansible.module_utils.basic import *
from ansible.module_utils.local_ansible_utils_extension import *
main()
