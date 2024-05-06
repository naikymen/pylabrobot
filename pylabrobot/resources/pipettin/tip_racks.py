# from pylabrobot.resources.tip import Tip
from pylabrobot.resources.itemized_resource import create_equally_spaced
from pylabrobot.resources.tip_rack import TipRack, TipSpot

def load_ola_tip_rack(platform_item, platform_data, *args, **kwargs):

  # def make_pew_tip():
  #   """ Make single tip.

  #   Attributes from the Tip class:
  #     has_filter: whether the tip type has a filter
  #     total_tip_length: total length of the tip, in in mm
  #     maximal_volume: maximal volume of the tip, in ul
  #     fitting_depth: the overlap between the tip and the pipette, in mm
  #   """
  #   tip = Tip(
  #     has_filter=False,
  #     total_tip_length=container_data["length"],
  #     maximal_volume=container_data["maxVolume"],
  #     fitting_depth=container_data["length"]-container_data["activeHeight"]
  #   )

  #   return tip

  tip_rack_item = TipRack(
      name=platform_item["name"],
      size_x=platform_data["width"],
      size_y=platform_data["length"],
      size_z=platform_data["height"],
      # category = "tip_rack", # The default.
      model=platform_data["name"], # Optional.
      items=create_equally_spaced(
        klass=TipSpot,
        num_items_x=platform_data["wellsColumns"],
        num_items_y=platform_data["wellsRows"],
        # item_dx: The size of the items in the x direction
        item_dx=platform_data["wellSeparationX"],
        # item_dy: The size of the items in the y direction
        item_dy=platform_data["wellSeparationY"],
        # dx: The X coordinate of the bottom left corner for items in the left column.
        dx=platform_data["firstWellCenterX"] - platform_data["wellSeparationX"]/2,
        # dy: The Y coordinate of the bottom left corner for items in the top row.
        dy=platform_data["length"]-platform_data["firstWellCenterY"]-platform_data["wellSeparationY"]*(0.5+platform_data["wellsRows"]),
        # dz: The z coordinate for all items.
        # TODO: I dont know how "dz" is used later on. Check that it corresponds to activeHeight.
        dz=platform_data["activeHeight"],
        # XY distance between adjacent items in the grid.
        item_size_x=platform_data["wellSeparationX"],
        item_size_y=platform_data["wellSeparationY"],
        # The TipSpot class will receive this argument (through **kwargs) to create its tips,
        # overriding the default "TipCreator" (see "tip_rack.py"). This is only used to create tips
        # when "tip tracking" is disabled, and a tip is required from an empty tip-spot.
        # Note that this is not needed for "wells", as there are no "well spots" in PLR.
        # There are however, "tube spots" in pipettin, which I don't know how to accommodate.
        # TODO: reconsider enabling this.
        #make_tip=make_pew_tip
      ),
      # NOTE: Skipping filling with tips for now.
      with_tips=False
    )

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
  tip_container_offsets = [o for o in pew_tip_rack["containers"] if o["container"] == tip_container["name"]]
  tip_container_offset = tip_container_offsets[0]

  # Create and populate the tip rack.
  tip_rack = load_ola_tip_rack(
     platform_item=pew_item,
     platform_data=pew_tip_rack,
     tip_container=tip_container)

  print(tip_rack)
