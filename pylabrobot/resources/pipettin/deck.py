import textwrap
from typing import Optional, Callable

from pylabrobot.resources import Coordinate, Deck, Trash


class SilverDeck(Deck):
  """ (Ag)nostic deck object.

  Boilerplate code written by Rick: https://forums.pylabrobot.org/t/writing-a-new-backend-agnosticity/844/16
  """

  def __init__(self,
               name: str= "silver_deck",
               # TODO: Update default size.
               size_x: float = 250,
               size_y: float = 350,
               size_z: float = 200,
               resource_assigned_callback: Optional[Callable] = None,
               resource_unassigned_callback: Optional[Callable] = None,
               # TODO: Update default origin.
               origin: Coordinate = Coordinate(0, 0, 0),
               # TODO: Update default trash location.
               trash_location: Coordinate = Coordinate(x=82.84, y=53.56, z=5),
               no_trash: bool = False):

    # Run init from the base Deck class.
    super().__init__(
      name=name,
      size_x=size_x, size_y=size_y, size_z=size_z,
      resource_assigned_callback=resource_assigned_callback,
      resource_unassigned_callback=resource_unassigned_callback,
      origin=origin)

    # TODO: write your init code, for example assign a "trash" resource:
    if not no_trash:
      self._assign_trash(location=trash_location)

  def _assign_trash(self, location: Coordinate):
    """ Assign the trash area to the deck. """

    trash = Trash(
      name="trash",
      # TODO: Update default dimensions.
      size_x=80,
      size_y=120,
      size_z=50
    )

    self.assign_child_resource(trash, location=location)

  def summary(self) -> str:
    """ Get a summary of the deck.

    >>> print(deck.summary())

    TODO: <write some printable ascii representation of the deck's current layout>
    """

    ascii_dck = textwrap.dedent(f"""
      Deck: {self.get_size_x()}mm x {self.get_size_y()}mm x {self.get_size_z()}mm (XYZ)

      +---------------------+
      |                     |
      |        ....         |
      |                     |
      +---------------------+
    """)

    return ascii_dck
