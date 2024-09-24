import asyncio
import pytest
from math import isclose

from pylabrobot.liquid_handling.backends.piper_backend import PiperBackend
from pylabrobot.resources import SilverDeck, Axy_24_DW_10ML, FourmlTF_L, Coordinate
from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.resources import set_tip_tracking, set_volume_tracking

from piper.datatools.datautils import load_objects
from piper.utils import default_config

from newt.translators.plr import deck_to_workspaces

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
  tools = db["tools"]

  # Instantiate the deck object.
  deck = SilverDeck(workspace, platforms, containers, tools)

  print("Deck setup done")
  return deck

def test_silver_deck():
  # Instantiate the deck.
  deck = make_silver_deck()

  # Try assigning and retrieving some resources.
  well_plate = Axy_24_DW_10ML("Axygen well-plate")
  tip_rack = FourmlTF_L("24x 4ml Tips with Filters")
  deck.assign_child_resource(well_plate, location=Coordinate(0,0,0))
  deck.assign_child_resource(tip_rack, location=Coordinate(0,150,0))
  deck.get_resource("Axygen well-plate")
  deck.get_resource("24x 4ml Tips with Filters")

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

def test_translation():
  """Check that translations work (or at least can run)"""
  # Instantiate the deck.
  deck = make_silver_deck()
  # Serialize deck.
  deck_data = deck.serialize()
  # Convert to workspace.
  deck_to_workspaces(deck_data)

def test_reverse_engineering():
  # Import the resource class
  from pylabrobot.resources import pipettin_test_plate as test_plate

  # Create an instance
  well_plate = test_plate(name="plate_01")
  well_plate.set_well_liquids(liquids=(None, 123))

  dx = well_plate["A1"][0].location.x
  dy = well_plate["H1"][0].location.y
  dz = well_plate["H1"][0].location.z
  item_dx = well_plate["A2"][0].location.x - well_plate["A1"][0].location.x
  item_dy = well_plate["A1"][0].location.y - well_plate["B1"][0].location.y

  from newt.translators.utils import calculate_plr_grid_parameters, derive_grid_parameters_from_plr

  serialized_well_plate = well_plate.serialize()

  params = calculate_plr_grid_parameters(serialized_well_plate)

  assert isclose(params["dx"], dx)
  assert isclose(params["dy"], dy)
  assert isclose(params["dz"], dz)
  assert isclose(params["item_dx"], item_dx)
  assert isclose(params["item_dy"], item_dy)

  new_params = derive_grid_parameters_from_plr(serialized_well_plate)

  # Dimensions as shown here:
  # https://assets.thermofisher.com/TFS-Assets/LSG/manuals/MAN0014419_ABgene_Storage_Plate_96well_1_2mL_QR.pdf
  assert isclose(new_params["firstWellCenterX"], 14.38)
  assert isclose(new_params["firstWellCenterY"], 11.24)
