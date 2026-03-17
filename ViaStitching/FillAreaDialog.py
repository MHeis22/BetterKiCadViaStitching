# -*- coding: utf-8 -*-
import wx

class FillAreaDialog(wx.Dialog):
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, id=wx.ID_ANY, title=u"Via Stitching Parameters", pos=wx.DefaultPosition, size=wx.Size(480, 800), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        
        self.m_bitmapStitching = wx.StaticBitmap(self, wx.ID_ANY, wx.NullBitmap, wx.DefaultPosition, wx.DefaultSize, 0)
        mainSizer.Add(self.m_bitmapStitching, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10)

        # --- Group 1: Target ---
        targetBox = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, u"Target Zone / Net"), wx.VERTICAL)
        fgTarget = wx.FlexGridSizer(0, 2, 8, 8)
        fgTarget.AddGrowableCol(1)
        
        fgTarget.Add(wx.StaticText(self, wx.ID_ANY, u"Net Name:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_cbNet = wx.ComboBox(self, wx.ID_ANY, u"GND", choices=[], style=wx.CB_READONLY)
        fgTarget.Add(self.m_cbNet, 1, wx.EXPAND | wx.ALL, 5)

        fgTarget.Add(wx.StaticText(self, wx.ID_ANY, u"Fill Pattern:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        # Reduced choices to the essentials
        self.m_cbFillType = wx.ComboBox(self, wx.ID_ANY, u"Rectangular", choices=[u"Rectangular", u"Hexagonal", u"Track Fencing"], style=wx.CB_READONLY)
        self.m_cbFillType.SetSelection(0)
        fgTarget.Add(self.m_cbFillType, 1, wx.EXPAND | wx.ALL, 5)
        
        targetBox.Add(fgTarget, 1, wx.EXPAND, 5)
        mainSizer.Add(targetBox, 0, wx.EXPAND | wx.ALL, 10)

        # --- Group 2: Stitching Profile ---
        profBox = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, u"Stitching Profile"), wx.VERTICAL)
        fgProf = wx.FlexGridSizer(0, 2, 8, 8)
        fgProf.AddGrowableCol(1)
        
        fgProf.Add(wx.StaticText(self, wx.ID_ANY, u"Application / Logic:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_Profile = wx.ComboBox(self, wx.ID_ANY, u"General / Mechanical", choices=[u"General / Mechanical", u"Thermal / High Current", u"RF / High-Speed"], style=wx.CB_READONLY)
        fgProf.Add(self.m_Profile, 1, wx.EXPAND | wx.ALL, 5)
        
        self.m_FreqLabel = wx.StaticText(self, wx.ID_ANY, u"Max Target Freq. (GHz):")
        fgProf.Add(self.m_FreqLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_Frequency = wx.TextCtrl(self, wx.ID_ANY, u"2.4")
        fgProf.Add(self.m_Frequency, 1, wx.EXPAND | wx.ALL, 5)
        
        profBox.Add(fgProf, 1, wx.EXPAND, 5)
        mainSizer.Add(profBox, 0, wx.EXPAND | wx.ALL, 10)

        # --- Group 3: Via Dimensions ---
        dimBox = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, u"Via Dimensions"), wx.VERTICAL)
        fgDim = wx.FlexGridSizer(0, 2, 8, 8)
        fgDim.AddGrowableCol(1)
        
        fgDim.Add(wx.StaticText(self, wx.ID_ANY, u"Board Defined Vias:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_ViaSelection = wx.ComboBox(self, wx.ID_ANY, choices=[], style=wx.CB_READONLY)
        fgDim.Add(self.m_ViaSelection, 1, wx.EXPAND | wx.ALL, 5)

        fgDim.Add(wx.StaticText(self, wx.ID_ANY, u"Outer Diameter (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_SizeMM = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString)
        fgDim.Add(self.m_SizeMM, 1, wx.EXPAND | wx.ALL, 5)
        
        fgDim.Add(wx.StaticText(self, wx.ID_ANY, u"Hole Diameter (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_DrillMM = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString)
        fgDim.Add(self.m_DrillMM, 1, wx.EXPAND | wx.ALL, 5)
        
        fgDim.Add(wx.StaticText(self, wx.ID_ANY, u"Via Clearance (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_ClearanceMM = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString)
        fgDim.Add(self.m_ClearanceMM, 1, wx.EXPAND | wx.ALL, 5)

        fgDim.Add(wx.StaticText(self, wx.ID_ANY, u"Extra Safe Clearance:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_ExtraClearance = wx.TextCtrl(self, wx.ID_ANY, u"0.0")
        fgDim.Add(self.m_ExtraClearance, 1, wx.EXPAND | wx.ALL, 5)

        fgDim.Add(wx.StaticText(self, wx.ID_ANY, u"Via Grid / Pitch (mm):"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_StepMM = wx.TextCtrl(self, wx.ID_ANY, wx.EmptyString)
        fgDim.Add(self.m_StepMM, 1, wx.EXPAND | wx.ALL, 5)
        
        self.m_FenceOffsetLabel = wx.StaticText(self, wx.ID_ANY, u"Fence Offset (mm):")
        fgDim.Add(self.m_FenceOffsetLabel, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.m_FenceOffset = wx.TextCtrl(self, wx.ID_ANY, u"1.0")
        fgDim.Add(self.m_FenceOffset, 1, wx.EXPAND | wx.ALL, 5)

        dimBox.Add(fgDim, 1, wx.EXPAND, 5)
        mainSizer.Add(dimBox, 0, wx.EXPAND | wx.ALL, 10)

        # --- Group 4: Constraints ---
        constBox = wx.StaticBoxSizer(wx.StaticBox(self, wx.ID_ANY, u"Constraints"), wx.VERTICAL)
        
        self.m_only_selected = wx.CheckBox(self, wx.ID_ANY, u"Only apply under selected Zone")
        constBox.Add(self.m_only_selected, 0, wx.ALL, 6)
        
        self.m_viaThroughAreas = wx.CheckBox(self, wx.ID_ANY, u"Ignore areas on other layers")
        constBox.Add(self.m_viaThroughAreas, 0, wx.ALL, 6)
        
        self.m_sameNetTracks = wx.CheckBox(self, wx.ID_ANY, u"Allow vias on tracks with same net")
        constBox.Add(self.m_sameNetTracks, 0, wx.ALL, 6)
        
        self.m_avoidSameNetPads = wx.CheckBox(self, wx.ID_ANY, u"Prevent vias on same net pads")
        self.m_avoidSameNetPads.SetValue(True)
        constBox.Add(self.m_avoidSameNetPads, 0, wx.ALL, 6)
        
        self.m_AutoRefill = wx.CheckBox(self, wx.ID_ANY, u"Automatically refill zones")
        self.m_AutoRefill.SetValue(True)
        constBox.Add(self.m_AutoRefill, 0, wx.ALL, 6)
        
        mainSizer.Add(constBox, 0, wx.EXPAND | wx.ALL, 10)

        # --- Buttons ---
        btnSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.m_button1 = wx.Button(self, wx.ID_OK, u"Run")
        self.m_button1.SetDefault()
        btnSizer.Add(self.m_button1, 0, wx.ALL, 5)
        
        self.m_button2 = wx.Button(self, wx.ID_CANCEL, u"Cancel")
        btnSizer.Add(self.m_button2, 0, wx.ALL, 5)
        
        mainSizer.Add(btnSizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        self.SetSizer(mainSizer)
        self.Layout()
        
        current_size = self.GetSize()
        self.SetSize(wx.Size(current_size.x + 30, current_size.y + 40))
        self.SetMinSize(self.GetSize())
        self.Centre(wx.BOTH)