# from pylabrobot.resources.tip import Tip
from pylabrobot.resources.itemized_resource import create_equally_spaced
from pylabrobot.resources.tip_rack import TipRack, TipSpot
from pylabrobot.resources.tip import Tip
from .utils import get_contents_container

def load_ola_tip_rack(
  deck: "SilverDeck",
  platform_item: dict,
  platform_data: dict,
  containers_data: list) -> TipRack:
  """Create a TipRack resource from Pipettin data objects.

  In pipettin the math for the top height and fitting height of a tip in a tip rack should be:

  1. (+) Workspace's Z origin (usually 0). Get this from the Deck.
  2. (+) Platform's Z position: usually 0 for all, can be adjusted. Get this from the TipRack's
         location.
  3. (+) Platform's activeHeight (i.e. tip slot Z position): height of the surface that supports the
         tips. This is not defined in PLR (a PW slot is not a PLR spot).
  4. (+) Container's offset: Distance from the tip's tip to the tip slot, usually negative (i.e. how
         much the tip "sinks" into the tip slot). This is also undefined in PLR.
         However, in combination with (3), the equivalent PLR tip spot location can be calculated:
         (3) - (4) = TipSpot's Z
  5. (+) Total tip's length. Available in the Tip object.
         This is now the absolute top Z coordinate of the tip.
  6. ( ) Tip's activeHeight. The distance from the tip's tip to its fitting height.
         Available in the Tip object (should be equal to the tip's length minus the tip's active
         height).
         To obtain the Z coordinate at which the tip is well fitted: (4) + (6)

  In summary, the TipSpot Z coordinate should be set equal to:
      `deck_z + plat_z + plat_activeHeight - container_z_offset + tip_active_height = tip_spot_z`

  Args:
      platform_item (dict): _description_
      platform_data (dict): _description_
      containers_data (list): _description_

  Returns:
      _type_: _description_
  """

  # TODO: Find a way to avoid defaulting to the first associated container.
  # NOTE: Perhaps PLR does not consider having different tips for the same tip rack.
  #       This would be uncommon anyway.
  linked_containers = platform_data["containers"]
  default_link = linked_containers[0]
  container_data = next(x for x in containers_data if x["name"] == default_link["container"])

  # NOTE: I need to create this function here, it is required by "TipSpot" later on.
  def make_pew_tip():
    return Tip(
      has_filter=False,
      total_tip_length=container_data["length"],
      maximal_volume=container_data["maxVolume"],
      fitting_depth=container_data["length"]-container_data["activeHeight"]
    )

  # Prepare parameters for "create_equally_spaced".
  dx, dy, dz = deck.rack_to_plr_dxdydz(platform_data, default_link, container_data)

  # Create the TipRack instance.
  tip_rack_item = TipRack(
      name=platform_item["name"],
      size_x=platform_data["width"],
      size_y=platform_data["length"],
      size_z=platform_data["height"],
      category=platform_data.get("type", None), # Optional in PLR.
      model=platform_data["name"], # Optional.

      # Use the "create_equally_spaced" helper function to create a regular 2D-grid of tip spots.
      items=create_equally_spaced(
        # NOTE: Parameters for "create_equally_spaced".
        klass=TipSpot,
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
        # NOTE: Additional keyword arguments are passed to the "klass" constructor set above.
        size_x=platform_data["wellDiameter"],
        size_y=platform_data["wellDiameter"],
        # TODO: Update the function definition above to use tips from the platform definition.
        make_tip=make_pew_tip

        # XY distance between adjacent items in the grid.
        # item_size_x=platform_data["wellSeparationX"],
        # item_size_y=platform_data["wellSeparationY"],
        # The TipSpot class will receive this argument (through **kwargs) to create its tips,
        # overriding the default "TipCreator" (see "tip_rack.py"). This is only used to create tips
        # when "tip tracking" is disabled, and a tip is required from an empty tip-spot.
        # Note that this is not needed for "wells", as there are no "well spots" in PLR.
        # There are however, "tube spots" in pipettin, which I don't know how to accommodate.
      ),
      # NOTE: Skipping filling with tips for now.
      with_tips=False
    )

  # Add tips in the platform item, if any.
  platform_contents = platform_item.get("content", [])
  for content in platform_contents:
    # Position of the tip on the rack.
    content_pos = content["position"]

    # Tip properties.
    container_data = get_contents_container(content, containers_data)
    tip_container_id = container_data["name"]

    # Create the Tip.
    new_tip = Tip(
      has_filter=container_data.get("has_filter", False),
      total_tip_length=container_data["length"],
      maximal_volume=container_data["maxVolume"],
      fitting_depth=container_data["length"]-container_data["activeHeight"]
    )

    # Get the tip's position indexes.
    # NOTE: "i" for "Y/rows", and "j" for "X/columns".
    i, j = content_pos["row"]-1, content_pos["col"]-1
    # Get the TipSpot.
    tip_spot = tip_rack_item.get_item((i, j))
    # Add the Tip.
    tip_spot.tracker.add_tip(new_tip, commit=True)

    # Get the offset for this specific tip model.
    container_offset_z = next(pc["containerOffsetZ"]
                              for pc in linked_containers
                              if pc["container"] == tip_container_id)
    # Fix the Z coordinate applying the proper offset.
    tip_spot.location.z = platform_data["activeHeight"]
    tip_spot.location.z -= container_offset_z
    tip_spot.location.z += container_data["activeHeight"]

  return tip_rack_item

# Example using exported data.
if __name__ == "__main__":
  import json

  # 'data/ws_export.json'
  ws_export_file = "data/pipettin-data-20240203/Workspaces.json"

  with open(ws_export_file, "r", encoding="utf-8") as f:
    workspaces = json.load(f)
  workspace = workspaces[0]

  pt_export_file = "data/pipettin-data-20240203/Platforms.json"

  with open(pt_export_file, "r", encoding="utf-8") as f:
    platforms = json.load(f)

  # Get a tip rack platform (the first one that shows up).
  pew_tip_racks = [p for p in platforms if p["type"] == "TIP_RACK"]
  pew_tip_rack = pew_tip_racks[0]

  # Get a platform item from the workspace, matching that platform.
  pew_items = [i for i in workspace["items"] if i["platform"] == pew_tip_rack["name"] ]
  pew_item = pew_items[0]

  # Get the item's position in the workspace.
  pew_item_pos = pew_item["position"]
  #pew_item_pos

  from pylabrobot.resources.coordinate import Coordinate

  pew_item_location = Coordinate(**pew_item_pos)
  #pew_item_location

  ct_export_file = "data/pipettin-data-20240203/Containers.json"
  with open(ct_export_file, "r", encoding="utf-8") as f:
    containers = json.load(f)

  pew_item_contents = pew_item["content"]
  tip_content = pew_item_contents[0]

  tip_containers = [c for c in containers if c["name"]==tip_content["container"]]
  tip_container = tip_containers[0]

  # Get container offset
  tip_container_offsets = [o for o in pew_tip_rack["containers"]
                           if o["container"] == tip_container["name"]]
  tip_container_offset = tip_container_offsets[0]

  # Create and populate the tip rack.
  tip_rack = load_ola_tip_rack(
     platform_item=pew_item,
     platform_data=pew_tip_rack,
     containers_data=containers)

  print(tip_rack)
