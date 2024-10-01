import math
from typing import Optional, Callable, cast, Dict, Any

from pylabrobot.serializer import deserialize
from pylabrobot.resources.container import Container
from pylabrobot.resources.liquid import Liquid
from pylabrobot.resources.resource import Resource

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
  half_sphere_vol = ((4/3) * math.pi * sphere_r**3) / 2
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
    if volume <= self.half_sphere_vol:
      return min(self.min_height, self.sphere_r)
    else:
      volume -= self.half_sphere_vol
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
