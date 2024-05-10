import math
from abc import ABCMeta
from typing import Optional, Callable, List, Union, Sequence, cast, Any, Dict

from pylabrobot.serializer import deserialize
from pylabrobot.resources.container import Container
from pylabrobot.resources.liquid import Liquid
#from pylabrobot.resources.plate import Plate
from pylabrobot.resources.resource import Resource, Coordinate
from pylabrobot.resources.itemized_resource import ItemizedResource, create_equally_spaced

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
  """ A tube tracker tracks tube operations and raises errors if the tube operations are invalid. """

  def __init__(self, thing: str):
    self.thing = thing
    self._is_disabled = False
    self._tube: Optional["Tube"] = None
    self._pending_tube: Optional["Tube"] = None
    self._tube_origin: Optional["TubeSpot"] = None # not currently in a transaction, do we need that?

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
    size_z: float = 0, category: str = "tube_spot"):
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
      category=category)
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
    }

  @classmethod
  def deserialize(cls, data: dict) -> "TubeSpot":
    """ Deserialize a tube spot. """
    tube_data = data["prototype_tube"]
    def make_tube() -> Tube:
      return cast(Tube, deserialize(tube_data))

    return cls(
      name=data["name"],
      size_x=data["size_x"],
      size_y=data["size_y"],
      size_z=data["size_z"],
      make_tube=make_tube,
      category=data.get("category", "tube_spot")
    )

  def serialize_state(self) -> Dict[str, Any]:
    return self.tracker.serialize()

  def load_state(self, state: Dict[str, Any]):
    self.tracker.load_state(state)


class TubeRack(ItemizedResource[TubeSpot], metaclass=ABCMeta):
  """ Abstract base class for Tube Rack resources.
  Boilerplate code copied from the 'Plate' class and the original 'TubeRack' class.
  """

  def __init__(
    self,
    name: str,
    size_x: float,
    size_y: float,
    size_z: float,
    items: Optional[List[List[TubeSpot]]] = None,
    model: Optional[str] = None,
    num_items_x: Optional[int] = None,
    num_items_y: Optional[int] = None,
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
      raise NotImplementedError("Filling a new TubeRack with tubes on startup is not implemented yet (with_tubes=True).")

    super().__init__(
      name=name,
      size_x=size_x,
      size_y=size_y,
      size_z=size_z,
      items=items,
      model=model,
      num_items_x=num_items_x,
      num_items_y=num_items_y,
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
  def _occupied_func(x: TubeSpot):
    return "U" if x.has_tube() else "-"

  def print_grid(self,occupied_func=None):
    super().print_grid(occupied_func=occupied_func)

  def get_tube(self, identifier: Union[str, int]) -> Tube:
    """ Get the item with the given identifier.

    See :meth:`~.get_item` for more information.
    """
    # NOTE: I think that the "get_item" method in "well plates"
    #       returns the resource directly. Here there may be an
    #       intermediary "spot" item, thus the difference from
    #       "return super().get_item(identifier)".
    return super().get_item(identifier).get_tube()

  def get_tubes(self, identifier: Union[str, Sequence[int]]) -> List[Tube]:
    """ Get the tubes with the given identifier.

    See :meth:`~.get_items` for more information.
    """
    # NOTE: This differs from the method in "well plates". See note in "get_tube".
    return [ts.get_tube() for ts in super().get_items(identifier)]

  def __getitem__(self, identifier):
    """Overrides [] from ItemizedResource, in order to return tubes instead of TubeSpots"""
    tube_spots = super().__getitem__(identifier)
    return [ts.get_tube() for ts in tube_spots]

  # TODO: Should I port "set_tip_state" from "TipRack" too?
  #       Fist I need to figure out how "make_tip" works.

  def disable_volume_trackers(self) -> None:
    """ Disable volume tracking for all tubes in the rack. """

    for tube in self.get_all_items():
      tube.tracker.disable()

  def enable_volume_trackers(self) -> None:
    """ Enable volume tracking for all tubes in the rack. """

    for tube in self.get_all_items():
      tube.tracker.enable()

  # TODO: Should I add "empty" from "TipRack" here?

  # TODO: Should I add "fill" from "TipRack" here?

  def get_all_tubes(self) -> List[Tube]:
    """ Get all tubes in the tube rack. """
    return [ts.get_tube() for ts in super().get_all_items() if ts.has_tube()]

  def set_tube_volumes(self, volumes: Union[List[List[float]], List[float], float]) -> None:
    """ Update the volume in the volume tracker of each tube in the plate.

    Args:
      volumes: A list of volumes, one for each tube in the plate. The list can be a list of lists,
        where each inner list contains the volumes for each tube in a column.  If a single float is
        given, the volume is assumed to be the same for all tubes. Volumes are in uL.

    Raises:
      ValueError: If the number of volumes does not match the number of tubes in the plate.

    Example:
      Set the volume of each tube in a 96-tube plate to 10 uL.

      >>> plate = Plate("plate", 127.0, 86.0, 14.5, num_items_x=12, num_items_y=8)
      >>> plate.update_tube_volumes(10)
    """

    if isinstance(volumes, float):
      volumes = [volumes] * self.num_items
    elif isinstance(volumes, list) and all(isinstance(column, list) for column in volumes):
      volumes = cast(List[List[float]], volumes) # mypy doesn't know that all() checks the type
      volumes = [list(column) for column in zip(*volumes)] # transpose the list of lists
      volumes = [volume for column in volumes for volume in column] # flatten the list of lists

    volumes = cast(List[float], volumes) # mypy doesn't know type is correct at this point.

    if len(volumes) != self.num_items:
      raise ValueError(f"Number of volumes ({len(volumes)}) does not match number of tubes "
                      f"({self.num_items}) in rack '{self.name}'.")

    for i, volume in enumerate(volumes):
      tube = self.get_tube(i)
      tube.tracker.set_used_volume(volume)

def load_ola_tube_rack(
  platform_item: dict,
  platform_data: dict,
  containers_data: list,
  *args, **kwargs):

  # NOTE: I need to create this function here, it is required by "TubeSpot" later on.
  def make_pew_tube():
    # TODO: Find a way to avoid defaulting to the first associated container.
    # NOTE: Perhaps PLR does not consider having different tubes for the same tube rack.
    first_container = platform_data["containers"][0]
    container_data = next(x for x in containers_data if x["name"] == first_container["container"])
    tube = Tube(
      # TODO: Names for tubes should all be different.
      name="placeholder name",
      size_x=container_data["width"],
      size_y=container_data["width"],
      size_z=container_data["length"],
      max_volume=container_data["maxVolume"],
      model=container_data["name"]
      # TODO: Add "activeHeight" somewhere here.
      #       It is needed to get the proper Z coordinate.
    )
    return tube

  # Create the TubeRack instance.
  tube_rack_item = TubeRack(
      name=platform_item["name"],
      size_x=platform_data["width"],
      size_y=platform_data["length"],
      size_z=platform_data["height"],
      # category = "tip_rack", # The default.
      model=platform_data["name"], # Optional.

      # Use the helper function to create a regular 2D-grid of tip spots.
      items=create_equally_spaced(
        # NOTE: Parameters for "create_equally_spaced".
        klass=TubeSpot,  # NOTE: the TipRack uses "TipSpot" class here. Should I use "Tube"?
        num_items_x=platform_data["wellsColumns"],
        num_items_y=platform_data["wellsRows"],
        # item_dx: The size of the items in the x direction
        item_dx=platform_data["wellSeparationX"],
        # item_dy: The size of the items in the y direction
        item_dy=platform_data["wellSeparationY"],
        # dx: The X coordinate of the bottom left corner for items in the left column.
        dx=platform_data["firstWellCenterX"] - platform_data["wellSeparationX"]/2,
        # dy: The Y coordinate of the bottom left corner for items in the top row.
        dy=platform_data["length"]-platform_data["firstWellCenterY"]-platform_data["wellSeparationY"]*(0.5+platform_data["wellsRows"]),
        # dz: The z coordinate for all items.
        # TODO: I dont know how "dz" is used later on. Check that it corresponds to activeHeight.
        dz=platform_data["activeHeight"],

        # NOTE: Additional keyword arguments are passed to the "klass" constructor set above.
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
      ),
      # Fill with tubes.
      with_tubes=False
    )

  # Add tubes in the platform item, if any.
  platform_contents = platform_item.get("content", [])
  for content in platform_contents:
    container_data = get_contents_container(content, containers_data)

    # Create the Tube.
    new_tube = Tube(
      name=content["name"],
      size_x=container_data["width"],
      size_y=container_data["width"],
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

  return tube_rack_item

class CustomPlatform(Resource):
  pass

def load_ola_custom(platform_item, platform_data, containers_data, **kwargs):
  custom = CustomPlatform(
    name=platform_item["name"],
    size_x=platform_data["width"],
    size_y=platform_data["length"],
    size_z=platform_data["height"],
    category=platform_data.get("type", None), # Optional in PLR.
    model=platform_data.get("name", None) # Optional in PLR (not documented in Resource).
  )
  # Add tubes in the platform item, if any.
  platform_contents = platform_item.get("content", [])
  for content in platform_contents:
    # Create the Tube.
    container_data = get_contents_container(content, containers_data)
    tube = Tube(
      name=content["name"],
      size_x=container_data["width"],
      size_y=container_data["width"],
      size_z=container_data["length"],
      max_volume=container_data["maxVolume"],
      model=container_data["name"],
      category=container_data["type"]  # "tube"
      # TODO: Add "activeHeight" somewhere here.
      #       It is needed to get the proper Z coordinate.
    )

    # TODO: Add liquid classes to our data schemas, even if it is water everywhere for now.
    # Add liquid to the tracker.
    tube.tracker.add_liquid(Liquid.WATER, volume=content["volume"])

    # Add the tube as a direct child.
    custom.assign_child_resource(tube, location=Coordinate(**content["position"]))

  return custom
