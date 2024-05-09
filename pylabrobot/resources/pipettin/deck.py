"""
Pipettin deck adapter for PLR.

Example:

```python3
from pylabrobot.resources import SilverDeck
from pylabrobot.resources.pipettin.utils import load_defaults

workspace, platforms, containers = load_defaults()

deck = SilverDeck(workspace, platforms, containers)
```

Have fun!
"""

import textwrap
# from typing import Optional, Callable

from pylabrobot.resources import Coordinate, Deck

from pylabrobot.resources.pipettin.tip_racks import load_ola_tip_rack
from pylabrobot.resources.pipettin.tube_racks import load_ola_tube_rack, load_ola_custom

from .utils import get_items_platform, create_trash, create_petri_dish

def importer_not_implemented(platform_item, platform_data, containers_data, *args, **kwargs):
  print("Method not implemented for platform type: " + platform_data["type"])
  # raise NotImplementedError("Method not implemented for platform type: " + platform_data["type"])

class SilverDeck(Deck):
  """ (Ag)nostic deck object.

  Boilerplate code written by Rick: https://forums.pylabrobot.org/t/writing-a-new-backend-agnosticity/844/16
  """

  platform_importers: dict = {
    "TUBE_RACK": load_ola_tube_rack,
    "CUSTOM": load_ola_custom,
    "TIP_RACK": load_ola_tip_rack,
    "BUCKET": create_trash,
    "PETRI_DISH": create_petri_dish,
    "ANCHOR": importer_not_implemented
  }

  def __init__(self,
               # Create from workspace and platforms.
               workspace: dict,
               platforms: dict,
               containers: dict,
               default_name: str= "silver_deck",
               # TODO: Update default size.
               default_size_x: float = 250,
               default_size_y: float = 350,
               default_size_z: float = 200,
               # TODO: Update default origin.
               default_origin: Coordinate = Coordinate(0, 0, 0)
               # TODO: Update default trash location.
               #trash_location: Coordinate = Coordinate(x=0.0, y=0.0, z=0.0),
               #no_trash: bool = True,
               # TODO: Check if it is important to override these callback methods.
               #resource_assigned_callback: Optional[Callable] = None,
               #resource_unassigned_callback: Optional[Callable] = None
               ):

    # Parse origin from padding.
    padding = workspace.get("padding", None)
    if padding:
      origin = Coordinate(
        x=padding["left"],
        y=padding["right"],
        z=default_origin.z
      )
    else:
      origin = default_origin

    # Run init from the base Deck class.
    super().__init__(
      name = workspace.get("name", default_name),
      size_x = workspace.get("width", default_size_x),
      size_y = workspace.get("length", default_size_y),
      size_z = workspace.get("height", default_size_z),
      origin = origin)

    # Load platform items.
    self.assign_platforms(workspace, platforms, containers)

  def assign_platforms(self, workspace, platforms, containers):
    """ Convert platforms to resources and add them to the deck. """
    items = workspace.get("items", [])
    for item in items:
      platform_data = get_items_platform(item, platforms)
      # Create a resource from the item.
      # Also add tubes, tips, and other resources in the platform item.
      self.assign_platform(item, platform_data, containers)

  def assign_platform(self, platform_item, platform_data, containers):
    # Get importer method.
    platform_type = platform_data["type"]
    importer = self.platform_importers[platform_type]
    # Execute the translation.
    platform_resource = importer(
      platform_item=platform_item,
      platform_data=platform_data,
      containers_data=containers
    )
    # Get the resources' location.
    position = platform_item["position"]
    location = Coordinate(**position)

    # Assign the translated resource.
    if platform_resource is not None:
      self.assign_child_resource(platform_resource, location=location)

    # Done!
    return platform_resource

  def summary(self) -> str:
    """ Get a summary of the deck.

    >>> print(deck.summary())

    TODO: <write some printable ascii representation of the deck's current layout>
    """

    ascii_dck = textwrap.dedent(f"""
      Deck: {self.get_size_x()}mm x {self.get_size_y()}mm x {self.get_size_z()}mm (XYZ)

      +---------------------+
      |                     |
      |        ....         |
      |                     |
      +---------------------+
    """)

    return ascii_dck
