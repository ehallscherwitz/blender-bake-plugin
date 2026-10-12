# Sidebar version. 0.5.0 is the one-map bake, with island size based on world size.
# bl_info in __init__.py must repeat this tuple as a literal. Blender will not load the addon otherwise.

VERSION = (0, 5, 0)


def version_string():
    return ".".join(str(part) for part in VERSION)
