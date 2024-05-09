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
import json
import urllib

from pylabrobot.resources import TipSpot
from pylabrobot.resources.pipettin.tube_racks import Tube as PiperTube
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
from piper.datatools.nodb import NoObjects
# from piper.log import setup_logging
from piper.utils import get_config_path
from piper.config.config_helper import TrackedDict
# Load newt module.
import newt

def load_objects_from_file(file_path):
  with open(file_path, "r", encoding="utf-8") as f:
    objects = json.load(f)
  return objects

def load_objects_from_url(target_url):
  data = urllib.request.urlopen(target_url)
  objects = json.load(data)
  return objects

class PiperBackend(LiquidHandlerBackend):
  """ Chatter box backend for 'How to Open Source' """

  controller: Controller

  def __init__(self,
               tools_json:str,
               piper_config:dict = None,
               num_channels: int = 1):
    """Init method for the PiperBackend."""

    print(f"Instantiating the PiperBackend with num_channels={num_channels}")
    super().__init__()

    self._num_channels = num_channels

    # Parse configuration.
    if piper_config is None:
      piper_config = {}
    base_config_file = get_config_path()
    base_config = TrackedDict(base_config_file, allow_edits=True)
    base_config.update(piper_config)
    self.config = base_config

    # Save tool data.
    self.tools = load_objects_from_url(tools_json)

  # Setup/Stop methods ####

  async def setup(self, home=False):

    await super().setup()

    # TODO: Set up logging. Will it interfere with PLRs?
    # setup_logging(directory=opts.get('logdir', None),
    #               level=opts.get('loglevel', logging.INFO))

    # Populate the controller's database with data from the Deck.
    database_tools = NoObjects()
    database_tools.workspaces = [self.deck.workspace]
    database_tools.platforms = self.deck.platforms
    database_tools.containers = self.deck.containers
    database_tools.tools = self.tools
    # database_tools.settings

    # Create the controller object.
    self.controller = Controller(config=self.config, database_tools=database_tools)

    # Set current data objects in the gcode builder.
    self.controller.builder.initialize_objects(
      workspace=self.deck.workspace, platformsInWorkspace=self.deck.platforms)

    # Populate the controller's database with Tool data.
    self.tool_ids = list(self.controller.builder.tools)

    # Start the controller.
    await self._start_controller(timeout=5, reset_firmware_on_error=True)

    # Home the robot's motion system.
    if home:
      await self._home_machine(timeout=43)

    # Mark finished.
    self.setup_finished = True

  async def _start_controller(self, timeout, reset_firmware_on_error):

    if self.controller.dry:
      print("Dry mode enabled, skipping setup.")
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

  def check_tool(self, tool_id):
    if tool_id not in self.tool_ids:
      raise ValueError(f"Tool with ID '{tool_id}' was not found in the backend's tools list ({self.tool_ids}).")


  # Action generators ####
  @staticmethod
  def get_spot_index(spot):
    """Find the index number of a resource (e.g. a TipSpot) from an itemized resource (e.g. a Tip Rack)."""
    itemized_resource = spot.parent
    index = next(i for i, s in enumerate(itemized_resource.get_all_items()) if s is spot)
    return index

  def make_home_action(self, axes=None) -> List:
    """make_home_action"""
    home_action = newt.protocol_actions.action_home(axis=axes)
    return [home_action]

  def make_tip_pickup_action(self, operations: List[Pickup], use_channels: List[int], tool_id: str) -> List:
    """make_tip_pickup_action"""
    self.check_tool(tool_id)

    pick_up_tip_actions = []
    for op, ch in zip(operations, use_channels):

      # Get the index of the TipSpot in the TipRack.
      tip_spot_index = self.get_spot_index(op.resource)

      # Make the action.
      pick_up_tip_action = newt.protocol_actions.action_pick_tip(
        tool=tool_id,
        item=op.resource.parent.name,
        # NOTE: Can't use names because PLR Tips don't have one.
        value=tip_spot_index, select_by="index"
      )
      pick_up_tip_actions.append(pick_up_tip_action)

    return pick_up_tip_actions

  def make_discard_tip_action(self, operations: List[Drop], use_channels: List[int], tool_id: str = None) -> List:
    """make_discard_tip_action"""
    self.check_tool(tool_id)


    # Use newt.
    discard_tip_actions = []
    for op, ch in zip(operations, use_channels):

      # Get the correct item name.
      # NOTE: PLR may pass a "Trash" or "TipSpot" resource to a Drop operation.
      if isinstance(op.resource, TipSpot):
        item_name = op.resource.parent.name
        content_name=op.resource.name
      else:
        # NOTE: Probably "Trash".
        item_name = op.resource.name
        content_name = None

      # TODO: Check if piper needs any more stuff from the "operation".
      discard_tip_action = newt.protocol_actions.action_discard_tip(
        tool=tool_id,
        # NOTE: Piper will deduce the type of drop location on its own.
        item=item_name,
        value=content_name, select_by="name"
      )
      discard_tip_actions.append(discard_tip_action)

    return discard_tip_actions

  def make_pipetting_action(self, operations: List[Aspiration], use_channels: List[int], tool_id: str) -> List:
    """make_pipetting_action"""
    self.check_tool(tool_id)

    pipetting_actions = []
    for op, ch in zip(operations, use_channels):

      # Get the correct item name.
      if isinstance(op.resource, PiperTube):
        # NOTE: Tubes are nested in TubeSpots.
        item_name = op.resource.parent.parent.name
      else:
        item_name = op.resource.parent.name

      # Choose the appropriate action function.
      if isinstance(op, Dispense):
        liquid_action_func = newt.protocol_actions.action_drop_liquid
      elif isinstance(op, Aspiration):
        liquid_action_func = newt.protocol_actions.action_load_liquid
      else:
        msg = f"The pipetting operation must Aspirate or Dispense, not '{op.__class__.__name__}'."
        raise ValueError(msg)

      # Generate the action.
      pipetting_action = liquid_action_func(
                volume=op.volume,
                tool=tool_id,
                # NOTE: Piper will deduce the type of drop location on its own.
                item=item_name,
                value=op.resource.name, select_by="name"
              )
      # Save it to the list.
      pipetting_actions.append(pipetting_action)

    return pipetting_actions

  # Atomic implemented in hardware ####

  def parse_actions(self, actions: list) -> List:
    gcode_list = []
    for a in actions:
      action_commands, _ = self.controller.builder.parseAction(a)
      gcode_list += action_commands
    return gcode_list

  async def run_gcode(self, gcode_list:list, timeout:float):
    for gcode in gcode_list:
      await self._send_command_wait_and_check(gcode, timeout=timeout)

  async def run_actions(self, actions:list):
    # Make GCODE
    gcode_list = self.parse_actions(actions)

    # Send and check for success
    # TODO: have the timeout based on an estimation.
    await self.run_gcode(gcode_list, timeout=10.0)

  async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], tool_id: str, **backend_kwargs):
    """Pick up tips.

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
    print(f"Picking up tips: {ops}")

    self.check_tool(tool_id)

    # TODO: Ask Rick how to choose a pipette (or channel from a multi-chanel pipette).
    #       The OT module has a "select_tip_pipette" method.

    # TODO: Handle multi-channel pick-up operations.
    actions = self.make_tip_pickup_action(ops, use_channels, tool_id)

    # Run the actions.
    await self.run_actions(actions)

  async def drop_tips(self, ops: List[Drop], use_channels: List[int], tool_id: str, **backend_kwargs):
    """drop_tips"""
    print(f"Dropping tips {ops}.")

    # TODO: reject operations which are not "discard to trash" using "NotImplementedError".
    # This is because the Pipettin robot (2023/03) ejects tips using a fixed "post" and not a regular ejector.

    # TODO: Ask Rick how to choose a pipette (or channel from a multi-chanel pipette).
    #       The OT module has a "select_tip_pipette" method.
    self.check_tool(tool_id)

    # TODO: Handle multi-channel pick-up operations.
    actions = self.make_discard_tip_action(ops, use_channels, tool_id=tool_id)

    # Run the actions.
    await self.run_actions(actions)


  async def aspirate(self, ops: List[Aspiration], use_channels: List[int], tool_id: str, **backend_kwargs):
    """aspirate"""
    print(f"Aspirating {ops}.")

    # TODO: Ask Rick how to choose a pipette (or channel from a multichanel pipette).
    #       The OT module has a "select_tip_pipette" method.
    self.check_tool(tool_id)

    # Make action
    actions = self.make_pipetting_action(ops, use_channels, tool_id)

    # Run the actions.
    await self.run_actions(actions)

  async def dispense(self, ops: List[Dispense], use_channels: List[int], **backend_kwargs):
    """dispense"""
    print(f"Dispensing {ops}.")

    # TODO: Ask Rick how to choose a pipette (or channel from a multichanel pipette).
    #       The OT module has a "select_tip_pipette" method.
    tool_id = None

    # Make action
    # TODO: ask Rick if the "Dispense" operation is really the same as "Aspirate" (see standard.py).
    actions = self.make_pipetting_action(ops, use_channels, tool_id)

    # Run the actions.
    await self.run_actions(actions)


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
