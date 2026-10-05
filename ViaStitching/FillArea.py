#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pcbnew import *
import pcbnew
import sys
import math
import traceback
from collections import defaultdict
import wx


def wxPrint(msg):
    wx.LogMessage(msg)


# --- API compatibility helpers (KiCad 8 / 9 / 10) -------------------------

def _local_clearance(item):
    # Returns std::optional<int> in KiCad 8+ (None or int in Python)
    try:
        v = item.GetLocalClearance()
    except Exception:
        return 0
    try:
        return int(v or 0)
    except TypeError:
        return 0


def _item_width(item):
    # PCB_VIA::GetWidth() without a layer asserts in KiCad 9+ (raises in Python)
    if item.GetClass() == "PCB_VIA":
        for getter in (lambda: item.GetWidth(pcbnew.F_Cu), item.GetFrontWidth, item.GetWidth):
            try:
                return int(getter())
            except Exception:
                pass
        return 0
    return int(item.GetWidth())


def _priority(zone):
    for name in ("GetAssignedPriority", "GetPriority"):
        f = getattr(zone, name, None)
        if f is not None:
            try:
                return int(f() or 0)
            except Exception:
                pass
    return 0


def _via_type_through():
    if hasattr(pcbnew, 'VIATYPE_THROUGH'):
        return pcbnew.VIATYPE_THROUGH
    if hasattr(pcbnew, 'VIATYPE') and hasattr(pcbnew.VIATYPE, 'THROUGH'):
        return pcbnew.VIATYPE.THROUGH
    if hasattr(pcbnew, 'PCB_VIA_VIATYPE_THROUGH'):
        return pcbnew.PCB_VIA_VIATYPE_THROUGH
    return None


def _copy_poly(poly):
    if hasattr(poly, "CloneDropTriangulation"):
        return poly.CloneDropTriangulation()
    return SHAPE_POLY_SET(poly)


def _simplify(poly):
    try:
        poly.Simplify()
    except TypeError:
        poly.Simplify(SHAPE_POLY_SET.PM_FAST)


def _deflate(poly, amount):
    try:
        poly.Deflate(int(amount), CORNER_STRATEGY_ROUND_ALL_CORNERS, FromMM(0.005))
    except TypeError:
        poly.Deflate(int(amount), 16)


def _inflate(poly, amount):
    try:
        poly.Inflate(int(amount), CORNER_STRATEGY_ROUND_ALL_CORNERS, FromMM(0.005))
    except TypeError:
        poly.Inflate(int(amount), 16)


def _bool_op(a, b, op):
    try:
        getattr(a, op)(b)
    except TypeError:
        getattr(a, op)(b, SHAPE_POLY_SET.PM_FAST)


def _poly_circle(cx, cy, r, n=32):
    # Circumscribed polygon, so it fully covers the true circle
    rr = r / math.cos(math.pi / n)
    s = SHAPE_POLY_SET()
    s.NewOutline()
    for k in range(n):
        a = 2 * math.pi * k / n
        s.Append(int(cx + rr * math.cos(a)), int(cy + rr * math.sin(a)))
    return s


def _poly_box(x0, y0, x1, y1):
    s = SHAPE_POLY_SET()
    s.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        s.Append(int(x), int(y))
    return s


# Safety margin on every clearance: KiCad's DRC tests polygonised pads/arcs, which
# can sit a few um outside the exact shape that HitTest() uses.
EPS = FromMM(0.005)


def _footprints(pcb):
    for name in ("GetFootprints", "Footprints", "GetModules"):
        f = getattr(pcb, name, None)
        if f is not None:
            try:
                return list(f())
            except Exception:
                pass
    return []


# --- Candidate storage ------------------------------------------------------

class ViaObject:
    __slots__ = ("X", "Y", "PosX", "PosY", "reason", "plane_gap")

    def __init__(self, x, y, pos_x, pos_y):
        self.X = x
        self.Y = y
        self.PosX = int(pos_x)
        self.PosY = int(pos_y)
        self.reason = 0  # REASON_OK
        self.plane_gap = 0  # min. spacing to other vias inside another net's plane


class CandidateIndex:
    """Uniform-grid spatial hash: each obstacle only visits candidates near it
    instead of scanning every candidate on the board."""

    def __init__(self, cell):
        self.cell = max(int(cell), 1)
        self.buckets = defaultdict(list)
        self.items = []

    def add(self, via):
        self.items.append(via)
        self.buckets[(via.PosX // self.cell, via.PosY // self.cell)].append(via)

    def query(self, x0, y0, x1, y1, include_rejected=False):
        c = self.cell
        for cx in range(int(x0) // c, int(x1) // c + 1):
            for cy in range(int(y0) // c, int(y1) // c + 1):
                for via in self.buckets.get((cx, cy), ()):
                    if (include_rejected or via.reason == 0) and x0 <= via.PosX <= x1 and y0 <= via.PosY <= y1:
                        yield via

    def query_box(self, bbox, inflate):
        return list(self.query(bbox.GetX() - inflate, bbox.GetY() - inflate,
                               bbox.GetRight() + inflate, bbox.GetBottom() + inflate))

    def near(self, x, y, dist):
        d2 = dist * dist
        for via in self.query(x - dist, y - dist, x + dist, y + dist, include_rejected=True):
            if (via.PosX - x) ** 2 + (via.PosY - y) ** 2 < d2:
                return True
        return False


class _SubProgress:
    """Maps a 0-100 progress range onto a slice of the real progress dialog."""

    def __init__(self, dlg, base, span, prefix):
        self.dlg, self.base, self.span, self.prefix = dlg, base, span, prefix

    def Update(self, value, msg=""):
        return self.dlg.Update(int(self.base + self.span * value / 100.0), self.prefix + msg)


class FillArea:
    ALIGNMENT_STEPS = 4  # 4 x 4 grid offsets per lattice cell

    REASON_OK = 0
    REASON_NO_SIGNAL = 1
    REASON_OTHER_SIGNAL = 2
    REASON_KEEPOUT = 3
    REASON_TRACK = 4
    REASON_PAD = 5
    REASON_DRAWING = 6
    REASON_EDGE = 7
    REASON_VIA = 8
    REASON_THERMAL = 9
    REASON_PLANE = 10
    REASON_PLANE_SPACING = 11

    REASON_TEXT = {
        REASON_OTHER_SIGNAL: "inside / too close to another net's zone",
        REASON_KEEPOUT: "inside a via keepout (rule area)",
        REASON_TRACK: "too close to a track",
        REASON_PAD: "too close to a pad or its hole",
        REASON_DRAWING: "too close to copper text / graphics",
        REASON_EDGE: "too close to the board edge",
        REASON_VIA: "too close to an existing via",
        REASON_THERMAL: "would cut a pad's thermal-relief spokes",
        REASON_PLANE: "would pinch another net's plane below min. width",
        REASON_PLANE_SPACING: "thinned so another net's plane stays connected",
    }

    FILL_TYPE_RECTANGULAR = "Rectangular"
    FILL_TYPE_HEXAGONAL = "Hexagonal"
    FILL_TYPE_TRACK_FENCING = "Track Fencing"

    def __init__(self, filename=None):
        self.filename = None
        self.pcb = None
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
        self.optimize_alignment = True

        self.netname = "GND"
        if self.pcb is not None:
            for lnet in ["GND", "/GND"]:
                if self.pcb.FindNet(lnet) is not None:
                    self.netname = lnet
                    break
        self.fill_type = self.FILL_TYPE_RECTANGULAR

        self.pcb_group = None
        self._plane_cache = {}
        self._circle_cache = {}
        self.target_net = None
        self.placed = 0
        self.candidates = 0
        self.rejected = {}
        self.warnings = []
        self.error = None

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

    def SetOptimizeAlignment(self, r):
        self.optimize_alignment = r
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

    def AddVia(self, position):
        # Parented to the board: the old code parented to a target zone and silently
        # placed nothing when the net had no zone (e.g. track fencing).
        m = PCB_VIA(self.pcb)
        m.SetPosition(position)
        if self.target_net is None:
            self.target_net = self.pcb.FindNet(self.netname)
        m.SetNet(self.target_net)
        via_type = _via_type_through()
        if via_type is not None:
            m.SetViaType(via_type)
        m.SetDrill(int(self.drill))
        m.SetWidth(int(self.size))
        m.SetIsFree(True)
        self.pcb.Add(m)
        self.pcb_group.AddItem(m)
        return m

    def RefillBoardAreas(self, bbox=None):
        zones = [z for z in self.pcb.Zones() if not z.GetIsRuleArea()]
        if bbox is not None:
            zones = [z for z in zones if z.GetBoundingBox().Intersects(bbox)]
        for z in zones:
            z.SetNeedRefill(True)
        try:
            filler = ZONE_FILLER(self.pcb)
            filler.Fill(zones)
        except Exception as e:
            wxPrint("Could not automatically fill zones: " + str(e))

    def Summary(self):
        if self.error:
            return "Via stitching failed:\n\n" + self.error
        lines = ["{} via(s) placed on net '{}' ({} candidate positions).".format(
            self.placed, self.netname, self.candidates)]
        if self.rejected:
            lines.append("")
            lines.append("Rejected positions:")
            for reason, n in sorted(self.rejected.items(), key=lambda kv: -kv[1]):
                lines.append("  {:>6}  {}".format(n, self.REASON_TEXT.get(reason, str(reason))))
        if self.warnings:
            lines.append("")
            lines.extend(self.warnings)
        return "\n".join(lines)

    # ------------------------------------------------------------------------

    def _collect_zones(self):
        zones = list(self.pcb.Zones())
        for fp in _footprints(self.pcb):
            zf = getattr(fp, "Zones", None) or getattr(fp, "GetZones", None)
            if zf is not None:
                try:
                    zones.extend(zf())
                except Exception:
                    pass
        return zones

    def _grid_steps(self, pitch):
        step_x = pitch
        step_y = pitch * math.sqrt(3) / 2.0 if self.fill_type == self.FILL_TYPE_HEXAGONAL else pitch
        return step_x, step_y

    def _prepare_grid_polys(self, valid_areas):
        # The via ring must lie fully inside the zone outline and outside its cutouts:
        # deflate each outline by the via radius once instead of edge-testing every point.
        polys = []
        bbox = None
        for area in valid_areas:
            p = _copy_poly(area.Outline())
            _deflate(p, self.size / 2.0)
            if p.OutlineCount() == 0:
                continue
            try:
                p.BuildBBoxCaches()
            except Exception:
                pass
            polys.append(p)
            b = p.BBox()
            if bbox is None:
                bbox = BOX2I(b.GetPosition(), b.GetSize())
            else:
                bbox.Merge(b)
        return polys, bbox

    def _generate_grid(self, index, polys, bbox, board_edge, pitch, offset=(0.0, 0.0)):
        if bbox is None:
            return
        step_x, step_y = self._grid_steps(pitch)

        # Anchor the grid to the board bbox origin (plus the alignment offset) so
        # repeated runs line up. Keep the BOX2I alive: GetPosition() on a temporary
        # returns a dangling reference.
        board_bbox = self.pcb.ComputeBoundingBox(False)
        ox, oy = board_bbox.GetX() + offset[0], board_bbox.GetY() + offset[1]
        x_start = int(math.floor((bbox.GetX() - ox) / step_x)) - 1
        x_end = int(math.ceil((bbox.GetRight() - ox) / step_x)) + 1
        y_start = int(math.floor((bbox.GetY() - oy) / step_y)) - 1
        y_end = int(math.ceil((bbox.GetBottom() - oy) / step_y)) + 1

        for y in range(y_start, y_end + 1):
            cy = oy + y * step_y
            if cy < bbox.GetY() or cy > bbox.GetBottom():
                continue
            # Python's % is non-negative for negative y, so odd rows always shift
            shift = step_x / 2.0 if (self.fill_type == self.FILL_TYPE_HEXAGONAL and y % 2) else 0.0
            for x in range(x_start, x_end + 1):
                cx = ox + x * step_x + shift
                if cx < bbox.GetX() or cx > bbox.GetRight():
                    continue
                pt = VECTOR2I(int(cx), int(cy))
                if not any(p.Contains(pt, -1, 0, True) for p in polys):
                    continue
                via = ViaObject(x, y, cx, cy)
                if not board_edge.Contains(pt):
                    via.reason = self.REASON_EDGE
                index.add(via)

    def _generate_fence(self, index, board_edge, pitch):
        tracks = [t for t in self.pcb.GetTracks()
                  if t.IsSelected() and t.GetClass() in ("PCB_TRACK", "PCB_ARC")]
        if not tracks:
            self.warnings.append("Track Fencing: no tracks selected. Select the track(s) to fence first.")
            return

        # A fence via must clear the fenced track by the copper clearance
        extra = self.extra_clearance if tracks[0].GetNetname() != self.netname else 0
        min_offset = self.clearance + extra + self.size / 2.0
        offset = self.fence_offset
        if offset < min_offset:
            self.warnings.append("Fence offset raised from {:.3f} to {:.3f} mm to keep vias clear of the track.".format(
                ToMM(int(offset)), ToMM(int(min_offset))))
            offset = min_offset
        min_spacing = self.size + self.clearance

        # Offset the union of all selected tracks and walk its outline at an even pitch.
        # This gives continuous fences around bends, arcs and junctions instead of
        # per-segment rows with gaps on the outside of every corner.
        try:
            outline = SHAPE_POLY_SET()
            for t in tracks:
                t.TransformShapeToPolygon(outline, t.GetLayer(), int(offset), FromMM(0.005), ERROR_OUTSIDE)
            _simplify(outline)
            chains = []
            for i in range(outline.OutlineCount()):
                chains.append(outline.Outline(i))
                for h in range(outline.HoleCount(i)):
                    chains.append(outline.Hole(i, h))
            for chain in chains:
                length = float(chain.Length())
                if length <= 0:
                    continue
                n = max(1, int(round(length / pitch)))
                spacing = length / n
                for k in range(n):
                    pt = chain.PointAlong(int(k * spacing))
                    self._add_fence_point(index, board_edge, pt.x, pt.y, min_spacing)
            return
        except Exception:
            wxPrint("Polygon fence failed, falling back to per-segment fence:\n" + traceback.format_exc())

        for track in tracks:
            if track.GetClass() != "PCB_TRACK":
                continue
            start, end = track.GetStart(), track.GetEnd()
            dx, dy = float(end.x - start.x), float(end.y - start.y)
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            ux, uy = dx / length, dy / length
            dist = track.GetWidth() / 2.0 + offset
            steps = max(1, int(round(length / pitch)))
            for direction in (-1, 1):
                nx, ny = -uy * direction, ux * direction
                for i in range(steps + 1):
                    self._add_fence_point(index, board_edge,
                                          start.x + nx * dist + dx * i / steps,
                                          start.y + ny * dist + dy * i / steps, min_spacing)

    def _add_fence_point(self, index, board_edge, px, py, min_spacing):
        if index.near(px, py, min_spacing):
            return
        via = ViaObject(-1, -1, px, py)
        if not board_edge.Contains(VECTOR2I(via.PosX, via.PosY)):
            via.reason = self.REASON_EDGE
        index.add(via)

    def _check_zones(self, index, all_areas, target_areas, dlg):
        radius = self.size / 2.0
        target_by_layer = defaultdict(list)
        for t in target_areas:
            for layer in t.GetLayerSet().Seq():
                target_by_layer[layer].append(t)

        n = len(all_areas)
        for idx, area in enumerate(all_areas):
            if idx % 20 == 0:
                if not dlg.Update(10 + int(15 * idx / max(n, 1)), "Checking keepouts & zones...")[0]:
                    return False
            is_rule = area.GetIsRuleArea()
            if is_rule:
                if not area.GetDoNotAllowVias():
                    continue
                reach = int(radius + EPS)
                reason = self.REASON_KEEPOUT
            else:
                if area.GetNetname() == self.netname or self.via_through_areas:
                    continue
                reach = int(max(self.clearance + self.extra_clearance, _local_clearance(area)) + radius + EPS)
                reason = self.REASON_OTHER_SIGNAL

            outline = area.Outline()
            prio = _priority(area)
            layers = list(area.GetLayerSet().Seq())
            for via in index.query_box(area.GetBoundingBox(), reach):
                pt = VECTOR2I(via.PosX, via.PosY)
                # Distance test against the real outline (holes included), not 4 corner samples
                if not outline.Collide(pt, reach):
                    continue
                if not is_rule:
                    # The other zone only owns copper here on layers where no
                    # higher-priority target-net zone covers the point.
                    owned = False
                    for layer in layers:
                        covered = any(_priority(t) > prio and t.Outline().Contains(pt)
                                      for t in target_by_layer.get(layer, ()))
                        if not covered:
                            owned = True
                            break
                    if not owned:
                        continue
                via.reason = reason
        return True

    def _plane_layers(self, zone, antipad, width):
        # Per zone: filled copper per layer plus the derived 'touch' / 'deep' regions.
        # Cached for the whole run, because alignment trials re-check the same zones.
        key = (zone.m_Uuid.AsString(), int(antipad), int(width))
        cached = self._plane_cache.get(key)
        if cached is not None:
            return cached
        layers = []
        for layer in zone.GetLayerSet().Seq():
            try:
                if not zone.HasFilledPolysForLayer(layer):
                    continue
                fill = zone.GetFilledPolysList(layer)
            except Exception:
                continue
            if fill is None or fill.OutlineCount() == 0:
                continue
            fill = _copy_poly(fill)
            touch = _copy_poly(fill)
            _inflate(touch, antipad)
            deep = _copy_poly(fill)
            _deflate(deep, antipad + width)
            for poly in (touch, deep):
                try:
                    poly.BuildBBoxCaches()
                except Exception:
                    pass
            layers.append({"fill": fill, "touch": touch, "deep": deep, "tiles": {}})
        self._plane_cache[key] = layers
        return layers

    def _local_fill(self, plane, x, y, half):
        # Fill clipped to a ~5 mm tile (plus margin) around the candidate, with its
        # boundary chains and their bounding boxes. Intersecting the whole plane for
        # every candidate cost ~1 ms each; a cached tile is tiny.
        tile = max(FromMM(5), int(4 * half))
        kx, ky = int(x // tile), int(y // tile)
        entry = plane["tiles"].get((kx, ky))
        if entry is None:
            piece = _copy_poly(plane["fill"])
            _bool_op(piece, _poly_box(kx * tile - half, ky * tile - half,
                                      (kx + 1) * tile + half, (ky + 1) * tile + half), "BooleanIntersection")
            chains = []
            for i in range(piece.OutlineCount()):
                rings = [piece.Outline(i)] + [piece.Hole(i, h) for h in range(piece.HoleCount(i))]
                for ring in rings:
                    b = ring.BBox()
                    chains.append((ring, b.GetX(), b.GetY(), b.GetRight(), b.GetBottom()))
            entry = plane["tiles"][(kx, ky)] = (piece, chains)
        return entry

    def _creates_neck(self, plane, via, antipad, width, half):
        """KiCad's connection_width rule: wherever copper remains between two voids it
        must be at least `width` wide. So every void boundary near the new antipad must
        either overlap it (the voids merge) or stay at least `width` away from it."""
        piece, chains = self._local_fill(plane, via.PosX, via.PosY, half)
        pt = VECTOR2I(via.PosX, via.PosY)
        reach = antipad + width + EPS
        merged = 0 if piece.Contains(pt) else 1  # centre already in a void
        for ring, x0, y0, x1, y1 in chains:
            dx = max(x0 - pt.x, 0, pt.x - x1)
            dy = max(y0 - pt.y, 0, pt.y - y1)
            if dx * dx + dy * dy >= reach * reach:
                continue
            gap = math.sqrt(ring.SquaredDistance(pt, True)) - antipad
            if gap <= 0:
                merged += 1
            elif gap < width + EPS:
                return True  # a sub-minimum copper web would remain
        if merged < 2:
            return False
        # The antipad joins two or more voids: make sure that does not cut a strip
        # of copper into separate pieces.
        box = _poly_box(via.PosX - half, via.PosY - half, via.PosX + half, via.PosY + half)
        before = _copy_poly(piece)
        _bool_op(before, box, "BooleanIntersection")
        circle = self._circle_cache.get(int(antipad))
        if circle is None:
            circle = self._circle_cache[int(antipad)] = _poly_circle(0, 0, antipad)
        hole = _copy_poly(circle)
        hole.Move(pt)
        after = _copy_poly(before)
        _bool_op(after, hole, "BooleanSubtract")
        min_area = width * width
        pieces_before = sum(1 for j in range(before.OutlineCount()) if before.UnitSet(j).Area() >= min_area)
        pieces_after = sum(1 for j in range(after.OutlineCount()) if after.UnitSet(j).Area() >= min_area)
        return pieces_after > pieces_before

    def _check_planes(self, index, all_areas, dlg, neck_test=True):
        """When vias may pass through other nets' zones, make sure the antipad each via
        punches into that zone's *filled* copper does not pinch it below the board's
        minimum connection width or cut it in two (DRC 'connection_width'), and remember
        how far apart vias inside that copper must stay so the webs between antipads survive."""
        if not self.via_through_areas:
            return True
        radius = self.size / 2.0
        bds = self.pcb.GetDesignSettings()
        min_conn = getattr(bds, "m_MinConn", 0) or 0
        zones = [z for z in all_areas if not z.GetIsRuleArea() and z.GetNetname() != self.netname]
        unfilled = 0
        n = len(zones)
        for idx, zone in enumerate(zones):
            if idx % 20 == 0:
                if not dlg.Update(25 + int(10 * idx / max(n, 1)), "Checking other nets' planes...")[0]:
                    return False
            zclr = max(self.clearance + self.extra_clearance, _local_clearance(zone)) + EPS
            antipad = radius + zclr
            width = max(min_conn, zone.GetMinThickness()) + EPS
            web = 2 * antipad + width
            candidates = index.query_box(zone.GetBoundingBox(), int(antipad))
            if not candidates:
                continue
            if not zone.IsFilled():
                unfilled += 1
                continue
            half = antipad + 3 * width
            for plane in self._plane_layers(zone, antipad, width):
                touch, deep = plane["touch"], plane["deep"]
                for via in candidates:
                    if via.reason != self.REASON_OK:
                        continue
                    pt = VECTOR2I(via.PosX, via.PosY)
                    if not touch.Contains(pt, -1, 0, True):
                        continue  # antipad does not reach this copper
                    if neck_test and not deep.Contains(pt, -1, 0, True):
                        # Near an edge or another hole: simulate the bite locally and
                        # reject only if it creates a neck or splits the copper.
                        if self._creates_neck(plane, via, antipad, width, half):
                            via.reason = self.REASON_PLANE
                            continue
                    via.plane_gap = max(via.plane_gap, web)
        if unfilled:
            self.warnings.append("{} other-net zone(s) were unfilled, so plane-neck checks skipped them. "
                                 "Refill zones (B) before stitching for full protection.".format(unfilled))
        return True

    def _thin_in_planes(self, index):
        # Vias through another net's plane must sit far enough apart that the copper
        # web between their antipads stays above the minimum connection width.
        kept = CandidateIndex(index.cell)
        for via in index.items:
            if via.reason != self.REASON_OK:
                continue
            if via.plane_gap > 0:
                g = via.plane_gap
                clash = any(o.plane_gap > 0 and (o.PosX - via.PosX) ** 2 + (o.PosY - via.PosY) ** 2 < max(g, o.plane_gap) ** 2
                            for o in kept.query(via.PosX - g, via.PosY - g, via.PosX + g, via.PosY + g))
                if clash:
                    via.reason = self.REASON_PLANE_SPACING
                    continue
            kept.add(via)

    def _thermal_gaps(self, all_areas):
        """Per pad net: list of (layer set, zone) for zones that connect pads with
        thermal spokes. A via whose antipad reaches a spoke's landing area starves it."""
        by_net = defaultdict(list)
        for z in all_areas:
            if z.GetIsRuleArea() or not z.GetNetname():
                continue
            by_net[z.GetNetname()].append((set(z.GetLayerSet().Seq()), z))
        return by_net

    def _pad_thermal_gap(self, pad, zones):
        if not zones:
            return 0
        thermal = getattr(pcbnew, "ZONE_CONNECTION_THERMAL", None)
        tht_thermal = getattr(pcbnew, "ZONE_CONNECTION_THT_THERMAL", None)
        inherited = getattr(pcbnew, "ZONE_CONNECTION_INHERITED", None)
        try:
            local_conn = pad.GetLocalZoneConnection()
        except Exception:
            local_conn = inherited
        try:
            gap_override = int(pad.GetLocalThermalGapOverride() or 0)
        except Exception:
            gap_override = 0
        try:
            spoke_override = int(pad.GetLocalThermalSpokeWidthOverride() or 0)
        except Exception:
            spoke_override = 0
        is_pth = pad.GetDrillSize().x > 0
        pad_layers = set(pad.GetLayerSet().Seq())
        gap = 0
        for layers, z in zones:
            if not (layers & pad_layers):
                continue
            conn = local_conn if local_conn not in (None, inherited) else z.GetPadConnection()
            if conn == thermal or (conn == tht_thermal and is_pth):
                # The spoke crosses the gap and must land on at least a spoke-width
                # of solid copper, so the via's antipad has to stay beyond both.
                gap = max(gap, (gap_override or z.GetThermalReliefGap()) +
                          (spoke_override or z.GetThermalReliefSpokeWidth()))
        return gap

    def _check_pads(self, index, dlg, all_areas):
        radius = self.size / 2.0
        drill_r = self.drill / 2.0
        bds = self.pcb.GetDesignSettings()
        h2h = getattr(bds, "m_HoleToHoleMin", 0) or 0
        hole_clr = getattr(bds, "m_HoleClearance", 0) or 0
        thermal_by_net = self._thermal_gaps(all_areas)
        pads = list(self.pcb.GetPads())
        n = len(pads)
        for idx, pad in enumerate(pads):
            if idx % 100 == 0:
                if not dlg.Update(35 + int(25 * idx / max(n, 1)), "Checking pad clearances...")[0]:
                    return False
            same_net = pad.GetNetname() == self.netname
            check_copper = self.avoid_same_net_pads or not same_net
            extra = 0 if same_net else self.extra_clearance
            clr = max(_local_clearance(pad), self.clearance + extra)
            # Pad copper vs via ring, and pad copper vs via hole (board hole clearance)
            cu_reach = int(max(clr + radius, hole_clr + drill_r) + EPS)
            # Keep out of the thermal-relief gap so spokes to the pad's zone survive
            gap = self._pad_thermal_gap(pad, thermal_by_net.get(pad.GetNetname()))
            th_reach = int(gap + clr + radius + EPS) if (gap and check_copper) else 0

            # Holes: hole-to-hole spacing, and via ring to pad hole (applies to NPTH too)
            drill = pad.GetDrillSize()
            hole_r = max(drill.x, drill.y) / 2.0
            hole_reach = (max(drill_r + hole_r + h2h, radius + hole_r + hole_clr) + EPS) if hole_r > 0 else 0
            pos = pad.GetPosition()

            reach = max(cu_reach, th_reach, int(hole_reach))
            for via in index.query_box(pad.GetBoundingBox(), reach):
                pt = VECTOR2I(via.PosX, via.PosY)
                if check_copper and pad.HitTest(pt, cu_reach):
                    via.reason = self.REASON_PAD
                elif hole_r > 0 and math.hypot(via.PosX - pos.x, via.PosY - pos.y) < hole_reach:
                    via.reason = self.REASON_PAD
                elif th_reach and pad.HitTest(pt, th_reach):
                    via.reason = self.REASON_THERMAL
        return True

    def _check_tracks(self, index, dlg):
        radius = self.size / 2.0
        drill_r = self.drill / 2.0
        bds = self.pcb.GetDesignSettings()
        h2h = getattr(bds, "m_HoleToHoleMin", 0) or 0
        hole_clr = getattr(bds, "m_HoleClearance", 0) or 0
        tracks = list(self.pcb.GetTracks())
        n = len(tracks)
        for idx, track in enumerate(tracks):
            if idx % 200 == 0:
                if not dlg.Update(60 + int(25 * idx / max(n, 1)), "Checking track & via clearances...")[0]:
                    return False
            same_net = track.GetNetname() == self.netname
            is_via = track.GetClass() == "PCB_VIA"
            if self.same_net_tracks and same_net and not is_via:
                continue
            extra = 0 if same_net else self.extra_clearance
            clr = max(_local_clearance(track), self.clearance + extra)

            if is_via:
                pos = track.GetPosition()
                w2 = _item_width(track) / 2.0
                d2 = track.GetDrillValue() / 2.0
                reach = max(w2 + clr + radius,          # ring to ring
                            drill_r + d2 + h2h,         # hole to hole
                            radius + d2 + hole_clr,     # our ring to its hole
                            w2 + drill_r + hole_clr) + EPS  # its ring to our hole
                for via in list(index.query(pos.x - reach, pos.y - reach, pos.x + reach, pos.y + reach)):
                    if math.hypot(via.PosX - pos.x, via.PosY - pos.y) < reach:
                        via.reason = self.REASON_VIA
            else:
                reach = int(max(clr + radius, hole_clr + drill_r) + EPS)
                for via in index.query_box(track.GetBoundingBox(), reach):
                    if track.HitTest(VECTOR2I(via.PosX, via.PosY), reach):
                        via.reason = self.REASON_TRACK
        return True

    def _check_drawings(self, index):
        # Copper text and graphics on any copper layer, board-level and inside footprints.
        # (The old filter looked for class "PTEXT", which no longer exists, so nothing was checked.)
        hole_clr = getattr(self.pcb.GetDesignSettings(), "m_HoleClearance", 0) or 0
        reach = int(max(self.clearance + self.extra_clearance + self.size / 2.0, hole_clr + self.drill / 2.0) + EPS)
        items = list(self.pcb.GetDrawings())
        for fp in _footprints(self.pcb):
            try:
                items.extend(fp.GraphicalItems())
            except Exception:
                pass
        for item in items:
            try:
                cls = item.GetClass()
                if cls not in ("PCB_SHAPE", "PCB_TEXT", "PCB_TEXTBOX") or not IsCopperLayer(item.GetLayer()):
                    continue
                if cls == "PCB_SHAPE" and item.GetNetname() == self.netname:
                    continue
            except Exception:
                continue
            for via in index.query_box(item.GetBoundingBox(), reach):
                if cls != "PCB_SHAPE" or item.HitTest(VECTOR2I(via.PosX, via.PosY), reach):
                    via.reason = self.REASON_DRAWING

    def Run(self):
        VIA_GROUP_NAME = "ViaStitching {}".format(self.netname)
        self.pcb_group = next((g for g in self.pcb.Groups() if g.GetName() == VIA_GROUP_NAME), None)

        pcb_frame = next((win for win in wx.GetTopLevelWindows() if win.GetName() == 'PcbFrame'), None)
        dlg = wx.ProgressDialog("Via Stitching", "Generating candidate positions...", maximum=100,
                                parent=pcb_frame, style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT)
        try:
            if self.pcb.FindNet(self.netname) is None:
                self.error = "Net '{}' does not exist on this board.".format(self.netname)
                return

            # Minimum centre-to-centre spacing: via diameter + copper clearance
            min_pitch = self.size + self.clearance
            pitch = self.step
            if pitch < min_pitch:
                self.warnings.append("Pitch raised from {:.3f} to {:.3f} mm (via diameter + clearance).".format(
                    ToMM(int(pitch)), ToMM(int(min_pitch))))
                pitch = min_pitch

            all_areas = self._collect_zones()
            target_areas = [a for a in all_areas if not a.GetIsRuleArea() and a.GetNetname() == self.netname]
            valid_areas = [a for a in target_areas if (not self.only_selected_area) or a.IsSelected()]

            board_edge = SHAPE_POLY_SET()
            try:
                self.pcb.GetBoardPolygonOutlines(board_edge, True)  # KiCad 10
            except TypeError:
                self.pcb.GetBoardPolygonOutlines(board_edge)
            # Edge clearance is to the via's copper ring, so deflate by the radius, not the diameter
            edge_clr = self.pcb.GetDesignSettings().m_CopperEdgeClearance or self.clearance
            _deflate(board_edge, edge_clr + self.size / 2.0 + EPS)

            is_fence = self.fill_type == self.FILL_TYPE_TRACK_FENCING
            if not is_fence:
                if not target_areas:
                    self.error = "Net '{}' has no copper zone to stitch.".format(self.netname)
                    return
                if not valid_areas:
                    self.error = ("'Only apply under selected zone' is ticked but no '{}' zone is selected.\n"
                                  "Select the zone in the PCB editor first, or untick the option.").format(self.netname)
                    return
                polys, bbox = self._prepare_grid_polys(valid_areas)

            self._plane_cache = {}
            self._circle_cache = {}

            def evaluate(offset, progress, neck_test=True):
                index = CandidateIndex(max(pitch, FromMM(1)))
                if is_fence:
                    self._generate_fence(index, board_edge, pitch)
                else:
                    self._generate_grid(index, polys, bbox, board_edge, pitch, offset)
                if not progress.Update(10, "Checking keepouts & zones...")[0]:
                    return None
                if not self._check_zones(index, all_areas, target_areas, progress):
                    return None
                if not self._check_planes(index, all_areas, progress, neck_test):
                    return None
                if not self._check_pads(index, progress, all_areas):
                    return None
                if not self._check_tracks(index, progress):
                    return None
                progress.Update(85, "Checking copper text & graphics...")
                self._check_drawings(index)
                self._thin_in_planes(index)
                return index

            if is_fence:
                index = evaluate(None, dlg)
            else:
                # Where the lattice lands relative to pads, existing vias and narrow
                # zone necks changes the count a lot (e.g. a hex grid whose rows line up
                # with an existing via grid). Try a set of sub-pitch offsets and keep the best.
                offsets = [(0.0, 0.0)]
                if self.optimize_alignment:
                    step_x, step_y = self._grid_steps(pitch)
                    period_y = 2 * step_y if self.fill_type == self.FILL_TYPE_HEXAGONAL else step_y
                    n = self.ALIGNMENT_STEPS
                    offsets = [(i * step_x / n, j * period_y / n) for j in range(n) for i in range(n)]
                finalists = [offsets[0]]
                if len(offsets) > 1:
                    # Rank offsets without the (slow) plane-neck simulation...
                    scored = []
                    for k, off in enumerate(offsets):
                        sub = _SubProgress(dlg, 5 + 50 * k / len(offsets), 50.0 / len(offsets),
                                           "Grid alignment {}/{}: ".format(k + 1, len(offsets)))
                        trial = evaluate(off, sub, neck_test=False)
                        if trial is None:
                            return
                        scored.append((-sum(1 for v in trial.items if v.reason == self.REASON_OK), k, off))
                    scored.sort()  # most vias first; ties keep the earlier (default-aligned) grid
                    # ...then fully check the best few plus the default grid, so the
                    # optimised result is never worse than the unoptimised one.
                    finalists = [off for _, _, off in scored[:3]]
                    if offsets[0] not in finalists:
                        finalists.append(offsets[0])
                index, best_ok = None, -1
                for k, off in enumerate(finalists):
                    sub = _SubProgress(dlg, 55 + 30 * k / len(finalists), 30.0 / len(finalists),
                                       "Final check {}/{}: ".format(k + 1, len(finalists)) if len(finalists) > 1 else "")
                    trial = evaluate(off, sub)
                    if trial is None:
                        return
                    n_ok = sum(1 for v in trial.items if v.reason == self.REASON_OK)
                    if n_ok > best_ok:
                        index, best_ok = trial, n_ok
            if index is None:
                return
            self.candidates = len(index.items)

            ok = [v for v in index.items if v.reason == self.REASON_OK]
            for v in index.items:
                if v.reason != self.REASON_OK:
                    self.rejected[v.reason] = self.rejected.get(v.reason, 0) + 1

            if self.rejected.get(self.REASON_OTHER_SIGNAL, 0) and not self.via_through_areas:
                self.warnings.append("Tip: tick 'Allow vias through other nets' zones' to stitch through "
                                     "power planes on other layers (their fill is cleared around each via).")
            if self.candidates == 0 and self.fill_type != self.FILL_TYPE_TRACK_FENCING:
                self.warnings.append("No grid point fell inside the zone. Try a smaller pitch.")

            dlg.Update(90, "Placing vias...")
            if ok:
                if self.pcb_group is None:
                    self.pcb_group = PCB_GROUP(self.pcb)
                    self.pcb_group.SetName(VIA_GROUP_NAME)
                    self.pcb.Add(self.pcb_group)
                xs = [v.PosX for v in ok]
                ys = [v.PosY for v in ok]
                for v in ok:
                    self.AddVia(VECTOR2I(v.PosX, v.PosY))
                self.placed = len(ok)

                if self.auto_refill:
                    dlg.Update(95, "Refilling copper zones...")
                    margin = int(self.size + self.clearance)
                    bbox = BOX2I(VECTOR2I(min(xs) - margin, min(ys) - margin),
                                 VECTOR2I(max(xs) - min(xs) + 2 * margin, max(ys) - min(ys) + 2 * margin))
                    self.RefillBoardAreas(bbox)

            wxPrint(self.Summary())
            if self.filename:
                self.pcb.Save(self.filename)

        except Exception:
            self.error = traceback.format_exc()
            wxPrint("Error during execution:\n" + self.error)
        finally:
            dlg.Destroy()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: %s <KiCad pcb filename>" % sys.argv[0])
    else:
        _app = wx.App(False)
        f = FillArea(sys.argv[1])
        f.Run()
        print(f.Summary())
