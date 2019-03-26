# Copyright (C) 2018 Christopher Gearhart
# chris@bblanimation.com
# http://bblanimation.com/
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# System imports
# NONE!

# Blender imports
import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d

# Addon imports
from ....lib.bricksDict.functions import *
from ....functions.common.blender import *
from ....lib.addon_common.cookiecutter.cookiecutter import CookieCutter


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


class bricksculpt_framework:
    """ modal framework for the paintbrush tool """

    #############################################
    # State keymap

    default_keymap = {
        # swith modes
        "switch_mode draw": {"D"},
        "switch_mode merge_split": {"M"},
        "switch_mode paint": {"P"},
        # execute action
        "add brick": {"LEFTMOUSE"},
        "remove brick": {"ALT+LEFTMOUSE", "SHIFT+LEFTMOUSE"},
        "split": {"ALT+LEFTMOUSE", "SHIFT+LEFTMOUSE"},
        "merge": {"LEFTMOUSE"},
        "paint": {"LEFTMOUSE"},
        # end bricksculpt
        "commit": {"RET"},
        "cancel": {"ESC"},
    }

    #############################################
    # State functions

    @CookieCutter.FSM_State("main")
    def modal_main(self):
        if self.mode == "DRAW":
            return "draw wait"
        elif self.mode == "MERGE/SPLIT":
            return "merge_split wait"
        elif self.mode == "PAINT":
            return "paint wait"

    #-------------------------------------------#
    # DRAW WAIT

    @CookieCutter.FSM_State("draw wait", "enter")
    def enter_draw_wait(self):
        self.addedBricks = []
        self.set_ui_text()

    @CookieCutter.FSM_State("draw wait")
    def modal_draw_wait(self):
        self.update_hover_scene()
        # switch state
        if self.actions.pressed("add brick"):
            return "add brick"
        if self.actions.pressed("remove brick"):
            return "remove brick"
        # switch mode
        if self.actions.pressed("switch_mode merge_split"):
            return "merge_split wait"
        if self.actions.pressed("switch_mode paint"):
            return "paint wait"
        # other actions
        if self.actions.pressed("commit"):
            self.done();
            return
        if self.actions.pressed("cancel"):
            self.done(cancel=True)
            return

    #-------------------------------------------#
    # ADD BRICK

    @CookieCutter.FSM_State("add brick", "enter")
    def enter_add_brick(self):
        self.lastMouse = Vector((-1000, -1000))

    @CookieCutter.FSM_State("add brick")
    def modal_add_brick(self):
        cm, n, curKey, curLoc, objSize = self.update_hover_scene()
        if self.obj is not None and self.mouseTravel > 5 and not self.obj.name in self.keysToMergeOnRelease and self.bricksDict[curKey]["name"] not in self.addedBricks:
            # add brick next to existing brick
            self.addBrick(cm, n, curKey, curLoc, objSize)
        # switch state
        if self.actions.released("add brick"):
            return "draw wait"

    @CookieCutter.FSM_State("add brick", "exit")
    def exit_add_brick(self):
        # merge bricks in 'self.keysToMerge'
        scn, cm, n = getActiveContextInfo()
        self.mergeBrick(cm, n, mode=self.mode, state="RELEASE")
        self.releaseTime = time.time()
        # clear bricks added from delete's auto update
        self.addedBricksFromDelete = []

    #-------------------------------------------#
    # REMOVE BRICK

    @CookieCutter.FSM_State("remove brick", "enter")
    def enter_remove_brick(self):
        self.lastMouse = Vector((-1000, -1000))

    @CookieCutter.FSM_State("remove brick")
    def modal_remove_brick(self):
        cm, n, curKey, curLoc, objSize = self.update_hover_scene()
        if self.obj is not None and self.mouseTravel > 10:
            # remove existing brick
            self.removeBrick(cm, n, self.event, curKey, curLoc, objSize)
        # switch state
        if self.actions.released("remove brick"):
            return "draw wait"

    @CookieCutter.FSM_State("remove brick", "exit")
    def exit_remove_brick(self):
        # merge bricks in 'self.keysToMerge'
        scn, cm, n = getActiveContextInfo()
        self.mergeBrick(cm, n, mode=self.mode, state="RELEASE")
        self.releaseTime = time.time()
        # clear bricks added from delete's auto update
        self.addedBricksFromDelete = []

    #-------------------------------------------#
    # MERGE/SPLIT WAIT

    @CookieCutter.FSM_State("merge_split wait", "enter")
    def enter_merge_split_wait(self):
        self.addedBricks = []

    @CookieCutter.FSM_State("merge_split wait")
    def modal_merge_split_wait(self):
        self.update_hover_scene()
        # switch state
        if self.actions.pressed("merge"):
            return "merge"
        if self.actions.pressed("split"):
            return "split"
        # switch mode
        if self.actions.pressed("switch_mode draw"):
            return "draw wait"
        if self.actions.pressed("switch_mode paint"):
            return "paint wait"
        # other actions
        if self.actions.pressed("commit"):
            self.done();
            return
        if self.actions.pressed("cancel"):
            self.done(cancel=True)
            return

    #-------------------------------------------#
    # MERGE

    @CookieCutter.FSM_State("merge", "enter")
    def enter_merge(self):
        self.lastMouse = Vector((-1000, -1000))

    @CookieCutter.FSM_State("merge")
    def modal_merge(self):
        cm, n, curKey, curLoc, objSize = self.update_hover_scene()
        if self.obj is not None and self.mouseTravel > 5 and self.obj.name not in self.addedBricks:
            # add current brick to 'self.keysToMerge'
            self.mergeBrick(cm, n, curKey, curLoc, objSize, mode=self.mode, state="DRAG")
        # switch state
        if self.actions.released("merge"):
            return "merge_split wait"

    @CookieCutter.FSM_State("merge", "exit")
    def exit_merge(self):
        # merge bricks in 'self.keysToMerge'
        scn, cm, n = getActiveContextInfo()
        self.mergeBrick(cm, n, mode=self.mode, state="RELEASE")
        self.releaseTime = time.time()
        # clear bricks added from delete's auto update
        self.addedBricksFromDelete = []

    #-------------------------------------------#
    # SPLIT

    @CookieCutter.FSM_State("split", "enter")
    def enter_split(self):
        self.lastMouse = Vector((-1000, -1000))

    @CookieCutter.FSM_State("split")
    def modal_split(self):
        cm, n, curKey, curLoc, objSize = self.update_hover_scene()
        if self.obj is not None and self.mouseTravel > 5:
            # split current brick
            self.splitBrick(cm, self.event, curKey, curLoc, objSize)
        # switch mode
        if self.actions.released("split"):
            return "merge_split wait"

    @CookieCutter.FSM_State("split", "exit")
    def exit_split(self):
        # merge bricks in 'self.keysToMerge'
        scn, cm, n = getActiveContextInfo()
        self.mergeBrick(cm, n, mode=self.mode, state="RELEASE")
        self.releaseTime = time.time()
        # clear bricks added from delete's auto update
        self.addedBricksFromDelete = []

    #-------------------------------------------#
    # PAINT WAIT

    @CookieCutter.FSM_State("paint wait", "enter")
    def enter_paint_wait(self):
        self.set_ui_text()

    @CookieCutter.FSM_State("paint wait")
    def modal_paint_wait(self):
        self.update_hover_scene()
        # switch state
        if self.actions.pressed("paint"):
            return "paint"
        # switch mode
        if self.actions.pressed("switch_mode draw"):
            return "draw wait"
        if self.actions.pressed("switch_mode merge_split"):
            return "merge_split wait"
        # other actions
        if self.actions.pressed("commit"):
            self.done();
            return
        if self.actions.pressed("cancel"):
            self.done(cancel=True)
            return

    #-------------------------------------------#
    # PAINT

    @CookieCutter.FSM_State("paint", "enter")
    def enter_paint(self):
        self.lastMouse = Vector((-1000, -1000))
        bpy.context.window.cursor_set("PAINT_BRUSH")
        tag_redraw_areas()

    @CookieCutter.FSM_State("paint")
    def modal_paint(self):
        cm, n, curKey, curLoc, objSize = self.update_hover_scene()
        if self.obj is not None and self.mouseTravel > 5 and self.bricksDict[curKey]["mat_name"] != self.matName:
            # change material
            self.changeMaterial(cm, n, curKey, curLoc, objSize)
        # switch state
        if self.actions.released("paint"):
            return "paint wait"

    @CookieCutter.FSM_State("paint", "exit")
    def exit_paint(self):
        self.releaseTime = time.time()
        # clear bricks added from delete's auto update
        self.addedBricksFromDelete = []








    def update_hover_scene(self):
        scn, cm, n = getActiveContextInfo()
        self.mouse = Vector((self.event.mouse_region_x, self.event.mouse_region_y))
        self.mouseTravel = abs(self.mouse.x - self.lastMouse.x) + abs(self.mouse.y - self.lastMouse.y)
        self.hover_scene(bpy.context, self.mouse.x, self.mouse.y, n, update_header=self.left_click)
        if self.obj is not None:
            self.lastMouse = self.mouse
            curKey = getDictKey(self.obj.name)
            curLoc = getDictLoc(self.bricksDict, curKey)
            objSize = self.bricksDict[curKey]["size"]
            bpy.context.window.cursor_set("PAINT_BRUSH")
        else:
            curKey, curLoc, objSize = None, None, None
            bpy.context.window.cursor_set("DEFAULT")

        return cm, n, curKey, curLoc, objSize











    def modal2(self, context, event):
        print("HERE")
        # check if function key pressed
        if event.type in ("LEFT_CTRL", "RIGHT_CTRL") and event.value == "PRESS":
            if self.layerSolod is not None:
                self.ctrlClickTime = time.time()
                self.possibleCtrlDisable = True
                return {"RUNNING_MODAL"}
            else:
                self.layerSolod = -1
        # if mouse moves, don't disable solo layer
        if event.type == "MOUSEMOVE":
            self.possibleCtrlDisable = False
        # clear solo layer if escape/quick ctrl pressed
        if (self.layerSolod is not None and
            ((event.type == "ESC" and event.value == "PRESS") or
             (event.type in ("LEFT_CTRL", "RIGHT_CTRL") and event.value == "RELEASE" and (time.time() - self.ctrlClickTime < 0.2)))):
            self.unSoloLayer()
            self.layerSolod = None
            self.possibleCtrlDisable = False
            return {"RUNNING_MODAL"}

        # check if left_click is pressed
        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                self.left_click = True
                # block left_click if not in 3D viewport
                space, i = get_quadview_index(context, event.mouse_x, event.mouse_y)
                if space is None:
                    return {"RUNNING_MODAL"}
            elif event.value == "RELEASE":
                self.left_click = False
                self.releaseTime = time.time()
                # clear bricks added from delete's auto update
                self.addedBricksFromDelete = []

        # cast ray to calculate mouse position and travel
        if event.type in ('MOUSEMOVE', 'LEFT_CTRL', 'RIGHT_CTRL') or self.left_click:
            scn, cm, n = getActiveContextInfo()
            self.mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            self.mouseTravel = abs(self.mouse.x - self.lastMouse.x) + abs(self.mouse.y - self.lastMouse.y)
            self.hover_scene(context, self.mouse.x, self.mouse.y, n, update_header=self.left_click)
            # self.update_ui_mouse_pos()
            # run solo layer functionality
            if event.ctrl and (not self.left_click or event.type in ("LEFT_CTRL", "RIGHT_CTRL")) and not (self.possibleCtrlDisable and time.time() - self.ctrlClickTime < 0.2) and self.mouseTravel > 10 and time.time() > self.releaseTime + 0.75:
                if len(self.hiddenBricks) > 0:
                    self.unSoloLayer()
                    self.hover_scene(context, self.mouse.x, self.mouse.y, n, update_header=self.left_click)
                if self.obj is not None:
                    self.lastMouse = self.mouse
                    curKey = getDictKey(self.obj.name)
                    curLoc = getDictLoc(self.bricksDict, curKey)
                    objSize = self.bricksDict[curKey]["size"]
                    self.layerSolod = self.soloLayer(cm, curKey, curLoc, objSize)
            elif self.obj is None:
                bpy.context.window.cursor_set("DEFAULT")
                return {"RUNNING_MODAL"}
            else:
                bpy.context.window.cursor_set("PAINT_BRUSH")

        # draw/remove bricks on left_click & drag
        if self.left_click and (event.type == 'LEFTMOUSE' or (event.type == "MOUSEMOVE" and (not event.alt or self.mouseTravel > 5))):
            # determine which action (if any) to run at current mouse position
            addBrick = not (event.alt or event.shift or self.obj.name in self.keysToMergeOnRelease) and self.mode == "DRAW"
            removeBrick = self.mode == "DRAW" and (event.alt or event.shift) and self.mouseTravel > 10
            changeMaterial = self.obj.name not in self.addedBricks and self.mode == "PAINT"
            splitBrick = self.mode == "MERGE/SPLIT" and (event.alt or event.shift)
            mergeBrick = self.obj.name not in self.addedBricks and self.mode == "MERGE/SPLIT" and not event.alt
            # get key/loc/size of brick at mouse position
            if addBrick or removeBrick or changeMaterial or splitBrick or mergeBrick:
                self.lastMouse = self.mouse
                curKey = getDictKey(self.obj.name)
                curLoc = getDictLoc(self.bricksDict, curKey)
                objSize = self.bricksDict[curKey]["size"]
            # add brick next to existing brick
            if addBrick and self.bricksDict[curKey]["name"] not in self.addedBricks:
                self.addBrick(cm, n, curKey, curLoc, objSize)
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
                self.mergeBrick(cm, n, curKey, curLoc, objSize, mode=self.mode, state="DRAG")
            return {"RUNNING_MODAL"}

        # clean up after splitting bricks
        if event.type in ("LEFT_ALT", "RIGHT_ALT", "LEFT_SHIFT", "RIGHT_SHIFT") and event.value == "RELEASE" and self.mode == "MERGE/SPLIT":
            deselectAll()

        return {"PASS_THROUGH" if event.type.startswith("NUMPAD") or event.type in ("Z", "TRACKPADZOOM", "TRACKPADPAN", "MOUSEMOVE", "NDOF_BUTTON_PANZOOM", "INBETWEEN_MOUSEMOVE", "MOUSEROTATE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "WHEELINMOUSE", "WHEELOUTMOUSE") else "RUNNING_MODAL"}

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
        # TODO: Use custom view layer with only current model instead?
        if b280(): view_layer = bpy.context.window.view_layer
        rv3d = context.region_data
        if rv3d is None:
            return None
        coord = x, y
        ray_max = 1000000  # changed from 10000 to 1000000 to increase accuracy
        view_vector = region_2d_to_vector_3d(self.region, rv3d, coord)
        ray_origin = region_2d_to_origin_3d(self.region, rv3d, coord)
        ray_target = ray_origin + (view_vector * ray_max)

        if b280():
            result, loc, normal, idx, obj, mx = scn.ray_cast(view_layer, ray_origin, ray_target)
        else:
            result, loc, normal, idx, obj, mx = scn.ray_cast(ray_origin, ray_target)

        if result and obj.name.startswith('Bricker_' + source_name):
            self.obj = obj
            self.loc = loc
            self.normal = normal
        else:
            self.obj = None
            self.loc = None
            self.normal = None
            if b280():
                context.area.header_text_set(text=None)
            else:
                context.area.header_text_set()

    ##########################
