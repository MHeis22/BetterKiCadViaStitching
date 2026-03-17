#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pcbnew import *
import sys
import os
import wx
import math

def wxPrint(msg):
    wx.LogMessage(msg)

class ViaObject:
    def __init__(self, x, y, pos_x, pos_y):
        self.X = x
        self.Y = y
        self.PosX = pos_x
        self.PosY = pos_y
        self.reason = 0 # REASON_OK

class FillArea:
    REASON_OK = 0
    REASON_NO_SIGNAL = 1
    REASON_OTHER_SIGNAL = 2
    REASON_KEEPOUT = 3
    REASON_TRACK = 4
    REASON_PAD = 5
    REASON_DRAWING = 6

    FILL_TYPE_RECTANGULAR = "Rectangular"
    FILL_TYPE_HEXAGONAL = "Hexagonal"
    FILL_TYPE_TRACK_FENCING = "Track Fencing"

    def __init__(self, filename=None):
        self.filename = None
        self.clearance = 0
        self.extra_clearance = 0
        self.fence_offset = FromMM(1.0)
        self.SetPCB(GetBoard())
        self.SetFile(filename)
        self.SetStepMM(2.54)
        self.SetSizeMM(0.46)
        self.SetDrillMM(0.20)
        self.SetClearanceMM(0.2)
        
        self.only_selected_area = False
        self.via_through_areas = False
        self.same_net_tracks = False
        self.avoid_same_net_pads = True
        self.auto_refill = True
        
        if self.pcb is not None:
            for lnet in ["GND", "/GND"]:
                if self.pcb.FindNet(lnet) is not None:
                    self.SetNetname(lnet)
                    break
                    
        self.netname = None
        self.fill_type = self.FILL_TYPE_RECTANGULAR
        if self.netname is None:
            self.SetNetname("GND")

        self.tmp_dir = None
        self.parent_area = None
        self.pcb_group = None
        self.target_net = None

    def SetFile(self, filename):
        self.filename = filename
        if self.filename: 
            self.SetPCB(LoadBoard(self.filename))

    def SetViaThroughAreas(self, r):
        self.via_through_areas = r
        return self

    def SetSameNetTracks(self, r):
        self.same_net_tracks = r
        return self

    def SetAvoidSameNetPads(self, r):
        self.avoid_same_net_pads = r
        return self

    def SetAutoRefill(self, r):
        self.auto_refill = r
        return self

    def SetType(self, type):
        self.fill_type = type
        return self

    def SetPCB(self, pcb):
        self.pcb = pcb
        if self.pcb is not None:
            self.pcb.BuildListOfNets()
        return self

    def SetNetname(self, netname):
        self.netname = netname
        return self

    def SetStepMM(self, s):
        self.step = float(FromMM(s))
        return self

    def SetSizeMM(self, s):
        self.size = float(FromMM(s))
        return self

    def SetDrillMM(self, s):
        self.drill = float(FromMM(s))
        return self

    def SetClearanceMM(self, s):
        self.clearance = float(FromMM(s))
        return self

    def SetExtraClearanceMM(self, s):
        self.extra_clearance = float(FromMM(s))
        return self

    def SetFenceOffsetMM(self, s):
        self.fence_offset = float(FromMM(s))
        return self

    def OnlyOnSelectedArea(self):
        self.only_selected_area = True
        return self

    def AddVia(self, position, x, y):
        if self.parent_area:
            m = PCB_VIA(self.parent_area)
            m.SetPosition(position)
            if self.target_net is None:
                self.target_net = self.pcb.FindNet(self.netname)
            m.SetNet(self.target_net)
            m.SetViaType(VIATYPE_THROUGH)
            m.SetDrill(int(self.drill))
            m.SetWidth(int(self.size))
            m.SetIsFree(True)
            self.pcb.Add(m)
            self.pcb_group.AddItem(m)
            return m

    def RefillBoardAreas(self):
        for i in range(self.pcb.GetAreaCount()):
            area = self.pcb.GetArea(i)
            area.SetNeedRefill(True)
                
        try:
            filler = ZONE_FILLER(self.pcb)
            filler.Fill(self.pcb.Zones())
        except Exception as e:
            wxPrint("Could not automatically fill zones: " + str(e))

    def Run(self):
        VIA_GROUP_NAME = "ViaStitching {}".format(self.netname)

        for i in self.pcb.Groups():
            if i.GetName() == VIA_GROUP_NAME:
                self.pcb_group = i

        if self.pcb_group is None:
            self.pcb_group = PCB_GROUP(None)
            self.pcb_group.SetName(VIA_GROUP_NAME)
            self.pcb.Add(self.pcb_group)

        pcb_frame = next((win for win in wx.GetTopLevelWindows() if win.GetName() == 'PcbFrame'), None)

        # Start Progress Dialog to prevent UI freeze
        dlg = wx.ProgressDialog(
            "Via Stitching",
            "Initializing Geometric Engine...",
            maximum=100,
            parent=pcb_frame,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT
        )
        keep_going = True
        
        try:
            l_clearance = self.clearance + self.size
            if l_clearance < self.step: l_clearance = self.step

            l_step_x = l_clearance
            l_step_y = l_clearance
            if self.fill_type == self.FILL_TYPE_HEXAGONAL:
                l_step_y = l_clearance * math.sqrt(3) / 2.0

            all_pads = self.pcb.GetPads()
            all_tracks = self.pcb.GetTracks()
            
            try:
                all_drawings = [x for x in self.pcb.GetDrawings() if x.GetClass() == "PTEXT" and self.pcb.GetLayerID(x.GetLayerName()) in (F_Cu, B_Cu)]
            except:
                all_drawings = []

            all_areas = [self.pcb.GetArea(i) for i in range(self.pcb.GetAreaCount())]
            target_areas = list(filter(lambda x: (x.GetNetname() == self.netname), all_areas))

            if target_areas and self.parent_area is None:
                self.parent_area = target_areas[0]

            board_edge = SHAPE_POLY_SET()
            self.pcb.GetBoardPolygonOutlines(board_edge)
            b_clearance = max(self.pcb.GetDesignSettings().m_CopperEdgeClearance, self.clearance) + self.size
            board_edge.Deflate(int(b_clearance), CORNER_STRATEGY_ROUND_ALL_CORNERS, FromMM(0.01))

            via_list = []  
            max_target_area_clearance = max([(a.GetLocalClearance() or 0) for a in target_areas]) if target_areas else 0

            target_bbox = BOX2I()
            has_valid_bbox = False
            for area in target_areas:
                if (not self.only_selected_area) or area.IsSelected():
                    if not has_valid_bbox:
                        target_bbox = area.GetBoundingBox()
                        has_valid_bbox = True
                    else:
                        target_bbox.Merge(area.GetBoundingBox())
                        
            if not has_valid_bbox:
                target_bbox = self.pcb.ComputeBoundingBox(False)

            if self.fill_type == self.FILL_TYPE_TRACK_FENCING:
                keep_going, _ = dlg.Update(5, "Calculating Track Fences...")
                selected_tracks = [t for t in all_tracks if t.IsSelected() and t.GetClass() == "PCB_TRACK"]
                for track in selected_tracks:
                    start = track.GetStart()
                    end = track.GetEnd()
                    dx = float(end.x - start.x)
                    dy = float(end.y - start.y)
                    length = math.sqrt(dx**2 + dy**2)
                    if length == 0: continue
                    
                    ux = dx / length
                    uy = dy / length
                    offset_dist = float(track.GetWidth() / 2.0) + self.fence_offset
                    
                    for direction in [-1, 1]:
                        nx = -uy * direction
                        ny = ux * direction
                        p_start_x = start.x + nx * offset_dist
                        p_start_y = start.y + ny * offset_dist
                        
                        steps = int(length / self.step)
                        steps = max(1, steps)
                        step_x = (dx / length) * (length / steps)
                        step_y = (dy / length) * (length / steps)
                        
                        # Minimum distance squared to prevent overlapping vias at corners (75% of step)
                        min_dist_sq = (self.step * 0.75) ** 2
                        
                        for i in range(steps + 1):
                            px = p_start_x + step_x * i
                            py = p_start_y + step_y * i
                            
                            # Check against existing vias to prevent double placements at joints
                            too_close = False
                            for existing_via in via_list:
                                if (existing_via.PosX - px)**2 + (existing_via.PosY - py)**2 < min_dist_sq:
                                    too_close = True
                                    break
                                    
                            if not too_close:
                                via_list.append(ViaObject(x=-1, y=-1, pos_x=px, pos_y=py))
            else:
                keep_going, _ = dlg.Update(5, "Generating Spatial Grid...")
                global_board_bbox = self.pcb.ComputeBoundingBox(False)
                origin = global_board_bbox.GetPosition()
                
                target_bbox.Inflate(int(self.clearance + self.size))
                
                x_start = max(0, int((target_bbox.GetX() - origin.x - l_clearance) / l_step_x))
                x_end   = int((target_bbox.GetRight() - origin.x + l_clearance) / l_step_x) + 1
                y_start = max(0, int((target_bbox.GetY() - origin.y - l_clearance) / l_step_y))
                y_end   = int((target_bbox.GetBottom() - origin.y + l_clearance) / l_step_y) + 1

                valid_areas = [a for a in target_areas if (not self.only_selected_area) or a.IsSelected()]

                for x in range(x_start, x_end + 1):
                    for y in range(y_start, y_end + 1):
                        cx = origin.x + (x * l_step_x)
                        if self.fill_type == self.FILL_TYPE_HEXAGONAL and y % 2 == 1:
                            cx += l_step_x / 2.0
                        cy = origin.y + (y * l_step_y)
                        
                        point_to_test = VECTOR2I(int(cx), int(cy))
                        
                        if not target_bbox.Contains(point_to_test):
                            continue
                            
                        is_inside = False
                        for area in valid_areas:
                            area_clearance = area.GetLocalClearance()
                            hit_test_area = False

                            for i in range(0, area.Outline().OutlineCount()):
                                area_outline = area.Outline().Outline(i)
                                hit_test_area = hit_test_area or area_outline.PointInside(point_to_test)

                            hit_test_edge = area.HitTestForEdge(point_to_test, int(max(area_clearance, 0)))
                            if hit_test_area and not hit_test_edge:
                                is_inside = True
                                break
                                
                        if is_inside and board_edge.Collide(point_to_test):
                            via_list.append(ViaObject(x=x, y=y, pos_x=cx, pos_y=cy))

            if not keep_going: return
            
            area_count = len(all_areas)
            for idx, area in enumerate(all_areas):
                if idx % 10 == 0:
                    keep_going, _ = dlg.Update(10 + int(20 * idx / area_count), "Checking Keepouts & Zones...")
                    if not keep_going: break
                    
                area_layer = area.GetLayer()
                area_clearance = area.GetLocalClearance() or 0
                area_priority = area.GetAssignedPriority() or 0
                is_rules_area = area.GetIsRuleArea()
                is_rule_exclude_via_area = area.GetIsRuleArea() and area.GetDoNotAllowVias()
                is_target_net = area.GetNetname() == self.netname
                
                if is_target_net and not is_rule_exclude_via_area:
                    continue 
                    
                extra = self.extra_clearance if not is_target_net else 0
                offset = max(self.clearance + extra, area_clearance) + self.size / 2
                
                area_bbox = area.GetBoundingBox()
                area_bbox.Inflate(int(offset + 10)) 
                
                for via in via_list:
                    if via.reason != self.REASON_OK: continue
                    
                    point_to_test = VECTOR2I(int(via.PosX), int(via.PosY))
                    if not area_bbox.Contains(point_to_test): continue 
                    
                    hit_test_area = False
                    for dx in [-offset, offset]:
                        for dy in [-offset, offset]:
                            pt = VECTOR2I(int(via.PosX + dx), int(via.PosY + dy))
                            for layer_id in area.GetLayerSet().CuStack():
                                for i in range(0, area.Outline().OutlineCount()):
                                    area_outline = area.Outline().Outline(i)
                                    if area.GetLayerSet().Contains(layer_id) and (layer_id != pcbnew.Edge_Cuts):
                                        hit_test_area = hit_test_area or area_outline.PointInside(pt)
                                        
                            hit_test_edge = area.HitTestForEdge(pt, 1)
                            try:
                                hit_test_zone = area.HitTestInsideZone(pt)
                            except:
                                hit_test_zone = False

                            if is_rule_exclude_via_area and (hit_test_area or hit_test_edge or hit_test_zone):
                                via.reason = self.REASON_KEEPOUT
                                break
                            elif (not self.via_through_areas) and (hit_test_area or hit_test_edge) and not is_rules_area:
                                via.reason = self.REASON_OTHER_SIGNAL
                                break
                            elif (not self.via_through_areas) and hit_test_zone and not is_rules_area:
                                target_areas_on_same_layer = [x for x in all_areas if x.GetPriority() > area_priority and x.GetLayer() == area_layer and x.GetNetname() == self.netname]
                                covered = False
                                for higher_area in target_areas_on_same_layer:
                                    if higher_area.HitTestInsideZone(pt):
                                        covered = True
                                        break
                                if not covered:
                                    via.reason = self.REASON_OTHER_SIGNAL
                                    break
                        if via.reason != self.REASON_OK: break

            if not keep_going: return

            pad_count = len(all_pads)
            dummy_via = PCB_VIA(self.parent_area)
            dummy_via.SetViaType(VIATYPE_THROUGH)
            dummy_via.SetDrill(int(self.drill))
            dummy_via.SetWidth(int(self.size))
            
            for idx, pad in enumerate(all_pads):
                if idx % 100 == 0:
                    keep_going, _ = dlg.Update(30 + int(30 * idx / pad_count), "Checking Pad Clearances...")
                    if not keep_going: break
                    
                if not self.avoid_same_net_pads and pad.GetNetname() == self.netname:
                    continue

                extra = self.extra_clearance if pad.GetNetname() != self.netname else 0
                
                own_clear = 0
                if hasattr(pad, 'GetLocalClearance'):
                    own_clear = pad.GetLocalClearance() or 0
                elif hasattr(pad, 'GetOwnClearance'):
                    own_clear = pad.GetOwnClearance(UNDEFINED_LAYER, "") or 0
                
                local_offset = max(own_clear, self.clearance + extra, max_target_area_clearance) + (self.size / 2)
                
                pad_bbox = pad.GetBoundingBox()
                pad_bbox.Inflate(int(local_offset) + 10) 
                
                pad_poly = None
                
                for via in via_list:
                    if via.reason != self.REASON_OK: continue
                    
                    point_to_test = VECTOR2I(int(via.PosX), int(via.PosY))
                    if not pad_bbox.Contains(point_to_test): continue 
                    
                    if pad.HitTest(point_to_test, int(local_offset)):
                        via.reason = self.REASON_PAD
                        continue
                        
                    if pad_poly is None:
                        pad_poly = pad.GetEffectivePolygon(pad.GetLayer())
                    
                    dummy_via.SetPosition(point_to_test)
                    if pad_poly.Collide(dummy_via.GetEffectiveShape()):
                        via.reason = self.REASON_PAD

            if not keep_going: return

            track_count = len(all_tracks)
            for idx, track in enumerate(all_tracks):
                if idx % 200 == 0:
                    keep_going, _ = dlg.Update(60 + int(25 * idx / track_count), "Checking Trace Clearances...")
                    if not keep_going: break
                    
                if self.same_net_tracks and track.GetNetname() == self.netname and track.GetClass() != "PCB_VIA":
                    continue

                extra = self.extra_clearance if track.GetNetname() != self.netname else 0
                
                own_clear = 0
                if hasattr(track, 'GetLocalClearance'):
                    own_clear = track.GetLocalClearance() or 0
                elif hasattr(track, 'GetOwnClearance'):
                    own_clear = track.GetOwnClearance(UNDEFINED_LAYER, "") or 0
                    
                hit_accuracy = max(own_clear, self.clearance + extra, max_target_area_clearance) + (self.size / 2)
                tr_clearance_bbox = hit_accuracy + (track.GetWidth() / 2)
                
                track_bbox = track.GetBoundingBox()
                track_bbox.Inflate(int(tr_clearance_bbox) + 10)
                
                for via in via_list:
                    if via.reason != self.REASON_OK: continue
                    
                    point_to_test = VECTOR2I(int(via.PosX), int(via.PosY))
                    if not track_bbox.Contains(point_to_test): continue
                    
                    if track.HitTest(point_to_test, int(hit_accuracy)):
                        via.reason = self.REASON_TRACK

            if not keep_going: return

            keep_going, _ = dlg.Update(85, "Checking Silkscreen & Text...")
            for draw in all_drawings:
                inter = float(self.clearance + self.size) / 2
                draw_bbox = draw.GetBoundingBox()
                draw_bbox.Inflate(int(inter))
                
                for via in via_list:
                    if via.reason != self.REASON_OK: continue
                    point_to_test = VECTOR2I(int(via.PosX), int(via.PosY))
                    if draw_bbox.Contains(point_to_test):
                        via.reason = self.REASON_DRAWING
                        
            keep_going, _ = dlg.Update(90, "Placing Vias on Board...")
            via_placed = 0
            for via in via_list:
                if via.reason == self.REASON_OK:
                    self.AddVia(VECTOR2I(int(via.PosX), int(via.PosY)), via.X, via.Y)
                    via_placed += 1

            if self.auto_refill:
                keep_going, _ = dlg.Update(95, "Refilling Copper Zones...")
                self.RefillBoardAreas()
                wxPrint("Done. {:d} vias placed. Zones refilled!".format(via_placed))
            else:
                wxPrint("Done. {:d} vias placed. Remember to press 'B' in KiCad to refill zones!".format(via_placed))
                
            if self.filename: self.pcb.Save(self.filename)
            
        except Exception as e:
            wxPrint("Error during execution: " + str(e))
        finally:
            dlg.Destroy()

if __name__ == "__main__":
    if len(sys.argv) < 2: print("Usage: %s <KiCad pcb filename>" % sys.argv[0])
    else: FillArea(sys.argv[1]).Run()