from pylabrobot.resources.tip import Tip
from pylabrobot.resources.itemized_resource import create_equally_spaced
from pylabrobot.resources.tip_rack import TipRack, TipSpot

def create_tip_rack(platform_item, platform_data, tip_container):

  def make_pew_tip():
    """ Make single tip.

    Attributes from the Tip class:
      has_filter: whether the tip type has a filter
      total_tip_length: total length of the tip, in in mm
      maximal_volume: maximal volume of the tip, in ul
      fitting_depth: the overlap between the tip and the pipette, in mm
    """
    tip = Tip(
      has_filter=False,
      total_tip_length=tip_container["length"],
      maximal_volume=tip_container["maxVolume"],
      fitting_depth=tip_container["length"]-tip_container["activeHeight"]
    )

    return tip

  tip_rack_item = TipRack(
      name=platform_item["name"],
      size_x=platform_data["width"],
      size_y=platform_data["length"],
      size_z=platform_data["height"],
      # category = "tip_rack", # The default.
      model=platform_data["name"], # Optional.
      items=create_equally_spaced(TipSpot,
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
        item_size_y=platform_data["wellSeparationY"],
        # TODO: This function should be replaced.
        # make_tip=standard_volume_tip_with_filter,
        make_tip=make_pew_tip
      ),
      with_tips=False
    )

  return tip_rack_item


if __name__ == "main":
  import json

  # 'data/ws_export.json'
  ws_export_file = 'data/pipettin-data-20240203/Workspaces.json'
  with open(ws_export_file, 'r', encoding='utf-8') as f:
      workspaces = json.load(f)
  workspace = workspaces[0]

  pt_export_file = 'data/pipettin-data-20240203/Platforms.json'
  with open(pt_export_file, 'r', encoding='utf-8') as f:
      platforms = json.load(f)

  # Get a tip rack platform (the first one that shows up).
  pew_tip_racks = [p for p in platforms if p["type"] == "TIP_RACK"]
  pew_tip_rack = pew_tip_racks[0]

  # Get a workspace item matching that platform.
  pew_items = [i for i in workspace["items"] if i["platform"] == pew_tip_rack["name"] ]
  pew_item = pew_items[0]

  # Get the item's position in the workspace.
  pew_item_pos = pew_item["position"]
  #pew_item_pos

  from pylabrobot.resources.coordinate import Coordinate

  pew_item_location = Coordinate(**pew_item_pos)
  #pew_item_location

  ct_export_file = 'data/pipettin-data-20240203/Containers.json'
  with open(ct_export_file, 'r', encoding='utf-8') as f:
      containers = json.load(f)

  pew_item_contents = pew_item["content"]
  tip_content = pew_item_contents[0]

  tip_container = [c for c in containers if c["name"]==tip_content["container"]][0]
  #tip_container

  # Get container offset
  tip_container_offset = [o for o in pew_tip_rack["containers"] if o["container"] == tip_container["name"]][0]
  #tip_container_offset

  # Create and populate the tip rack.
  tip_rack = create_tip_rack(
     platform_item=pew_item,
     platform_data=pew_tip_rack,
     tip_container=tip_container)

  print(tip_rack)
