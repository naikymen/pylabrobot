import pytest
from math import isclose
from copy import deepcopy
from pprint import pformat
import json

from deepdiff import DeepDiff

from pylabrobot.liquid_handling.backends.piper_backend import PiperBackend
from pylabrobot.resources import Deck, SilverDeck, Axy_24_DW_10ML, FourmlTF_L, Coordinate
from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.resources import set_tip_tracking, set_volume_tracking
from pylabrobot.resources import pipettin_test_plate

from pylabrobot.resources.pipettin.utils import format_number, compare, json_dump

from piper.datatools.datautils import load_objects
from piper.utils import default_config

from newt.translators.plr import deck_to_workspaces, convert_item, deck_to_db
from newt.translators.utils import (
  scrub, calculate_plr_dz_tip, calculate_plr_dz_tube, calculate_plr_dz_slot
)
from newt.translators.utils import calculate_plr_grid_parameters, derive_grid_parameters_from_plr

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
  back = PiperBackend(config=config)
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

def test_reverse_engineering():
  # Create an instance
  well_plate = pipettin_test_plate(name="plate_01")
  well_plate.set_well_liquids(liquids=(None, 123))

  dx = well_plate["A1"][0].location.x
  dy = well_plate["H1"][0].location.y
  dz = well_plate["H1"][0].location.z
  item_dx = well_plate["A2"][0].location.x - well_plate["A1"][0].location.x
  item_dy = well_plate["A1"][0].location.y - well_plate["B1"][0].location.y

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

def test_translation_basic():
  """Check that translations work (or at least can run)"""
  # Instantiate the deck.
  deck = make_silver_deck()
  # Serialize deck.
  deck_data = deck.serialize()
  # Convert to workspace.
  deck_to_workspaces(deck_data)


def test_translation_plr_plate():
  """Check that translations work (or at least can run)"""
  # Create an instance
  well_plate = pipettin_test_plate(name="plate_01")
  well_plate.set_well_liquids(liquids=(None, 123))

  # well_plate.print_grid()

  deck = Deck(size_x=300, size_y=200)

  deck.assign_child_resource(well_plate, location=Coordinate(100,100,0))

  # Serialize deck.
  deck_data = deck.serialize()
  # Convert to workspace.
  result = deck_to_db(deck_data)

  json_dump(deck_data, "/tmp/deck_original.json")
  json_dump(result["workspaces"], "/tmp/workspaces_converted.json")

def test_conversions():

  # Choose the database and a workspace.
  # workspace_name = "MK3 Baseplate"
  workspace_name = "Basic Workspace"

  # Instantiate the deck object.
  deck = SilverDeck(db=db_location, workspace_name=workspace_name)

  item_name = "Pocket PCR"

  # Get the item.
  item_resource = deck.get_resource(item_name)  # "Pocket PCR"

  # Serialize the resource.
  serialized_resource = item_resource.serialize()

  # Convert the resource.
  # data_converted = convert_custom(serialized_resource, deck.get_size_y())
  data_converted = convert_item(serialized_resource, deck.get_size_y())

  converted_item = data_converted[0]  # ["piper_item"]
  converted_platform = data_converted[1]  # ["piper_platform"]
  converted_containers = data_converted[2]  # ["container_data"]
  # TODO: Allow and test descriptions.
  converted_containers = [{k:v for k, v in cntnr.items() if k != "description"} for cntnr in converted_containers]

  # Item
  pocket_item = deepcopy(next(p for p in deck.workspace_items if p["name"] == item_resource.name))
  if "platformData" in converted_item:
    del converted_item["platformData"]
  if "containerData" in converted_item:
    del converted_item["containerData"]

  # Platform
  pocket_platform = deepcopy(next(p for p in deck.platforms if p["name"] == item_resource.model))

  # Clean up non essentials.
  scrub([pocket_platform, converted_platform], "description")
  scrub([pocket_platform, converted_platform], "color")

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
  else:
    json_dump(pocket_platform, "/tmp/pocket_platform.json")
    json_dump(converted_platform, "/tmp/pocket_converted.json")
  # Assert that there are no differences
  assert not diff_result, f"Differences found in platform translation of the {pocket_platform['name']} platform:\n" + \
    pformat(diff_result) #+ "\n" + pformat(converted_platform)

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
  assert not diff_result, f"Differences found in platform translation of the {converted_item['name']} item:\n" + \
    pformat(diff_result) # + "\n" + pformat(converted_item)

  # Compare
  diff_result = DeepDiff(
      t1 = pocket_containers,
      t2 = converted_containers,
      # math_epsilon=0.001
      number_to_string_func = format_number, significant_digits=4,
      ignore_numeric_type_changes=True
  )
  if not diff_result:
    print(f"No differences in {converted_item['name']} used containers.")
  # Assert that there are no differences
  assert not diff_result, f"Differences found in container translation of the {converted_item['name']} item:\n" + \
      pformat(diff_result) # + "\n" + pformat(pocket_containers) + "\n" + pformat(converted_containers)

def test_translation_advanced():

  db = load_objects(db_location)["pipettin"]

  # Test all workspaces.
  workspace_names = [w["name"] for w in db["workspaces"]]

  # Iterate over all workspaces.
  for workspace_name in workspace_names:

    # Instantiate the deck object.
    deck = SilverDeck(db=db_location, workspace_name=workspace_name)

    # Serialize deck.
    deck_data = deck.serialize()

    # Convert to workspace.
    new_workspaces, new_items, new_platforms, new_containers = deck_to_workspaces(deck_data)
    new_workspace = deepcopy(new_workspaces[0])
    workspace = deepcopy(deck.workspace)
    platforms = deck.platforms
    containers = deck.containers

    json_dump([deck.workspace], "/tmp/workspaces_orig.json")
    json_dump(new_workspaces, "/tmp/workspaces_new.json")

    json_dump(deck.platforms, "/tmp/platforms_orig.json")
    json_dump(new_platforms, "/tmp/platforms_new.json")

    # Remove "stuff".
    scrub([workspace, new_workspace, containers, new_containers, platforms, new_platforms],
           "description")
    scrub([platforms, new_platforms], "color")

    # Compare.
    diff_result = compare(platforms, new_platforms)
    # Test.
    assert not diff_result, f"Differences found in translation of platforms in '{workspace_name}':\n" + \
      pformat(diff_result)

    # Containers
    new_containers_names = [c["name"] for c in new_containers]
    containers = [c for c in containers if c["name"] in new_containers_names]

    json_dump(containers, "/tmp/object_original.json")
    json_dump(new_containers, "/tmp/object_new.json")

    # Compare
    diff_result = compare(containers, new_containers)
    assert not diff_result, f"Differences found in containers from {workspace_name}:\n" + \
      pformat(diff_result, width=200)

    # Workspaces
    for item in workspace["items"]:
      new_item = next(i for i in new_items if i["name"] == item["name"])

      json_dump(item, "/tmp/object_original.json")
      json_dump(new_item, "/tmp/object_new.json")

      # These are not in the direct database export.
      if "platformData" in new_item:
        del new_item["platformData"]
      if "containerData" in new_item:
        del new_item["containerData"]

      # Compare
      diff_result = compare(t1 = item, t2 = new_item)
      # Assert that there are no differences
      assert not diff_result, f"Differences found in translation of item {item['name']}:\n" + \
          pformat(diff_result, width=200) # + "\n" + pformat(pocket_containers) + "\n" + pformat(converted_containers)

def test_tip_z_calculation():

  # We enable tip and volume tracking globally using the `set_volume_tracking` and `set_tip_tracking` methods.
  set_volume_tracking(enabled=True)
  set_tip_tracking(enabled=True)

  # Get objects.
  deck = SilverDeck(db=db_location, workspace_name="MK3 Baseplate")
  rack = deck.get_resource("Blue tip rack")
  spots = rack.get_all_items()

  # tip_spot = rack.get_item("H1")
  for spot in spots:
    if spot.has_tip():
      tip = spot.get_tip()

      # Get the container ID of the tip.
      container = next(c for c in deck.containers if c["name"] == tip.model)
      rack_platform = next(p for p in deck.platforms if p["name"] == rack.name)
      container_link = next(l for l in rack_platform["containers"]
                            if l["container"] == container["name"])

      spot_Z = calculate_plr_dz_tip(rack_platform, container_link)
      # spot_Z = rack_platform["activeHeight"] - container_offset_z

      assert isclose(spot.location.z, spot_Z), f"spot_Z check failed for {rack.name} in {deck.name}"


def test_tube_z_calculation():

  # We enable tip and volume tracking globally using the `set_volume_tracking` and `set_tip_tracking` methods.
  set_volume_tracking(enabled=True)
  set_tip_tracking(enabled=True)

  # Get objects.
  deck = SilverDeck(db=db_location, workspace_name="MK3 Baseplate")
  rack = deck.get_resource("Tube Rack [5x16]")
  spots = rack.get_all_items()

  # tip_spot = rack.get_item("H1")
  for spot in spots:
    if spot.has_tube():
      tube = spot.get_tube()

      # Get the container ID of the tube.
      container = next(c for c in deck.containers if c["name"] == tube.model)
      rack_platform = next(p for p in deck.platforms if p["name"] == rack.name)
      container_link = next(l for l in rack_platform["containers"]
                            if l["container"] == container["name"])

      spot_Z = calculate_plr_dz_tube(rack_platform, container_link, container)
      # spot_Z = rack_platform["activeHeight"] - container_offset_z

      assert isclose(spot.location.z, spot_Z), f"spot_Z check failed for {rack.name} in {deck.name}"

def test_slot_z_calculation():

  # We enable tip and volume tracking globally using the `set_volume_tracking` and `set_tip_tracking` methods.
  set_volume_tracking(enabled=True)
  set_tip_tracking(enabled=True)

  # Get objects.
  workspace_name = "Basic Workspace"
  item_name = "Pocket PCR"
  deck = SilverDeck(db=db_location, workspace_name=workspace_name)
  custom = deck.get_resource(item_name)
  spots = custom.children

  # tip_spot = rack.get_item("H1")
  for spot in spots:
    if spot.has_tube():
      tube = spot.get_tube()

      item = next(p for p in deck.workspace["items"] if p["name"] == custom.name)
      platform = next(p for p in deck.platforms if p["name"] == item["platform"])
      content = next(c for c in item["content"] if c["name"] == tube.name)
      container = next(c for c in deck.containers if c["name"] == content["container"])
      slot = platform["slots"][content["index"] - 1]
      link = next(l for l in slot["containers"] if l["container"] == container["name"])

      spot_z = calculate_plr_dz_slot(platform, slot, link, container)

      assert isclose(tube.parent.location.z, spot_z), f"spot_Z check failed for {custom.name} in {deck.name}"
