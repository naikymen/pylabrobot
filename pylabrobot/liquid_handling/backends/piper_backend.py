"""
Piper backend for PLR.

It relies on the pipettin piper module, which uses the the websocket API provided by the Moonkraker program.

See "klipper_backend.py" for a discussion on "Klipper macro" v.s. "Piper" as possible backends.
"""

# pylint: disable=unused-argument

from typing import List

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
from piper.commander_utils_mongo import MongoObjects
from piper.gcode import GcodeBuilder
from piper.coroutines_moon import moonControl


class PiperBackend(LiquidHandlerBackend):
    """ Chatter box backend for 'How to Open Source' """
    commands: List[dict] = []
    tracker: dict = {}

    def __init__(self,
                 num_channels: int = 1,
                 mongo_url: str = "mongodb://localhost:27017/",
                 verbose: bool = True,
                 protocol_name=None,
                 workspace=None):
        """Init method for the PiperBackend."""

        print(
            f"Instantiating the PiperBackend with num_channels={num_channels}")
        super().__init__()

        self._num_channels = num_channels

        self.verbose = verbose

        # Setup database tools.
        self.mo = MongoObjects(mongo_url=mongo_url, verbose=verbose)

        # List protocols (will print possible protocol names).
        self.protocols = self.mo.listProtocols()

        # Get workspace info (i.e. the "deck" in PLR terms).
        if not protocol_name:
            protocol_name = self.protocols[-1]["name"]
        protocol, workspace, platforms_in_workspace = self.mo.getProtocolObjects(
            protocol_name=protocol_name)
        # workspace = self.mo.getWorkspaceByName(workspace_name="asdasd")
        # platforms_in_workspace = self.mo.getPlatformsInWorkspace(workspace=workspace)
        # workspace, platforms_in_workspace = None, None

        # Instatiate the builder class
        self.builder = GcodeBuilder(protocol=protocol,
                                    workspace=workspace,
                                    platformsInWorkspace=platforms_in_workspace,
                                    verbose=verbose)

        # Setup
        # Connection to Moonraker
        self.moon = moonControl(commands=self.commands,
                                tracker=self.tracker, verbose=verbose)

    async def setup(self):
        await super().setup()
        print("Setting up the robot.")

        # TODO: connect to Moonraker
        self.moon.start_as_task()

        # TODO: customize parameters.
        home_action = {'cmd': 'HOME'}
        gcode = self.builder.addAction(action=home_action)

        # TODO: send the home command to moonraker.

    async def stop(self):
        await super().stop()
        print("Stopping the robot.")
        await self.moon.stop()

    @property
    def num_channels(self) -> int:
        return self._num_channels

    async def assigned_resource_callback(self, resource: Resource):
        print(f"Resource {resource.name} was assigned to the robot.")
        # TODO: should this update the workspace?

    async def unassigned_resource_callback(self, name: str):
        print(f"Resource {name} was unassigned from the robot.")
        # TODO: should this update the workspace?

    # Atomic implemented in hardware ####

    async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], **backend_kwargs):
        print(f"Picking up tips {ops}.")

        # Make GCODE
        # TODO: customize parameters.
        pick_up_tip_action = {
            'args': {'item': '200ul_tip_rack_MULTITOOL 1', 'tool': 'P200'},
            'cmd': 'PICK_TIP'}
        gcode = self.builder.addAction(action=pick_up_tip_action)

        # Send commands.
        cmd_id = await self.moon.send_gcode_script(gcode, wait=True, check=True, timeout=1.0)

        # Wait for idle printer.
        await self.moon.wait_for_idle_printer()

    async def drop_tips(self, ops: List[Drop], use_channels: List[int], **backend_kwargs):
        print(f"Dropping tips {ops}.")

        # TODO: customize parameters.
        drop_tip_action = {
            'args': {'item': 'descarte 1'}, 'cmd': 'DISCARD_TIP'}
        gcode = self.builder.addAction(action=drop_tip_action)

        # Send commands.
        cmd_id = await self.moon.send_gcode_script(gcode, wait=True, check=True, timeout=1.0)

        # Wait for idle printer.
        await self.moon.wait_for_idle_printer()

    async def aspirate(self, ops: List[Aspiration], use_channels: List[int], **backend_kwargs):
        print(f"Aspirating {ops}.")

        # Make GCODE
        aspirate_liquid_action = {
            'args': {'item': '5x16_1.5_rack 1', 'selector': {'by': 'name', 'value': 'tube1'}, 'volume': 100},
            'cmd': 'LOAD_LIQUID'}
        gcode = self.builder.addAction(action=aspirate_liquid_action)

        # Send commands.
        cmd_id = await self.moon.send_gcode_script(gcode, wait=True, check=True, timeout=1.0)

        # Wait for idle printer.
        await self.moon.wait_for_idle_printer()

    async def dispense(self, ops: List[Dispense], use_channels: List[int], **backend_kwargs):
        print(f"Dispensing {ops}.")

        # Make GCODE
        dispense_liquid_action = {
            'args': {'item': '5x16_1.5_rack 1', 'selector': {'by': 'name', 'value': 'tube2'}, 'volume': 100},
            'cmd': 'DROP_LIQUID'}
        gcode = self.builder.addAction(action=dispense_liquid_action)

        # Send commands.
        cmd_id = await self.moon.send_gcode_script(gcode, wait=True, check=True, timeout=1.0)

        # Wait for idle printer.
        await self.moon.wait_for_idle_printer()

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
