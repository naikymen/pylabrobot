from pylabrobot.resources import Coordinate, Resource

class Anchor(Resource):
  """A carrier-like resource for PW Anchors."""

  resource: Resource = None
  active_height: float = 0.0

  def assign_child_resource(self,
                            resource: Resource,
                            # NOTE: Location is deduced from slot. This offset is added.
                            offset: Coordinate = Coordinate.zero()):

    # Check that the anchor is empty.
    assert self.resource is None, "The anchor is occupied by another resource."

    # Convert PW rotation angle of anchors to XY offsets for PLR.
    x = (-resource.get_size_x() if self.rotation in [90, 180] else 0.0)
    y = (-resource.get_size_y() if self.rotation in [0, 90] else 0.0)
    # Note that "activeHeight" must be added to the location here.
    # This is needed to apply the Z offset added by the anchor,
    # to the calculation in "get_absolute_location".
    z = self.active_height
    # Add the provided offset if any.
    location = Coordinate(x, y, z) + offset

    # Assign the resource as usual.
    super().assign_child_resource(resource, location)
    # TODO: Check if instead I would like the anchor to assign this
    #       new child to the anchor's parent. This would match the
    #       behavior of anchors in PW, which do not "contain" resources,
    #       technically they only "align" them to the workspace.
    # For example:
    # self.parent.assign_child_resource(resource, location)

    # Save the resource to the anchor.
    self.resource = resource

  def unassign_child_resource(self, resource):
    self.resource = None
    return super().unassign_child_resource(resource)

def load_ola_anchor(platform_item, platform_data, **kwargs):
  anchor = Anchor(
    name=platform_item["name"],
    size_x=platform_data["width"],
    size_y=platform_data["length"],
    size_z=platform_data["height"],
    category=platform_data.get("type", None), # Optional in PLR.
    model=platform_data.get("name", None) # Optional in PLR (not documented in Resource).
  )
  # NOTE: Because "size_z" is not propagated to the location of child resources,
  #       I will save the "activeHeight" to a new class attribute.
  anchor.active_height = platform_data["activeHeight"]
  # Apply rotations using the method from Resource.
  # TODO: Check that it works as expected.
  anchor.rotate(platform_data.get("rotation", 0))
  return anchor
