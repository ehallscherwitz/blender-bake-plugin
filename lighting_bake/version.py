# Sidebar version. 0.6.0 is the failure pass: skip bad meshes and keep baking the rest.
# bl_info in __init__.py must repeat this tuple as a literal. Blender will not load the addon otherwise.

VERSION = (0, 6, 0)


def version_string():
    return ".".join(str(part) for part in VERSION)
