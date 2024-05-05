import math
from typing import Optional, Callable, List, Union, Sequence, cast
from pylabrobot.resources.container import Container
#from pylabrobot.resources.plate import Plate
from pylabrobot.resources.resource import Resource, Coordinate
from pylabrobot.resources.itemized_resource import ItemizedResource
from pylabrobot.resources.itemized_resource import create_equally_spaced

class TubeLid:
  """Small helper object to hold the state of the lid of a particular tube."""
  is_open: bool = False
  has_lid: bool = True
  # NOTE: There are many types of tube lids:
  #       "hinge" "screw" "cork" "rubber_cap" "vial_stopper" "none"
  type: str = "hinge"

  def __init__(self, lid_type, is_open: False) -> None:

    self.type = lid_type

    if self.type is None:
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
  If using microliters, which are cubic millimieters, the output will be in millimeters.
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
  # Cyllinder.
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

    # Stage 1: Cyllindrical.
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
      self.lid = TubeLid(lid_type=None)
    else:
      self.lid = lid

    if shape is None:
      # Defaults to "cone bottom shape".
      self.shape = ConeBottomShape()
    else:
      self.shape = shape

    if max_volume is None:
      raise ValueError("The maximum volume for tubes must be specified.")

    super().__init__(name, size_x=size_x, size_y=size_y, size_z=size_z, category=category,
      volume=volume, max_volume=max_volume, model=model)

  def level(self):
    """Calculate the liquid level (height) from the current volume."""
    volume = self.tracker.get_used_volume()
    height = self.shape.level(volume) + self.shape.wall_width
    return height

# TODO: Consider writing a "TubeSpot" class.
#       Issues: probably requires a "SpotTubeTracker" tracker class,
#       which I don't know how to implement.

class TubeRack(ItemizedResource[Tube]):
  """ Base class for Rack resources.
  Boilerplate code copied from the 'Plate' class.
  """

  def __init__(
    self,
    name: str,
    size_x: float,
    size_y: float,
    size_z: float,
    items: Optional[List[List[Tube]]] = None,
    num_items_x: Optional[int] = None,
    num_items_y: Optional[int] = None,
    category: str = "rack",
    compute_volume_from_height: Optional[Callable[[float], float]] = None,
    model: Optional[str] = None,
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

    super().__init__(name, size_x, size_y, size_z, items=items, num_items_x=num_items_x,
      num_items_y=num_items_y, category=category, model=model)
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

  def unassign_child_resource(self, resource):
    return super().unassign_child_resource(resource)

  def serialize(self):
    return super().serialize()

  def __repr__(self) -> str:
    return (f"{self.__class__.__name__}(name={self.name}, size_x={self._size_x}, "
            f"size_y={self._size_y}, size_z={self._size_z}, location={self.location}, ")

  def get_tube(self, identifier: Union[str, int]) -> Tube:
    """ Get the item with the given identifier.

    See :meth:`~.get_item` for more information.
    """

    return super().get_item(identifier)

  def get_tubes(self,
    identifier: Union[str, Sequence[int]]) -> List[Tube]:
    """ Get the tubes with the given identifier.

    See :meth:`~.get_items` for more information.
    """

    return super().get_items(identifier)

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


def create_tube_rack(platform_item, platform_data, *args):

  tube_rack_item = TubeRack(
      name=platform_item["name"],
      size_x=platform_data["width"],
      size_y=platform_data["length"],
      size_z=platform_data["height"],
      # category = "tip_rack", # The default.
      model=platform_data["name"], # Optional.
      items=create_equally_spaced(
        klass=TubeSpot,
        num_items_x=platform_data["wellsColumns"],
        num_items_y=platform_data["wellsRows"],
        # dx: The bottom left corner for items in the left column.
        dx=platform_data["firstWellCenterX"]-platform_data["wellSeparationX"]/2,
        # dy: The bottom left corner for items in the top row.
        dy=platform_data["firstWellCenterY"]-platform_data["wellSeparationY"]/2,
        # dz: The z coordinate for all items.
        # TODO: I dont know how "dz" is used later on. Check that it corresponds to activeHeight.
        dz=platform_data["activeHeight"],
        # XY distance between adjacent items in the grid.
        item_size_x=platform_data["wellSeparationX"],
        item_size_y=platform_data["wellSeparationY"]
        # The TubeSpot class will receive this argument (through kwargs) to create its tubes.
        # Note that this is not needed for "wells", as there are no "well spots" in PLR.
        # There are however, "tube spots" in pipettin, which I don't know how to accomodate.
        #make_tip=make_pew_tube
      ),
      # Fill with tubes.
      with_tubes=False
    )

  return tube_rack_item
