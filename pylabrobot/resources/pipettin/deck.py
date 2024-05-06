import textwrap
# from typing import Optional, Callable

from pylabrobot.resources import Coordinate, Deck, Trash

from pylabrobot.resources.pipettin.tip_racks import create_tip_rack
from pylabrobot.resources.pipettin.tube_racks import create_tube_rack

def not_implemented(*args, **kwargs):
  raise NotImplementedError("Method not implemented.")

def create_trash(platform_item, platform_data, *args):
  trash = Trash(
    name=platform_item.get("name"),
    size_x=platform_data.get("width"),
    size_y=platform_data.get("length"),
    size_z=platform_data.get("height"),
    category=platform_data.get("type", None), # Optional in PLR.
    model=platform_data.get("name", None) # Optional in PLR (not documented in Resource).
  )

  return trash

class SilverDeck(Deck):
  """ (Ag)nostic deck object.

  Boilerplate code written by Rick: https://forums.pylabrobot.org/t/writing-a-new-backend-agnosticity/844/16
  """

  platform_importers: dict = {
    "TUBE_RACK": create_tube_rack,
    "TIP_RACK": create_tip_rack,
    "BUCKET": create_trash,
    "CUSTOM": not_implemented,
    "PETRI_DISH": not_implemented,
    "ANCHOR": not_implemented
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
        x=padding.get("left"),
        y=padding.get("right"),
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
      # resource_assigned_callback = resource_assigned_callback,
      # resource_unassigned_callback = resource_unassigned_callback,
      origin = origin)

    # Load platform items.
    self.assign_platforms(workspace, platforms, containers)

  def assign_platforms(self, workspace, platforms, containers):
    """ Convert platforms to resources and add them to the deck. """
    items = workspace.get("items", [])
    for item in items:
      platform_data = self.get_items_platform(item, platforms)
      # Create a resource from the item.
      platform_resource = self.assign_platform(item, platform_data)
      # Add tubes, tips, and other resources in the platform item.
      self.assign_contents(platform_resource, item, platform_data, containers)

  def assign_platform(self, platform_item, platform_data):
    # Get importer method.
    platform_type = platform_data.get("type")
    importer = self.platform_importers[platform_type]
    # Execute the translation.
    platform_resource = importer(
      platform_item=platform_item,
      platform_data=platform_data
    )
    # Get the resources' location.
    position = platform_item.get("position")
    location = Coordinate(**position)
    # Assign the translated resource.
    self.assign_child_resource(platform_resource, location=location)
    # Done!
    return platform_resource

  def assign_contents(self, platform_resource, platform_item, platform_data, containers):

    platform_contents = platform_item.get("contents")
    for content in platform_contents:
      content_position = content.get("position")
      container_data = self.get_contents_container(content, containers)
      content_resource = content
      platform_resource.assign_child_resource(content_resource)

    raise NotImplementedError("Have't written this part yet.")

  @staticmethod
  def get_items_platform(item, platforms):
    platform_data = next(x for x in platforms if x["name"] == item.get("platform"))
    return platform_data

  @staticmethod
  def get_contents_container(content, containers):
    container_data = next(x for x in containers if x["name"] == content.get("container"))
    return container_data

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
