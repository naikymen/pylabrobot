# from pylabrobot.resources.tip import Tip
from pylabrobot.resources.utils import create_ordered_items_2d
from pylabrobot.resources.tip_rack import TipRack, TipSpot
from pylabrobot.resources.tip import Tip
from pylabrobot.resources.resource import Rotation, Coordinate
from .utils import get_contents_container, get_fitting_depth
from newt.translators.utils import rack_to_plr_dxdydz
from newt.utils import guess_shape

def load_ola_tip_rack(
  deck: "SilverDeck",
  platform_item: dict,
  platform_data: dict,
  tools_data: dict,
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

  # "tip_stages": {
  #   "default": "p200",
  #   "p200": {
  #     "vol_max": 200,
  #     "flowrate": 100,
  #     "z_offset": 0,
  #     "z_offset.description": "Distance at which the stip stage begins, relative to the end of the tip holder.",
  #     "tip_fit_distance": {
  #       "200 uL Tip": 4.8,
  #       "200 uL Tip Tarsons": 4.3
  #     },
  #     "tip_fit_distance.description": "Fitting depth for each tip definition in the containers database.",
  #     "probe_extra_dist": 1,
  #     "tip_ejector": {
  #       "e_start": 22,
  #       "e_end": 27,
  #       "eject_feedrate": 200
  #     },
  #     "tension_correction": {
  #       "start_vol": 20,
  #       "max_correction": 2
  #     }
  #   }
  # },

  # Get platform-container links.
  linked_containers = platform_data["containers"]
  compatible_tips = []
  for link in linked_containers:
    container_data = get_contents_container(link, containers_data)
    tip_container_id = container_data["name"]
    # Get fitting depths.
    fitting_depth = get_fitting_depth(tools_data, tip_container_id)
    compatible_tip = Tip(
      has_filter=False,
      total_tip_length=container_data["length"],
      maximal_volume=container_data["maxVolume"],
      fitting_depth=fitting_depth,
      category=container_data["type"],  # "tip"
      model=tip_container_id
    )
    compatible_tip.active_z = container_data["activeHeight"]
    compatible_tips.append({
      "content": compatible_tip,
      # Save the "containerOffsetZ" here, to restore it later on export.
      "link": link
    })

  # NOTE: I need to create this function here, it is required by "TipSpot" later on.
  def make_pew_tip():
    return compatible_tips[0]["content"]

  # First spot offsets.
  # TODO: Override "dz"/default_link the the appropriate offset for each tip.
  default_link = linked_containers[0]
  # TODO: Consider setting "dz" to zero in this case, and apply "containerOffsetZ" later.
  dx, dy, dz = rack_to_plr_dxdydz(platform_data, default_link)

  # Use the "create_ordered_items_2d" helper function to create a regular 2D-grid of tip spots.
  ordered_items = create_ordered_items_2d(
    # NOTE: Parameters for "create_ordered_items_2d".
    klass=TipSpot,
    num_items_x=platform_data["wellsColumns"],
    num_items_y=platform_data["wellsRows"],
    # dx: The X coordinate of the bottom left corner for items in the left column.
    # dy: The Y coordinate of the bottom left corner for items in the top row.
    # dz: The z coordinate for all items.
    dx=dx, dy=dy, dz=dz,
    # item_dx: The separation of the items in the x direction
    item_dx=platform_data["wellSeparationX"],
    # item_dy: The separation of the items in the y direction
    item_dy=platform_data["wellSeparationY"],

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
  )

  # Guess the shape of the platform.
  size_x, size_y, shape = guess_shape(platform_data)

  # Create the TipRack instance.
  tip_rack_item = TipRack(
    name=platform_item["name"],
    size_x=size_x,
    size_y=size_y,
    size_z=platform_data["height"],
    category=platform_data.get("type", None), # Optional in PLR.
    model=platform_data["name"], # Optional.
    ordered_items=ordered_items,
    # NOTE: Skipping filling with tips for now.
    with_tips=False
  )
  # Save the platform's active height.
  # This will help recover some information later.
  tip_rack_item.active_z = platform_data["activeHeight"]
  # Save the platform's shape.
  tip_rack_item.shape = shape
  # Compatible children.
  tip_rack_item.compatibles = compatible_tips
  # Locked state.
  tip_rack_item.locked = platform_item.get("locked", None)
  # TODO: Add rotation, even though it wont be usable and cause crashes.
  tip_rack_item.rotation = Rotation(z=platform_data["rotation"])

  # Add tips in the platform item, if any.
  platform_contents = platform_item.get("content", [])
  for content in platform_contents:
    # Position of the tip on the rack.
    content_pos = content["position"]

    # Get this tip's container data.
    container_data = get_contents_container(content, containers_data)
    tip_container_id = container_data["name"]

    # Get fitting depths.
    fitting_depth = get_fitting_depth(tools_data, tip_container_id)

    # Create the Tip.
    new_tip = Tip(
      has_filter=container_data.get("has_filter", False),
      total_tip_length=container_data["length"],
      maximal_volume=container_data["maxVolume"],
      fitting_depth=fitting_depth,
      model=tip_container_id,
      category=container_data["type"],  # "tip"
      # # TODO: Names must be unique. This should be checked for tips and tubes.
      name=content["name"]
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
    # Fix the Z coordinate applying the offset
    # of this particular tip.
    tip_spot.location.z = platform_data["activeHeight"]
    tip_spot.location.z -= container_offset_z

  # Save the platform's active height such that "container_offset_z" can
  # be recovered later on (e.g. during an export) with the following formula:
  #   "container_offset_z = tip_rack_item.active_z - tip_spot.location.z"
  tip_rack_item.active_z = platform_data["activeHeight"]

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
  # TODO: Convert this to a test.
  # tip_rack = load_ola_tip_rack(
  #    platform_item=pew_item,
  #    platform_data=pew_tip_rack,
  #    containers_data=containers)
  # print(tip_rack)
