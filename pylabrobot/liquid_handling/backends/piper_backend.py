"""
Piper backend for PLR.

It relies on the "piper" module, which implements a robot controller for the OLA/Pipettin lab automation project.

Example:

```python3
from pylabrobot.liquid_handling import LiquidHandler

from pylabrobot.liquid_handling.backends import PiperBackend
from pylabrobot.resources import SilverDeck
from pylabrobot.resources.pipettin.utils import load_defaults

workspace, platforms, containers = load_defaults()

deck = SilverDeck(workspace, platforms, containers)
back = PiperBackend()
lh = LiquidHandler(backend=back, deck=deck)

await lh.setup()
```

Have fun!
"""

# pylint: disable=unused-argument

from pprint import pformat
from typing import List
import asyncio

from pylabrobot.liquid_handling.backends import LiquidHandlerBackend
from pylabrobot.resources import Resource
from pylabrobot.liquid_handling.standard import (
    Pickup,
    PickupTipRack,
    Drop,
    DropTipRack,
    Aspiration,
    AspirationPlate,
    Dispense,
    DispensePlate,
    Move
)

# Load piper modules.
from piper.coroutines_moon import Controller
# from piper.log import setup_logging
from piper.utils import get_config_path
from piper.config.config_helper import TrackedDict
# Load newt module.
import newt

class PiperBackend(LiquidHandlerBackend):
    """ Chatter box backend for 'How to Open Source' """

    def __init__(self,
                 piper_config:dict = None,
                 num_channels: int = 1):
        """Init method for the PiperBackend."""

        print(f"Instantiating the PiperBackend with num_channels={num_channels}")
        super().__init__()

        self._num_channels = num_channels

        if piper_config is None:
            piper_config = {}
        base_config_file = get_config_path()
        base_config = TrackedDict(base_config_file, allow_edits=True)
        base_config.update(piper_config)

        self.config = base_config
        self.controller = Controller(config=self.config)

    # Setup/Stop methods ####

    async def setup(self, home=False):

        await super().setup()

        # TODO: Set up logging. Will it interfere with PLRs?
        # setup_logging(directory=opts.get('logdir', None),
        #               level=opts.get('loglevel', logging.INFO))

        # Start the controller.
        await self._setup_controller(timeout=5, reset_firmware_on_error=True)

        # Home the robot's motion system.
        if home:
            await self._home_machine(timeout=43)

        # Mark finished.
        self.setup_finished = True

    async def _setup_controller(self, timeout, reset_firmware_on_error):

        if self.controller.dry:
            print("Dry mode enabled, skipping Moonraker connection.")
            return

        # Start the controller.
        print("Setting up connections...")
        self.controller_task: asyncio.Task = asyncio.create_task(self.controller.moon_commander())

        # Wait for readiness.
        ws_ready = await self.controller.wait_for_setup(timeout=timeout, raise_error=True)
        printer_ready = await self.controller.wait_for_ready(reset=reset_firmware_on_error, wait_time=1.1, timeout=timeout)
        if not ws_ready:
            raise Exception("Moonraker is not ready, check its logs.")
        elif not printer_ready:
            raise Exception("Klipper is not ready, check its logs.")
        else:
            print("Connections successfully setup.")

    async def _home_machine(self, timeout):
        # TODO: customize parameters.
        home_action = self.make_home_action()
        gcode = self.controller.builder.parseAction(action=home_action)

        if self.controller.dry:
            print("Dry mode enabled, skipping Homing routine.")
            return

        # Send commands.
        print("Homing the machine's axes...")
        cmd_id = await self.controller.send_gcode_script(gcode, wait=False, check=False, cmd_id="PLR setup", timeout=0.0)

        # Wait for idle printer.
        print("Waiting for homing completion (idle machine)...")
        result = await self.controller.wait_for_idle_printer(timeout=timeout)
        if not result:
            print(f"The homing process timed out. Try increasing the value of 'timeout' (currently at {timeout}), or check the logs for errors.")

        # Check for homing success
        print("Checking for homing success...")
        result = await self.controller.check_command_result_ok(cmd_id=cmd_id, timeout=timeout/2, loop_delay=0.2)
        if not result:
            await super().stop()
            response = self.controller.get_response_by_id(cmd_id)
            raise Exception("Failed to HOME. Response:\n" + pformat(response) + "\n")

        print("Homing done!")

    async def stop(self, timeout=2.0, home=True):
        if home:
            # Home the robot.
            await self._home_machine(timeout)

        if self.controller.dry:
            print("Dry mode enabled, skipping Backend cleanup.")
            await super().stop()
            return
        else:
            print("Stopping the robot.")

            # Try sending a "motors-off" command.
            cmd_id = await self.controller.send_gcode_cmd("M84", wait=True, check=True, timeout=timeout)

            # Send an "emergency stop" command if M84 failed.
            if not await self.controller.check_command_result_ok(cmd_id=cmd_id, timeout=timeout, loop_delay=0.2):
                self.controller.firmware_restart()

            # TODO: comment on what this does.
            await super().stop()

            # Close the connection to moonraker.
            await self.controller.stop()

    # Resource callback methods ####

    async def assigned_resource_callback(self, resource: Resource):
        print(f"piper_backend: Resource with name='{resource.name}' was assigned to the robot.")
        # TODO: should this update the workspace?

    async def unassigned_resource_callback(self, name: str):
        print(f"piper_backend: Resource with name='{name}' was unassigned from the robot.")
        # TODO: should this update the workspace?

    # Helper methods ####

    @property
    def num_channels(self) -> int:
        return self._num_channels

    @staticmethod
    def get_coords(operation):
        # pick_up_op
        coordinate = operation.get_absolute_location()
        coordinate_dict = coordinate.serialize()
        return coordinate_dict

    async def _send_command_wait_and_check(self, gcode, timeout):
        # TODO: customize timeout.
        # Send gcode commands.
        if not self.controller.dry:
            # Send commands.
            await self.controller.send_gcode_script(gcode, wait=True, check=True, timeout=timeout)

            # Wait for idle printer.
            return await self.controller.wait_for_idle_printer(timeout=1.0)
        else:
            print(f"Backend in dry mode, commands ignored:\n{pformat(gcode)}")

    # Pipetting action generators ####

    def make_home_action(self, axes=None):
        # home_action = {'cmd': 'HOME'}
        # if axes:
        #     home_action["args"] = {"axis": axes}
        home_action = newt.protocol_actions.action_home(axis=axes)
        return home_action

    def make_tip_pickup_action(self, operation: Pickup, tool_id: str):
        # TODO: Add validation through "jsonschema.validate" (maybe in piper, maybe here).
        # NOTE: The platform version of the content definition is not useful for now.
        # pick_up_tip_action = {
        #     'args': {'item': '200ul_tip_rack_MULTITOOL 1', 'tool': 'P200'},
        #     'cmd': 'PICK_TIP'}
        # NOTE: Using the platformless content definition.
        # pick_up_tip_action = {
        #     'cmd': 'PICK_TIP',
        #     'args': {'coords': self.get_coords(operation),
        #              'tool': tool_id,
        #              'tip': {'maxVolume': operation.tip.maximal_volume,
        #                      'tipLength': operation.tip.total_tip_length,
        #                      'volume': 0}}}
        pick_up_tip_action = newt.protocol_actions.action_pick_tip_coords(
            coords=self.get_coords(operation),
            tool=tool_id,
            volume=0.0, # TODO: Does an initial volume make sense here?
            tip_max_volume=operation.tip.maximal_volume,
            tip_length=operation.tip.total_tip_length
        )

        return pick_up_tip_action

    def make_discard_tip_action(self, operation: Pickup, tool_id: str = None):
        # TODO: The tip ejection coordinates are configured in the tool definition,
        #       and are unaffected by the location defined in the "deck" object.
        #       See "drop_tips" for more details.
        # discard_tip_action = {'args': {'tool': tool_id}, 'cmd': 'DISCARD_TIP'}

        # Use newt.
        discard_tip_action = newt.protocol_actions.action_discard_tip(
            item=None, tool=tool_id
            # TODO: Check if piper needs any of the stuff in "operation".
        )
        return discard_tip_action

    def make_pipetting_action(self, operation: Aspiration, tool_id: str, dispense:bool=False):
        # TODO: Add validation through "jsonschema.validate" (maybe in piper, maybe here).
        # NOTE: The platform version of the content definition is not useful for now.
        # pipetting_action = {
        #     'args': {'item': '5x16_1.5_rack 1', 'selector': {'by': 'name', 'value': 'tube1'}, 'volume': 100},
        #     'cmd': 'LOAD_LIQUID'}
        # NOTE: Using the platformless content definition.
        # pipetting_action = {
        #         "cmd": "LOAD_LIQUID",
        #         "args": {
        #             "coords": self.get_coords(operation),
        #             "tube": {"volume": operation.resource.tracker.get_used_volume()},
        #             "volume": operation.volume,
        #             "tool": tool_id
        #         }
        #     }

        if dispense:
            pipetting_action = newt.protocol_actions.action_drop_liquid_coords(
                coords=self.get_coords(operation),
                volume=operation.volume,
                tool=tool_id,
                used_volume=operation.resource.tracker.get_used_volume()
            )
        else:
            pipetting_action = newt.protocol_actions.action_load_liquid_coords(
                coords=self.get_coords(operation),
                volume=operation.volume,
                tool=tool_id,
                used_volume=operation.resource.tracker.get_used_volume()
            )

        return pipetting_action

    # Atomic implemented in hardware ####

    async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], **backend_kwargs):
        """_summary_

        The action can also provide the tip's coordinates directly, but must provide "tip" data explicitly:
            'args': {'coords': {"x": 20, "y": 200, "z": 30},
                    'tool': 'P200',
                    'tip': tip_definition},  # Note the tip data passed here (described below).
            'cmd': 'PICK_TIP'

        Example "tip_definition" for "coords" type args:
            'maxVolume': 160,
            'tipLength': 50.0,
            'volume': 0
        """
        print(f"Picking up tips {ops}.")

        # TODO: Ask Rick how to choose a pipette (or channel from a multichanel pipette).
        #       The OT module has a "select_tip_pipette" method.
        tool_id = "P200"

        # TODO: Handle multi-channel pick-up operations.
        action = self.make_tip_pickup_action(ops[0], tool_id)

        # Make GCODE
        gcode = self.controller.builder.parseAction(action=action)

        # TODO: have the timeout based on an estimation.
        timeout = 10.0

        # Send and check for success
        await self._send_command_wait_and_check(gcode, timeout=timeout)

    async def drop_tips(self, ops: List[Drop], use_channels: List[int], **backend_kwargs):
        print(f"Dropping tips {ops}.")
        # TODO: reject operations which are not "discard to trash" using "NotImplementedError".
        # This is because the Pipettin robot (2023/03) ejects tips using a fixed "post" and not a regular ejector.

        # TODO: Ask Rick how to choose a pipette (or channel from a multichanel pipette).
        #       The OT module has a "select_tip_pipette" method.
        tool_id = None

        # TODO: Handle multi-channel pick-up operations.
        drop_tip_action = self.make_discard_tip_action(ops[0], tool_id=tool_id)

        # Make GCODE
        gcode = self.controller.builder.parseAction(action=drop_tip_action)

        # TODO: have the timeout based on an estimation.
        timeout = 10.0

        # Send and check for success
        await self._send_command_wait_and_check(gcode, timeout=timeout)

    async def aspirate(self, ops: List[Aspiration], use_channels: List[int], **backend_kwargs):
        print(f"Aspirating {ops}.")

        # TODO: Ask Rick how to choose a pipette (or channel from a multichanel pipette).
        #       The OT module has a "select_tip_pipette" method.
        tool_id = None

        # Make action
        action = self.make_pipetting_action(ops[0], tool_id)

        # Make GCODE
        gcode = self.controller.builder.parseAction(action=action)

        # TODO: have the timeout based on an estimation.
        timeout = 10.0

        # Send and check for success
        await self._send_command_wait_and_check(gcode, timeout=timeout)

    async def dispense(self, ops: List[Dispense], use_channels: List[int], **backend_kwargs):
        print(f"Dispensing {ops}.")

        # TODO: Ask Rick how to choose a pipette (or channel from a multichanel pipette).
        #       The OT module has a "select_tip_pipette" method.
        tool_id = None

        # Make action:
        # dispense_liquid_action = {
        #     'args': {'item': '5x16_1.5_rack 1', 'selector': {'by': 'name', 'value': 'tube2'}, 'volume': 100},
        #     'cmd': 'DROP_LIQUID'}

        # Make action
        # TODO: ask Rick if the "Dispense" operation is really the same as "Aspirate" (see standard.py).
        action = self.make_pipetting_action(ops[0], tool_id, dispense=True)

        # Make GCODE
        gcode = self.controller.builder.parseAction(action=action)

        # TODO: have the timeout based on an estimation.
        timeout = 10.0

        # Send and check for success
        await self._send_command_wait_and_check(gcode, timeout=timeout)

    # Atomic actions not implemented in hardware  ####
    # TODO: implement these methods as a required human intervention.
    async def pick_up_tips96(self, pickup: PickupTipRack):
        raise NotImplementedError("The backend does not support the CoRe 96.")

    async def drop_tips96(self, drop: DropTipRack):
        raise NotImplementedError("The backend does not support the CoRe 96.")

    async def aspirate96(self, aspiration: AspirationPlate):
        raise NotImplementedError("The backend does not support the CoRe 96.")

    async def dispense96(self, dispense: DispensePlate):
        raise NotImplementedError("The backend does not support the CoRe 96.")

    async def move_resource(self, move: Move):
        """ Move the specified lid within the robot. """
        raise NotImplementedError("Moving resources is not implemented yet.")
