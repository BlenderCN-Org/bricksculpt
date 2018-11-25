"""
    Copyright (C) 2018 Bricks Brought to Life
    http://bblanimation.com/
    chris@bblanimation.com

    Created by Christopher Gearhart

        This program is free software: you can redistribute it and/or modify
        it under the terms of the GNU General Public License as published by
        the Free Software Foundation, either version 3 of the License, or
        (at your option) any later version.

        This program is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU General Public License for more details.

        You should have received a copy of the GNU General Public License
        along with this program.  If not, see <http://www.gnu.org/licenses/>.
    """

# System imports
# NONE!

# Blender imports
import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d
from bpy.types import Operator, SpaceView3D, bpy_struct

# Addon imports
from .drawAdjacent import *
from ..undo_stack import *
from ..functions import *
from ...brickify import *
from ....lib.Brick import *
from ....lib.bricksDict.functions import getDictKey
from ....functions import *
from ....operators.delete import OBJECT_OT_delete_override


def get_quadview_index(context, x, y):
    for area in context.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        is_quadview = len(area.spaces.active.region_quadviews) == 0
        i = -1
        for region in area.regions:
            if region.type == 'WINDOW':
                i += 1
                if (x >= region.x and
                    y >= region.y and
                    x < region.width + region.x and
                    y < region.height + region.y):

                    return (area.spaces.active, None if is_quadview else i)
    return (None, None)


class paintbrushTools:
    """ functionality from the paintbrush tool """

    ################################################
    # Blender Operator methods

    def modal(self, context, event):
        try:
            # commit changes on return key press
            if event.type == "ESC" and event.value == "PRESS":
                bpy.context.window.cursor_set("DEFAULT")
                self.cancel(context)
                self.undo_stack.undo_pop_clean()
                return{"CANCELLED"}

            # commit changes on return key press
            if event.type == "RET" and event.value == "PRESS":
                bpy.context.window.cursor_set("DEFAULT")
                self.cancel(context)
                self.commitChanges()
                return{"FINISHED"}

            # block undo action
            if event.type == "Z" and (event.ctrl or event.oskey):
                return {"RUNNING_MODAL"}

            # check if left_click is pressed
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                self.left_click = True
                # block left_click if not in 3D viewport
                space, i = get_quadview_index(context, event.mouse_x, event.mouse_y)
                if space is None:
                    return {"RUNNING_MODAL"}
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                self.left_click = False

            # clear recentlyAddedBricks on mousemove when left_click not pressed
            if event.type == "MOUSEMOVE" and len(self.recentlyAddedBricks) > 0 and not self.left_click:
                self.recentlyAddedBricks = []

            # cast ray to calculate mouse position and travel
            if event.type in ['TIMER', 'MOUSEMOVE'] or self.left_click:
                scn, cm, n = getActiveContextInfo()
                self.mouse = Vector((event.mouse_region_x, event.mouse_region_y))
                self.mouseTravel = abs(self.mouse.x - self.lastMouse.x) + abs(self.mouse.y - self.lastMouse.y)
                self.hover_scene(context, self.mouse.x, self.mouse.y, cm.source_name, update_header=self.left_click)
                # self.update_ui_mouse_pos()
                if self.obj is None:
                    bpy.context.window.cursor_set("DEFAULT")
                    return {"PASS_THROUGH"}
                else:
                    bpy.context.window.cursor_set("PAINT_BRUSH")

            # draw/remove bricks on left_click & drag
            if self.left_click and (event.type == 'LEFTMOUSE' or (event.type == "MOUSEMOVE" and (not event.alt or self.mouseTravel > 5))):
                self.lastMouse = self.mouse
                # determine which action (if any) to run at current mouse position
                addBrick = not (event.alt or self.obj.name in self.recentlyAddedBricks) and self.mode == "BRICK"
                removeBrick = event.alt and self.mode == "BRICK"
                changeMaterial = self.obj.name not in self.addedBricks and self.mode == "MATERIAL"
                splitBrick = self.mode == "SPLIT/MERGE" and (event.alt or event.shift)
                mergeBrick = self.obj.name not in self.addedBricks and self.mode == "SPLIT/MERGE" and not event.alt
                # get key/loc/size of brick at mouse position
                if addBrick or removeBrick or changeMaterial or splitBrick or mergeBrick:
                    curKey = getDictKey(self.obj.name)
                    curLoc = getDictLoc(self.bricksDict, curKey)
                    objSize = self.bricksDict[curKey]["size"]
                # add brick next to existing brick
                if addBrick and self.bricksDict[curKey]["name"] not in self.recentlyAddedBricks:
                    self.addBrick(cm, curKey, curLoc, objSize)
                # remove existing brick
                elif removeBrick:
                    self.removeBrick(cm, n, event, curKey, curLoc, objSize)
                # change material
                elif changeMaterial and self.bricksDict[curKey]["mat_name"] != self.matName:
                    self.changeMaterial(cm, n, curKey, curLoc, objSize)
                # split current brick
                elif splitBrick:
                    self.splitBrick(cm, event, curKey, curLoc, objSize)
                # add current brick to 'self.keysToMerge'
                elif mergeBrick:
                    self.mergeBrick(cm, curKey, curLoc, objSize, state="DRAG")
                return {"RUNNING_MODAL"}

            # clear bricks added from delete's auto update
            if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self.mode == "BRICK":
                self.addedBricksFromDelete = []

            # clean up after splitting bricks
            if event.type in ["LEFT_ALT", "RIGHT_ALT", "LEFT_SHIFT", "RIGHT_SHIFT"] and event.value == "RELEASE" and self.mode == "SPLIT/MERGE":
                deselectAll()

            # merge bricks in 'self.keysToMerge'
            if event.type == "LEFTMOUSE" and event.value == "RELEASE" and self.mode == "SPLIT/MERGE" and not (event.alt or event.shift):
                scn, cm, n = getActiveContextInfo()
                self.mergeBrick(cm, state="RELEASE")

            return {"PASS_THROUGH"}
        except:
            bpy.context.window.cursor_set("DEFAULT")
            self.cancel(context)
            handle_exception()
            return {"CANCELLED"}

    # def invoke(self, context, event):
    #     return context.window_manager.invoke_props_popup(self, event)

    ###################################################
    # class variables

    BrickSculptInstalled = True

    #############################################
    # class methods

    def addBrick(self, cm, curKey, curLoc, objSize):
        # get difference between intersection loc and object loc
        locDiff = self.loc - transformToWorld(Vector(self.bricksDict[curKey]["co"]), self.parent.matrix_world, self.junk_bme)
        locDiff = transformToLocal(locDiff, self.parent.matrix_world)
        nextLoc = getNearbyLocFromVector(locDiff, curLoc, self.dimensions, cm.zStep, width_divisor=3.2 if self.brickType in getRoundBrickTypes() else 2.05)
        # draw brick at nextLoc location
        nextKey, adjBrickD = drawAdjacent.getBrickD(self.bricksDict, nextLoc)
        if not adjBrickD or self.bricksDict[nextKey]["val"] == 0 and self.bricksDict[curKey]["name"] not in self.recentlyAddedBricks:
            self.adjDKLs = getAdjDKLs(cm, self.bricksDict, curKey, self.obj)
            # add brick at nextKey location
            status = drawAdjacent.toggleBrick(cm, self.bricksDict, self.adjDKLs, [[False]], self.dimensions, nextLoc, curKey, curLoc, objSize, self.brickType, 0, 0, self.keysToMerge, temporaryBrick=True)
            if not status["val"]:
                self.report({status["report_type"]}, status["msg"])
            self.addedBricks.append(self.bricksDict[nextKey]["name"])
            self.recentlyAddedBricks.append(self.bricksDict[nextKey]["name"])
            self.targettedBrickKeys.append(curKey)
            # draw created bricks
            drawUpdatedBricks(cm, self.bricksDict, [nextKey], action="adding new brick", selectCreated=False, tempBrick=True)

    def removeBrick(self, cm, n, event, curKey, curLoc, objSize):
        shallowDelete = self.obj.name in self.addedBricks
        deepDelete = event.shift and not (shallowDelete or self.obj.name in self.addedBricksFromDelete)
        if deepDelete:
            # split bricks and update adjacent brickDs
            brickKeys, curKey = self.splitBrickAndGetNearest1x1(cm, n, curKey, curLoc)
            curLoc = getDictLoc(self.bricksDict, curKey)
            keysToUpdate, onlyNewKeys = OBJECT_OT_delete_override.updateAdjBricksDicts(self.bricksDict, cm.zStep, curKey, curLoc, [])
            self.addedBricksFromDelete += [self.bricksDict[k]["name"] for k in onlyNewKeys]
        if shallowDelete:
            # remove current brick from addedBricks
            self.addedBricks.remove(self.bricksDict[curKey]["name"])
        if shallowDelete or deepDelete:
            # reset bricksDict values
            self.bricksDict[curKey]["draw"] = False
            self.bricksDict[curKey]["val"] = 0
            self.bricksDict[curKey]["parent"] = None
            self.bricksDict[curKey]["created_from"] = None
            self.bricksDict[curKey]["flipped"] = False
            self.bricksDict[curKey]["rotated"] = False
            self.bricksDict[curKey]["top_exposed"] = False
            self.bricksDict[curKey]["bot_exposed"] = False
            brick = bpy.data.objects.get(self.bricksDict[curKey]["name"])
            if brick is not None:
                delete(brick)
                tag_redraw_areas()
        if deepDelete:
            # draw created bricks
            drawUpdatedBricks(cm, self.bricksDict, uniquify(brickKeys + keysToUpdate), action="updating surrounding bricks", selectCreated=False, tempBrick=True)
            self.keysToMerge += brickKeys + keysToUpdate

    def changeMaterial(self, cm, n, curKey, curLoc, objSize):
        if max(objSize[:2]) > 1:
            brickKeys, curKey = self.splitBrickAndGetNearest1x1(cm, n, curKey, curLoc)
        else:
            brickKeys = [curKey]
        self.bricksDict[curKey]["mat_name"] = self.matName
        self.bricksDict[curKey]["custom_mat_name"] = True
        self.addedBricks.append(self.bricksDict[curKey]["name"])
        self.keysToMerge += brickKeys
        # draw created bricks
        drawUpdatedBricks(cm, self.bricksDict, brickKeys, action="updating material", selectCreated=False, tempBrick=True)

    def splitBrick(self, cm, event, curKey, curLoc, objSize):
        brick = bpy.data.objects.get(self.bricksDict[curKey]["name"])
        if (event.alt and max(self.bricksDict[curKey]["size"][:2]) > 1) or (event.shift and self.bricksDict[curKey]["size"][2] > 1):
            brickKeys = Bricks.split(self.bricksDict, curKey, cm.zStep, cm.brickType, loc=curLoc, v=event.shift, h=event.alt)
            self.allUpdatedKeys += brickKeys
            # remove large brick
            brick = bpy.data.objects.get(self.bricksDict[curKey]["name"])
            delete(brick)
            # draw split bricks
            drawUpdatedBricks(cm, self.bricksDict, brickKeys, action="splitting bricks", selectCreated=True, tempBrick=True)
        else:
            select(brick)

    def mergeBrick(self, cm, curKey=None, curLoc=None, objSize=None, state="DRAG"):
        if state == "DRAG":
            # TODO: Light up bricks as they are selected to be merged
            brickKeys = getKeysInBrick(self.bricksDict, objSize, cm.zStep, curKey, curLoc)
            self.keysToMerge += brickKeys
            self.addedBricks.append(self.bricksDict[curKey]["name"])
            select(self.obj)
        elif state == "RELEASE":
            if len(self.keysToMerge) > 1:
                # delete outdated brick
                for obj_name in self.addedBricks:
                    delete(bpy.data.objects.get(obj_name))
                # split up bricks
                Bricks.splitAll(self.bricksDict, cm.zStep, keys=self.keysToMerge)
                # merge bricks after they've been split
                mergedKeys = mergeBricks.mergeBricks(self.bricksDict, self.keysToMerge, cm, anyHeight=True)
                self.allUpdatedKeys += mergedKeys
                # draw merged bricks
                drawUpdatedBricks(cm, self.bricksDict, mergedKeys, action="merging bricks", selectCreated=False, tempBrick=True)
            # reset lists
            self.keysToMerge = []
            self.addedBricks = []

    # from CG Cookie's retopoflow plugin
    def hover_scene(self, context, x, y, source_name, update_header=True):
        """ casts ray through point x,y and sets self.obj if obj intersected """
        scn = context.scene
        self.region = context.region
        self.r3d = context.space_data.region_3d
        rv3d = context.region_data
        if rv3d is None:
            return None
        coord = x, y
        ray_max = 1000000  # changed from 10000 to 1000000 to increase accuracy
        view_vector = region_2d_to_vector_3d(self.region, rv3d, coord)
        ray_origin = region_2d_to_origin_3d(self.region, rv3d, coord)
        ray_target = ray_origin + (view_vector * ray_max)

        result, loc, normal, idx, obj, mx = scn.ray_cast(ray_origin, ray_target)

        if result and obj.name.startswith('Bricker_' + source_name):
            self.obj = obj
            self.loc = loc
            self.normal = normal
        else:
            self.obj = None
            self.loc = None
            self.normal = None
            context.area.header_text_set()

    def splitBrickAndGetNearest1x1(self, cm, n, curKey, curLoc):
        brickKeys = Bricks.split(self.bricksDict, curKey, cm.zStep, cm.brickType, loc=curLoc, v=True, h=True)
        brick = bpy.data.objects.get(self.bricksDict[curKey]["name"])
        delete(brick)
        # get difference between intersection loc and object loc
        minDiff = None
        for k in brickKeys:
            brickLoc = transformToWorld(Vector(self.bricksDict[k]["co"]), self.parent.matrix_world, self.junk_bme)
            locDiff = abs(self.loc[0] - brickLoc[0]) + abs(self.loc[1] - brickLoc[1]) + abs(self.loc[2] - brickLoc[2])
            if minDiff is None or locDiff < minDiff:
                minDiff = locDiff
                curKey = k
        return brickKeys, curKey

    def commitChanges(self):
        scn, cm, _ = getActiveContextInfo()
        keysToUpdate = []
        # execute final operations for current mode
        if self.mode == "SPLIT/MERGE":
            deselectAll()
            keysToUpdate = uniquify(self.allUpdatedKeys)
            # set exposure of split bricks
            for k in keysToUpdate:
                setAllBrickExposures(self.bricksDict, cm.zStep, k)
        elif self.mode in ["MATERIAL", "BRICK"]:
            self.keysToMerge = uniquify(self.keysToMerge)
            # attempt to merge created bricks
            if mergableBrickType(self.brickType):
                mergedKeys = mergeBricks.mergeBricks(self.bricksDict, self.keysToMerge, cm, targetType="BRICK" if cm.brickType == "BRICKS AND PLATES" else self.brickType)
            else:
                mergedKeys = self.keysToMerge
            # set exposure of created bricks and targetted bricks
            keysToUpdate = uniquify(mergedKeys + (self.targettedBrickKeys if self.mode == "BRICK" else []))
            for k in keysToUpdate:
                setAllBrickExposures(self.bricksDict, cm.zStep, k)
            # remove merged 1x1 bricks
            for k in self.keysToMerge:
                if k not in mergedKeys:
                    delete(bpy.data.objects.get(self.bricksDict[k]["name"]))
        # draw updated bricks
        drawUpdatedBricks(cm, self.bricksDict, keysToUpdate, action="committing changes", selectCreated=False)

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        context.area.header_text_set()
        bpy.props.running_paintbrush = False
        self.ui_end()

    ##########################
