"""
Pipettin deck adapter for PLR.

Example:

```python3
from pylabrobot.resources import SilverDeck
from pylabrobot.resources.pipettin.utils import load_defaults

workspace, platforms, containers, tools = load_defaults()

deck = SilverDeck(workspace, platforms, containers, tools)
```

Have fun!
"""

import math
import textwrap
from copy import deepcopy
# from typing import Optional, Callable

from pylabrobot.resources import Coordinate, Deck, Resource, ResourceNotFoundError

from .tip_racks import load_ola_tip_rack
from .tube_racks import load_ola_tube_rack, load_ola_custom
from .anchor import load_ola_anchor

from .utils import get_items_platform, create_trash, create_petri_dish, importer_not_implemented
from newt.translators.utils import xy_to_plr

class SilverDeck(Deck):
  """ (Ag)nostic deck object.

    - Discussion: https://forums.pylabrobot.org/t/writing-a-new-backend-agnosticity/844/16
    - Boilerplate code written by Rick.
  """

  platform_importers: dict = {
    "TIP_RACK": load_ola_tip_rack,
    "TUBE_RACK": load_ola_tube_rack,
    "CUSTOM": load_ola_custom,
    "BUCKET": create_trash,
    "PETRI_DISH": create_petri_dish,
    "ANCHOR": load_ola_anchor
  }

  def __init__(self,
               # Create from workspace and platforms.
               workspace: dict,
               platforms: dict,
               containers: dict,
               tools: dict,
               default_name: str= "silver_deck",
               # TODO: Update default size.
               default_size_x: float = 250,
               default_size_y: float = 350,
               default_size_z: float = 200,
               # TODO: Update default origin.
               default_origin: Coordinate = None,
               offset_origin: bool = False
               ):

    # Save the pipettin objects.
    self._workspace = workspace
    self._platforms = platforms
    self._containers = containers
    self.tools = tools

    # Default origin to zero.
    if default_origin is None:
      default_origin = Coordinate(0, 0, 0)

    # Get the padding.
    self.offset_origin = offset_origin
    self.workspace_padding = workspace.get("padding", None)
    if self.workspace_padding and self.offset_origin:
      # Offset origin by the workspace's padding.
      origin = Coordinate(
        x=self.workspace_padding["left"],
        y=self.workspace_padding["right"],
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
    self.assign_platforms(workspace, platforms, containers, tools)

  def assign_platforms(self, workspace, platforms, containers, tools, anchors_first=True):
    """ Convert platforms to resources and add them to the deck.
    Items are sorted to assign anchors first. This prevents errors when
    an item's anchor has not been assigned yet. This can be disabled
    by setting `anchors_first=False`.
    """
    items = workspace.get("items", [])

    # Sort items with "ANCHOR" type first
    if anchors_first:
      items = sorted(items, key=lambda item: item.get("type") != "ANCHOR")

    for item in items:
      platform_data = get_items_platform(item, platforms)
      # Create a resource from the item.
      # Also add tubes, tips, and other resources in the platform item.
      self.assign_platform(item, platform_data, containers, tools)

  def assign_platform(self, platform_item, platform_data, containers, tools):
    # Get importer method.
    platform_type = platform_data["type"]
    importer = self.platform_importers.get(platform_type, importer_not_implemented)
    # Execute the translation.
    platform_resource = importer(
      deck=self,
      platform_item=platform_item,
      platform_data=platform_data,
      containers_data=containers,
      tools_data=tools,
    )
    # print(f"Assigned {platform_resource.name} to {self.name}.")

    # Assign the translated resource.
    if platform_resource is not None:
      # Check if the item is anchored.
      anchor_name = platform_item.get("snappedAnchor", None)

      if anchor_name is not None:
        # Assign as an anchor's child.
        anchor = self.get_resource(anchor_name)
        anchor.assign_child_resource(platform_resource)

      else:
        # Get the resources' location.
        position = platform_item["position"]
        # Convert position the PLR coordinate system and origin.
        x, y = xy_to_plr(position["x"], position["y"],
                         workspace_height=self.get_size_y())
        # Generate the location coordinate object for PLR.
        location = Coordinate(x, y, position["z"])

        # Assign as a direct child.
        self.assign_child_resource(platform_resource, location=location)

    # Done!
    return platform_resource

  def get_resource(self, name: str, resources_list=None, parent=None, recursing=False) -> Resource:
    """ Returns the resource with the given name, recursively scanning children.

    This method overrides 'get_resource' from the base Deck class.

    Raises:
      ResourceNotFoundError: If the resource is not found.
    """

    if parent is None:
      parent = self
    if resources_list is None:
      resources_list = []

    # print(f"Looking for '{name}' in '{parent.name}'.")
    for child in parent.children:
      if child.name == name:
        # print("Found " + child.name)
        resources_list.append(child)
      if isinstance(child, Resource):
        # print(f"Recursing into {child.name}")
        self.get_resource(name, resources_list, child, True)

    if recursing:
      # Skip checks if recursing.
      return
    elif not resources_list:
      # Raise the standard error if not found.
      msg = f"Resource '{name}' not found after recursion"
      # print(msg)
      raise ResourceNotFoundError(msg)
    if len(resources_list) > 1 and not recursing:
      # Raise a custom error if multiple matches were found.
      msg = f"Multiple resources named '{name}' were found, as children of: '"
      msg += "', '".join([child.parent.name for child in resources_list]) + "'"
      # print(msg)
      raise ResourceNotFoundError(msg)

    # Return the first match.
    # print("Done looking")
    return resources_list[0]

  # Getter methods for pipettin data objects.
  @property
  def workspace(self):
    return deepcopy(self._workspace)
  @property
  def platforms(self):
    return deepcopy(self._platforms)
  @property
  def containers(self):
    return deepcopy(self._containers)
  @property
  def workspace_items(self):
    return deepcopy(self._workspace["items"])

  def summary(self, **kwargs) -> str:
    """ Generate an ASCII summary of the deck.

    Usage:
    >>> print(deck.summary())
    """

    kwargs.setdefault("indent", 4)

    ascii_dck = textwrap.dedent(f"""
    {self.name}: {self.get_size_x()}mm x {self.get_size_y()}mm x {self.get_size_z()}mm (XYZ)
    {draw_ascii_workspace(self.workspace, self.platforms, **kwargs)[kwargs["indent"]:]}
    Origin: {self.location}
    """)

    if self.workspace_padding and self.offset_origin:
      ascii_dck += f"\nPadding: {self.workspace_padding}"

    return ascii_dck

  def __str__(self):
    return self.summary()

def draw_ascii_workspace(
  workspace: dict, platforms: list,
  downscale_factor: float = 20,
  width_scaler: float = 2.2,
  anchor_char: str = "@",
  item_char: str = "¬",
  empty_char: str = " ",
  indent:int = 0):
  """
  Generates an ASCII art representation of platform items in a workspace.

  Args:
      downscale_factor (float): Factor used to scale the units down.

  Returns:
      str: ASCII art representation of the workspace and platform items.

  Example:
      MK3 Baseplate: 488mm x 290mm x 8mm (XYZ)
      .----------------------------------------------------.
      |                                                    |
      |                                                    |
      |                                                    |
      |                                        ¬¬¬¬¬¬¬¬¬¬¬ |
      |                                        ¬¬¬¬¬¬¬¬¬¬¬ |
      |                      @@@@¬¬¬¬¬¬¬¬¬     ¬¬¬¬¬¬¬¬¬¬¬ |
      |                      @¬¬¬¬¬¬¬¬¬¬¬¬     ¬¬¬¬¬¬¬¬¬¬¬ |
      |                      ¬¬¬¬¬¬¬¬¬¬¬¬¬     ¬¬¬¬¬¬¬¬¬¬¬ |
      |                      ¬¬¬¬¬¬¬¬¬¬¬¬¬                 |
      |                                                    |
      |      @@@@¬¬¬¬¬¬¬¬¬   @@@@¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬       |
      |      @¬¬¬¬¬¬¬¬¬¬¬¬   @¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬       |
      |      ¬¬¬¬¬¬¬¬¬¬¬¬¬   ¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬¬       |
      '----------------------------------------------------'
      Origin: (000.000, 000.000, 000.000)
  """

  platform_items = sorted(workspace["items"], key=lambda item: item.get("type") != "ANCHOR")

  # Convert workspace dimensions to ASCII grid size (1 char = 20 mm)
  width = math.ceil(width_scaler * workspace["width"] / downscale_factor)
  length = math.ceil(workspace["length"] / downscale_factor)

  # Create an empty grid to represent the workspace
  grid = [[empty_char for _ in range(width)] for _ in range(length)]

  # Add the boundaries of the workspace
  for i in range(width):
    grid[0][i] = "-"
    grid[length - 1][i] = "-"
  for i in range(length):
    grid[i][0] = "|"
    grid[i][width - 1] = "|"

  # Corners
  grid[0][0]   = "."
  grid[0][-1]  = "."
  grid[-1][0]  = "'"
  grid[-1][-1] = "'"

  # Draw each platform in the workspace
  for item in platform_items:
    platform = next(p for p in platforms if p["name"] == item["platform"])
    platform_width = round(width_scaler * platform["width"] // downscale_factor)
    platform_length = round(platform["length"] // downscale_factor)
    x = round(width_scaler * item["position"]["x"] // downscale_factor)
    y = round(item["position"]["y"] // downscale_factor)

    # Draw the item as a filled square in the grid
    i_range = range(y, min(y + platform_length, length))
    j_range = range(x, min(x + platform_width, width))
    for i in i_range:
      for j in j_range:
        if platform.get("type") == "ANCHOR" and (i == i_range[0] or j == j_range[0]):
          # Mark anchor corners.
          grid[i][j] = anchor_char
        elif grid[i][j] == empty_char:
          # Mark platform area.
          grid[i][j] = item_char

  # Convert grid to a string representation
  result = "\n".join([indent * " " + "".join(row) for row in grid])
  return result
