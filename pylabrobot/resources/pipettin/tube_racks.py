from abc import ABCMeta
from typing import Optional, Callable, List, Union, Sequence, cast, Tuple

from pylabrobot.resources.liquid import Liquid
#from pylabrobot.resources.plate import Plate
from pylabrobot.resources.resource import Resource, Coordinate, Rotation
from pylabrobot.resources.itemized_resource import ItemizedResource
from pylabrobot.resources.utils import create_ordered_items_2d

from newt.translators.utils import rack_to_plr_dxdy, calculate_plr_dz_tube
from newt.utils import guess_shape
from .utils import get_contents_container
from .tubes import Tube, TubeSpot

class TubeRack(ItemizedResource[TubeSpot], metaclass=ABCMeta):
  """ Abstract base class for Tube Rack resources.

  Boilerplate code copied from the 'Plate', 'TubeRack', and 'TipRack' classes.

  In pipettin the math for the top height and fitting height of a tube in a tip rack should be:

  1. (+) Workspace's Z origin (usually 0). Get this from the Deck.
  2. (+) Platform's Z position: usually 0 for all, can be adjusted. Get this from the rack's
         location.
  3. (+) Platform's activeHeight (i.e. tube slot Z position - not the slot): height of the surface
         that supports the tubes. This is not defined in PLR.
  4. (+) Container's offset: Distance from the tube's external bottom to the tube slot, usually
         negative (i.e. how much the tube "sinks" into the tube slot). This is also undefined in
         PLR. However, in combination with (3), the equivalent PLR tube *spot* location can be
         calculated: (3) - (4) = TipSpot's Z
  5. (+) Total tube's length. Available in the Tube object.
         This is now the absolute top Z coordinate of the tube.
  6. (-) Tube's activeHeight. The distance from the external bottom of the tube to its internal
         bottom. Use with (4) and (5) to obtain the Z coordinate at which the tube is well fitted.

  In summary, the TubeSpot's Z coordinate should be equal to:
      `plat_active_height - container_z_offset`

  """

  def __init__(
    self,
    name: str,
    size_x: float,
    size_y: float,
    size_z: float,
    ordered_items: Optional[List[List[TubeSpot]]] = None,
    model: Optional[str] = None,
    # TODO: Merge upstream.
    # num_items_x: Optional[int] = None,
    # num_items_y: Optional[int] = None,
    category: str = "rack",
    compute_volume_from_height: Optional[Callable[[float], float]] = None,
    # Fill with tubes.
    with_tubes: bool = False
  ):
    """ Initialize a Tube Rack resource.

    Args:
      name: Name of the rack.
      size_x: Size of the rack in the x direction.
      size_y: Size of the rack in the y direction.
      size_z: Size of the rack in the z direction.
      dx: The distance between the start of the rack and the center of the first tube (A1) in the x
        direction.
      dy: The distance between the start of the rack and the center of the first tube (A1) in the y
        direction.
      dz: The distance between the start of the rack and the center of the first tube (A1) in the z
        direction.
      num_items_x: Number of tubes in the x direction.
      num_items_y: Number of tubes in the y direction.
      tube_size_x: Size of the tubes in the x direction.
      tube_size_y: Size of the tubes in the y direction.
      compute_volume_from_height: ???
    """

    if with_tubes:
      msg = "Filling a new TubeRack with tubes on startup is not implemented yet (with_tubes=True)."
      raise NotImplementedError(msg)

    super().__init__(
      name=name,
      size_x=size_x,
      size_y=size_y,
      size_z=size_z,
      ordered_items=ordered_items,
      model=model,
      # TODO: Merge upstream.
      # num_items_x=num_items_x,
      # num_items_y=num_items_y,
      category=category)

    # TODO: Figure out if this is important,
    #       and implement the missing methods.
    # if items is not None and len(items) > 0:
    #   if with_tubes:
    #     self.fill()
    #   else:
    #     self.empty()

    self._compute_volume_from_height = compute_volume_from_height

  def compute_volume_from_height(self, height: float) -> float:
    """ Compute the volume of liquid in a tube from the height of the liquid.

    Args:
      height: Height of the liquid in the tube.

    Returns:
      The volume of liquid in the tube.

    Raises:
      NotImplementedError: If the plate does not have a volume computation function.
    """

    if self._compute_volume_from_height is None:
      raise NotImplementedError("compute_volume_from_height not implemented.")

    return self._compute_volume_from_height(height)

  def assign_child_resource(
    self,
    resource: Resource,
    location: Optional[Coordinate],
    reassign: bool = True
  ):

    assert location is not None, "Location in the tube rack must be specified."

    return super().assign_child_resource(resource, location=location, reassign=reassign)

  # TODO: Should I override these?
  # def unassign_child_resource(self, resource):
  #   return super().unassign_child_resource(resource)
  # def serialize(self):
  #   return super().serialize()

  def __repr__(self) -> str:
    return (f"{self.__class__.__name__}(name={self.name}, size_x={self._size_x}, "
            f"size_y={self._size_y}, size_z={self._size_z}, location={self.location})")

  @staticmethod
  def _occupied_func(item: TubeSpot):
    return "U" if item.has_tube() else "-"

  def get_tube(self, identifier: Union[str, int]) -> Tube:
    """ Get the item with the given identifier.

    NOTE: I think that the "get_item" method in "well plates"
    returns the resource directly. Here there may be an
    intermediary "spot" item, thus the difference from
    "return super().get_item(identifier)".
    """
    return super().get_item(identifier).get_tube()

  def get_tubes(self, identifier: Union[str, Sequence[int]]) -> List[Tube]:
    """ Get the tubes with the given identifier.
    NOTE: This differs from the method in "well plates". See note in "get_tube".
    """
    return [ts.get_tube() for ts in super().get_items(identifier)]

  def __getitem__(self, identifier):
    """Overrides '[]' from ItemizedResource.
    This is needed to return tubes instead of TubeSpots.
    """
    tube_spots = super().__getitem__(identifier)
    return [ts.get_tube() for ts in tube_spots]

  # TODO: Should I port "set_tip_state" from "TipRack" too?
  #       Fist I need to figure out how "make_tip" works.

  # TODO: Should I add "empty" from "TipRack" here?

  # TODO: Should I add "fill" from "TipRack" here?

  def get_all_tubes(self) -> List[Tube]:
    """ Get all tubes in the tube rack. """
    return [ts.get_tube() for ts in super().get_all_items() if ts.has_tube()]

  def set_tube_liquids(
    self,
    liquids: Union[
      List[List[Tuple[Optional["Liquid"], Union[int, float]]]],
      List[Tuple[Optional["Liquid"], Union[int, float]]],
      Tuple[Optional["Liquid"], Union[int, float]]]
  ) -> None:
    """ Update the volume in the volume tracker of each tube in the rack.

    Based on "set_well_liquids" in the "Plate" class.

    Args:
      volumes: A list of volumes, one for each tube in the rack. The list can be a list of lists,
        where each inner list contains the volumes for each tube in a column.  If a single float is
        given, the volume is assumed to be the same for all tubes. Volumes are in uL.

    Raises:
      ValueError: If the number of volumes does not match the number of tubes in the rack.

    # TODO: Update this irrelevant example from "Plate".
    Example:
      Set the volume of each tube in a 96-tube plate to 10 uL.

      >>> plate = Plate("plate", 127.0, 86.0, 14.5, num_items_x=12, num_items_y=8)
      >>> plate.update_tube_volumes(10)
    """

    if isinstance(liquids, tuple):
      liquids = [liquids] * self.num_items
    elif isinstance(liquids, list) and all(isinstance(column, list) for column in liquids):
      # mypy doesn't know that all() checks the type
      liquids = cast(List[List[Tuple[Optional["Liquid"], float]]], liquids)
      liquids = [list(column) for column in zip(*liquids)] # transpose the list of lists
      liquids = [volume for column in liquids for volume in column] # flatten the list of lists

    if len(liquids) != self.num_items:
      raise ValueError(f"Number of liquids ({len(liquids)}) does not match number of tubes "
                       f"({self.num_items}) in tube rack '{self.name}'.")

    for i, (liquid, volume) in enumerate(liquids):
      tube = self.get_tube(i)
      tube.tracker.set_liquids([(liquid, volume)]) # type: ignore

  def disable_volume_trackers(self) -> None:
    """ Disable volume tracking for all tubes in the rack. """

    for tube in self.get_all_items():
      tube.tracker.disable()

  def enable_volume_trackers(self) -> None:
    """ Enable volume tracking for all tubes in the rack. """

    for tube in self.get_all_items():
      tube.tracker.enable()

def load_ola_tube_rack(
  deck: "SilverDeck",
  platform_item: dict,
  platform_data: dict,
  tools_data: dict,
  containers_data: list) -> TubeRack:

  # TODO: Find a way to avoid defaulting to the first associated container.
  # NOTE: Perhaps PLR does not consider having different tubes for the same tube rack.
  linked_containers = platform_data["containers"]
  compatible_tubes = []
  for link in linked_containers:
    container_data = get_contents_container(link, containers_data)
    # Get fitting depths.
    compatible_tube = Tube(
      # Use the container name here, not important.
      name=container_data["name"],
      size_x=platform_data["wellDiameter"],
      size_y=platform_data["wellDiameter"],
      size_z=container_data["length"],
      max_volume=container_data["maxVolume"],
      model=container_data["name"],
      category=container_data["type"]
    )
    compatible_tube.active_z = container_data["activeHeight"]
    compatible_tubes.append({
      "content": compatible_tube,
      # Save the "containerOffsetZ" here, to restore it later on export.
      "link": link
    })

  # NOTE: I need to create this function here, it is required by "TubeSpot" later on.
  def make_pew_tube():
    return compatible_tubes[0]["content"]

  # First spot offsets.
  # TODO: Override "dz"/default_link the the appropriate offset for each tube.
  default_link = linked_containers[0]
  default_container_data = get_contents_container(link, containers_data)
  # Prepare parameters for "create_ordered_items_2d".
  dx, dy = rack_to_plr_dxdy(platform_data)
  # NOTE: According to Rick and the sources, the "Z of a TipSpot" is the "Z of the tip's tip" when
  # the tip is in its spot, relative to the base of the tip rack (I guessed this last part).
  default_dz = calculate_plr_dz_tube(platform_data, default_link, default_container_data)

  # Use the helper function to create a regular 2D-grid of tube spots.
  ordered_items=create_ordered_items_2d(
    # NOTE: Parameters for "create_ordered_items_2d".
    klass=TubeSpot,  # NOTE: the TipRack uses "TipSpot" class here. Should I use "Tube"?
    num_items_x=platform_data["wellsColumns"],
    num_items_y=platform_data["wellsRows"],
    # item_dx: The size of the items in the x direction
    item_dx=platform_data["wellSeparationX"],
    # item_dy: The size of the items in the y direction
    item_dy=platform_data["wellSeparationY"],
    # dx: The X coordinate of the bottom left corner for items in the left column.
    # dy: The Y coordinate of the bottom left corner for items in the top row.
    # dz: The z coordinate for all items.
    dx=dx, dy=dy, dz=default_dz,
    # NOTE: Additional keyword arguments are passed to the "klass" constructor.
    # Set the dimensions of the tube spot to the diameter of the well.
    size_x=platform_data["wellDiameter"],
    size_y=platform_data["wellDiameter"],
    # size_z=platform_data["height"]
    # NOTE: The TubeSpot class will receive this argument (through kwargs) to create its tubes.
    #       Note that this is not needed for "wells", as there are no "well spots" in PLR.
    #       There are however, "tube spots" in pipettin, which I don't know how to accommodate.
    make_tube=make_pew_tube

    # XY distance between adjacent items in the grid.
    # item_size_x=platform_data["wellSeparationX"],
    # item_size_y=platform_data["wellSeparationY"],
  )

  # Set "active_z" in the default spots to "containerOffsetZ".
  for spot in ordered_items.values():
    spot.active_z = default_link["containerOffsetZ"]

  # Guess the shape of the platform.
  size_x, size_y, shape = guess_shape(platform_data)

  # Create the TubeRack instance.
  tube_rack_item = TubeRack(
      name=platform_item["name"],
      size_x=size_x,
      size_y=size_y,
      size_z=platform_data["height"],
      category=platform_data.get("type", None), # Optional in PLR.
      model=platform_data["name"], # Optional.
      ordered_items=ordered_items,
      # Don't fill the rack with tubes.
      # Tubes would otherwise be created and added to the rack, using "make_pew_tube".
      with_tubes=False,
  )
  # Save the platform's active height.
  # This will help recover some information later.
  tube_rack_item.active_z = platform_data["activeHeight"]
  # Save the platform's shape.
  tube_rack_item.shape = shape
  # Compatible children.
  tube_rack_item.compatibles = compatible_tubes
  # Locked state.
  tube_rack_item.locked = platform_item.get("locked", None)
  # TODO: Add rotation, even though it wont be usable and cause crashes.
  tube_rack_item.rotation = Rotation(z=platform_data["rotation"])

  # Add tubes in the platform item, if any.
  platform_contents = platform_item.get("content", [])
  for content in platform_contents:
    # Get the tube's container data.
    container_data = get_contents_container(content, containers_data)

    # Create the Tube.
    new_tube = Tube(
      # TODO: Names must be unique. This should be checked for tips and tubes.
      name=content["name"],
      # TODO: Reconsider setting "size_x" and "size_y" to something else.
      size_x=platform_data["wellDiameter"],
      size_y=platform_data["wellDiameter"],
      size_z=container_data["length"],
      max_volume=container_data["maxVolume"],
      model=container_data["name"],
      category=container_data["type"]  # "tube"
    )
    # Set "activeHeight" for the tube.
    # It is needed to get the proper Z coordinate.
    new_tube.active_z = container_data["activeHeight"]
    # Save tags.
    new_tube.tags = content["tags"]

    # Add liquid to the tracker.
    # TODO: Add liquid classes to our data schemas, even if it is water everywhere for now.
    new_tube.tracker.add_liquid(Liquid.WATER, volume=content["volume"])

    # Get the tube's position indexes.
    # NOTE: "i" for "Y/rows", and "j" for "X/columns".
    i, j = content["position"]["row"]-1, content["position"]["col"]-1
    # Get the TubeSpot.
    tube_spot: TubeSpot = tube_rack_item.get_item((i, j))

    # Get the offset for this specific tip model.
    container_link = next(l for l in linked_containers if l["container"] == container_data["name"])

    # Override the default "active_z" set before.
    tube_spot.active_z = container_link["containerOffsetZ"]

    # Set the spot's location to the (lowest) pipetting height.
    tube_spot.location.z = calculate_plr_dz_tube(platform_data, container_link, container_data)

    # Add the Tube to the tracker.
    tube_spot.tracker.add_tube(new_tube, commit=True)
    # Add the Tube to the TubeSpot as a child resource.
    # NOTE: This is required, otherwise it does not show up in the deck by name.
    tube_spot.assign_child_resource(new_tube, location=Coordinate(0,0,0))

  return tube_rack_item
