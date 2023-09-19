# Ignition kernel provisioner
Juptyer kernel provisioner to orchestrate interfacing with Ignition

# Overview

This project allows connections to be added to Jupyter that let it coordinate requesting kernels from an Ignition instance. The Ignition instance requires a project that contains all the needed code; see the sibling repo [ignition-project](https://github.com/ignition-kernel/ignition-project) for the project export to load.

The provisioner requires at least Python 3.6.1 as per `jupyter-client` >=v7.0.0.

> Note that the provisioner always validates user credentials before spinning up a kernel.
> To create a connection, you must provide a valid username and password that the Ignition gateway will accept.
> **Credentials are stored using your operating system's keyring via the [Keyring module](https://github.com/jaraco/keyring)**

# Quickstart

The easiest way is to use pip directly:
> `pip install ignition_kernel --upgrade`

## Default `localhost` gateway
For a blank, fresh install gateway:
> `python -m ignition_kernel --install`

## Connect to a `localhost` designer session
Assuming a `localhost` designer session:
> `python -m ignition_kernel --install --designer`

To connect a kernel, open the script console of the designer and launch the kernel manager so it can start listening for connections:
> `shared.tools.jupyter.handlers.web.kernel.launch_designer_kernel_management()`

![image](https://github.com/ignition-kernel/kernel-provisioner/assets/11398106/0676e4bf-8ab1-4c98-8e93-612ce8aa255b)

## Gateway with a domain name
I have a cert just to stay in the habit of using HTTPS, so my setup looks like this:

```sh
c:\Workspace>python -m ignition_kernel --install --hostname https://localhost.corso.systems:8043

Adding the following kernel:
Config                         Value
------------------------------ -----
Name                           Ignition-CS-Surface61
Gateway Homepage               https://localhost.corso.systems:8043
WebDev Endpoint                system/webdev/jupyter/kernel
Auth username                  admin
Password in Keyring            False
Enter the password for the user 'admin' :
Password saved in Keyring for admin@https://localhost.corso.systems:8043

c:\Workspace>
```
