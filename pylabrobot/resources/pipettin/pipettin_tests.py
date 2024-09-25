import pytest
from math import isclose
from copy import deepcopy
from pprint import pformat

from deepdiff import DeepDiff

from pylabrobot.liquid_handling.backends.piper_backend import PiperBackend
from pylabrobot.resources import SilverDeck, Axy_24_DW_10ML, FourmlTF_L, Coordinate
from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.resources import set_tip_tracking, set_volume_tracking

from piper.datatools.datautils import load_objects
from piper.utils import default_config

from newt.translators.plr import deck_to_workspaces, convert_custom

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

  # Cleanup.
  await lh.stop()

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

def test_conversions():

  # Choose the database and a workspace.
  workspace_name = "Basic Workspace"

  # Instantiate the deck object.
  deck = SilverDeck(db=db_location, workspace_name=workspace_name)

  pocket = deck.get_resource("Pocket PCR")
  pocket_serialized = pocket.serialize()

  data_converted = convert_custom(pocket_serialized, deck.get_size_y())

  converted_platform = data_converted["piper_platform"]
  converted_item = data_converted["piper_item"]
  converted_containers = data_converted["container_data"]
  # TODO: Allow and test descriptions.
  converted_containers = [{k:v for k, v in cntnr.items() if k != "description"} for cntnr in converted_containers]

  def format_number(x, significant_digits=4, number_format_notation=None):
    """function for DeepDiff's number_to_string_func argument.
    Example:
    format_number(3.123123), format_number(0), format_number(0.0)
    """
    fstring = "{0:." + str(significant_digits+1) + "g}"
    return fstring.format(x)

  # Item
  pocket_item = deepcopy(next(p for p in deck.workspace["items"] if p["name"] == pocket.name))
  del converted_item["platformData"]
  del converted_item["containerData"]

  # Platform
  pocket_platform = deepcopy(next(p for p in deck.platforms if p["name"] == pocket.name))
  del pocket_platform["color"]
  del pocket_platform["description"]
  del pocket_platform["rotation"]

  # Containers
  pocket_container_names = [cntnt["container"] for cntnt in pocket_item["content"] ]
  pocket_containers = deepcopy([cntnr for cntnr in deck.containers if cntnr["name"] in pocket_container_names])
  # Remove description.
  pocket_containers = [{k:v for k, v in cntnr.items() if k != "description"} for cntnr in pocket_containers]

  # Compare
  diff_result = DeepDiff(
      t1 = pocket_platform,
      t2 = converted_platform,
      # math_epsilon=0.001
      number_to_string_func = format_number, significant_digits=4,
      ignore_numeric_type_changes=True
  )
  if not diff_result:
    print(f"No differences in {pocket_platform['name']} platform.")
  # Assert that there are no differences
  assert not diff_result, f"Differences found in platform translation of the {pocket_platform['name']} platform:\n" + pformat(diff_result)

  # Compare
  diff_result = DeepDiff(
      t1 = pocket_item,
      t2 = converted_item,
      # math_epsilon=0.001
      number_to_string_func = format_number, significant_digits=4,
      ignore_numeric_type_changes=True
  )
  if not diff_result:
     print(f"No differences in {converted_item['name']} item.")
  # Assert that there are no differences
  assert not diff_result, f"Differences found in platform translation of the {converted_item['name']} item:\n" + pformat(diff_result)

  # Compare
  diff_result = DeepDiff(
      t1 = converted_containers,
      t2 = pocket_containers,
      # math_epsilon=0.001
      number_to_string_func = format_number, significant_digits=4,
      ignore_numeric_type_changes=True
  )
  if not diff_result:
     print(f"No differences in {converted_item['name']} used containers.")
  # Assert that there are no differences
  assert not diff_result, f"Differences found in container translation of the {converted_item['name']} item:\n" + pformat(diff_result)
