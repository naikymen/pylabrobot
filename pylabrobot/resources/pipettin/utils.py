import json
import urllib.request

from pylabrobot.resources import Coordinate, Trash, PetriDish, Colony
from pylabrobot.resources.liquid import Liquid

def get_items_platform(item, platforms):
  """Get the data for a platform item."""
  platform_data = next(x for x in platforms if x["name"] == item.get("platform"))
  return platform_data

def get_contents_container(content, containers):
  """Get the container data for a content."""
  container_data = next(x for x in containers if x["name"] == content.get("container"))
  return container_data

def create_trash(platform_item, platform_data, **kwargs):
  trash = Trash(
    name=platform_item["name"],
    size_x=platform_data["width"],
    size_y=platform_data["length"],
    size_z=platform_data["height"],
    category=platform_data.get("type", None), # Optional in PLR.
    model=platform_data.get("name", None) # Optional in PLR (not documented in Resource).
  )
  return trash

def create_petri_dish(platform_item, platform_data, **kwargs):
  dish = PetriDish(
    name=platform_item["name"],
    diameter=platform_data["diameter"],
    height=platform_data["height"],
    category=platform_data.get("type", None),
    model=platform_data.get("name", None)
  )

  # Add tubes in the platform item, if any.
  platform_contents = platform_item.get("content", [])
  for content in platform_contents:
    # Create the colony.
    colony = Colony(
      name=content["name"],

      # TODO: Figure out actually useful values for "diameter" and "height".
      diameter=content["volume"],
      height=content["volume"],

      category=content.get("type", None),  # "colony"

      # TODO: The "model" should be the container data.
      model=content.get("type", None),

      # NOTE: Colonies have no "containers" in PW's data schemas.
      max_volume=content.get("maxVolume", None)
    )

    # TODO: Add liquid classes to our data schemas, even if it is water everywhere for now.
    # Add liquid to the tracker.
    colony.tracker.add_liquid(Liquid.WATER, volume=content["volume"])

    # Add the colony as a direct child.
    dish.assign_child_resource(colony, location=Coordinate(**content["position"]))

  return dish

def load_objects_from_url(target_url):
  data = urllib.request.urlopen(target_url)
  objects = json.load(data)
  return objects

def load_defaults():
  # Example using exported data.

  target_url = 'https://gitlab.com/pipettin-bot/pipettin-gui/-/raw/develop/api/src/db/defaults/workspaces.json'
  workspace = load_objects_from_url(target_url)[0]

  target_url = 'https://gitlab.com/pipettin-bot/pipettin-gui/-/raw/develop/api/src/db/defaults/platforms.json'
  platforms = load_objects_from_url(target_url)

  target_url = 'https://gitlab.com/pipettin-bot/pipettin-gui/-/raw/develop/api/src/db/defaults/containers.json'
  containers = load_objects_from_url(target_url)

  return workspace, platforms, containers
