import pcbnew
import wx
import json
import math
import os
from . import FillArea
from . import FillAreaDialog

def PopulateNets(anet, dlg):
    netnames = list(set([zone.GetNetname() for zone in pcbnew.GetBoard().Zones()]))
    netnames.sort()
    dlg.m_cbNet.SetItems(netnames)
    if anet is not None:
        index = dlg.m_cbNet.FindString(anet)
        if index != wx.NOT_FOUND:
            dlg.m_cbNet.Select(index)

class FillAreaDialogEx(FillAreaDialog.FillAreaDialog):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.m_Profile.Bind(wx.EVT_COMBOBOX, self.OnProfileChange)
        self.m_cbFillType.Bind(wx.EVT_COMBOBOX, self.OnPatternChange)
        self.m_Frequency.Bind(wx.EVT_TEXT, self.OnFreqChange)
        self.m_ViaSelection.Bind(wx.EVT_COMBOBOX, self.OnViaSelection)
        
        self.m_FreqLabel.Hide()
        self.m_Frequency.Hide()
        self.m_FenceOffsetLabel.Hide()
        self.m_FenceOffset.Hide()

    def OnProfileChange(self, event):
        prof = self.m_Profile.GetStringSelection()
        if prof == "RF / High-Speed":
            self.m_FreqLabel.Show()
            self.m_Frequency.Show()
            if event is not None: # Only auto-calculate if user clicked it
                self.CalculateRFGrid()
        else:
            self.m_FreqLabel.Hide()
            self.m_Frequency.Hide()
            if event is not None: # Only force defaults if user actively changed the profile
                if prof == "Thermal / High Current":
                    self.m_StepMM.SetValue("1.27")
                    # Attempt to pick the largest defined via
                    if self.m_ViaSelection.GetCount() > 0:
                        self.m_ViaSelection.SetSelection(self.m_ViaSelection.GetCount() - 1)
                        self.OnViaSelection(None)
                else: # General
                    self.m_StepMM.SetValue("2.54")
        self.Layout()
        self.Fit()

    def OnPatternChange(self, event):
        # FIX: Catch the incoming string directly
        pat = event.GetString() if event else self.m_cbFillType.GetStringSelection()
        
        if pat == "Track Fencing":
            self.m_FenceOffsetLabel.Show()
            self.m_FenceOffset.Show()
        else:
            self.m_FenceOffsetLabel.Hide()
            self.m_FenceOffset.Hide()
        self.Layout()
        self.Fit()

    def OnFreqChange(self, event):
        self.CalculateRFGrid()

    def CalculateRFGrid(self):
        # CRITICAL: Prevent calculation from firing if we aren't in RF mode
        if self.m_Profile.GetStringSelection() != "RF / High-Speed":
            return
            
        try:
            freq_val = self.m_Frequency.GetValue().replace(',', '.')
            freq_ghz = float(freq_val)
            if freq_ghz > 0:
                wavelength = 300.0 / (freq_ghz * math.sqrt(4.5))
                pitch = wavelength / 20.0 
                self.m_StepMM.SetValue(f"{pitch:.2f}")
        except ValueError:
            pass
            
    def OnViaSelection(self, event):
        # FIX: Catch the incoming string directly
        sel = event.GetString() if event else self.m_ViaSelection.GetStringSelection()
        if "/" in sel:
            parts = sel.split("/")
            if len(parts) == 2:
                self.m_SizeMM.SetValue(parts[0].strip())
                self.m_DrillMM.SetValue(parts[1].strip())

class FillAreaAction(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Via Stitching Generator"
        self.category = "Modify PCB"
        self.description = "Intelligent Via Stitching for PCB Zones & RF"
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "./stitching-vias.png")
        self.show_toolbar_button = True

    def Run(self):
        pcb_frame = next((win for win in wx.GetTopLevelWindows() if win.GetName() == 'PcbFrame'), None)
        
        a = FillAreaDialogEx(pcb_frame)
        self.board = pcbnew.GetBoard()
        self.boardDesignSettings = self.board.GetDesignSettings()
        
        img_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "stitching-vias-help.png")
        if os.path.exists(img_path):
            a.m_bitmapStitching.SetBitmap(wx.Bitmap(img_path))

        PopulateNets("GND", a)

        via_list = []
        try:
            if hasattr(self.boardDesignSettings, 'm_ViasDimensionsList'):
                vias = self.boardDesignSettings.m_ViasDimensionsList
            elif hasattr(self.boardDesignSettings, 'GetViasDimensionsList'):
                vias = self.boardDesignSettings.GetViasDimensionsList()
            else:
                vias = []
                
            for i in range(len(vias)):
                via = vias[i]
                dia = pcbnew.ToMM(via.m_Diameter)
                drill = pcbnew.ToMM(via.m_Drill)
                if dia > 0 and drill > 0:
                    via_list.append(f"{dia:.4g} / {drill:.4g}")
        except Exception:
            pass
            
        if not via_list:
            dia = pcbnew.ToMM(self.boardDesignSettings.GetCurrentViaSize())
            drill = pcbnew.ToMM(self.boardDesignSettings.GetCurrentViaDrill())
            via_list.append(f"{dia:.4g} / {drill:.4g}")

        via_list = list(dict.fromkeys(via_list))
        a.m_ViaSelection.SetItems(via_list)
        if via_list:
            a.m_ViaSelection.SetSelection(0)
            a.OnViaSelection(None)
        
        a.m_StepMM.SetValue("2.54")
        a.m_ClearanceMM.SetValue(str(pcbnew.ToMM(self.boardDesignSettings.GetSmallestClearanceValue())))

        config_file = os.path.join(os.path.dirname(__file__), "viastitching_config.json")
        try:
            with open(config_file, 'r') as f:
                cfg = json.load(f)
                if 'step' in cfg: a.m_StepMM.SetValue(cfg['step'])
                if 'size' in cfg: a.m_SizeMM.SetValue(cfg['size'])
                if 'drill' in cfg: a.m_DrillMM.SetValue(cfg['drill'])
                if 'clearance' in cfg: a.m_ClearanceMM.SetValue(cfg['clearance'])
                if 'extra_clearance' in cfg: a.m_ExtraClearance.SetValue(cfg['extra_clearance'])
                if 'fence_offset' in cfg: a.m_FenceOffset.SetValue(cfg['fence_offset'])
                if 'netname' in cfg:
                    idx = a.m_cbNet.FindString(cfg['netname'])
                    if idx >= 0: a.m_cbNet.SetSelection(idx)
                if 'fill_type' in cfg:
                    idx = a.m_cbFillType.FindString(cfg['fill_type'])
                    if idx >= 0: 
                        a.m_cbFillType.SetSelection(idx)
                        a.OnPatternChange(None)
                if 'only_selected' in cfg: a.m_only_selected.SetValue(cfg['only_selected'])
                if 'viaThroughAreas' in cfg: a.m_viaThroughAreas.SetValue(cfg['viaThroughAreas'])
                if 'sameNetTracks' in cfg: a.m_sameNetTracks.SetValue(cfg['sameNetTracks'])
                if 'avoidSameNetPads' in cfg: a.m_avoidSameNetPads.SetValue(cfg['avoidSameNetPads'])
                if 'auto_refill' in cfg: a.m_AutoRefill.SetValue(cfg['auto_refill'])
                if 'profile' in cfg:
                    idx = a.m_Profile.FindString(cfg['profile'])
                    if idx >= 0: 
                        a.m_Profile.SetSelection(idx)
                        a.OnProfileChange(None)
                if 'frequency' in cfg: a.m_Frequency.SetValue(cfg['frequency'])
        except Exception:
            pass

        modal_result = a.ShowModal()
        if modal_result == wx.ID_OK:
            try:
                cfg = {
                    'step': a.m_StepMM.GetValue(),
                    'size': a.m_SizeMM.GetValue(),
                    'drill': a.m_DrillMM.GetValue(),
                    'clearance': a.m_ClearanceMM.GetValue(),
                    'extra_clearance': a.m_ExtraClearance.GetValue(),
                    'fence_offset': a.m_FenceOffset.GetValue(),
                    'netname': a.m_cbNet.GetStringSelection(),
                    'fill_type': a.m_cbFillType.GetStringSelection(),
                    'only_selected': a.m_only_selected.IsChecked(),
                    'viaThroughAreas': a.m_viaThroughAreas.IsChecked(),
                    'sameNetTracks': a.m_sameNetTracks.IsChecked(),
                    'avoidSameNetPads': a.m_avoidSameNetPads.IsChecked(),
                    'auto_refill': a.m_AutoRefill.IsChecked(),
                    'profile': a.m_Profile.GetStringSelection(),
                    'frequency': a.m_Frequency.GetValue()
                }
                with open(config_file, 'w') as f:
                    json.dump(cfg, f)
            except Exception as e:
                print("Failed to save configuration:", e)

            wx.LogMessage('Via Stitching Execution Started')
            
            fill = FillArea.FillArea()
            fill.SetStepMM(float(a.m_StepMM.GetValue().replace(',', '.')))
            fill.SetSizeMM(float(a.m_SizeMM.GetValue().replace(',', '.')))
            fill.SetDrillMM(float(a.m_DrillMM.GetValue().replace(',', '.')))
            fill.SetClearanceMM(float(a.m_ClearanceMM.GetValue().replace(',', '.')))
            
            try:
                ext_c = float(a.m_ExtraClearance.GetValue().replace(',', '.'))
            except ValueError:
                ext_c = 0.0
            fill.SetExtraClearanceMM(ext_c)
            
            try:
                fen_off = float(a.m_FenceOffset.GetValue().replace(',', '.'))
            except ValueError:
                fen_off = 1.0
            fill.SetFenceOffsetMM(fen_off)
            
            fill.SetNetname(a.m_cbNet.GetStringSelection())
            fill.SetViaThroughAreas(a.m_viaThroughAreas.IsChecked())
            fill.SetType(a.m_cbFillType.GetStringSelection())
            fill.SetSameNetTracks(a.m_sameNetTracks.IsChecked())
            fill.SetAvoidSameNetPads(a.m_avoidSameNetPads.IsChecked())
            fill.SetAutoRefill(a.m_AutoRefill.IsChecked())
            
            if a.m_only_selected.IsChecked():
                fill.OnlyOnSelectedArea()
            fill.Run()

        a.Destroy()

FillAreaAction().register()