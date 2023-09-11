"""
    Ignition Jupyter Kernel Provisioner

    Unlike a local provisioner, Jupyter can't control the full lifecycle 
    of an Ignition kernel. Instead, it must request Ignition to perform
    the startup, maintenance, and tear down work on its behalf.

    For convenience, we'll assume the interface to Ignition is the WebDev
    module and an endpoint is set up for it. The REST API will use typical
    HTTP methods like GET/POST/DELETE to manage the kernel.

"""


from jupyter_client.provisioning.provisioner_base import KernelProvisionerBase
from jupyter_client.connect import KernelConnectionInfo, LocalPortCache
from jupyter_client.localinterfaces import is_local_ip, local_ips

from typing import Any, Dict, List, Optional, Union
from traitlets.config import Instance, LoggingConfigurable, Unicode, Bool

import json, sys, zmq
from datetime import datetime, timedelta
import signal
import requests
import keyring
from urllib.parse import urljoin
import asyncio



class IgnitionKernelProvisioner(KernelProvisionerBase):
    """
    Request and manage a kernel from an Ignition instance.

    Docstrings are copied from KernelProvisionerBase abstract methods.

    Retrofitted from the LocalProvisioner and documentation at
    https://github.com/jupyter/jupyter_client/blob/main/docs/provisioning.rst

    Where the LocalProvisioner uses `process` we'll use `ignition_kernel_id`. 
    Ignition generates a new ignition_kernel_id for each kernel that spins up, 
    so this is a useful identifier for if a kernel is running.

    In practice, we would expect `kernel_id` == `ignition_kernel_id` except
    for when the `ignition_kernel_id` is None because the kernel is torn down.
    """


    # defaults
    host_url: Union[str, Unicode] = Unicode(config=True)
    endpoint: Union[str, Unicode] = Unicode("system/webdev/jupyter/kernel", config=True)
    username: Union[str, Unicode] = Unicode(config=True)
    password: Union[str, Unicode] = Unicode("keyring", config=True)

    connection_info: KernelConnectionInfo = {}

    ignition_kernel_id: str = Unicode(None, allow_none=True)

    # behave like a Designer session's scripting, or like an async gateway script
    run_through_trial: bool = Bool(True, config=True)


    HEARTBEAT_TIMEOUT = timedelta(minutes=5)

    ## TODO: port caching for preventing messy race stuff
    # for compatibility with the usual usage
    ports_cached = False
    ip = None

#terminating on: 
# 'https://localhost.corso.systems:8043/system/webdev/jupyter/7d679e14-07d8-460a-bc1c-2ba9de12851c'

    @property
    def ignition_endpoint(self):
        return urljoin(self.host_url, self.endpoint)

    @property
    def ignition_kernel_endpoint(self):
        return self.ignition_endpoint + '/' + self.ignition_kernel_id

    @property
    def _keyring_identifier(self):
        return f'{self.username}@{self.host_url}'

    @property
    def _requests_keyring_authentication(self):
        return requests.auth.HTTPBasicAuth(self.username, self._keyring_password)


    @property
    def has_process(self) -> bool:
        """
        True if Ignition has allocated an ID to the kernel.

        Returns true if this provisioner is currently managing a process.

        This property is asserted to be True immediately following a call to
        the provisioner's :meth:`launch_kernel` method.
        """
        return self.ignition_kernel_id is not None


    async def poll(self) -> Optional[int]:
        """
        Ask Ignition for the status.

        Checks if kernel process is still running.

        If running, None is returned, otherwise the process's integer-valued exit code is returned.
        This method is called from :meth:`KernelManager.is_alive`.
        """
        if self.heartbeat_stream:
            # react to the last heartbeat
            if self.last_heartbeat < (datetime.now() - self.HEARTBEAT_TIMEOUT):
                return -3
            # send a ping; when we come back 'round we'll verify it
            self.heartbeat_stream.send_string('Ping', zmq.NOBLOCK)
            return
        else:
            response = requests.head(self.ignition_kernel_endpoint, auth=self._requests_keyring_authentication)
            # Only deal with success or failure
            if response.status_code == 200 or (self.run_through_trial and response.status_code == 402):
                self.last_heartbeat = datetime.now()
                return
            else:
                # I think negative codes are application crash signals?
                # so this 
                return -response.status_code


    async def wait(self) -> Optional[int]:
        """
        Wait while Ignition tears down a kernel.

        Waits for kernel process to terminate.

        This method is called from `KernelManager.finish_shutdown()` and
        `KernelManager.kill_kernel()` when terminating a kernel gracefully or
        immediately, respectively.
        """
        if self.ignition_kernel_id is None:
            return 0

        # pause until Ignition replies that the kernel is gone
        while await self.poll() is None:
            await asyncio.sleep(0.050)

        # Ignition cleans up the kernel on our behalf
        self.ignition_kernel_id = None

        return -404 # kernel is no longer found


    async def send_signal(self, signum: int) -> None:
        """
        Tell Ignition to signal the kernel, always assumed to be to die.
        (There's potential for supporting Stop and Cont, and even Core,
         but for now it does not.)

        Sends signal identified by signum to the kernel process.

        This method is called from `KernelManager.signal_kernel()` to send the
        kernel process a signal.
        """
        if self.ignition_kernel_id is None:
            return

        # TODO: contextual death
        #   SCRAM on KILL
        #   tear_down on TERM
        #   stop running Python on INT

        # assert signum in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL), "Non-death signals not yet supported."

        # assert signum == signal.SIGTERM, "Non-SIGTERM signals not yet supported."

        response = requests.delete(self.ignition_kernel_endpoint, auth=self._requests_keyring_authentication,
                                   json={'signal': signum})

        assert response.status_code == 200, "Got %r: %r" % (response.status_code, response)

        # regardless of how it worked, the old execution context is gone
        self.last_heartbeat -= (2* self.HEARTBEAT_TIMEOUT)

        return


    async def kill(self, restart: bool = False) -> None:
        """
        Kill the kernel in Ignition. 

        Kill the provisioner and optionally restart.
        """
        if self.ignition_kernel_id is None:
            return

        # if simply a restart, don't tear down the kernel
        if restart:
            # the Ignition kernel is managed by messages, not process directives
            await self.send_signal(0)
        else:
            await self.send_signal(-1)



    async def terminate(self, restart: bool = False) -> None:
        """
        Terminate the kernel in Ignition.

        Terminate the provisioner and optionally restart.
        """
        if self.ignition_kernel_id is None:
            return

        # if simply a restart, don't tear down the kernel
        if restart:
            # the Ignition kernel is managed by messages, not process directives
            await self.send_signal(0)
        else:
            await self.send_signal(signal.SIGTERM)



    async def cleanup(self, restart: bool = False) -> None:
        """
        Clean up port reservations and such. This is _purely_ for Jupyter's
        benefit, since Ignition handles all the actual binding bits.

        Clean up the resources used by the provisioner and optionally restart.
        """
        if self.ports_cached and not restart:
            # provisioner is about to be destroyed, return cached ports
            lpc = LocalPortCache.instance()
            ports = (
                self.connection_info['shell_port'],
                self.connection_info['iopub_port'],
                self.connection_info['stdin_port'],
                self.connection_info['hb_port'],
                self.connection_info['control_port'],
            )
            for port in ports:
                lpc.return_port(port)

            if self.heartbeat_stream and not self.heartbeat_stream.closed():
                self.heartbeat_stream.close()



    async def pre_launch(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Prepare the connection request to be sent to Ignition

        Perform any steps in preparation for kernel process launch.

        This includes applying additional substitutions to the kernel launch command
        and environment. It also includes preparation of launch parameters.

        NOTE: Subclass implementations are advised to call this method as it applies
        environment variable substitutions from the local environment and calls the
        provisioner's :meth:`_finalize_env()` method to allow each provisioner the
        ability to cleanup the environment variables that will be used by the kernel.

        This method is called from `KernelManager.pre_start_kernel()` as part of its
        start kernel sequence.

        Returns the (potentially updated) keyword arguments that are passed to
        :meth:`launch_kernel()`.
        """

        # grab the auth password from keyring
        assert self.password == 'keyring', "Only keyring password storage is currently supported. At least, not plaintext."
        self._keyring_password = keyring.get_password("Jupyter-Kernel", self._keyring_identifier)


        # Kernel Manager will be generating the connection info
        # (TODO: At least for this PoC testing...)
        km = self.parent
        if km:
            if km.transport == 'tcp' and not is_local_ip(km.ip):
                msg = (
                    "Can only launch a kernel on a local interface. "
                    "This one is not: {}."
                    "Make sure that the '*_address' attributes are "
                    "configured properly. "
                    "Currently valid addresses are: {}".format(km.ip, local_ips())
                )
                raise RuntimeError(msg)
            # build the Popen cmd
            extra_arguments = kwargs.pop('extra_arguments', [])

            # write connection file / get default ports
            # TODO - change when handshake pattern is adopted
            if km.cache_ports and not self.ports_cached:
                lpc = LocalPortCache.instance()
                km.shell_port = lpc.find_available_port(km.ip)
                km.iopub_port = lpc.find_available_port(km.ip)
                km.stdin_port = lpc.find_available_port(km.ip)
                km.hb_port = lpc.find_available_port(km.ip)
                km.control_port = lpc.find_available_port(km.ip)
                self.ports_cached = True
            if 'env' in kwargs:
                jupyter_session = kwargs['env'].get("JPY_SESSION_NAME", "")
                km.write_connection_file(jupyter_session=jupyter_session)
            else:
                km.write_connection_file()
            self.connection_info = km.get_connection_info()

            kernel_cmd = km.format_kernel_cmd(
                extra_arguments=extra_arguments
            )  # This needs to remain here for b/c
        else:
            extra_arguments = kwargs.pop('extra_arguments', [])
            kernel_cmd = self.kernel_spec.argv + extra_arguments

        # OK all that nonsense and we're just going to accept it's not doing anything =/
        assert not kernel_cmd, "No external tooling is used when launching Ignition kernels."
        return await super().pre_launch(cmd=kernel_cmd, **kwargs)



    async def launch_kernel(self, cmd: List[str], **kwargs: Any) -> KernelConnectionInfo:
        """
        Ignition launches the kernel and replies with the connection info.

        Launch the kernel process and return its connection information.

        This method is called from `KernelManager.launch_kernel()` during the
        kernel manager's start kernel sequence.
        """
        kernel_config_payload = self.connection_info.copy()

        # # symmetry is nice, right?
        kernel_config_payload['kernel_id'] = self.kernel_id

        # cast to string for json serialization
        kernel_config_payload['key'] = kernel_config_payload['key'].decode('ascii')

        response = requests.post(self.ignition_endpoint, json=kernel_config_payload, auth=self._requests_keyring_authentication)

        if response.status_code == 402:
            raise RuntimeError('Ignition gateway is in trial. Reset trial to enable WebDev.\nGateway at %s' % (self.host_url,))

        connection_info = response.json()

        self.ignition_kernel_id = connection_info.pop('ignition_kernel_id')

        assert all(
                (value.decode('ascii') if isinstance(value, bytes) else value
                    ) == connection_info[key]
                for key, value 
                in self.connection_info.items()
            )
        return self.connection_info


    async def post_launch(self, **kwargs: Any) -> None:
        """
        Ignition

        Perform any steps following the kernel process launch.

        This method is called from `KernelManager.post_start_kernel()` as part of its
        start kernel sequence.
        """
        kernel_manager = self.parent
        if kernel_manager:
            # context = kernel_manager.context
            # socket = context.socket(zmq.REQ)
            # socket.setsockopt(zmq.RCVTIMEO, 5000) # 5 second timeout
            # socket.linger
            # socket.connect(kernel_manager._make_url('hb'))

            self.heartbeat_stream = kernel_manager.connect_hb()
            def heartbeat_acked(msg, provisioner=self):
                if msg:
                    reply = msg[0].decode('utf-8').lower()
                    if reply in ('ping', 'pong'):
                        provisioner.last_heartbeat = datetime.now()
                    # this won't be used, but illustrates how we'll signal the death of a kernel in poll()
                    if reply in ('', 'restart', 'gone',):
                        provisioner.last_heartbeat -= (2* self.HEARTBEAT_TIMEOUT)
            self.heartbeat_stream.on_recv(heartbeat_acked)
        else:
            self.heartbeat_stream = None
        self.last_heartbeat = datetime.now()




    async def get_provisioner_info(self) -> Dict:
        """Captures the base information necessary for persistence relative to this instance."""
        provisioner_info = await super().get_provisioner_info()
        provisioner_info.update({
            'host_url': self.host_url,
            'endpoint': self.endpoint,
            'ignition_kernel_id': self.ignition_kernel_id,
        })
        return provisioner_info


    async def load_provisioner_info(self, provisioner_info: Dict) -> None:
        """Loads the base information necessary for persistence relative to this instance."""
        await super().load_provisioner_info(provisioner_info)
        self.host_url = provisioner_info['host_url']
        self.endpoint = provisioner_info['endpoint']
        self.ignition_kernel_id = provisioner_info['ignition_kernel_id']



    def get_shutdown_wait_time(self, recommended: float = 5.0) -> float:
        """
        Returns the time allowed for a complete shutdown. This may vary by provisioner.

        This method is called from `KernelManager.finish_shutdown()` during the graceful
        phase of its kernel shutdown sequence.

        The recommended value will typically be what is configured in the kernel manager.
        """
        return recommended

    def get_stable_start_time(self, recommended: float = 10.0) -> float:
        """
        Returns the expected upper bound for a kernel (re-)start to complete.
        This may vary by provisioner.

        The recommended value will typically be what is configured in the kernel restarter.
        """
        return recommended

