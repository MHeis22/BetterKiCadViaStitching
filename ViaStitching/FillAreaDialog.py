# -*- coding: utf-8 -*-
import wx


class FillAreaDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, id=wx.ID_ANY, title=u"Via Stitching Parameters", pos=wx.DefaultPosition,
                           style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        # All settings live in a scrolled panel; the buttons sit outside it so they are
        # always visible, even on short laptop screens without a scroll wheel.
        self.m_scroll = wx.ScrolledWindow(self, wx.ID_ANY, style=wx.VSCROLL)
        self.m_scroll.SetScrollRate(0, 20)
        p = self.m_scroll
        mainSizer = wx.BoxSizer(wx.VERTICAL)

        self.m_bitmapStitching = wx.StaticBitmap(p, wx.ID_ANY, wx.NullBitmap, wx.DefaultPosition, wx.DefaultSize, 0)
        mainSizer.Add(self.m_bitmapStitching, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 6)

        # --- Group 1: Target ---
        targetBox = wx.StaticBoxSizer(wx.StaticBox(p, wx.ID_ANY, u"Target Zone / Net"), wx.VERTICAL)
        fgTarget = wx.FlexGridSizer(0, 2, 4, 8)
        fgTarget.AddGrowableCol(1)

        fgTarget.Add(wx.StaticText(p, wx.ID_ANY, u"Net Name:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_cbNet = wx.ComboBox(p, wx.ID_ANY, u"GND", choices=[], style=wx.CB_READONLY)
        fgTarget.Add(self.m_cbNet, 1, wx.EXPAND | wx.ALL, 3)

        fgTarget.Add(wx.StaticText(p, wx.ID_ANY, u"Fill Pattern:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_cbFillType = wx.ComboBox(p, wx.ID_ANY, u"Rectangular", choices=[u"Rectangular", u"Hexagonal", u"Track Fencing"], style=wx.CB_READONLY)
        self.m_cbFillType.SetSelection(0)
        fgTarget.Add(self.m_cbFillType, 1, wx.EXPAND | wx.ALL, 3)

        targetBox.Add(fgTarget, 1, wx.EXPAND, 3)
        mainSizer.Add(targetBox, 0, wx.EXPAND | wx.ALL, 6)

        # --- Group 2: Stitching Profile ---
        profBox = wx.StaticBoxSizer(wx.StaticBox(p, wx.ID_ANY, u"Stitching Profile"), wx.VERTICAL)
        fgProf = wx.FlexGridSizer(0, 2, 4, 8)
        fgProf.AddGrowableCol(1)

        fgProf.Add(wx.StaticText(p, wx.ID_ANY, u"Application / Logic:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_Profile = wx.ComboBox(p, wx.ID_ANY, u"General / Mechanical", choices=[u"General / Mechanical", u"Thermal / High Current", u"RF / High-Speed"], style=wx.CB_READONLY)
        fgProf.Add(self.m_Profile, 1, wx.EXPAND | wx.ALL, 3)

        self.m_FreqLabel = wx.StaticText(p, wx.ID_ANY, u"Max Target Freq. (GHz):")
        fgProf.Add(self.m_FreqLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_Frequency = wx.TextCtrl(p, wx.ID_ANY, u"2.4")
        fgProf.Add(self.m_Frequency, 1, wx.EXPAND | wx.ALL, 3)

        self.m_ErLabel = wx.StaticText(p, wx.ID_ANY, u"Dielectric Constant (εr):")
        fgProf.Add(self.m_ErLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_Er = wx.TextCtrl(p, wx.ID_ANY, u"4.5")
        self.m_Er.SetToolTip(u"FR-4 is about 4.2-4.6. Using the full εr (not εeff) is conservative for microstrip.")
        fgProf.Add(self.m_Er, 1, wx.EXPAND | wx.ALL, 3)

        profBox.Add(fgProf, 1, wx.EXPAND, 3)

        self.m_ProfileDesc = wx.StaticText(p, wx.ID_ANY, u"Description will appear here.")
        font = self.m_ProfileDesc.GetFont()
        font.SetStyle(wx.FONTSTYLE_ITALIC)
        self.m_ProfileDesc.SetFont(font)
        self.m_ProfileDesc.Wrap(380)
        profBox.Add(self.m_ProfileDesc, 0, wx.ALL | wx.EXPAND, 3)

        mainSizer.Add(profBox, 0, wx.EXPAND | wx.ALL, 6)

        # --- Group 3: Via Dimensions ---
        dimBox = wx.StaticBoxSizer(wx.StaticBox(p, wx.ID_ANY, u"Via Dimensions"), wx.VERTICAL)
        fgDim = wx.FlexGridSizer(0, 2, 4, 8)
        fgDim.AddGrowableCol(1)

        fgDim.Add(wx.StaticText(p, wx.ID_ANY, u"Board Defined Vias:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_ViaSelection = wx.ComboBox(p, wx.ID_ANY, choices=[], style=wx.CB_READONLY)
        fgDim.Add(self.m_ViaSelection, 1, wx.EXPAND | wx.ALL, 3)

        fgDim.Add(wx.StaticText(p, wx.ID_ANY, u"Outer Diameter (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_SizeMM = wx.TextCtrl(p, wx.ID_ANY, wx.EmptyString)
        fgDim.Add(self.m_SizeMM, 1, wx.EXPAND | wx.ALL, 3)

        fgDim.Add(wx.StaticText(p, wx.ID_ANY, u"Hole Diameter (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_DrillMM = wx.TextCtrl(p, wx.ID_ANY, wx.EmptyString)
        fgDim.Add(self.m_DrillMM, 1, wx.EXPAND | wx.ALL, 3)

        fgDim.Add(wx.StaticText(p, wx.ID_ANY, u"Via Clearance (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_ClearanceMM = wx.TextCtrl(p, wx.ID_ANY, wx.EmptyString)
        self.m_ClearanceMM.SetToolTip(u"Copper-to-copper clearance between the via ring and anything else.")
        fgDim.Add(self.m_ClearanceMM, 1, wx.EXPAND | wx.ALL, 3)

        fgDim.Add(wx.StaticText(p, wx.ID_ANY, u"Extra Safe Clearance (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_ExtraClearance = wx.TextCtrl(p, wx.ID_ANY, u"0.0")
        self.m_ExtraClearance.SetToolTip(u"Added to the clearance for copper of other nets only.")
        fgDim.Add(self.m_ExtraClearance, 1, wx.EXPAND | wx.ALL, 3)

        fgDim.Add(wx.StaticText(p, wx.ID_ANY, u"Via Grid / Pitch (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_StepMM = wx.TextCtrl(p, wx.ID_ANY, wx.EmptyString)
        self.m_StepMM.SetToolTip(u"Centre-to-centre via spacing. Raised automatically to diameter + clearance if smaller.")
        fgDim.Add(self.m_StepMM, 1, wx.EXPAND | wx.ALL, 3)

        self.m_FenceOffsetLabel = wx.StaticText(p, wx.ID_ANY, u"Fence Offset (mm):")
        fgDim.Add(self.m_FenceOffsetLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 3)
        self.m_FenceOffset = wx.TextCtrl(p, wx.ID_ANY, u"1.0")
        self.m_FenceOffset.SetToolTip(u"Distance from the track edge to the via centre.")
        fgDim.Add(self.m_FenceOffset, 1, wx.EXPAND | wx.ALL, 3)

        dimBox.Add(fgDim, 1, wx.EXPAND, 3)
        mainSizer.Add(dimBox, 0, wx.EXPAND | wx.ALL, 6)

        # --- Group 4: Constraints ---
        constBox = wx.StaticBoxSizer(wx.StaticBox(p, wx.ID_ANY, u"Constraints"), wx.VERTICAL)

        self.m_only_selected = wx.CheckBox(p, wx.ID_ANY, u"Only apply under selected zone")
        constBox.Add(self.m_only_selected, 0, wx.ALL, 4)

        self.m_viaThroughAreas = wx.CheckBox(p, wx.ID_ANY, u"Allow vias through other nets' zones")
        self.m_viaThroughAreas.SetToolTip(u"Needed on multilayer boards with power planes: otherwise any point covered by "
                                          u"another net's zone on any layer is skipped. That zone's fill is cleared around each via.")
        self.m_viaThroughAreas.SetValue(True)
        constBox.Add(self.m_viaThroughAreas, 0, wx.ALL, 4)

        self.m_sameNetTracks = wx.CheckBox(p, wx.ID_ANY, u"Allow vias on tracks with same net")
        constBox.Add(self.m_sameNetTracks, 0, wx.ALL, 4)

        self.m_avoidSameNetPads = wx.CheckBox(p, wx.ID_ANY, u"Prevent vias on same net pads")
        self.m_avoidSameNetPads.SetValue(True)
        constBox.Add(self.m_avoidSameNetPads, 0, wx.ALL, 4)

        self.m_OptimizeAlignment = wx.CheckBox(p, wx.ID_ANY, u"Optimise grid alignment (places more vias)")
        self.m_OptimizeAlignment.SetToolTip(u"Tries 16 sub-pitch offsets of the grid and keeps the one that fits the most vias "
                                            u"around pads, existing vias and narrow zone areas. Untick for a grid anchored to the board corner.")
        self.m_OptimizeAlignment.SetValue(True)
        constBox.Add(self.m_OptimizeAlignment, 0, wx.ALL, 4)

        self.m_AutoRefill = wx.CheckBox(p, wx.ID_ANY, u"Automatically refill zones")
        self.m_AutoRefill.SetValue(True)
        constBox.Add(self.m_AutoRefill, 0, wx.ALL, 4)

        mainSizer.Add(constBox, 0, wx.EXPAND | wx.ALL, 6)

        # Keep content clear of overlay scrollbars (macOS draws them on top of the client area)
        sb_w = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        wrapSizer = wx.BoxSizer(wx.HORIZONTAL)
        wrapSizer.Add(mainSizer, 1, wx.EXPAND | wx.RIGHT, max(sb_w, 16))
        p.SetSizer(wrapSizer)

        # --- Buttons (outside the scrolled area) ---
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.m_scroll, 1, wx.EXPAND)
        outer.Add(wx.StaticLine(self), 0, wx.EXPAND)
        btnSizer = wx.StdDialogButtonSizer()
        self.m_button1 = wx.Button(self, wx.ID_OK, u"Place Vias")
        self.m_button1.SetDefault()
        btnSizer.AddButton(self.m_button1)
        self.m_button2 = wx.Button(self, wx.ID_CANCEL, u"Cancel")
        btnSizer.AddButton(self.m_button2)
        btnSizer.Realize()
        outer.Add(btnSizer, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer)

        self.FitToScreen()

    def RefreshLayout(self):
        # After showing/hiding rows: re-layout inside the scroll area instead of
        # Fit(), which grew the dialog past the bottom of the screen.
        self.m_scroll.Layout()
        self.m_scroll.FitInside()
        self.Layout()

    def FitToScreen(self):
        self.m_scroll.Layout()
        content = self.m_scroll.GetSizer().CalcMin()
        buttons_h = self.m_button1.GetBestSize().y + 2 * 8 + 2
        idx = wx.Display.GetFromWindow(self.GetParent()) if self.GetParent() else wx.NOT_FOUND
        area = wx.Display(idx if idx != wx.NOT_FOUND else 0).GetClientArea()
        scrollbar = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        if scrollbar <= 0:
            scrollbar = 16

        frame_extra = self.GetSize() - self.GetClientSize()
        want_w = content.x + scrollbar + frame_extra.x
        want_h = content.y + buttons_h + frame_extra.y
        w = min(want_w, int(area.width * 0.95))
        h = min(want_h, int(area.height * 0.9))

        self.m_scroll.SetMinSize(wx.Size(-1, 120))
        self.SetMinSize(wx.Size(min(w, 360), min(h, 300)))
        self.SetSize(wx.Size(w, h))
        self.m_scroll.FitInside()
        self.Layout()
        self.Centre(wx.BOTH)
        # Centring on the KiCad window can push the dialog past the screen edge
        # (e.g. when the editor window sits low): keep it fully on the display.
        pos = self.GetPosition()
        x = min(max(pos.x, area.x), area.x + area.width - w)
        y = min(max(pos.y, area.y), area.y + area.height - h)
        self.SetPosition(wx.Point(x, y))
