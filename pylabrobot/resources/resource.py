from __future__ import annotations

import itertools
import json
import logging
import sys
from typing import Any, Callable, Dict, List, Optional, cast

from .coordinate import Coordinate
from .errors import ResourceNotFoundError
from pylabrobot.serializer import serialize, deserialize
from pylabrobot.utils.object_parsing import find_subclass

if sys.version_info >= (3, 11):
  from typing import Self
else:
  from typing_extensions import Self

logger = logging.getLogger("pylabrobot")


WillAssignResourceCallback = Callable[["Resource"], None]
DidAssignResourceCallback = Callable[["Resource"], None]
WillUnassignResourceCallback = Callable[["Resource"], None]
DidUnassignResourceCallback = Callable[["Resource"], None]
ResourceDidUpdateState = Callable[[Dict[str, Any]], None]


class Resource:
  """ Base class for deck resources.

  Args:
    name: The name of the resource.
    size_x: The size of the resource in the x-direction.
    size_y: The size of the resource in the y-direction.
    size_z: The size of the resource in the z-direction.
    location: The location of the resource, relative to its parent.
      (see :meth:`get_absolute_location`)
    category: The category of the resource, e.g. `tips`, `plate_carrier`, etc.
  """

  def __init__(
    self,
    name: str,
    size_x: float,
    size_y: float,
    size_z: float,
    category: Optional[str] = None,
    model: Optional[str] = None,
  ):
    self._name = name
    self._size_x = size_x
    self._size_y = size_y
    self._size_z = size_z
    self.category = category
    self.model = model

    self.location: Optional[Coordinate] = None
    self.parent: Optional[Resource] = None
    self.children: List[Resource] = []

    self.rotation = 0 # TODO: like location, this should be wrt parent

    self._will_assign_resource_callbacks: List[WillAssignResourceCallback] = []
    self._did_assign_resource_callbacks: List[DidAssignResourceCallback] = []
    self._will_unassign_resource_callbacks: List[WillUnassignResourceCallback] = []
    self._did_unassign_resource_callbacks: List[DidUnassignResourceCallback] = []
    self._resource_state_updated_callbacks: List[ResourceDidUpdateState] = []

  def serialize(self) -> dict:
    """ Serialize this resource. """
    return {
      "name": self.name,
      "type": self.__class__.__name__,
      "size_x": self._size_x,
      "size_y": self._size_y,
      "size_z": self._size_z,
      "location": serialize(self.location),
      "rotation": self.rotation,
      "category": self.category,
      "model": self.model,
      "children": [child.serialize() for child in self.children],
      "parent_name": self.parent.name if self.parent is not None else None
    }

  @property
  def name(self) -> str:
    """ Get the name of this resource. """
    return self._name

  @name.setter
  def name(self, name: str):
    """ Set the name of this resource.

    Will raise a `RuntimeError` if the resource is assigned to another resource.
    """

    if self.parent is not None:
      raise RuntimeError("Cannot change the name of a resource that is assigned.")
    self._name = name

  def __eq__(self, other):
    return (
      isinstance(other, Resource) and
      self.name == other.name and
      self.get_size_x() == other.get_size_x() and
      self.get_size_y() == other.get_size_y() and
      self.get_size_z() == other.get_size_z() and
      self.location == other.location and
      self.category == other.category and
      self.children == other.children
    )

  def __repr__(self) -> str:
    return f"{self.__class__.__name__}(name={self.name}, location={self.location}, " \
           f"size_x={self._size_x}, size_y={self._size_y}, size_z={self._size_z}, " \
           f"category={self.category})"

  def __hash__(self) -> int:
    return hash(repr(self))

  def get_absolute_location(self) -> Coordinate:
    """ Get the absolute location of this resource, probably within the
    :class:`pylabrobot.resources.Deck`. """
    assert self.location is not None, "Resource has no location."
    if self.parent is None:
      return self.location
    return self.parent.get_absolute_location() + self.location

  def get_size_x(self) -> float:
    if self.rotation in {90, 270}:
      return self._size_y
    return self._size_x

  def get_size_y(self) -> float:
    if self.rotation in {90, 270}:
      return self._size_x
    return self._size_y

  def get_size_z(self) -> float:
    """ Get the size of this resource in the z-direction. """
    return self._size_z

  def assign_child_resource(
    self,
    resource: Resource,
    location: Coordinate,
    reassign: bool = True):
    """ Assign a child resource to this resource.

    Before the resource is assigned, all callbacks registered with
    :meth:`~Resource.register_will_assign_resource_callback` will be called. If any of these
    callbacks raises an exception, the resource will not be assigned.

    After the resource is assigned, all callbacks registered with
    :meth:`~Resource.register_did_assign_resource_callback` will be called.

    Args:
      resource: The resource to assign.
      location: The location of the resource, relative to this resource.
      reassign: If `False`, an error will be raised if the resource to be assigned is already
        assigned to this resource. Defaults to `True`.
    """

    # Check for unsupported resource assignment operations
    self._check_assignment(resource=resource, reassign=reassign)

    # Call "will assign" callbacks
    for callback in self._will_assign_resource_callbacks:
      callback(resource)

    # Modify the tree structure
    resource.parent = self
    resource.location = location
    self.children.append(resource)

    # Register callbacks on the new child resource so that they can be propagated up the tree.
    resource.register_will_assign_resource_callback(self._call_will_assign_resource_callbacks)
    resource.register_did_assign_resource_callback(self._call_did_assign_resource_callbacks)
    resource.register_will_unassign_resource_callback(self._call_will_unassign_resource_callbacks)
    resource.register_did_unassign_resource_callback(self._call_did_unassign_resource_callbacks)

    # Call "did assign" callbacks
    for callback in self._did_assign_resource_callbacks:
      callback(resource)

  # Helper methods to call all callbacks. These are used to propagate callbacks up the tree.
  def _call_will_assign_resource_callbacks(self, resource: Resource):
    for callback in self._will_assign_resource_callbacks:
      callback(resource)
  def _call_did_assign_resource_callbacks(self, resource: Resource):
    for callback in self._did_assign_resource_callbacks:
      callback(resource)
  def _call_will_unassign_resource_callbacks(self, resource: Resource):
    for callback in self._will_unassign_resource_callbacks:
      callback(resource)
  def _call_did_unassign_resource_callbacks(self, resource: Resource):
    for callback in self._did_unassign_resource_callbacks:
      callback(resource)

  def _check_assignment(self, resource: Resource, reassign: bool = True):
    """ Check if the resource assignment produces unsupported or dangerous conflicts. """
    msgs = []

    # Check for self assignment
    if resource is self:
      msgs.append(f"Cannot assign resource '{self.name}' to itself.")

    # Check for reassignment to the same (non-null) parent
    if (resource.parent is not None) and (resource.parent is self):
      if reassign:
        # Inform the user that this is redundant.
        logger.warning("Resource '%s' already assigned to '%s'", resource.name,
          resource.parent.name)
      else:
        # Else raise an error.
        msgs.append(f"Will not reassign resource '{resource.name}' " +
                    f"to the same parent: '{resource.parent.name}'.")

    # Check for pre-existing parent
    if resource.parent is not None and not reassign:
      msgs.append(f"Will not assign resource '{resource.name}' " +
                  f"that already has a parent: '{resource.parent.name}'.")

    if len(msgs) > 0:
      msg = " ".join(msgs)
      raise ValueError(msg)

  def unassign_child_resource(self, resource: Resource):
    """ Unassign a child resource from this resource.

    Before the resource is unassigned, all callbacks registered with
    :meth:`~Resource.register_will_unassign_resource_callback` will be called.

    After the resource is unassigned, all callbacks registered with
    :meth:`~Resource.register_did_unassign_resource_callback` will be called.
    """

    if resource not in self.children:
      raise ValueError(f"Resource with name '{resource.name}' is not a child of this resource "
                       f"('{self.name}').")

    # Call "will unassign" callbacks
    for callback in self._will_unassign_resource_callbacks:
      callback(resource)

    # Update the tree structure
    resource.parent = None
    self.children.remove(resource)

    # Delete callbacks on the child resource so that they are not propagated up the tree.
    resource.deregister_will_assign_resource_callback(self._call_will_assign_resource_callbacks)
    resource.deregister_did_assign_resource_callback(self._call_did_assign_resource_callbacks)
    resource.deregister_will_unassign_resource_callback(self._call_will_unassign_resource_callbacks)
    resource.deregister_did_unassign_resource_callback(self._call_did_unassign_resource_callbacks)

    # Call "did unassign" callbacks
    for callback in self._did_unassign_resource_callbacks:
      callback(resource)

  def unassign(self):
    """ Unassign this resource from its parent. """
    if self.parent is not None:
      self.parent.unassign_child_resource(self)

  def get_all_children(self) -> List[Resource]:
    """ Recursively get all children of this resource. """
    children = self.children.copy()
    for child in self.children:
      children += child.get_all_children()
    return children

  def get_resource(self, name: str) -> Resource:
    """ Get a resource by name.

    Args:
      name: The name of the resource to get.

    Returns:
      The resource with the given name.

    Raises:
      ValueError: If no resource with the given name exists.
    """

    if self.name == name:
      return self

    for child in self.children:
      try:
        return child.get_resource(name)
      except ResourceNotFoundError:
        pass

    raise ResourceNotFoundError(f"Resource with name '{name}' does not exist.")

  def rotate(self, degrees: int):
    """ Rotate counter clockwise by the given number of degrees.

    Args:
      degrees: must be a multiple of 90, but not also 360.
    """

    effective_degrees = degrees % 360

    if effective_degrees % 90 != 0:
      raise ValueError(f"Invalid rotation: {degrees}")

    for child in self.children:
      assert child.location is not None, "child must have a location when it's assigned."

      old_x = child.location.x

      if effective_degrees == 90:
        child.location.x = self.get_size_y() - child.location.y - child.get_size_y()
        child.location.y = old_x
      elif effective_degrees == 180:
        child.location.x = self.get_size_x() - child.location.x - child.get_size_x()
        child.location.y = self.get_size_y() - child.location.y - child.get_size_y()
      elif effective_degrees == 270:
        child.location.x = child.location.y
        child.location.y = self.get_size_x() - old_x - child.get_size_x()
      child.rotate(effective_degrees)

    self.rotation = (self.rotation + degrees) % 360

  def copy(self) -> Self:
    resource_copy = self.__class__.deserialize(self.serialize())
    resource_copy.load_all_state(self.serialize_all_state())
    return resource_copy

  def rotated(self, degrees: int) -> Self:
    """ Return a copy of this resource rotated by the given number of degrees.

    Args:
      degrees: must be a multiple of 90, but not also 360.
    """

    new_resource = self.copy()
    new_resource.rotate(degrees)
    return new_resource

  def center(self, x: bool = True, y: bool = True, z: bool = False) -> Coordinate:
    """ Get the center of this resource.

    Args:
      x: If `True`, the x-coordinate will be the center, otherwise it will be 0.
      y: If `True`, the y-coordinate will be the center, otherwise it will be 0.
      z: If `True`, the z-coordinate will be the center, otherwise it will be 0.

    Examples:
      Get the center of a resource in the xy plane:

      >>> r = Resource("resource", size_x=12, size_y=12, size_z=12)
      >>> r.center()

      Coordinate(x=6.0, y=6.0, z=0.0)

      Get the center of a resource with only the x-coordinate:

      >>> r = Resource("resource", size_x=12, size_y=12, size_z=12)
      >>> r.center(x=True, y=False, z=False)

      Coordinate(x=6.0, y=0.0, z=0.0)

      Get the center of a resource in the x, y, and z directions:

      >>> r = Resource("resource", size_x=12, size_y=12, size_z=12)
      >>> r.center(x=True, y=True, z=True)

      Coordinate(x=6.0, y=6.0, z=6.0)
    """

    return Coordinate(
      self.get_size_x() / 2 if x else 0,
      self.get_size_y() / 2 if y else 0,
      self.get_size_z() / 2 if z else 0
    )

  def centers(self, xn: int = 1, yn: int = 1, zn: int = 1) -> List[Coordinate]:
    """ Get equally spaced points in the x, y, and z directions.

    Args:
      xn: the number of points in the x direction.
      yn: the number of points in the y direction.
      zn: the number of points in the z direction.

    Returns:
      A grid of points in the x, y, and z directions.

    Examples:
      Get the center of a resource:

      >>> r = Resource("resource", size_x=12, size_y=12, size_z=12)
      >>> r.centers()

      Coordinate(x=6.0, y=6.0, z=6.0)

      Get the center of a resource with 2 points in the x direction:

      >>> r = Resource("resource", size_x=12, size_y=12, size_z=12)
      >>> r.centers(xn=2)

      [Coordinate(x=4.0, y=6.0, z=6.0), Coordinate(x=9.0, y=6.0, z=6.0)]

      Get the center of a resource with 2 points in the x and y directions:

      >>> r = Resource("resource", size_x=12, size_y=12, size_z=12)
      >>> r.centers(xn=2, yn=2)
      [Coordinate(x=4.0, y=4.0, z=6.0), Coordinate(x=8.0, y=4.0, z=6.0),
       Coordinate(x=4.0, y=8.0, z=6.0), Coordinate(x=8.0, y=8.0, z=6.0)]
    """

    def _get_centers(n, dim_size):
      if n < 0:
        raise ValueError(f"Invalid number of points: {n}")
      if n == 0:
        return [0]
      return [(i+1) * dim_size/(n+1)  for i in range(n)]

    xs = _get_centers(xn, self.get_size_x())
    ys = _get_centers(yn, self.get_size_y())
    zs = _get_centers(zn, self.get_size_z())

    return [Coordinate(x, y, z) for x, y, z in itertools.product(xs, ys, zs)]

  def save(self, fn: str, indent: Optional[int] = None):
    """ Save a resource to a JSON file.

    Args:
      fn: File name. Caution: file will be overwritten.
      indent: Same as `json.dump`'s `indent` argument (for json pretty printing).

    Examples:
      Saving to a json file:

      >>> from pylabrobot.resources.hamilton import STARLetDeck
      >>> deck = STARLetDeck()
      >>> deck.save("my_layout.json")
    """

    serialized = self.serialize()
    with open(fn, "w", encoding="utf-8") as f:
      json.dump(serialized, f, indent=indent)

  @classmethod
  def deserialize(cls, data: dict) -> Self:
    """ Deserialize a resource from a dictionary.

    Examples:
      Loading a resource from a json file:

      >>> from pylabrobot.resources import Resource
      >>> with open("my_resource.json", "r") as f:
      >>>   content = json.load(f)
      >>> resource = Resource.deserialize(content)
    """

    data_copy = data.copy() # copy data because we will be modifying it

    subclass = find_subclass(data["type"], cls=Resource)
    if subclass is None:
      raise ValueError(f"Could not find subclass with name '{data['type']}'")
    assert issubclass(subclass, cls) # mypy does not know the type after the None check...

    for key in ["type", "parent_name", "location"]: # delete meta keys
      del data_copy[key]
    children_data = data_copy.pop("children")
    rotation = data_copy.pop("rotation")
    resource = subclass(**data_copy)
    resource.rotation = rotation

    for child_data in children_data:
      child_cls = find_subclass(child_data["type"], cls=Resource)
      if child_cls is None:
        raise ValueError(f"Could not find subclass with name {child_data['type']}")
      child = child_cls.deserialize(child_data)
      location_data = child_data.get("location", None)
      if location_data is not None:
        location = cast(Coordinate, deserialize(location_data))
      else:
        raise ValueError(f"Child resource '{child.name}' has no location.")
      resource.assign_child_resource(child, location=location)

    return resource

  @classmethod
  def load_from_json_file(cls, json_file: str) -> Self: # type: ignore
    """ Loads resources from a JSON file.

    Args:
      json_file: The path to the JSON file.

    Examples:
      Loading a resource from a json file:

      >>> from pylabrobot.resources import Resource
      >>> resource = Resource.deserialize("my_resource.json")
    """

    with open(json_file, "r", encoding="utf-8") as f:
      content = json.load(f)

    return cls.deserialize(content)

  def register_will_assign_resource_callback(self, callback: WillAssignResourceCallback):
    """ Add a callback that will be called before a resource is assigned to this resource. These
    callbacks can raise errors in case the proposed assignment is invalid.

    Args:
      callback: The callback to add.
    """
    self._will_assign_resource_callbacks.append(callback)

  def register_did_assign_resource_callback(self, callback: DidAssignResourceCallback):
    """ Add a callback that will be called after a resource is assigned to this resource.

    Args:
      callback: The callback to add.
    """
    self._did_assign_resource_callbacks.append(callback)

  def register_will_unassign_resource_callback(self, callback: WillUnassignResourceCallback):
    """ Add a callback that will be called before a resource is unassigned from this resource.

    Args:
      callback: The callback to add.
    """
    self._will_unassign_resource_callbacks.append(callback)

  def register_did_unassign_resource_callback(self, callback: DidUnassignResourceCallback):
    """ Add a callback that will be called after a resource is unassigned from this resource.

    Args:
      callback: The callback to add.
    """
    self._did_unassign_resource_callbacks.append(callback)

  def deregister_will_assign_resource_callback(self, callback: WillAssignResourceCallback):
    """ Remove a callback that will be called before a resource is assigned to this resource.

    Args:
      callback: The callback to remove.
    """
    self._will_assign_resource_callbacks.remove(callback)

  def deregister_did_assign_resource_callback(self, callback: DidAssignResourceCallback):
    """ Remove a callback that will be called after a resource is assigned to this resource. """
    self._did_assign_resource_callbacks.remove(callback)

  def deregister_will_unassign_resource_callback(self, callback: WillUnassignResourceCallback):
    """ Remove a callback that will be called before a resource is unassigned from this resource."""
    self._will_unassign_resource_callbacks.remove(callback)

  def deregister_did_unassign_resource_callback(self, callback: DidUnassignResourceCallback):
    """ Remove a callback that will be called after a resource is unassigned from this resource. """
    self._did_unassign_resource_callbacks.remove(callback)

  # -- state --

  # Developer note: this method serializes the state of this resource only. If you want to serialize
  # a custom state for a resource, override this method in the subclass.
  def serialize_state(self) -> Dict[str, Any]:
    """ Serialize the state of this resource only.

    Use :meth:`pylabrobot.resources.resource.Resource.serialize_all_state` to serialize the state of
    this resource and all children.
    """
    return {}

  # Developer note: you probably don't need to override this method. Instead, override
  # `serialize_state`.
  def serialize_all_state(self) -> Dict[str, Dict[str, Any]]:
    """ Serialize the state of this resource and all children.

    Use :meth:`pylabrobot.resources.resource.Resource.serialize_state` to serialize the state of
    this resource only.

    Returns:
      A dictionary where the keys are the names of the resources and the values are the serialized
      states of the resources.
    """

    state = {self.name: self.serialize_state()}
    for child in self.children:
      state.update(child.serialize_all_state())
    return state

  # Developer note: this method deserializes the state of this resource only. If you want to
  # deserialize a custom state for a resource, override this method in the subclass.
  def load_state(self, state: Dict[str, Any]) -> None:
    """ Load state for this resource only. """
    # no state to load by default

  # Developer note: you probably don't need to override this method. Instead, override `load_state`.
  def load_all_state(self, state: Dict[str, Dict[str, Any]]) -> None:
    """ Load state for this resource and all children. """
    for child in self.children:
      child.load_state(state[child.name])
      child.load_all_state(state)

  def save_state_to_file(self, fn: str, indent: Optional[int] = None):
    """ Save the state of this resource and all children to a JSON file.

    Args:
      fn: File name. Caution: file will be overwritten.
      indent: Same as `json.dump`'s `indent` argument (for json pretty printing).

    Examples:
      Saving to a json file:

      >>> deck.save_state_to_file("my_state.json")
    """

    serialized = self.serialize_all_state()
    with open(fn, "w", encoding="utf-8") as f:
      json.dump(serialized, f, indent=indent)

  def load_state_from_file(self, fn: str) -> None:
    """ Load the state of this resource and all children from a JSON file.

    Args:
      fn: The file name to load the state from.

    Examples:
      Loading from a json file:

      >>> deck.load_state_from_file("my_state.json")
    """

    with open(fn, "r", encoding="utf-8") as f:
      content = json.load(f)
    self.load_all_state(content)

  def register_state_update_callback(self, callback: ResourceDidUpdateState):
    """ Register a callback that will be called when the state of the resource changes. """
    self._resource_state_updated_callbacks.append(callback)

  def deregister_state_update_callback(self, callback: ResourceDidUpdateState):
    """ Remove a callback that will be called when the state of the resource changes. """
    self._resource_state_updated_callbacks.remove(callback)

  def _state_updated(self):
    for callback in self._resource_state_updated_callbacks:
      callback(self.serialize_state())
