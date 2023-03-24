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


class PiperBackend(LiquidHandlerBackend):
    """ Chatter box backend for 'How to Open Source' """

    async def setup(self):
        print("Setting up the robot.")

    async def stop(self):
        print("Stopping the robot.")

    async def assigned_resource_callback(self, resource: Resource):
        print(f"Resource {resource.name} was assigned to the robot.")

    async def unassigned_resource_callback(self, name: str):
        print(f"Resource {name} was unassigned from the robot.")

    # Atomic implemented in hardware.
    async def pick_up_tips(self, ops: List[Pickup], use_channels: List[int], **backend_kwargs):
        print(f"Picking up tips {ops}.")

    async def drop_tips(self, ops: List[Drop], use_channels: List[int], **backend_kwargs):
        print(f"Dropping tips {ops}.")

    async def aspirate(self, ops: List[Aspiration], use_channels: List[int], **backend_kwargs):
        print(f"Aspirating {ops}.")

    async def dispense(self, ops: List[Dispense], use_channels: List[int], **backend_kwargs):
        print(f"Dispensing {ops}.")

    # Atomic actions not implemented in hardware.
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
