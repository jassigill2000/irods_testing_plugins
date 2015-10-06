#!/usr/bin/python

import json
import os
import pwd

def run_tests(module, result):
    install_testing_dependencies(module)
    install_plugin(module)
    do_globus_config(module)
    module.run_command(['sudo', 'su', '-', 'irods', '-c', 'cd tests/pydevtest; python run_tests.py --xml_output --run_specific_test test_irods_auth_plugin_gsi'], check_rc=True)

def install_testing_dependencies(module):
    module.run_command(['wget', 'http://toolkit.globus.org/ftppub/gt6/installers/repo/globus-toolkit-repo_latest_all.deb'], check_rc=True)
    install_os_packages_from_files(['globus-toolkit-repo_latest_all.deb'])
    packages = ['git', 'globus-gsi'] #'libglobus-gsi-callback-dev', 'libglobus-gsi-proxy-core-dev', 'libglobus-gssapi-gsi-dev', 'libglobus-callout-dev', 'libglobus-gss-assist-dev']
    install_os_packages(packages)

def install_plugin(module):
    plugin_directory = os.path.join(module.params['plugin_root_directory'], get_irods_platform_string())
    plugin_basename = filter(lambda x:module.params['package_prefix']+'-' in x, os.listdir(plugin_directory))[0]
    package_name = os.path.join(plugin_directory, plugin_basename)
    install_os_packages_from_files([package_name])

def do_globus_config(module):
    #globus_client_username = 'globus_client_os_user'
    #module.run_command(['sudo', 'useradd', globus_client_os_user], check_rc=True)
    #module.run_command(['sudo', 'mkhomedir_helper', globus_client_username], check_rc=True)
    #module.run_command(['sudo', 'su', '-', globus_client_username, '-c', ''], check_rc=True)
    irodsbuild_password = create_irodsbuild_certificate(module)
    create_irods_certificate(module)
    generate_proxy(module, 'irodsbuild', irodsbuild_password)
    generate_proxy(module, 'irods', None)
    irodsbuild_proxy_copy = make_irods_readable_copy_of_irodsbuild_proxy(module)
    irodsbuild_distinguished_name = get_irodsbuild_distinguished_name(module)
    create_test_configuration_json(irodsbuild_proxy_copy, irodsbuild_distinguished_name, module)

def create_irodsbuild_certificate(module):
    module.run_command(['grid-cert-request', '-nopw', '-force', '-cn', 'gsi_client_user'], check_rc=True)
    module.run_command(['chmod', 'u+w', '.globus/userkey.pem'], check_rc=True)
    private_key_password = 'gsitest'
    module.run_command(['openssl', 'rsa', '-in', '.globus/userkey.pem', '-out', '.globus/userkey.pem', '-des3', '-passout', 'pass:{0}'.format(private_key_password)], check_rc=True)
    module.run_command(['chmod', '400', '.globus/userkey.pem'], check_rc=True)

    temporary_certificate_location = '/tmp/gsicert'
    module.run_command(['sudo', 'su', '-s', '/bin/bash', '-c', 'grid-ca-sign -in ~irodsbuild/.globus/usercert_request.pem -out {0}'.format(temporary_certificate_location), 'simpleca'], check_rc=True)

    module.run_command(['cp', temporary_certificate_location, '.globus/usercert.pem'], check_rc=True)
    module.run_command(['sudo', 'rm', temporary_certificate_location], check_rc=True)
    return private_key_password

def create_irods_certificate(module):
    module.run_command(['sudo', 'su', '-', 'irods', '-c', 'grid-cert-request -nopw -force -cn irods_service'], check_rc=True)

    temporary_certificate_location = '/tmp/gsicert'
    module.run_command(['sudo', 'su', '-s', '/bin/bash', '-c', 'grid-ca-sign -in ~irods/.globus/usercert_request.pem -out {0}'.format(temporary_certificate_location), 'simpleca'], check_rc=True)

    module.run_command(['sudo', 'cp', temporary_certificate_location, '~irods/.globus/usercert.pem'], check_rc=True)
    module.run_command(['sudo', 'rm', temporary_certificate_location], check_rc=True)
    return None

def generate_proxy(module, username, password):
    if password:
        module.run_command(['sudo', 'su', '-', username, '-c' 'echo {0} | grid-proxy-init -pwstdin'.format(password)], check_rc=True)
    else:
        module.run_command(['sudo', 'su', '-', username, '-c' 'grid-proxy-init'], check_rc=True)

def make_irods_readable_copy_of_irodsbuild_proxy(module):
    uid = pwd.getpwnam('irodsbuild').pw_uid
    proxy_file = '/tmp/x509up_u' + str(uid)
    irods_copy_of_proxy = '/tmp/irods_copy_of_irodsbuild_gsi_proxy'
    module.run_command(['sudo', 'cp', proxy_file, irods_copy_of_proxy], check_rc=True)
    module.run_command(['sudo', 'chown', 'irods:irods', irods_copy_of_proxy], check_rc=True)
    return irods_copy_of_proxy

def get_irodsbuild_distinguished_name(module):
    _, name, _ = module.run_command(['grid-cert-info', '-subject'], check_rc=True)
    return name.strip()

def create_test_configuration_json(irodsbuild_proxy_copy, irodsbuild_distinguished_name, module):
    config = {'client_user_proxy': irodsbuild_proxy_copy,
              'client_user_DN': irodsbuild_distinguished_name}
    config_file = '/tmp/gsi_test_cfg.json'
    with open(config_file, 'w') as f:
        json.dump(config, f)
    module.run_command(['sudo', 'chmod', '777', config_file], check_rc=True)

def unknown_terrelling():
    pass
    # fix symlinks
    # Ubuntu_14
    #install_command = ['sudo', 'ln', '-s', '/usr/lib/x86_64-linux-gnu/libglobus_callout.so.0', '/usr/lib/x86_64-linux-gnu/libglobus_callout.so']
    #module.run_command(install_command, check_rc=True)
    #install_command = ['sudo', 'ln', '-s', '/usr/lib/x86_64-linux-gnu/libglobus_gss_assist.so.3', '/usr/lib/x86_64-linux-gnu/libglobus_gss_assist.so']
    #module.run_command(install_command, check_rc=True)

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
