from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pylabrobot.resources.volume_tracker import VolumeTracker


@dataclass
class Tip:
  """ A single tip.

  Attributes:
    has_filter: whether the tip type has a filter
    total_tip_length: total length of the tip, in in mm
    maximal_volume: maximal volume of the tip, in ul
    fitting_depth: the overlap between the tip and the pipette, in mm
  """

  has_filter: bool
  total_tip_length: float
  maximal_volume: float
  fitting_depth: float
  model: str = "default"
  active_z: float = 0.0

  def __post_init__(self):
    self.tracker = VolumeTracker(max_volume=self.maximal_volume)

  def serialize(self) -> dict:
    return {
      "type": self.__class__.__name__,
      "total_tip_length": self.total_tip_length,
      "has_filter": self.has_filter,
      "maximal_volume": self.maximal_volume,
      "fitting_depth": self.fitting_depth,
      # TODO: Discuss this with Rick. The tip may be one of several brands/models.
      #       I need this to know which tip to insert in the rack.
      "model": self.model,
      "active_z": self.active_z, # Used for compatible tip tracking of "containerOffsetZ".
      # TODO: Deduplicate these keys.
      #       Added it with another key for consistency with Tubes.
      "max_volume": self.maximal_volume,
      "size_z": self.total_tip_length,
    }


TipCreator = Callable[[], Tip]
