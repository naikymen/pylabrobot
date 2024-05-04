import tempfile
import os
import unittest

from pylabrobot.resources import (
  Coordinate,
  Deck,
  Plate,
  PlateCarrier,
  Resource,
  TipCarrier,
  TipRack,
  TipSpot,
  Well,
  ResourceNotFoundError,
  create_equally_spaced,
  standard_volume_tip_with_filter,
  create_homogeneous_carrier_sites
)


class DeckTests(unittest.TestCase):
  """ Tests for the `Deck` class. """

  def test_assign_resource(self):
    deck = Deck()
    resource = Resource(name="resource", size_x=1, size_y=1, size_z=1)
    deck.assign_child_resource(resource, location=Coordinate.zero())
    self.assertEqual(deck.get_resource("resource"), resource)

  def test_assign_resource_twice(self):
    deck = Deck()
    resource = Resource(name="resource", size_x=1, size_y=1, size_z=1)
    deck.assign_child_resource(resource, location=Coordinate.zero())
    with self.assertRaises(ValueError):
      deck.assign_child_resource(resource, location=Coordinate.zero())

  def test_clear(self):
    deck = Deck()
    r1 = Resource(name="r1", size_x=1, size_y=1, size_z=1)
    r2 = Resource(name="r2", size_x=1, size_y=1, size_z=1)
    r3 = Resource(name="r3", size_x=1, size_y=1, size_z=1)
    deck.assign_child_resource(r1, location=Coordinate.zero())
    deck.assign_child_resource(r2, location=Coordinate(x=2))
    deck.assign_child_resource(r3, location=Coordinate(x=4))
    deck.clear()
    with self.assertRaises(ResourceNotFoundError):
      deck.get_resource("resource")

  def test_json_serialization_standard(self):
    self.maxDiff = None
    tmp_dir = tempfile.gettempdir()

    # test with custom classes
    custom_1 = Deck()
    tc = TipCarrier("tc", 200, 200, 200, sites=create_homogeneous_carrier_sites([
      Coordinate(10, 20, 30)], site_size_x=10, site_size_y=10))

    tc[0] = TipRack("tips", 10, 20, 30,
      items=create_equally_spaced(TipSpot,
        num_items_x=1, num_items_y=1,
        dx=-1, dy=-1, dz=-1,
        item_dx=1, item_dy=1,
        size_x=1, size_y=1,
        make_tip=standard_volume_tip_with_filter))
    pc = PlateCarrier("pc", 100, 100, 100, sites=create_homogeneous_carrier_sites([
      Coordinate(10, 20, 30)], site_size_x=10, site_size_y=10))
    pc[0] = Plate("plate", 10, 20, 30,
      items=create_equally_spaced(Well,
        num_items_x=1, num_items_y=1,
        dx=-1, dy=-1, dz=-1,
        item_dx=1, item_dy=1,
        size_x=1, size_y=1, size_z=1))
    custom_1.assign_child_resource(tc, location=Coordinate(0, 0, 0))
    custom_1.assign_child_resource(pc, location=Coordinate(100, 0, 0))

    fn = os.path.join(tmp_dir, "layout.json")
    custom_1.save(fn)
    custom_recover = Deck.load_from_json_file(fn)

    self.assertEqual(custom_1, custom_recover)
