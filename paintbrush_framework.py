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

# Addon imports
from ..undo_stack import *
from ....lib.bricksDict.functions import getDictKey


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


class paintbrushFramework:
    """ modal framework for the paintbrush tool """

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

    ###################################################
    # class variables

    BrickSculptInstalled = True
    BrickSculptLoaded = True

    #############################################
    # class methods

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

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        context.area.header_text_set()
        bpy.props.running_paintbrush = False
        self.ui_end()

    ##########################
