from functools import partial

from pylabrobot.resources.liquid import Liquid
#from pylabrobot.resources.plate import Plate
from pylabrobot.resources.resource import Resource, Coordinate, Rotation

from newt.translators.utils import xy_to_plr, calculate_plr_dz_slot
from newt.utils import guess_shape
from .utils import get_contents_container
from .tubes import Tube, TubeSpot

# pylint: disable=locally-disabled, inconsistent-quotes

class CustomPlatform(Resource):
  def __getitem__(self, item):
    """Override the indexer operator "[]" to get children with a simpler syntax."""
    if isinstance(item, int):
      return self.children[item]
    return self.get_resource(item)

def make_tube_from_slot(container, slot):
  """Generate a default tube for the slot / tube spot
  Function used to generate tubes in TubeRacks when missing.
  """
  if container:
    return Tube(
      name=f"{container['name']} in {slot['slotName']}",
      size_x=slot["slotSize"],  # Same as the slot.
      size_y=slot["slotSize"],  # Same as the slot.
      size_z=container["length"],
      max_volume=container["maxVolume"],
      model=container["name"],
      category=container["type"]  # "tube"
      # TODO: Add "activeHeight" somewhere here.
      #       It is needed to get the proper Z coordinate.
    )
  else:
    raise NotImplementedError(f"No container data available for slot {slot['slotName']}.")

def load_ola_custom(platform_item: dict,
                    platform_data: dict,
                    containers_data: dict,
                    tools_data: dict):

  # {
  #   "height": 100,
  #   "activeHeight": 40.8,
  #   "rotation": 0,
  #   "slots": [...],
  #   "width": 0,
  #   "length": 0,
  #   "diameter": 150,
  #   "name": "Centrifuge",
  #   "description": "",
  #   "type": "CUSTOM",
  #   "color": "#757575"
  # }

  #   {
  #     "platform": "Pocket PCR",
  #     "name": "Pocket PCR",
  #     "snappedAnchor": null,
  #     "position": {
  #       "x": 25.39,
  #       "y": 268.37,
  #       "z": 0
  #     },
  #     "content": [...],
  #     "locked": false
  #   }

  # Guess the shape of the platform.
  size_x, size_y, shape = guess_shape(platform_data)

  # Create the custom platform item.
  custom = CustomPlatform(
    name=platform_item["name"],
    size_x=size_x,
    size_y=size_y,
    size_z=platform_data["height"],
    category=platform_data["type"], # "CUSTOM", Optional in PLR.
    model=platform_data["name"]  # "Pocket PCR", Optional in PLR (not documented in Resource).
  )
  # Save the platform's active height.
  # This will help recover some information later.
  custom.active_z = platform_data["activeHeight"]
  # Save the platform's shape.
  custom.shape = shape
  # Locked state.
  custom.locked = platform_item.get("locked", None)
  # TODO: Add rotation, even though it wont be usable and cause crashes.
  custom.rotation = Rotation(z=platform_data["rotation"])

  # Get the item's content.
  platform_contents = platform_item.get("content", [])

  # Create the TubeSpot.
  for index, slot in enumerate(platform_data.get("slots", [])):

    # Get the content in the slot (if any).
    content = next((c for c in platform_contents if c["index"] - 1 == index), None)

    # Add the content if any.
    if content:
      # Get the container data for the tube.
      container_data = get_contents_container(content, containers_data)
      # {
      #   "name": "2.0 mL tube",
      #   "description": "Standard 2.0 mL micro-centrifuge tube with hinged lid",
      #   "type": "tube",
      #   "length": 40,
      #   "maxVolume": 2000,
      #   "activeHeight": 2
      # },

      # Check container type.
      assert container_data["type"] == "tube", \
        f"Can't load {container_data['type']}s into a custom platform. Only tubes are supported."

      # Create the tube.
      # "content": [
      #   {
      #     "container": "0.2 mL tube",
      #     "index": 3,
      #     "name": "tube3 (1)",
      #     "tags": [
      #       "target"
      #     ],
      #     "position": {
      #       "x": 25.87785,
      #       "y": 11.90983
      #     },
      #     "volume": 0
      #   }
      # ],
      tube_content = Tube(
        name=content["name"],
        size_x=slot["slotSize"],  # Same as the slot.
        size_y=slot["slotSize"],  # Same as the slot.
        size_z=container_data["length"],
        max_volume=container_data["maxVolume"],
        model=container_data["name"],
        category=container_data["type"]  # "tube"
      )
      # Add "activeHeight" somewhere here.
      # It is needed to get the proper Z coordinate.
      tube_content.active_z = container_data["activeHeight"]
      tube_content.tags = content["tags"]

      # Add liquid to the tracker.
      # TODO: Add liquid classes to our data schemas, even if it is water everywhere for now.
      tube_content.tracker.add_liquid(Liquid.WATER, volume=content["volume"])

      # Get the container and its link.
      link = next(l for l in slot["containers"] if l["container"] == container_data["name"])
      container = container_data

    else:
      # If no content was found in it, try using a default.
      if slot["containers"]:
        # Use the first container data for the slot.
        link = slot["containers"][0]
        container = next(c for c in containers_data if c["name"] == link["container"])
      else:
        # Empty defaults if no containers have been linked.
        link, container  = {}, {}

    # "slots": [
    #  {
    #    "slotName": "Tube3",
    #    "slotPosition": {
    #      "slotX": 25.87785,
    #      "slotY": 11.90983
    #    },
    #    "slotActiveHeight": 0,
    #    "slotSize": 9,
    #    "slotHeight": 10,
    #    "containers": [
    #      {
    #        "container": "0.2 mL tube",
    #        "containerOffsetZ": 0
    #      }
    #    ]
    #  },
    # ],

    # Tube generating function, with arguments fixed by "partial".
    # https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/cell-var-from-loop.html
    make_tube = partial(make_tube_from_slot, container, slot)

    # Make a tube spot from the slot.
    tube_spot = TubeSpot(
      name=slot["slotName"],
      size_x=slot["slotSize"],
      size_y=slot["slotSize"],
      make_tube=make_tube,
      size_z=slot["slotHeight"],
      # Set a default container.
      model=link.get("container", None)
    )
    # Set a default container offset.
    tube_spot.active_z = slot["slotActiveHeight"]

    # Prepare PLR location object for the slot.
    x, y = xy_to_plr(slot["slotPosition"]["slotX"],
                     slot["slotPosition"]["slotY"],
                     platform_data["length"])
    dz = calculate_plr_dz_slot(platform_data, slot, link, container)
    slot_location=Coordinate(x=x, y=y, z=dz)
    # Add the tube spot as a direct child.
    custom.assign_child_resource(tube_spot, location=slot_location)

    # Add a tube to teh spot if a content was found.
    if content:
      # Prepare PLR location object.
      # NOTE: In this case, the content's position is equal to
      #       the position of the slot, which has already been set.
      #       We only need to add the active height here.
      tube_z = tube_content.active_z + link["containerOffsetZ"]
      location=Coordinate(z=tube_z)

      # Add the Tube to the tracker.
      tube_spot.tracker.add_tube(tube_content, commit=True)
      # Add the Tube to the TubeSpot as a child resource.
      # NOTE: This is required, otherwise it does not show up in the deck by name.
      tube_spot.assign_child_resource(tube_content, location=location)

  return custom
