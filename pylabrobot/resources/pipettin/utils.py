import json

from pylabrobot.resources import Coordinate, Trash, PetriDish, Colony
from pylabrobot.resources.liquid import Liquid

from deepdiff import DeepDiff

# def sortedDeep(d):
#   if isinstance(d,list):
#     if len(d) > 0:
#       if isinstance(d[0],dict):
#         return [sortedDeep(v) for v in d]
#     return sorted( sortedDeep(v) for v in d )
#   if isinstance(d,dict):
#     return { k: sortedDeep(d[k]) for k in sorted(d)}
#   return d

def json_dump(data, path, indent=4, sort_keys=True):
  d = json.dumps(data, indent = indent, sort_keys=sort_keys)
  with open(path, "w", encoding="utf-8") as f:
    f.write(d)

def compare(t1, t2, ignore_order=True):
  # Compare
  diff_result = DeepDiff(
      t1 = t1, # sortedDeep(t1),
      t2 = t2, # sortedDeep(t2),
      # math_epsilon=0.001
      number_to_string_func = format_number, significant_digits=4,
      ignore_numeric_type_changes=True,
      ignore_order=ignore_order
  )
  return diff_result

def format_number(x, significant_digits=4, number_format_notation=None):
  """function for DeepDiff's number_to_string_func argument.
  Example:
  format_number(3.123123), format_number(0), format_number(0.0)
  """
  fstring = "{0:." + str(significant_digits+1) + "g}"
  return fstring.format(x)

def get_fitting_depth(tools_data: dict, tip_container_id: str):
  fitting_depths = {}
  for tool in [td for td in tools_data if td["type"] == "Micropipette"]:
    tip_stages = tool["parameters"]["tip_stages"]
    tip_fit_distance = [v["tip_fit_distance"] for k, v in tip_stages.items() if k != "default"]
    for tfd in tip_fit_distance:
      fitting_depths.update(tfd)
  fitting_depth = fitting_depths[tip_container_id]
  return fitting_depth

def importer_not_implemented(*args, platform_data, **kwargs):
  print("Method not implemented for platform type: " + platform_data["type"])
  # raise NotImplementedError("Method not implemented for platform type: " + platform_data["type"])

def get_items_platform(item, platforms):
  """Get the data for a platform item."""
  platform_data = next(x for x in platforms if x["name"] == item.get("platform"))
  return platform_data

def get_contents_container(container_link, containers):
  """Get container data for a container link."""
  container_data = next(x for x in containers if x["name"] == container_link.get("container"))
  return container_data

def create_trash(deck: "SilverDeck", platform_item, platform_data, tools_data: dict, **kwargs):
  trash = Trash(
    name=platform_item["name"],
    size_x=platform_data["width"],
    size_y=platform_data["length"],
    size_z=platform_data["height"],
    category=platform_data.get("type", None), # Optional in PLR.
    model=platform_data.get("name", None) # Optional in PLR (not documented in Resource).
  )
  trash.active_z = platform_data["activeHeight"]
  trash.locked = platform_item["locked"]
  return trash

def create_petri_dish(deck: "SilverDeck", platform_item, platform_data, tools_data: dict, **kwargs):
  dish = PetriDish(
    name=platform_item["name"],
    diameter=platform_data["diameter"],
    height=platform_data["height"],
    category=platform_data["type"],
    model=platform_data["name"],
    max_volume=platform_data["maxVolume"],
  )
  dish.active_z = platform_data["activeHeight"]
  dish.shape = "circular"

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
