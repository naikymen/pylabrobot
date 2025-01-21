"""
Piper backend for PLR.

It relies on the "piper" module, which implements a robot
controller for the OLA/Pipettin lab automation project.

Example:

```python3
from pylabrobot.liquid_handling import LiquidHandler

from pylabrobot.liquid_handling.backends import PiperBackend
from pylabrobot.resources import SilverDeck
from pylabrobot.resources.pipettin.utils import load_defaults

workspace, platforms, containers, tools = load_defaults()

deck = SilverDeck(workspace, platforms, containers, tools)
back = PiperBackend()
lh = LiquidHandler(backend=back, deck=deck)

await lh.setup()
```

Have fun!
"""

from pprint import pformat
from typing import List, Union
import asyncio
import logging

from pylabrobot.resources import TipSpot
from pylabrobot.resources.pipettin.tube_racks import Tube as PiperTube
from pylabrobot.liquid_handling.backends import LiquidHandlerBackend
from pylabrobot.resources import Resource, ItemizedResource
from pylabrobot.liquid_handling.standard import (
  Pickup,
  PickupTipRack,
  Drop,
  DropTipRack,
  Aspiration,
  AspirationPlate,
  Dispense,
  DispensePlate,
  ResourceDrop,
  ResourceMove,
  ResourcePickup,
)
# TODO: Raise "NoChannelError" in the backend when appropriate.
# from pylabrobot.liquid_handling.errors import NoChannelError

# Custom stuff.
from pylabrobot.resources.pipettin.utils import DynamicAttributes
# Load piper modules.
from piper.controller import Controller
from piper.datatools.nodb import NoObjects
from piper.datatools.mongo import MongoObjects
# Load newt module.
import newt
from newt.translators.utils import index_to_row_first_index

class PiperError(Exception):
  """ Raised when the Piper backend fails."""

class PiperBackend(LiquidHandlerBackend):
  """ Backend for Piper, OLA's liquid-handler controller module."""

  def __init__(self, config:dict = None, home_on_setup_and_close=False):
    """Init method for the PiperBackend."""

    # Init LiquidHandlerBackend.
    super().__init__()

    # Declare attributes.
    self.controller: Controller = None
    self._num_channels: int = None
    self._channels: dict = None
    self.home_on_setup_and_close = home_on_setup_and_close

    # Set the default configuration.
    self.config = config
    self.verbose = self.config.get("verbose", False)

  def init_channels(self, tool_defs: dict):
    """ Compute and save number of channels.

    This requires tool definitions with the following properties:

    tool_defs = {
      "P200": {"parameters": {"channels": 1} },
      "P300x8": {"parameters": {"channels": 8} }
    }
    """
    self._num_channels = 0
    self._channels = {}
    for tool in tool_defs:
      if tool.get("type", None) == "Micropipette":
        ch_count: int = tool["parameters"]["channels"]
        tool_name: str = tool["name"]
        for ch in range(self._num_channels, self._num_channels+ch_count):
          if ch in self._channels:
            raise ValueError(f"Channel {ch} is already provided by {self._channels[ch]}.")
          self._num_channels += 1
          self._channels[ch] = tool_name
          if self.verbose:
            print(f"Assigning channel number {ch} to tool '{tool_name}'.")
    print(f"Configured the PiperBackend with {self._num_channels} channels: {", ".join(self._channels.values())}")
    # The channels property is a dynamic attribute.
    print(self.channels)

  @property
  def channels(self):
    return DynamicAttributes(what="Channels", **{v: k for k, v in self._channels.items()})

  def init_controller(self):
    """Instantiate a controller object and save it to this backend instance.
    Requires an associated SilverDeck.
    """
    # Check.
    if self.controller:
      raise PiperError("Controller object already configured.")

    # Create the controller object.
    # TODO: Check if it makes sense to use the "deck" object here.
    self.controller = Controller(config=self.config)

    # Set current data objects in the gcode builder.
    # TODO: This is not deck-agnostic.
    self.controller.builder.initialize_objects(
      workspace=self.deck.workspace,
      platformsInWorkspace=self.deck.platforms
    )

    # Save tool names.
    self.tool_ids = list(self.controller.builder.tools)

  # Setup/Stop methods ####

  async def setup(self, home=False, controller: Controller = None):
    """Backend setup method, called by LiquidHandler.

    Args:
        home (bool, optional): Home the machine on setup. Defaults to False.
        controller (Controller, optional): Provide a controller object. Defaults to None.
    """
    # Parent class setup. Must happen first.
    await super().setup()

    # Define a controller object.
    if controller is None:
      self.init_controller()

    # Configure channels.
    self.init_channels(self.deck.tools)

    # Start the controller.
    await self._start_controller(timeout=5)

    # Home the robot's motion system.
    if home or self.home_on_setup_and_close:
      await self._home_machine()

    # Mark finished.
    self.setup_finished = True

  async def _start_controller(self, timeout=5):

    # Start the controller.
    print("Setting up connections...")
    try:
      status = await asyncio.wait_for(
        self.controller.start_and_wait(),
        timeout=timeout
      )
    except (asyncio.exceptions.TimeoutError, asyncio.CancelledError):
      logging.error("Timed-out while setting up connections.")
      status = None

    # Check for readiness.
    if not status:
      raise PiperError("Firmware not ready, check the logs on the robot's computer.")
    else:
      print("Connections successfully setup.")

  async def _home_machine(self, axes=None):
    # TODO: customize parameters.

    if self.controller.machine.dry:
      print("Dry mode enabled, skipping Homing routine.")
      return

    try:
      # Generate the homing actions.
      home_actions = self.make_home_actions(axes=axes)

      # Generate the actions' gcode.
      await self.run_actions(home_actions)

    except Exception as e:
      raise PiperError("Failed to home.") from e

    print("Homing done!")

  async def stop(self, timeout=2.0, home=False):
    # Home the robot.
    if home or self.home_on_setup_and_close:
      # TODO: Check if it makes sense, this only parks the tool, but does not home if already homed.
      await self._home_machine(axes="xyz")

    if self.controller.machine.dry:
      print("Dry mode enabled, skipping machine cleanup.")
    else:
      print("Stopping the robot.")

      # Try sending a "motors-off" command.
      cmd_id = await self.controller.machine.send_gcode_cmd("M84", wait=True, check=True, timeout=timeout)

      # Send an "emergency stop" command if M84 failed.
      result = await self.controller.machine.check_command_result_ok(
        cmd_id=cmd_id, timeout=timeout, loop_delay=0.2)
      if not result:
        await self.controller.machine.firmware_restart()

    # TODO: comment on what this does.
    await super().stop()

    # Close the connection to moonraker.
    await self.controller.stop()

  # Resource callback methods ####

  async def assigned_resource_callback(self, resource: Resource):
    if self.config.get("verbose", False):
      print(f"piper_backend: Resource '{resource.name}' assigned to the robot.")
    # TODO: should this update the workspace?

  async def unassigned_resource_callback(self, name: str):
    if self.config.get("verbose", False):
      print(f"piper_backend: Resource '{name}' unassigned from the robot.")
    # TODO: should this update the workspace?

  # Helper methods ####

  @property
  def num_channels(self) -> int:
    return self._num_channels

  @staticmethod
  def get_coords(operation: Union[Pickup, Drop]):
    # pick_up_op
    coordinate = operation.get_absolute_location()
    coordinate_dict = coordinate.serialize()
    return coordinate_dict

  # Action generators ####
  @staticmethod
  def get_spot_index(spot):
    """Find the index of a resource (e.g. a TipSpot) in an itemized resource (e.g. a Tip Rack)."""
    # Get the rack.
    itemized_resource: ItemizedResource = spot.parent
    # Get the spot's index.
    col_first_index = next(i for i, s in enumerate(itemized_resource.get_all_items()) if s is spot)
    # Convert PLR's index to piper's index.
    columns, rows = itemized_resource.num_items_x, itemized_resource.num_items_y
    row_first_index = index_to_row_first_index(col_first_index, rows, columns)
    # Return piper's index.
    return row_first_index

  def make_home_actions(self, axes=None) -> List:
    """Make a homing action"""
    home_action = newt.protocol_actions.action_home(axis=axes)
    return [home_action]

  def make_tip_pickup_action(self, operations: List[Pickup], use_channels: List[int]) -> List:
    """Make a tip pickup action"""

    pick_up_tip_actions = []
    for op, ch in zip(operations, use_channels):

      # Get the index of the TipSpot in the TipRack.
      content_index = self.get_spot_index(op.resource) + 1

      # Make the action.
      pick_up_tip_action = newt.protocol_actions.action_pick_tip(
        tool=self._channels[ch],
        item=op.resource.parent.name,
        # NOTE: Can't use names because PLR Tips don't have one.
        value=content_index, select_by="index"
      )
      pick_up_tip_actions.append(pick_up_tip_action)

    return pick_up_tip_actions

  def make_discard_tip_action(self, operations: List[Drop], use_channels: List[int]) -> List:
    """Make a discard tip action"""

    # Use newt.
    discard_tip_actions = []
    for op, ch in zip(operations, use_channels):

      # Get the correct item name.
      # NOTE: PLR may pass a "Trash" or "TipSpot" resource to a Drop operation.
      if isinstance(op.resource, TipSpot):
        # Rack name.
        item_name, select_by = op.resource.parent.name, "index"
        # Get the index of the TipSpot in the TipRack.
        value = self.get_spot_index(op.resource)
      else:
        # NOTE: Probably "Trash".
        item_name, select_by = op.resource.name, "name"
        value = None

      # TODO: Check if piper needs any more stuff from the "operation".
      discard_tip_action = newt.protocol_actions.action_discard_tip(
        tool=self._channels[ch],
        # NOTE: Piper will deduce the type of drop location on its own.
        item=item_name, select_by=select_by,
        value=value,
      )
      discard_tip_actions.append(discard_tip_action)

    return discard_tip_actions

  def make_pipetting_action(self, operations: List[Aspiration], use_channels: List[int]) -> List:
    """Make a dispense/aspirate action"""

    pipetting_actions = []
    for op, ch in zip(operations, use_channels):

      # Get the correct tube spot.
      if isinstance(op.resource, PiperTube):
        # NOTE: Tubes are nested in TubeSpots in my custom TubeRack.
        spot = op.resource.parent
      else:
        # Regular PLR tubes and wells are not in spots.
        spot = op.resource

      # Get the item name.
      item_name = spot.parent.name
      # Get the index of the spot in the parent.
      content_index = self.get_spot_index(spot) + 1

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
                tool=self._channels[ch],
                # NOTE: Piper will deduce the type of drop location on its own.
                item=item_name,
                # value=op.resource.name, select_by="name"
                value=content_index, select_by="index"
              )
      # Save it to the list.
      pipetting_actions.append(pipetting_action)

    return pipetting_actions

  # GCODE generation and execution ####

  def parse_actions(self, actions: list):
    """Parse actions into GCODE"""
    gcode_list = []
    actions_list = []
    for a in actions:
      action = self.controller.builder.parseAction(a)
      gcode_list += action["GCODE"]
      actions_list += [action]
    return gcode_list, actions_list

  async def _send_command_wait_and_check(self, gcode: list, timeout):
    # Send commands.
    # TODO: customize timeout.
    await self.controller.machine.send_gcode_script(gcode, wait=True, check=True, timeout=timeout)
    # Wait for idle printer.
    return await self.controller.machine.wait_for_idle_printer(timeout=1.0)

  async def run_gcode(self, gcode_list:list, timeout:float):
    # TODO: Consider removing this method and "_send_command_wait_and_check". No longer used.
    if self.controller.machine.dry:
      print(f"Backend in dry mode: {len(gcode_list)} commands will be ignored.")
    for gcode in gcode_list:
      await self._send_command_wait_and_check(gcode, timeout=timeout)

  async def run_actions(self, actions: list):
    if self.verbose:
      print("Executing actions:\n" + pformat(actions))

    # Make GCODE
    gcode_list, parsed_actions = self.parse_actions(actions)

    # Send and check for success

    # Run the actions.
    await self.controller.run_actions_protocol(actions=parsed_actions)

  # Atomic implemented in hardware ####

  async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], **backend_kwargs):
    """Pick up tips.

    The action can also provide the tip's coordinates directly,
    but must provide "tip" data explicitly:
      'args': {'coords': {"x": 20, "y": 200, "z": 30},
          'tool': 'P200',
          'tip': tip_definition},  # Note the tip data passed here (described below).
      'cmd': 'PICK_TIP'

    Example "tip_definition" for "coords" type args:
      'maxVolume': 160,
      'tipLength': 50.0,
      'volume': 0
    """
    if self.verbose:
      print(f"Picking up tips: {ops}")

    # TODO: Ask Rick how to choose a pipette (or channel from a multi-chanel pipette).
    #       The OT module has a "select_tip_pipette" method.

    # TODO: Handle multi-channel pick-up operations.
    actions = self.make_tip_pickup_action(ops, use_channels)

    # Run the actions.
    await self.run_actions(actions)

  async def drop_tips(self, ops: List[Drop], use_channels: List[int], **backend_kwargs):
    """drop_tips"""
    if self.verbose:
      print(f"Dropping tips {ops}.")

    # TODO: reject operations which are not "discard to trash" using "NotImplementedError".
    # This is because the Pipettin robot (2023/03) ejects tips using
    # a fixed "post" and not a regular ejector.

    # TODO: Handle multi-channel pick-up operations.
    actions = self.make_discard_tip_action(ops, use_channels)

    # Run the actions.
    await self.run_actions(actions)

  async def aspirate(self, ops: List[Aspiration], use_channels: List[int], **backend_kwargs):
    """aspirate"""
    if self.verbose:
      print(f"Aspirating {ops}.")

    # Make action
    actions = self.make_pipetting_action(ops, use_channels)

    # Run the actions.
    await self.run_actions(actions)

  async def dispense(self, ops: List[Dispense], use_channels: List[int], **backend_kwargs):
    """dispense"""
    if self.verbose:
      print(f"Dispensing {ops}.")

    # Make action
    # TODO: ask Rick if the "Dispense" operation is really the same as "Aspirate" (see standard.py).
    actions = self.make_pipetting_action(ops, use_channels)

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

  async def pick_up_resource(self, pickup: ResourcePickup):
    """Pick up a resource like a plate or a lid using the integrated robotic arm."""
    raise NotImplementedError("The backend does not support moving resources.")

  async def move_picked_up_resource(self, move: ResourceMove):
    """Move a picked up resource like a plate or a lid using the integrated robotic arm."""
    raise NotImplementedError("The backend does not support moving resources.")

  async def drop_resource(self, drop: ResourceDrop):
    """Drop a resource like a plate or a lid using the integrated robotic arm."""
    raise NotImplementedError("The backend does not support moving resources.")


class EchoBackend(LiquidHandlerBackend):
  """ Yet another Chatter box backend for 'How to Open Source' """

  commands = []
  """Just a list to store incoming data, for later inspection"""

  def __init__(self, num_channels: int = 1, name="echo"):
    """Init method for the EchoBackend."""
    print(f"EchoBackend - Instantiating the EchoBackend with num_channels={num_channels}")
    self.name=name
    super().__init__()
    self._num_channels = num_channels

  async def setup(self):
    await super().setup()
    print("EchoBackend - Setting up the robot.")

  async def stop(self):
    await super().stop()
    print("EchoBackend - Stopping the robot.")

  @property
  def num_channels(self) -> int:
    return self._num_channels

  async def assigned_resource_callback(self, resource: Resource):
    print(f"EchoBackend - Resource {resource.name} was assigned to the robot:\n" + pformat(resource.serialize))

  async def unassigned_resource_callback(self, name: str):
    print(f"EchoBackend - Resource with name '{name}' was unassigned from the robot.")

  # Atomic implemented in hardware.
  async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], **backend_kwargs):
    print(f"EchoBackend - {len(self.commands)} - Picking up tips {ops}.")
    self.commands.append(
      {"cmd": "pick_up_tips", "ops": ops, "use_channels": use_channels, **backend_kwargs}
    )

  async def drop_tips(self, ops: List[Drop], use_channels: List[int], **backend_kwargs):
    print(f"EchoBackend - {len(self.commands)} - Dropping tips {ops}.")
    self.commands.append(
      {"cmd": "drop_tips", "ops": ops, "use_channels": use_channels, **backend_kwargs}
    )

  async def aspirate(self, ops: List[Aspiration], use_channels: List[int], **backend_kwargs):
    print(f"EchoBackend - {len(self.commands)} - Aspirating {ops}.")
    self.commands.append(
      {"cmd": "aspirate", "ops": ops, "use_channels": use_channels, **backend_kwargs}
    )

  async def dispense(self, ops: List[Dispense], use_channels: List[int], **backend_kwargs):
    print(f"EchoBackend - {len(self.commands)} - Dispensing {ops}.")
    self.commands.append(
      {"cmd": "dispense", "ops": ops, "use_channels": use_channels, **backend_kwargs}
    )

  # Atomic actions not implemented in hardware.
  async def pick_up_tips96(self, pickup: PickupTipRack, **backend_kwargs):
    raise NotImplementedError("EchoBackend - The backend does not support the CoRe 96.")

  async def drop_tips96(self, drop: DropTipRack, **backend_kwargs):
    raise NotImplementedError("EchoBackend - The backend does not support the CoRe 96.")

  async def aspirate96(self, aspiration: AspirationPlate):
    raise NotImplementedError("EchoBackend - The backend does not support the CoRe 96.")

  async def dispense96(self, dispense: DispensePlate):
    raise NotImplementedError("EchoBackend - The backend does not support the CoRe 96.")

  async def pick_up_resource(self, pickup: ResourcePickup):
    """Pick up a resource like a plate or a lid using the integrated robotic arm."""
    raise NotImplementedError("The backend does not support moving resources.")

  async def move_picked_up_resource(self, move: ResourceMove):
    """Move a picked up resource like a plate or a lid using the integrated robotic arm."""
    raise NotImplementedError("The backend does not support moving resources.")

  async def drop_resource(self, drop: ResourceDrop):
    """Drop a resource like a plate or a lid using the integrated robotic arm."""
    raise NotImplementedError("The backend does not support moving resources.")
