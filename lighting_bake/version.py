# Sidebar version. 0.4.2 matches the bake confirmation to Individual or One map.
# bl_info in __init__.py must repeat this tuple as a literal. Blender will not load the addon otherwise.

VERSION = (0, 4, 2)


def version_string():
    return ".".join(str(part) for part in VERSION)
