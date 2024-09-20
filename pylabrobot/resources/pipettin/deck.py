"""
Pipettin deck adapter for PLR.

Example:

```python3
from pylabrobot.resources import SilverDeck
from pylabrobot.resources.pipettin.utils import load_defaults

workspace, platforms, containers, tools = load_defaults()

deck = SilverDeck(workspace, platforms, containers)
```

Have fun!
"""

import math
import textwrap
# from typing import Optional, Callable

from pylabrobot.resources import Coordinate, Deck

from .tip_racks import load_ola_tip_rack
from .tube_racks import load_ola_tube_rack, load_ola_custom
from .anchor import load_ola_anchor

from .utils import get_items_platform, create_trash, create_petri_dish, importer_not_implemented

class SilverDeck(Deck):
  """ (Ag)nostic deck object.

    - Discussion: https://forums.pylabrobot.org/t/writing-a-new-backend-agnosticity/844/16
    - Boilerplate code written by Rick.
  """

  platform_importers: dict = {
    "TUBE_RACK": load_ola_tube_rack,
    "CUSTOM": load_ola_custom,
    "TIP_RACK": load_ola_tip_rack,
    "BUCKET": create_trash,
    "PETRI_DISH": create_petri_dish,
    "ANCHOR": load_ola_anchor
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
               default_origin: Coordinate = None,
               offset_origin: bool = False
               ):

    self.workspace = workspace
    self.workspace_items = workspace["items"]
    self.platforms = platforms
    self.containers = containers

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
    self.assign_platforms(workspace, platforms, containers)

  def assign_platforms(self, workspace, platforms, containers, anchors_first=True):
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
      self.assign_platform(item, platform_data, containers)

  def assign_platform(self, platform_item, platform_data, containers):
    # Get importer method.
    platform_type = platform_data["type"]
    importer = self.platform_importers.get(platform_type, importer_not_implemented)
    # Execute the translation.
    platform_resource = importer(
      platform_item=platform_item,
      platform_data=platform_data,
      containers_data=containers
    )

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
        position["x"], position["y"] = self.xy_to_plr(position["x"], position["y"])
        # Generate the location coordinate object for PLR.
        location = Coordinate(**position)

        # Assign as a direct child.
        self.assign_child_resource(platform_resource, location=location)

    # Done!
    return platform_resource

  def summary(self) -> str:
    """ Generate an ASCII summary of the deck.

    Usage:
    >>> print(deck.summary())
    """

    ascii_dck = textwrap.dedent(f"""
    {self.name}: {self.get_size_x()}mm x {self.get_size_y()}mm x {self.get_size_z()}mm (XYZ)
    {draw_ascii_workspace(self.workspace, self.platforms, indent=4)[4:]}
    Origin: {self.location}
    """)

    if self.workspace_padding and self.offset_origin:
      ascii_dck += f"\nPadding: {self.workspace_padding}"

    return ascii_dck

    def __str__(self):
      print(self.summary())

  def xy_to_plr(self, x: float, y: float, workspace_width: float = None, workspace_height: float = None):
    """Convert XY coordinates from top-left origin to bottom-left origin.

    To convert XY coordinates from a coordinate system where the origin is at the top-left
    (with the positive X direction to the right and the positive Y direction towards the bottom) to
    another coordinate system where the origin is at the bottom-left, you can apply the following
    conversion:

    - X coordinate stays the same since both systems have the positive X direction to the right.
    - Y coordinate needs to be flipped. In the top-left-origin system, Y increases downward, while
      in the bottom-left-origin system, Y increases upward.

    Given the width and height of the workspace, you can transform the Y-coordinate as follows:

        New Y-coordinate = height_of_workspace - original_y_coordinate

    Args:
        x (float): X coordinate in the original system (top-left origin, positive to the right).
        y (float): Y coordinate in the original system (top-left origin, positive "downwards").
        workspace_width (optional, float): Width of the workspace.
        workspace_height (optional, float): Height of the workspace.

    Returns:
        tuple: New (x, y) coordinates in the system with the bottom-left origin.
    """

    if workspace_width is None:
      workspace_width = self.get_size_x()
    if workspace_height is None:
      workspace_height = self.get_size_y()

    new_x = x  # X stays the same
    new_y = workspace_height - y  # Flip the Y coordinate

    return new_x, new_y

  def plr_to_xy(self, x: float, y: float, workspace_width: float = None, workspace_height: float = None):
      """Convert XY coordinates from bottom-left origin to top-left origin.

      Inverse function of xy_to_plr, which converts coordinates from the bottom-left origin
      (positive Y upward) back to the top-left origin (positive Y downward).

      - X-coordinate stays the same, since the direction doesn't change in either system.
      - Y-coordinate needs to be inverted by subtracting it from the total workspace height.

      Test:
        foo = (-10, 10)
        bar = deck.xy_to_plr(*foo)
        baz = deck.plr_to_xy(*bar)
        assert foo == baz

      Args:
          x (float): X coordinate in the system with the bottom-left origin.
          y (float): Y coordinate in the system with the bottom-left origin (positive upwards).
          workspace_width (optional, float): Width of the workspace.
          workspace_height (optional, float): Height of the workspace.

      Returns:
          tuple: New (x, y) coordinates in the system with the top-left origin.
      """

      if workspace_width is None:
          workspace_width = self.get_size_x()
      if workspace_height is None:
          workspace_height = self.get_size_y()

      new_x = x  # X stays the same
      new_y = workspace_height - y  # Flip the Y coordinate back to top-left origin

      return new_x, new_y


def draw_ascii_workspace(workspace: dict, platforms: list, downscale_factor: float = 20, width_scaler: float = 2.2, indent:int=0):
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
        |                                        +++++++++++ |
        |                                        +++++++++++ |
        |                      @@@@+++++++++     +++++++++++ |
        |                      @++++++++++++     +++++++++++ |
        |                      +++++++++++++     +++++++++++ |
        |                      +++++++++++++                 |
        |                                                    |
        |      @@@@+++++++++   @@@@+++++++++++++++++++       |
        |      @++++++++++++   @++++++++++++++++++++++       |
        |      +++++++++++++   +++++++++++++++++++++++       |
        '----------------------------------------------------'
        Origin: (000.000, 000.000, 000.000)
    """

    platform_items = sorted(workspace["items"], key=lambda item: item.get("type") != "ANCHOR")

    # Convert workspace dimensions to ASCII grid size (1 char = 20 mm)
    width = math.ceil(width_scaler * workspace["width"] / downscale_factor)
    length = math.ceil(workspace["length"] / downscale_factor)

    # Create an empty grid to represent the workspace
    grid = [[' ' for _ in range(width)] for _ in range(length)]

    # Add the boundaries of the workspace
    for i in range(width):
        grid[0][i] = '-'
        grid[length - 1][i] = '-'
    for i in range(length):
        grid[i][0] = '|'
        grid[i][width - 1] = '|'

    # Corners
    grid[0][0]   = '.'
    grid[0][-1]  = '.'
    grid[-1][0]  = '\''
    grid[-1][-1] = '\''

    # Draw each platform in the workspace
    for item in platform_items:
        platform = next(p for p in platforms if p["name"] == item["platform"])
        platform_width = round(width_scaler * platform['width'] // downscale_factor)
        platform_length = round(platform['length'] // downscale_factor)
        x = round(width_scaler * item['position']["x"] // downscale_factor)
        y = round(item['position']["y"] // downscale_factor)

        # Draw the item as a filled square in the grid
        i_range = range(y, min(y + platform_length, length))
        j_range = range(x, min(x + platform_width, width))
        for i in i_range:
            for j in j_range:
                if grid[i][j] == " ":
                    grid[i][j] = '+'
                if platform.get("type") == "ANCHOR" and (i == i_range[0] or j == j_range[0]):
                    grid[i][j] = '@'

    # Convert grid to a string representation
    result = '\n'.join([indent * ' ' + ''.join(row) for row in grid])
    return result
