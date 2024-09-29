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

import textwrap
from copy import deepcopy
# PLR-native imports.
from pylabrobot.resources import Coordinate, Deck, Resource, ResourceNotFoundError
# Pipettin-PLR imports.
from .tip_racks import load_ola_tip_rack
from .tube_racks import load_ola_tube_rack
from .custom_racks import load_ola_custom
from .anchor import load_ola_anchor, Anchor
from .utils import get_items_platform, create_trash, create_petri_dish, importer_not_implemented
# Pipettin imports.
from newt.translators.utils import xy_to_plr
from newt.translators.plr import deck_to_db
from newt.utils import draw_ascii_workspace
from piper.datatools.datautils import load_objects

pipettin_db_url = \
  "https://gitlab.com/pipettin-bot/pipettin-gui/-/raw/develop/api/src/db/defaults/databases.json"

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
               workspace: dict = None,
               platforms: dict = None,
               containers: dict = None,
               tools: dict = None,
               # Alternatively, import them from a DB.
               db: dict = None,
               db_name = "pipettin",
               workspace_name: str = None,
               # TODO: Update defaults.
               default_name: str= "silver_deck",
               default_size_x: float = 250,
               default_size_y: float = 350,
               default_size_z: float = 200,
               # TODO: Update default origin.
               default_origin: Coordinate = None,
               offset_origin: bool = False,
               # Subset platforms on load.
               subset_platforms=True
               ):

    if db:
      workspace, platforms, containers, tools = self.load_objects(
        db, db_name, workspace_name,
        workspace, platforms, containers, tools,
        subset_platforms
      )

    # Save the pipettin objects.
    if workspace is None:
      raise ValueError("workspace or database details not provided.")
    if platforms is None:
      raise ValueError("platforms or database details not provided.")
    if containers is None:
      raise ValueError("containers or database details not provided.")
    if tools is None:
      raise ValueError("tools or database details not provided.")
    self._workspace = workspace
    self._platforms = platforms
    self._containers = containers
    self.tools = tools

    # Default origin to zero.
    if default_origin is None:
      default_origin = Coordinate(0, 0, 0)

    # Get the padding.
    self.offset_origin = offset_origin
    self.padding = workspace.get("padding", None)
    if self.padding and self.offset_origin:
      # Offset origin by the workspace's padding.
      origin = Coordinate(
        x=self.padding["left"],
        y=self.padding["right"],
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

  def load_objects(self, db_location, db_name, workspace_name: str,
                   workspace, platforms, containers, tools, subset_platforms = True):
    # Load the database.
    db = load_objects(db_location)[db_name]

    # Get the workspace and discard its thumbnail.
    if workspace is None:
      if workspace_name is None:
        raise ValueError("workspace_name must be provided, and can't be None.")
      workspace = next(w for w in db["workspaces"] if w["name"] == workspace_name)
    if "thumbnail" in workspace:
      del workspace["thumbnail"]

    # Get all platforms and containers.
    if platforms is None:
      if subset_platforms:
        workspace_items = workspace.get("items", [])
        platforms_in_workspace = [item["platform"] for item in workspace_items]
        platforms = [p for p in db["platforms"] if p["name"] in platforms_in_workspace]
      else:
        platforms = db["platforms"]

    # Get all containers.
    if containers is None:
      containers = db["containers"]

    # Get all tools.
    if tools is None:
      tools = db["tools"]

    return workspace, platforms, containers, tools

  def serialize(self):
    return {
      **super().serialize(),
      "padding": self.padding
    }

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

    # Assign the translated resource.
    if platform_resource is not None:
      # Check if the item is anchored.
      anchor_name = platform_item.get("snappedAnchor", None)

      if anchor_name is not None:
        # Assign as an anchor's child.
        anchor: Anchor = self.get_resource(anchor_name)
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

  def __getitem__(self, item):
    """Override the indexer operator "[]" to get children with a simpler syntax."""
    if isinstance(item, int):
      return self.children[item]
    return self.get_resource(item)

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

    for child in parent.children:
      if child.name == name:
        resources_list.append(child)
      if isinstance(child, Resource):
        self.get_resource(name, resources_list, child, True)

    if recursing:
      # Skip checks if recursing.
      return
    elif not resources_list:
      # Raise the standard error if not found.
      msg = f"Resource '{name}' not found after recursion"
      raise ResourceNotFoundError(msg)
    if len(resources_list) > 1 and not recursing:
      # Raise a custom error if multiple matches were found.
      msg = f"Multiple resources named '{name}' were found, as children of: '"
      msg += "', '".join([child.parent.name for child in resources_list]) + "'"
      raise ResourceNotFoundError(msg)

    # Return the first match.
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

    d = self.serialize()
    db = deck_to_db(d)
    workspace = db["workspaces"][0]
    platforms = db["platforms"]

    ascii_workspace = draw_ascii_workspace(workspace, platforms, **kwargs)[kwargs["indent"]:]

    ascii_dck = textwrap.dedent(f"""
    {self.name}: {self.get_size_x()}mm x {self.get_size_y()}mm x {self.get_size_z()}mm (XYZ)
    {ascii_workspace}
    Origin: {self.location}
    """)

    if self.padding and self.offset_origin:
      ascii_dck += f"\nPadding: {self.padding}"

    print(ascii_dck)

def make_silver(
  db_location = pipettin_db_url,
  workspace_name = "Basic Workspace",
  empty=False,
  ):
  # Load objects.
  db = load_objects(db_location)
  workspace = next(w for w in db["pipettin"]["workspaces"] if w["name"] == workspace_name)
  # Remove items.
  if empty:
    workspace["items"] = []
  # Instantiate the deck object.
  deck = SilverDeck(
    db=db,
    workspace=workspace,
    subset_platforms=False
  )

  return deck
