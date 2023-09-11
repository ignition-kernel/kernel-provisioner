"""
    Interactive kernel config installer

    Since each Ignition instance is fairly unique (aside from basic localhost default installs),
    running `python -m ignition_kernel` as a command line lets you set up and reconfigure
    kernel connections. It'll set up so you don't have to fiddle with things.
"""


from jupyter_client.kernelspec import KernelSpecManager, NoSuchKernel
import json, os
import argparse
from getpass import getpass
import keyring
import re, requests
from urllib.parse import urlparse



import ignition_kernel


kernel_spec_manager = KernelSpecManager()

# Default values           unless provided by ENVironment variables
IGNITION_KERNEL_NAME     = os.environ.get('IGNITION_KERNEL_NAME'     , 'Ignition')


IGNITION_KERNEL_HOSTNAME = os.environ.get('IGNITION_KERNEL_HOSTNAME' , 'http://127.0.0.1:8088')
IGNITION_KERNEL_ENDPOINT = os.environ.get('IGNITION_KERNEL_ENDPOINT' , 'system/webdev/jupyter/kernel')
IGNITION_KERNEL_URL      = os.environ.get('IGNITION_KERNEL_URL'      , IGNITION_KERNEL_HOSTNAME + '/' + IGNITION_KERNEL_ENDPOINT)

IGNITION_KERNEL_USERNAME = os.environ.get('IGNITION_KERNEL_USERNAME' , 'admin')
try:
    IGNITION_KERNEL_PASSWORD = os.environ['IGNITION_KERNEL_PASSWORD']
    env_pass_set = True
except KeyError:
    IGNITION_KERNEL_PASSWORD = ''
    env_pass_set = False




parser = argparse.ArgumentParser(prog="python -m ignition_kernel", description = """
    Create or modify a kernel connection to an Ignition gateway.

    Each of these values can be autoresolved via environment variables.

    If both URL and some combination of HOST and ENDPONT are given then the URL will be used instead.
""")

parser.add_argument('kernel_name', default=None, metavar='KERNEL NAME', nargs='?',
                    help=f"""Kernel name in Jupyter. Defaults to resolving the gateway's name if online, or else '{IGNITION_KERNEL_HOSTNAME}'.""")

parser.add_argument('--version', '-v', action='store_true',
                    help=f"Print this ignition kernel provisioner version. Which happens to be {ignition_kernel.__version__}")

parser.add_argument('--list', '-l', action='store_true',
                    help="List all the currently configured kernels. Includes the name and url.")

parser.add_argument('--show', '-s', action='store_true',
                    help="Dump the kernel spec")

parser.add_argument('--install', action='store_true',
                    help=f"""Install (or modify) the named kernel""")

parser.add_argument('--remove', action='store_true',
                    help=f"Remove the named installed kernel")

parser.add_argument('--hostname', dest='gateway_address', metavar='HOST',
                    default=IGNITION_KERNEL_HOSTNAME,
                    help=f'URL for the Ignition gateway. Defaults to {IGNITION_KERNEL_HOSTNAME}.')

parser.add_argument('--endpoint', dest='endpoint', metavar='ENDPONT',
                    default=IGNITION_KERNEL_ENDPOINT,
                    help=f'Endpoint on gateway that will spin up kernel. Defaults to {IGNITION_KERNEL_ENDPOINT}')

parser.add_argument('--url', dest='url', metavar='URL',
                    default=IGNITION_KERNEL_URL,
                    help=f'Full URL to endpoint on gateway. Defaults to {IGNITION_KERNEL_URL}')

parser.add_argument('--username', dest='username', metavar='USER',
                    default=IGNITION_KERNEL_USERNAME,
                    help=f'Username for gateway access. Defaults to {IGNITION_KERNEL_USERNAME}')

parser.add_argument('--password', dest='password', action='store_true',
                    help='Password to username for gateway access. Requires interactive prompt. Stored in Keyring if entered here, clearing the keyring entry if no value is found. (Keyring service label is "Jupyter-Kernel" and will use "username@https://ignition_gateway_address:XXXX".) Defaults to whatever is in IGNITION_KERNEL_PASSWORD.')


cli_arguments = parser.parse_args()



def get_ignition_kernels():
    specs = []
    for kernel_name, location in kernel_spec_manager.find_kernel_specs().items():
        with open(os.path.join(location, 'kernel.json'), 'r') as spec_file:
            spec = json.load(spec_file)
        try:
            if spec['metadata']['kernel_provisioner']['provisioner_name'] == 'ignition-kernel-provisioner':
                specs.append((kernel_name, location, spec))
        except KeyError:
            pass
    return specs

def print_current_ignition_kernels():

    print(f"{'KERNEL NAME':<30} URL")
    print(f"-" * 30 + " ---")
    for kernel_name, location, spec in sorted(get_ignition_kernels()):
        url = spec['metadata']['kernel_provisioner']['config']['host_url']
        print(f"{kernel_name:<30} {url}")
    print('\nReference the name to modify or remove current kernels.')



if cli_arguments.version:
    print(f"Installed version is {ignition_kernel.__version__}")
    exit()

if cli_arguments.list:
    print_current_ignition_kernels()
    exit()



ignition_gateway_address = cli_arguments.gateway_address
ignition_gateway_endpoint = cli_arguments.endpoint

# override if url was provided
if cli_arguments.url != IGNITION_KERNEL_URL:
    url_parts = urlparse(url)

    ignition_gateway_address = f'{url_parts.scheme}://{url_parts.netloc}'
    ignition_gateway_endpoint = url_parts.path[1:]




if cli_arguments.kernel_name is None:
    # attempt to connect to the gateway to get it's name
    gateway_name_pattern = 'class=\"gateway-name\"[^>]*>(?P<gateway_name>.+?)</div>'
    try:
        try:
            response = requests.get(ignition_gateway_address)
        except Exception as error:
            print(f'Gateway does not appear available at {ignition_gateway_address}. Cannot name kernel based on gateway name.')
            raise error
        ignition_kernel_name = re.findall(gateway_name_pattern, response.content.decode('utf-8'))[0]
    except:
        print(f'Using default kernel name of {IGNITION_KERNEL_NAME}')
        ignition_kernel_name = IGNITION_KERNEL_NAME
else:
    ignition_kernel_name = cli_arguments.kernel_name




def get_kernel_spec(kernel_name):
    kernel_spec = kernel_spec_manager.get_kernel_spec(kernel_name)
    return {
         "argv": kernel_spec.argv,
         "display_name": kernel_spec.display_name,
         "language": kernel_spec.language,
         "interrupt_mode": kernel_spec.interrupt_mode,
         "metadata": kernel_spec.metadata,
    }


def create_keyring_identier(kernel_spec):
    return (
    kernel_spec['metadata']['kernel_provisioner']['config']['username'] +
    '@' +
    kernel_spec['metadata']['kernel_provisioner']['config']['host_url']
    )

def clear_password(keyring_identifer=None):
    keyring_identifer = keyring_identifer or KEYRING_IDENTIFIER
    try:
        keyring.delete_password("Jupyter-Kernel", keyring_identifer)
    except keyring.errors.PasswordDeleteError:
        pass
    print(f"Password is CLEARED in Keyring for {keyring_identifer}")

def set_password(keyring_identifer=None):
    keyring_identifer = keyring_identifer or KEYRING_IDENTIFIER
    if env_pass_set:
        password = IGNITION_KERNEL_PASSWORD
    else:
        password = getpass(f"Enter the password for the user '{cli_arguments.username}' :")

    if password:
        keyring.set_password("Jupyter-Kernel", keyring_identifer, password)
        print(f"Password saved in Keyring for {keyring_identifer}")
    else:
        print('Exiting. Password must be set to install kernel.')
        exit()

def has_password(keyring_identifer=None):
    keyring_identifer = keyring_identifer or KEYRING_IDENTIFIER
    if keyring.get_password('Jupyter-Kernel', keyring_identifer):
        return True
    else:
        return False



def show_kernel_spec(kernel):
    if isinstance(kernel, dict):
        kernel_spec = kernel
    else:
        kernel_spec = get_kernel_spec(kernel)

    try:        
        print(f"{'Config':<30} {'Value'}")
        print(f"{'-'*30:<30} {  '-----'}")

        print(f"{'Name':<30} {               kernel_spec['display_name']}")
        print(f"{'Gateway Homepage':<30} {   kernel_spec['metadata']['kernel_provisioner']['config']['host_url']}")
        print(f"{'WebDev Endpoint':<30} {    kernel_spec['metadata']['kernel_provisioner']['config']['endpoint']}")
        print(f"{'Auth username':<30} {      kernel_spec['metadata']['kernel_provisioner']['config']['username']}")
        print(f"{'Password in Keyring':<30} {has_password(create_keyring_identier(kernel_spec))}")
    except NoSuchKernel:
        print('Kernel not found!')




if cli_arguments.show:
    show_kernel_spec(ignition_kernel_name)
    exit()



if cli_arguments.kernel_name is None and not (cli_arguments.install or cli_arguments.remove):
    parser.print_help()
    exit()




try:
    KERNEL_SPEC = get_kernel_spec(ignition_kernel_name)
except Exception as error:
    KERNEL_SPEC = {
     "argv": [],
     "display_name": ignition_kernel_name,
     "language": "python",
     "interrupt_mode": "message",
     "metadata": {
        "kernel_provisioner": {
            "provisioner_name": "ignition-kernel-provisioner",
            "config": {
                "host_url": ignition_gateway_address,
                "endpoint": ignition_gateway_endpoint,
                "username": cli_arguments.username,
                "password": cli_arguments.password if env_pass_set else "keyring",
            }
        }
     }
    }

KEYRING_IDENTIFIER = create_keyring_identier(KERNEL_SPEC)




def remove_kernel(kernel_name):
    print('\nRemove the following kernel?')
    show_kernel_spec(kernel_name)
    
    try:
        assert (input(f'Really delete the connection settings for {kernel_name}? [Y/N]') or 'NO').lower() in ('y', 'yes', 'ok', 'fine', 'alright', 'sure')
        clear_password()
        kernel_spec_manager.remove_kernel_spec(kernel_name.lower())
        print(f'Removed {kernel_name} from Jupyter')

    except (AssertionError, KeyboardInterrupt):
        print(f'\nDid not remove kernel {kernel_name}')


def add_kernel(kernel_spec):
    print('\nAdding the following kernel:')
    show_kernel_spec(kernel_spec)

    if cli_arguments.password or not has_password():
        set_password()

    assert kernel_spec['metadata']['kernel_provisioner']['config']['password'] == 'keyring', "Password is expected to be set when configuration is installed. The config param is otherwise ignored."

    user_kernel_dir = kernel_spec_manager.user_kernel_dir

    kernel_dir = os.path.join(user_kernel_dir, kernel_spec['display_name'].lower()) 
    os.makedirs(kernel_dir, exist_ok=True)

    with open(os.path.join(kernel_dir, 'kernel.json'), 'w') as kernel_file:
        json.dump(kernel_spec, kernel_file, indent='  ')


try:
    if cli_arguments.remove:
        remove_kernel(ignition_kernel_name)
    elif cli_arguments.install:    
        add_kernel(KERNEL_SPEC)
    else:
        pass
except KeyboardInterrupt:
    print('\nCancelled.')



