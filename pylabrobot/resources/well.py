import enum
import math
from typing import Callable, List, Optional, Tuple, Union

from pylabrobot.resources.container import Container
from pylabrobot.resources.liquid import Liquid


class WellBottomType(enum.Enum):
  """ Enum for the type of bottom of a well. """

  FLAT = "flat"
  U = "U"
  V = "V"
  UNKNOWN = "unknown"


class CrossSectionType(enum.Enum):
  """ Enum for the type of cross section of a well.

  A well with a circular cross section will be a cylinder, and a well with a rectangular cross
  section will be a cuboid. Note that the bottom section of a well may be any of the
  :class:`WellBottomType` values.
  """

  CIRCLE = "circle"
  RECTANGLE = "rectangle"


class Well(Container):
  """ Base class for Well resources.

  Note that in regular use these will be automatically generated by the
  :class:`pylabrobot.resources.Plate` class.
  """

  def __init__(
    self,
    name: str,
    size_x: float, size_y: float, size_z: float,
    material_z_thickness: Optional[float] = None,
    bottom_type: Union[WellBottomType, str] = WellBottomType.UNKNOWN,
    category: str = "well", model: Optional[str] = None,
    max_volume: Optional[float] = None,
    compute_volume_from_height: Optional[Callable[[float], float]] = None,
    compute_height_from_volume: Optional[Callable[[float], float]] = None,
    cross_section_type: Union[CrossSectionType, str] = CrossSectionType.CIRCLE):
    """ Create a new well.

    Args:
      name: Name of the well.
      size_x: Size of the well in the x direction.
      size_y: Size of the well in the y direction.
      size_z: Size of the well in the z direction.
      bottom_type: Type of the bottom of the well. If a string, must be the raw value of the
        :class:`WellBottomType` enum. This is used to deserialize and may be removed in the future.
      category: Category of the well.
      max_volume: Maximum volume of the well. If not specified, the well will be seen as a cylinder
        and the max volume will be computed based on size_x, size_y, and size_z.
      compute_volume_from_height: function to compute the volume from the height relative to the
        bottom
      cross_section_type: Type of the cross section of the well. If not specified, the well will be
        seen as a cylinder.
    """

    if isinstance(bottom_type, str):
      bottom_type = WellBottomType(bottom_type)
    if isinstance(cross_section_type, str):
      cross_section_type = CrossSectionType(cross_section_type)

    if max_volume is None:
      if compute_volume_from_height is None:
        # we assume flat bottom as a best guess, bottom types require additional information
        if cross_section_type == CrossSectionType.CIRCLE:
          assert size_x == size_y, "size_x and size_y must be equal for circular wells."
          max_volume = math.pi * (size_x / 2) ** 2 * size_z
        elif cross_section_type == CrossSectionType.RECTANGLE:
          max_volume = size_x * size_y * size_z
      else:
        max_volume = compute_volume_from_height(size_z)

    super().__init__(name, size_x=size_x, size_y=size_y, size_z=size_z, category=category,
      max_volume=max_volume, model=model, compute_volume_from_height=compute_volume_from_height,
      compute_height_from_volume=compute_height_from_volume,
      material_z_thickness=material_z_thickness)
    self.bottom_type = bottom_type
    self.cross_section_type = cross_section_type

    self.tracker.register_callback(self._state_updated)

  def serialize(self):
    return {
      **super().serialize(),
      "bottom_type": self.bottom_type.value,
      "cross_section_type": self.cross_section_type.value,
      # TODO: Refactor the conversion to pipettin to use "serialize_state" instead.
      "well_tracker": self.tracker.serialize()
    }

  def set_liquids(self, liquids: List[Tuple[Optional["Liquid"], float]]):
    """ Set the liquids in the well.

    (wraps :meth:`~.VolumeTracker.set_liquids`)

    Example:
      Set the liquids in a well to 10 uL of water:

      >>> well.set_liquids([(Liquid.WATER, 10)])
    """

    self.tracker.set_liquids(liquids)
