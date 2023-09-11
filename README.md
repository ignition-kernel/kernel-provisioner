# Ignition kernel provisioner
Juptyer kernel provisioner to orchestrate interfacing with Ignition

# Overview

This project allows connections to be added to Jupyter that let it coordinate requesting kernels from an Ignition instance. The Ignition instance requires a project that contains all the needed code; see the sibling repo `ignition-project` for the project export to load.

The provisioner requires at least Python 3.6.1 as per `jupyter-client` >=v7.0.0.


# Quickstart

`pip install ignition_kernel --upgrade`

For a blank, fresh install gateway:
`python -m ignition_kernel --install`

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
