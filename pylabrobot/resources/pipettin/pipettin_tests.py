import asyncio
import pytest

from pylabrobot.liquid_handling.backends.piper_backend import PiperBackend
from pylabrobot.resources import SilverDeck
from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.resources import set_tip_tracking, set_volume_tracking

from piper.datatools.datautils import load_objects
from piper.utils import default_config

# Example using exported data.
db_location = 'https://gitlab.com/pipettin-bot/pipettin-gui/-/raw/develop/api/src/db/defaults/databases.json'

def make_silver_deck(workspace_name = "MK3 Baseplate"):
  print("Deck setup")
  db = load_objects(db_location)["pipettin"]

  # Choose one workspace.
  workspace = next(w for w in db["workspaces"] if w["name"] == workspace_name)

  # Get all platforms and containers.
  platforms = db["platforms"]
  containers = db["containers"]

  # Instantiate the deck object.
  deck = SilverDeck(workspace, platforms, containers)

  print("Deck setup done")
  return deck

def test_silver_deck():
  # Instantiate the deck.
  deck = make_silver_deck()

  # Inspect the workspace's contents.
  print(deck.summary())

@pytest.mark.asyncio
async def test_piper_backend():

  # Get tool definitions.
  db = load_objects(db_location)["pipettin"]
  tool_defs = db["tools"]

  # Load default configuration, and set it to dry mode.
  config = default_config()
  config.update({
    "dry": True,
    "ws_address": "",
    "sio_address": ""
  })
  # Piper backend.
  print("Backend setup")
  back = PiperBackend(config=config, tool_defs=tool_defs)
  print("Backend setup done")

  # Instantiate the deck.
  deck = make_silver_deck()

  # TODO: Ask for a better error message when a non-instantiated backend is passed.
  print("LH setup")
  lh = LiquidHandler(backend=back, deck=deck)
  await lh.setup()
  print("LH done")

  # We enable tip and volume tracking globally using the `set_volume_tracking` and `set_tip_tracking` methods.
  print("Setting volume tracking")
  set_volume_tracking(enabled=True)
  set_tip_tracking(enabled=True)

  # Pickup.
  print("Pickup operation")
  tiprack = lh.get_resource("Blue tip rack")
  tip_spots = tiprack["A1:A2"]
  # TODO: Ask for a better error message when tips are passed instead of tip spots.
  pickups = await lh.pick_up_tips(tip_spots, use_channels=[0, 1])
  tiprack.print_grid()

  # Tube rack.
  print("Get tube")
  tube_rack = lh.get_resource("Tube Rack [5x16]")
  _ = tube_rack["A1"]
  _ = tube_rack.make_grid()

  # Tube spots.
  tube_spots = tube_rack.children
  _ = all([spot.tracker.has_tube for spot in tube_spots])

  # Tubes.
  tubes = tube_rack.get_all_tubes()

  # Tube volume tracker.
  _ = [tube.tracker.liquids for tube in tubes]

  # Aspirate.
  print("Aspirate operation")
  # await lh.aspirate(tubes, vols=[100.0, 50.0, 200.0], use_channels=[0])
  await lh.aspirate(tubes[:1], vols=[100.0], use_channels=[0])
  # Dispense.
  print("Dispense operation")
  # await lh.dispense(tubes, vols=[1.0, 1.0, 1.0])
  await lh.dispense(tubes[:1], vols=[10])
