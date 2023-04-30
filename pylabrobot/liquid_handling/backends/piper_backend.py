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
# Load newt module.
# import newt

class PiperBackend(LiquidHandlerBackend):
    """ Chatter box backend for 'How to Open Source' """
    commands: List[dict] = []
    tracker: dict = {}

    def __init__(self,
                 num_channels: int = 1,
                 mongo_url: str = "mongodb://localhost:27017/",
                 sio_address: str = "http://localhost:3333", # Pipettin GUI node server.
                 ws_address: str = "ws://localhost:7125/websocket", # Moonraker server.
                 verbose: bool = True,
                 protocol_name=None,
                 protocol=None, 
                 workspace=None,
                 platforms_in_workspace=None):
        """Init method for the PiperBackend.
        
        Note: 'protocol_name' will override the other parameters if a MongoDB address is given.
        """

        print(
            f"Instantiating the PiperBackend with num_channels={num_channels}")
        super().__init__()

        self._num_channels = num_channels

        self.verbose = verbose

        self.mongo_url = mongo_url
        if self.mongo_url:
            # Setup database connection and tools.
            self.mo = MongoObjects(mongo_url=self.mongo_url, verbose=self.verbose)
            # List protocols (will print possible protocol names).
            self.protocols = self.mo.listProtocols()
        else:
            self.mo = None
            self.protocols = None

        # Get workspace info (i.e. the "deck" in PLR terms) from MongoDB if up.
        if self.mo and protocol_name:
            
            # if not protocol_name:
            #     # Get the name of the newest protocol by default.
            #     protocol_name = self.protocols[-1]["name"]
            
            # Get the main objects from the protocol's name.
            protocol, workspace, platforms_in_workspace = self.mo.getProtocolObjects(protocol_name=protocol_name)
            # Other options:
            # workspace = self.mo.getWorkspaceByName(workspace_name="asdasd")
            # platforms_in_workspace = self.mo.getPlatformsInWorkspace(workspace=workspace)
            # workspace, platforms_in_workspace = None, None

        # Save objects
        self.protocol, self.workspace, self.platforms_in_workspace = protocol, workspace, platforms_in_workspace
        
        # Instatiate the GCODE builder class
        self.builder = GcodeBuilder(protocol=protocol,
                                    workspace=workspace,
                                    platformsInWorkspace=platforms_in_workspace,
                                    verbose=self.verbose)

        # Setup
        # Connection to Moonraker
        self.moon = moonControl(commands=self.commands,
                                sio_address=sio_address, # "http://localhost:3333", # Pipettin GUI node server.
                                ws_address=ws_address, # "ws://localhost:7125/websocket", # Moonraker server.
                                tracker=self.tracker, verbose=self.verbose)

    async def setup(self):
        await super().setup()
        print("Setting up the robot.")

        # TODO: connect to Moonraker
        self.moon.start_as_task()

        # TODO: customize parameters.
        home_action = {'cmd': 'HOME'}
        gcode = self.builder.parseAction(action=home_action)

        # Send commands.
        cmd_id = await self.moon.send_gcode_script(gcode, wait=True, check=True, timeout=1.0)

        # Wait for idle printer.
        await self.moon.wait_for_idle_printer()

    async def stop(self, timeout=2.0):
        print("Stopping the robot.")
        
        cmd_id = await self.moon.send_gcode_cmd("M84", wait=True, check=True, timeout=timeout)
        
        if not await self.moon.check_command_result_ok(cmd_id=cmd_id, timeout=timeout, loop_delay=0.2):
            self.moon.firmware_restart()
        
        await super().stop()
        
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
        
        # TODO: Handle multi-channel pick-up operations.
        pick_up_op = pick_up_ops[0]
        coordinate = pick_up_op.get_absolute_location()
        coordinate_dict = coordinate.serialize()

        # TODO: Customize action parameters from the arguments above.
        
        # NOTE: Using the platformless content definition.
        # TODO: Ask Rick how to choose a pipette (or channel from a multichanel pipette).
        #       The OT module has a "select_tip_pipette" method.
        pick_up_tip_action = {
            'cmd': 'PICK_TIP',
            'args': {'coords': coordinate_dict, 
                     'tool': 'P200',
                     'tip': {'maxVolume': pick_up_op.tip.maximal_volume,
                             'tipLength': pick_up_op.tip.total_tip_length,
                             'volume': 0}}}
        
        # TODO: Add validation through "jsonschema.validate" (maybe in piper, maybe here).
        
        # NOTE: The platform version of the content definition is not useful for now.
        # pick_up_tip_action = {
        #     'args': {'item': '200ul_tip_rack_MULTITOOL 1', 'tool': 'P200'},
        #     'cmd': 'PICK_TIP'}
        
        # Make GCODE
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
