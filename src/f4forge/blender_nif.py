"""Runs inside headless Blender (blender -b --python blender_nif.py -- <mode> <pynifly dir> <in> <out>).

Loads PyNifly from its tools folder by path and registers it for this process only; nothing is installed
into the user's Blender. Prints one line: F4FORGE_RESULT {json}.
"""
import json
import sys
import traceback


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mode, pynifly, src, out = argv[:4]
    import addon_utils
    import bpy
    if mode in ("import", "roundtrip"):
        bpy.ops.wm.read_factory_settings(use_empty=True)  # before enabling: a factory reset drops add-ons
    else:
        bpy.ops.wm.open_mainfile(filepath=src, load_ui=False)
    # Never write the user's preferences: the add-on is enabled for this process only.
    bpy.context.preferences.use_preferences_save = False
    sys.path.insert(0, pynifly)
    mod = addon_utils.enable("io_scene_nifly", default_set=True, persistent=False)
    if mod is None:
        raise RuntimeError("PyNifly could not be enabled from " + pynifly)
    if mode in ("import", "roundtrip"):
        res = bpy.ops.import_scene.pynifly(filepath=src)
        if "FINISHED" not in res:
            raise RuntimeError(f"import returned {res}")
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if mode == "import":
        bpy.ops.wm.save_as_mainfile(filepath=out)
    else:
        bpy.ops.object.select_all(action="DESELECT")
        for o in meshes:
            o.select_set(True)
        if meshes:
            bpy.context.view_layer.objects.active = meshes[0]
        res = bpy.ops.export_scene.pynifly(filepath=out, target_game="FO4")
        # PyNifly 30.3 returns an empty set after a successful export, so the file is the evidence.
        import os
        if "CANCELLED" in res or not os.path.isfile(out):
            raise RuntimeError(f"export returned {res} and wrote no file")
    return {"ok": True, "meshes": len(meshes), "objects": len(bpy.context.scene.objects),
            "blender": bpy.app.version_string}


try:
    result = main()
except Exception as e:  # report every failure as JSON for the forge
    result = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}
print("F4FORGE_RESULT " + json.dumps(result), flush=True)
