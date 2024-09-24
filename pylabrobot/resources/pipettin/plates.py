""" Thermo Fisher Scientific  Inc. (and all its brand) plates
Adjusted
"""

# pylint: disable=invalid-name

from pylabrobot.resources.well import Well, WellBottomType, CrossSectionType
from pylabrobot.resources.utils import create_ordered_items_2d
from pylabrobot.resources.plate import Plate

def pipettin_test_plate(name: str, with_lid: bool = False) -> Plate:
  """ Thermo Fisher Scientific/Fisher Scientific cat. no.: AB1127/10243223.

  A copy of `Thermo_TS_96_wellplate_1200ul_Rb` at `pylabrobot/resources/thermo_fisher/plates.py`.

  Faithful to the technical drawing:
  https://assets.thermofisher.com/TFS-Assets/LSG/manuals/MAN0014419_ABgene_Storage_Plate_96well_1_2mL_QR.pdf


  - Material: Polypropylene (AB-1068, polystyrene).
  - Brand: Thermo Scientific.
  - Sterilization compatibility: Autoclaving (15 minutes at 121°C) or
    Gamma Irradiation.
  - Chemical resistance: to DMSO (100%); Ethanol (100%); Isopropanol (100%).
  - Round well shape designed for optimal sample recovery or square shape to
    maximize sample volume within ANSI footprint design.
  - Each well has an independent sealing rim to prevent cross-contamination
  - U-bottomed wells ideally suited for sample resuspension.
  - Sealing options: Adhesive Seals, Heat Seals, Storage Plate Caps and Cap
    Strips, and Storage Plate Sealing Mats.
  - Cleanliness: 10243223/AB1127: Cleanroom manufacture.
  - ANSI/SLAS-format for compatibility with automated systems.
  """

  if with_lid:
    raise NotImplementedError("This lid is not currently defined.")

  return Plate(
    name=name,
    size_x=127.76,
    size_y=85.48,
    size_z=24.0,
    lid=None,
    model="Thermo_TS_96_wellplate_1200ul_Rb",
    ordered_items=create_ordered_items_2d(Well,
      num_items_x=12,
      num_items_y=8,
      dx=10.18,   # Should be 10.23 (14.38 - 8.4/2), not 10.0.
      dy=7.04,    # Should be 7.09 (11.24 - 8.4/2), not 7.3.
      dz=2.5, # 2.5. https://github.com/PyLabRobot/pylabrobot/pull/183
      item_dx=9,
      item_dy=9,
      size_x=8.4, # Should be 8.4, not 8.3.
      size_y=8.4, # Should be 8.4, not 8.3.
      size_z=20.5,
      bottom_type=WellBottomType.U,
      material_z_thickness=1.15,
      cross_section_type=CrossSectionType.RECTANGLE,
      # NOTE: Disabled these as I did not want to deal with import errors.
      # compute_volume_from_height=(
      #   _compute_volume_from_height_Thermo_TS_96_wellplate_1200ul_Rb
      # ),
      # compute_height_from_volume=(
      #   _compute_height_from_volume_Thermo_TS_96_wellplate_1200ul_Rb
      # )
    ),
  )
