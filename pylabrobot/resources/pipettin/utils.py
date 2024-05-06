def get_items_platform(item, platforms):
  """Get the data for a platform item."""
  platform_data = next(x for x in platforms if x["name"] == item.get("platform"))
  return platform_data

def get_contents_container(content, containers):
  """Get the container data for a content."""
  container_data = next(x for x in containers if x["name"] == content.get("container"))
  return container_data
