import math
from abc import ABCMeta
from typing import Optional, Callable, List, Union, Sequence, cast, Any, Dict, Tuple

from pylabrobot.serializer import deserialize
from pylabrobot.resources.container import Container
from pylabrobot.resources.liquid import Liquid
#from pylabrobot.resources.plate import Plate
from pylabrobot.resources.resource import Resource, Coordinate
from pylabrobot.resources.itemized_resource import ItemizedResource
from pylabrobot.resources.utils import create_ordered_items_2d

from newt.translators.utils import rack_to_plr_dxdydz, xy_to_plr, guess_shape
from .utils import get_contents_container

# TODO: There is already a "Tube" class. Try integrating it to the one below.
# from pylabrobot.resources.tube import Tube

class TubeLid:
  """Small helper object to hold the state of the lid of a particular tube."""
  is_open: bool = False
  has_lid: bool = True
  # NOTE: There are many types of tube lids:
  #       "hinge" "screw" "cork" "rubber_cap" "vial_stopper" "none"
  lid_type: str = "hinged"

  def __init__(self, lid_type, is_open: False) -> None:

    self.lid_type = lid_type

    if self.lid_type is None:
      self.has_lid = False
      self.is_open = True
    else:
      self.has_lid = True
      self.is_open = is_open

  def __bool__(self):
    """Shortcut to evaluate the trueness of a lid.

    If there is no lid, this will be true. If there is a lid, and it is open, this will be true too.

    It will be false only when there is a lid and it is not open.
    """
    return self.is_open

class ConeBottomShape:
  """Cone-Bottom shape level calculations.

  Note that the unit's dimensions must be compatible for the output to make sense.
  If using microliters, which are cubic millimeters, the output will be in millimeters.
  Use other units under your own risk!

  Refs:
    - https://www.omnicalculator.com/construction/tank-volume
    - https://handling-solutions.eppendorf.com/sample-handling/mix-shake/principles/detailview-principles/news/dipping-your-thermometer-into-your-sample/
  """
  # Min height / base height for pipetting.
  min_height = 0.2
  wall_width = 1.1
  # Bottom.
  sphere_r = 3.6/2
  halfsphere_vol = ((4/3) * math.pi * sphere_r**3) / 2
  # Cone.
  cone_length=17.8
  cone_r_minor=3.6/2
  cone_r_major=8.7/2
  wall_angle = math.atan((cone_r_major - cone_r_minor) / cone_length)
  # Cylinder.
  cyl_length = 20.0 - 2.0
  cyl_r = 8.7/2
  cyl_vol = math.pi * cyl_r**2 * cyl_length
  # Whole tube.
  max_volume = 1500

  def __init__(self) -> None:
    self.trunc_vol = self.cone_volume(self.wall_angle, self.cone_r_minor)
    self.cone_vol = self.cone_volume(self.wall_angle, self.cone_r_major) - self.trunc_vol

  def level(self, volume):
    """Liquid level in the container, given a volume.

    Args:
        volume (float): Volume in the container.

    Returns:
        float: Height of the liquid level occupying the container.
    """
    if volume > self.max_volume:
      raise ValueError("level: The provided volume is greater than the shapes's maximum volume.")

    # Height trackers.
    height = 0.0

    # Stage 0: Tube bottom.
    # ¿At 1.1 mm from the external bottom?
    if volume <= self.halfsphere_vol:
      return min(self.min_height, self.sphere_r)
    else:
      volume -= self.halfsphere_vol
      height += self.sphere_r

    # Stage 1: Conical.
    if volume <= self.cone_vol:
      level = self.cone_level(volume + self.trunc_vol, self.wall_angle)
      level -= self.cone_height(self.wall_angle, self.cone_r_minor)
      return level
    else:
      volume -= self.cone_vol
      height += self.cone_length

    # Stage 1: Cylindrical.
    if volume <= self.cyl_vol:
      level = volume / (math.pi * self.cyl_r**2)
      return level
    else:
      raise ValueError("level: The provided volume is greater than the shapes's maximum volume.")
      # volume -= self.cyl_vol
      # height += self.cyl_length

  @staticmethod
  def cone_height(a, r):
    """Height of a cone from its radius and wall angle.

    Derivation: math.tan(a) = r / h

    Args:
        a (float): Wall angle in radians.
        r (float): Cone radius.

    Returns:
        float: Cone height.
    """
    h = r / math.tan(a)
    return h

  def cone_volume(self, a, r):
    """Volume of a cone given its wall angle and radius.

    Args:
        a (float): Wall angle in radians.
        r (float): Cone radius.

    Returns:
        float: Cone volume.
    """
    h = self.cone_height(a, r)
    vol = (1/3) * math.pi * (r**2) * h
    return vol

  def cone_level(self, vol: float, a: float):
    """Calculate the level of a liquid in a conical container given the volume and the cone's wall angle.

    Derivation:
      math.tan(a) = r / h
      r = math.tan(a) * h
      V = (1/3) * math.pi * (r**2) * h
      V = (1/3) * math.pi * ( (math.tan(a)*h)**2 ) * h
      V = (1/3) * math.pi * (math.tan(a)**2) * (h**2) * h
      V = (1/3) * math.pi * (math.tan(a)**2) * (h**3)
      V / ((1/3) * math.pi * (math.tan(a)**2)) = (h**3)
      h = (vol / ((1/3) * math.pi * (math.tan(a)**2)))**(1/3)

    Args:
        vol (float): Volume in microliters.
        a (float): Wall angle in radians.

    Returns:
        float: Cone height.
    """
    h = (vol / ((1/3) * math.pi * (math.tan(a)**2)))**(1/3)
    return h

class Tube(Container):
  """ Base class for Tube resources."""

  lid: TubeLid = None
  shape: ConeBottomShape = None

  def __init__(
      self,
      name: str,
      size_x: float, size_y: float, size_z: float,
      # TODO: Add "activeHeight" somewhere here. Find out where...
      #       It will be needed to adjust the Z coordinate for pipetting.
      category: str = "tube",
      volume: float = 0,
      max_volume: Optional[float] = None,
      model: Optional[str] = None,
      lid: TubeLid = None,
      shape: ConeBottomShape = None):
    """ Create a new tube.

    Args:
      name: Name of the tube.
      size_x: Internal size of the container in the x direction.
      size_y: Internal size of the container in the y direction. Equal to 'size_x' in square or round Tubes.
      size_z: Internal size of the tube container in the z direction.
      category: Category of the tube container.
      volume: Initial volume of the tube container.
      max_volume: Maximum volume of the tube container.
      lid: Initial status of the tube's lid. True when closed, False when open, None when lid-less.
    """

    if lid is None:
      # Defaults to "no lid".
      self.lid = TubeLid(lid_type=None, is_open=True)
    else:
      self.lid = lid

    if shape is None:
      # Defaults to "cone bottom shape".
      self.shape = ConeBottomShape()
    else:
      self.shape = shape

    if max_volume is None:
      raise ValueError("The maximum volume for tubes must be specified.")

    super().__init__(
      name=name,
      size_x=size_x,
      size_y=size_y,
      size_z=size_z,
      category=category,
      # TODO: Find out where the initial volume must go.
      #       A "Tube" is a "Container", which has a "VolumeTracker".
      #       This "tracker" has information about liquids in the container.
      # volume=volume,
      max_volume=max_volume,
      model=model
    )


    # NOTE: The tracker object is inherited from the "Container" class.
    #       Example from "using-trackers.ipynb":
    #         plate.get_item("A1").tracker.set_liquids([(Liquid.WATER, 10)])
    self.tracker.set_liquids([(Liquid.WATER, volume)])

  def level(self):
    """Calculate the liquid level (height) from the current volume."""
    volume = self.tracker.get_used_volume()
    height = self.shape.level(volume) + self.shape.wall_width
    return height

# TODO: I really don't know what this is. Taken from "tip_tracker.py".
TrackerCallback = Callable[[], None]

# TODO: Adapting the "TipTracker" class to tubes.
class HasTubeError(Exception):
  """ Raised when a tip already exists in a location where a tip is being added. """
class NoTubeError(Exception):
  """ Raised when a tip was expected but none was found. """
class TubeTracker:
  """ A tube tracker tracks tube operations and raises errors if operations on them are invalid. """

  def __init__(self, thing: str):
    self.thing = thing
    self._is_disabled = False
    self._tube: Optional["Tube"] = None
    self._pending_tube: Optional["Tube"] = None
    self._tube_origin: Optional["TubeSpot"] = None # not currently in a transaction, is it needed?

    self._callback: Optional[TrackerCallback] = None

  @property
  def is_disabled(self) -> bool:
    return self._is_disabled

  @property
  def has_tube(self) -> bool:
    """ Whether the tube tracker has a tube. Note that this includes pending operations. """
    return self._pending_tube is not None

  def get_tube(self) -> "Tube":
    """ Get the tube. Note that does includes pending operations.

    Raises:
      NoTubeError: If the tube spot does not have a tube.
    """

    if self._tube is None:
      raise NoTubeError(f"{self.thing} does not have a tube.")
    return self._tube

  def disable(self) -> None:
    """ Disable the tube tracker. """
    self._is_disabled = True

  def enable(self) -> None:
    """ Enable the tube tracker. """
    self._is_disabled = False

  def add_tube(self, tube: Tube, origin: Optional["TubeSpot"] = None, commit: bool = True) -> None:
    """ Update the pending state with the operation, if the operation is valid.

    Args:
      tube: The tube to add.
      commit: Whether to commit the operation immediately. If `False`, the operation will be
        committed later with `commit()` or rolled back with `rollback()`.
    """
    if self.is_disabled:
      raise RuntimeError("Tube tracker is disabled. Call `enable()`.")
    if self._pending_tube is not None:
      raise HasTubeError(f"{self.thing} already has a tube.")
    self._pending_tube = tube

    self._tube_origin = origin

    if commit:
      self.commit()

  def remove_tube(self, commit: bool = False) -> None:
    """ Update the pending state with the operation, if the operation is valid """
    if self.is_disabled:
      raise RuntimeError("Tube tracker is disabled. Call `enable()`.")
    if self._pending_tube is None:
      raise NoTubeError(f"{self.thing} does not have a tube.")
    self._pending_tube = None

    if commit:
      self.commit()

  def commit(self) -> None:
    """ Commit the pending operations. """
    self._tube = self._pending_tube
    if self._callback is not None:
      self._callback()

  def rollback(self) -> None:
    """ Rollback the pending operations. """
    assert not self.is_disabled, "Tube tracker is disabled. Call `enable()`."
    self._pending_tube = self._tube

  def clear(self) -> None:
    """ Clear the history. """
    self._tube = None
    self._pending_tube = None

  def serialize(self) -> dict:
    """ Serialize the state of the tube tracker. """
    return {
      "tube": self._tube.serialize() if self._tube is not None else None,
      "tube_state": self._tube.tracker.serialize() if self._tube is not None else None,
      "pending_tube": self._pending_tube.serialize() if self._pending_tube is not None else None
    }

  def load_state(self, state: dict) -> None:
    """ Load a saved tube tracker state. """

    self._tube = cast(Optional[Tube], deserialize(state.get("tube")))
    self._pending_tube = cast(Optional[Tube], deserialize(state.get("pending_tube")))

  def get_tube_origin(self) -> Optional["TubeSpot"]:
    """ Get the origin of the current tube, if known. """
    return self._tube_origin

  def __repr__(self) -> str:
    return f"TubeTracker({self.thing}, is_disabled={self.is_disabled}, has_tube={self.has_tube}" + \
      f" tube={self._tube}, pending_tube={self._pending_tube})"

  def register_callback(self, callback: TrackerCallback) -> None:
    self._callback = callback


# TODO: I really don't know what this does at all. It mimics "TipCreator".
TubeCreator = Callable[[], Tube]
# TODO: Consider writing a "TubeSpot" class.
#       Issues: probably requires a "SpotTubeTracker" tracker class,
#       which I don't know how to implement.
class TubeSpot(Resource):
  """ A tube spot, a location in a tube rack where there may or may not be a tube. """

  def __init__(self, name: str, size_x: float, size_y: float, make_tube: TubeCreator,
    size_z: float = 0, category: str = "tube_spot", **kwargs):
    """ Initialize a tube spot.

    Args:
      name: the name of the tube spot.
      size_x: the size of the tube spot in the x direction.
      size_y: the size of the tube spot in the y direction.
      size_z: the size of the tube spot in the z direction.
      make_tube: a function that creates a tube for the tube spot.
      category: the category of the tube spot.
    """

    super().__init__(name, size_x=size_y, size_y=size_x, size_z=size_z,
      category=category, **kwargs)
    # TODO: Write a "TubeTracker" similar to "TipTracker".
    self.tracker = TubeTracker(thing="Tube spot")
    self.parent: Optional["TubeRack"] = None

    self.make_tube = make_tube

    self.tracker.register_callback(self._state_updated)

  def get_tube(self) -> Tube:
    """ Get a tube from the tube spot. """

    # TODO: Ask Rick about this and re-enable it.
    # Tracker will raise an error if there is no tube.
    # We spawn a new tube if tube tracking is disabled
    # tracks = does_tip_tracking() and not self.tracker.is_disabled
    # if not self.tracker.has_tip and not tracks:
    #   self.tracker.add_tube(self.make_tube())

    return self.tracker.get_tube()

  def has_tube(self) -> bool:
    """ Check if the tube spot has a tube. """
    return self.tracker.has_tube

  def empty(self) -> None:
    """ Empty the tube spot. """
    self.tracker.remove_tube()

  def serialize(self) -> dict:
    """ Serialize the tube spot. """
    return {
      **super().serialize(),
      "prototype_tube": self.make_tube().serialize(),
      # Add info about the tip. Is there one or not?
      # TODO: This may be a hack. Review "tip_tracker.py" and "tip.py".
      "tube_tracker": self.tracker.serialize()
    }

  @classmethod
  def deserialize(cls, data: dict) -> "TubeSpot":
    """ Deserialize a tube spot. """
    tube_data = data["prototype_tube"]
    def make_tube() -> Tube:
      return cast(Tube, deserialize(tube_data))

    tube_spot = cls(
      name=data["name"],
      size_x=data["size_x"],
      size_y=data["size_y"],
      size_z=data["size_z"],
      make_tube=make_tube,
      category=data.get("category", "tube_spot")
    )

    # Add the tube.
    # TODO: This may be a hack. Review "tip_tracker.py" and "tip.py".
    #       For example, it does not restore liquid history.
    if data.get("tube_tracker", {}).get(["tube"], None):
      tube_spot.tracker.add_tube(tube_spot.make_tip())

    return tube_spot

  def serialize_state(self) -> Dict[str, Any]:
    return self.tracker.serialize()

  def load_state(self, state: Dict[str, Any]):
    self.tracker.load_state(state)


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
  default_link = linked_containers[0]
  container_data = next(x for x in containers_data if x["name"] == default_link["container"])

  def make_pew_tube(name="placeholder name"):
    """Function to create default tubes, passed to create_ordered_items_2d."""
    # NOTE: I need to create this function here, it is required by "TubeSpot" later on.
    return Tube(
      # TODO: Names for tubes should all be different.
      name=name,
      size_x=platform_data["wellDiameter"],
      size_y=platform_data["wellDiameter"],
      size_z=container_data["length"],
      max_volume=container_data["maxVolume"],
      model=container_data["name"]
      # TODO: Add "activeHeight" somewhere here.
      #       It is needed to get the proper Z coordinate.
    )

  # Prepare parameters for "create_ordered_items_2d".
  dx, dy, dz = rack_to_plr_dxdydz(platform_data, default_link)

  # Use the helper function to create a regular 2D-grid of tip spots.
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
    dx=dx, dy=dy, dz=dz,
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

  # Add tubes in the platform item, if any.
  platform_contents = platform_item.get("content", [])
  for content in platform_contents:
    container_data = get_contents_container(content, containers_data)

    # Create the Tube.
    new_tube = Tube(
      name=content["name"],
      # TODO: Reconsider setting "size_x" and "size_y" to something else.
      size_x=platform_data["wellDiameter"],
      size_y=platform_data["wellDiameter"],
      size_z=container_data["length"],
      max_volume=container_data["maxVolume"],
      model=container_data["name"],
      category=container_data["type"]  # "tube"
      # TODO: Add "activeHeight" somewhere here.
      #       It is needed to get the proper Z coordinate.
    )

    # Add liquid to the tracker.
    # TODO: Add liquid classes to our data schemas, even if it is water everywhere for now.
    new_tube.tracker.add_liquid(Liquid.WATER, volume=content["volume"])

    # Get the tube's position indexes.
    # NOTE: "i" for "Y/rows", and "j" for "X/columns".
    i, j = content["position"]["row"]-1, content["position"]["col"]-1
    # Get the TubeSpot.
    tube_spot: TubeSpot = tube_rack_item.get_item((i, j))
    # Add the Tube to the tracker.
    tube_spot.tracker.add_tube(new_tube, commit=True)
    # Add the Tube to the TubeSpot as a child resource.
    # NOTE: This is required, otherwise it does not show up in the deck by name.
    tube_spot.assign_child_resource(new_tube, location=Coordinate(0,0,0))

  # Save the platform's active height such that "container_offset_z" can
  # be recovered later on (e.g. during an export) with the following formula:
  #   "container_offset_z = tube_rack_item.active_z - tube_spot.location.z"
  tube_rack_item.active_z = platform_data["activeHeight"]

  return tube_rack_item

class CustomPlatform(Resource):
  pass

def load_ola_custom(deck: "SilverDeck",
                    platform_item: dict,
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

  # Get the item's content.
  platform_contents = platform_item.get("content", [])

  # Create the TubeSpot.
  for index, slot in enumerate(platform_data.get("slots", [])):

    # Get the content in the slot (if any).
    content = next((c for c in platform_contents if c["index"] == index), None)

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

    def make_tube():
      """Generate a default tube for the slot / tube spot"""
      if container:
        return Tube(
          name=f"{container["name"]} in {slot["slotName"]}",
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
    slot_location=Coordinate(x=x, y=y,
      # NOTE: Must add the slots's active height here.
      #       The slot's is an offset respect to it.
      z=tube_spot.active_z
    )
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
