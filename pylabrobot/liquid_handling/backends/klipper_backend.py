"""
Klipper backend for PLR.

It relies on the websocket API provided by the Moonkraker program.

Options:

- subclass LiquidHandlerBackend: "Abstract base class for liquid handling robot backends".
- subclass SerializingBackend: "A backend that serializes all commands received, and sends them to `self.send_command` for
  processing. The implementation of `send_command` is left to the subclasses.".

SerializingBackend makes more sense as it has the serializing feature, it is also a subclass of LiquidHandlerBackend.
The chatterbox and opentrons backends use only LiquidHandlerBackend. Sticking to it then...

To-do:

- Find out what "assigned_resource_callback" and "unassigned_resource_callback" are for.
- It is becomeing clear to me that backends delegate all movement/pipetting logic to the robot.
  This means that a "Klipper backend" would not be useful directly. For example: ¿how should Klipper
  react to a "drop tip" command? The straightforward way would be to pass values from PLR to Klipper
  (Jinja2) macros, which can be tuned to a specific robot by the user, using Klipper config files.

Klipper accepts parameters for macros, see: https://www.klipper3d.org/Command_Templates.html?h=macro#macro-parameters

There are at least some important unknowns:

- Tool-changing: ¿should this be managed by this backend? ¿or in a klipper macro?
- Would it be better to instead write a backend for pipettin piper instead?

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


class ChatterBoxBackend(LiquidHandlerBackend):
    """ Chatter box backend for 'How to Open Source' """

    async def setup(self):
        print("Setting up the robot.")

    async def stop(self):
        print("Stopping the robot.")

    async def assigned_resource_callback(self, resource: Resource):
        print(f"Resource {resource.name} was assigned to the robot.")

    async def unassigned_resource_callback(self, name: str):
        print(f"Resource {name} was unassigned from the robot.")

    async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], **backend_kwargs):
        print(f"Picking up tips {ops}.")

    async def drop_tips(self, ops: List[Drop], use_channels: List[int], **backend_kwargs):
        print(f"Dropping tips {ops}.")

    async def aspirate(self, ops: List[Aspiration], use_channels: List[int], **backend_kwargs):
        print(f"Aspirating {ops}.")

    async def dispense(self, ops: List[Dispense], use_channels: List[int], **backend_kwargs):
        print(f"Dispensing {ops}.")

    async def move_resource(self, move: Move, **backend_kwargs):
        print(f"Moving {move}.")

    async def pick_up_tips96(self, pickup: PickupTipRack, **backend_kwargs):
        print(f"Picking up tips from {pickup.resource.name}.")

    async def drop_tips96(self, drop: DropTipRack, **backend_kwargs):
        print(f"Dropping tips to {drop.resource.name}.")

    async def aspirate96(self, aspiration: AspirationPlate):
        print(f"Aspirating {aspiration.volume} from {aspiration.resource}.")

    async def dispense96(self, dispense: DispensePlate):
        print(f"Dispensing {dispense.volume} to {dispense.resource}.")
