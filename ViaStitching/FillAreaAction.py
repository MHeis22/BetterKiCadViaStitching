import pcbnew
import wx
import json
import math
import os
from . import FillArea
from . import FillAreaDialog


def _float(text):
    return float(text.strip().replace(',', '.'))


def PopulateNets(anet, dlg):
    board = pcbnew.GetBoard()
    netnames = set(zone.GetNetname() for zone in board.Zones() if not zone.GetIsRuleArea())
    netnames.discard("")
    # Track fencing does not need a zone on the net, so always offer the ground net
    for gnd in ("GND", "/GND"):
        if board.FindNet(gnd) is not None:
            netnames.add(gnd)
    netnames = sorted(netnames)
    dlg.m_cbNet.SetItems(netnames)
    if anet is not None:
        index = dlg.m_cbNet.FindString(anet)
        if index != wx.NOT_FOUND:
            dlg.m_cbNet.Select(index)
    if dlg.m_cbNet.GetSelection() == wx.NOT_FOUND and netnames:
        dlg.m_cbNet.Select(0)


class FillAreaDialogEx(FillAreaDialog.FillAreaDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.m_Profile.Bind(wx.EVT_COMBOBOX, self.OnProfileChange)
        self.m_cbFillType.Bind(wx.EVT_COMBOBOX, self.OnPatternChange)
        self.m_Frequency.Bind(wx.EVT_TEXT, self.OnFreqChange)
        self.m_Er.Bind(wx.EVT_TEXT, self.OnFreqChange)
        self.m_ViaSelection.Bind(wx.EVT_COMBOBOX, self.OnViaSelection)
        self.m_button1.Bind(wx.EVT_BUTTON, self.OnOK)

        for w in (self.m_FreqLabel, self.m_Frequency, self.m_ErLabel, self.m_Er,
                  self.m_FenceOffsetLabel, self.m_FenceOffset):
            w.Hide()

        self.UpdateProfileDescription()
        self.RefreshLayout()

    def UpdateProfileDescription(self):
        prof = self.m_Profile.GetStringSelection()
        if prof == "General / Mechanical":
            desc = "Standard via stitching. Provides solid ground connections across the board and prevents large copper islands from peeling. Uses standard pitch (e.g., 2.54mm)."
        elif prof == "Thermal / High Current":
            desc = "Optimized for heat dissipation and low resistance. Uses a denser grid (e.g., 1.27mm) and defaults to the largest available via size. Ideal under power components or large ICs."
        elif prof == "RF / High-Speed":
            desc = "Calculates via pitch based on wavelength (λ/20) for the target frequency. Prevents resonance and electromagnetic emissions. Pitch adjusts automatically when frequency changes. Also use with Track Fencing pattern while highlighting a trace."
        else:
            desc = ""

        self.m_ProfileDesc.SetLabel(desc)
        self.m_ProfileDesc.Wrap(380)

    def OnProfileChange(self, event):
        prof = self.m_Profile.GetStringSelection()
        self.UpdateProfileDescription()

        is_rf = prof == "RF / High-Speed"
        for w in (self.m_FreqLabel, self.m_Frequency, self.m_ErLabel, self.m_Er):
            w.Show(is_rf)

        if event is not None:  # Only force defaults if the user actively changed the profile
            if is_rf:
                self.CalculateRFGrid()
            elif prof == "Thermal / High Current":
                self.m_StepMM.SetValue("1.27")
                self.SelectLargestVia()
            else:
                self.m_StepMM.SetValue("2.54")
        self.RefreshLayout()

    def SelectLargestVia(self):
        best, best_dia = wx.NOT_FOUND, -1.0
        for i in range(self.m_ViaSelection.GetCount()):
            try:
                dia = _float(self.m_ViaSelection.GetString(i).split("/")[0])
            except ValueError:
                continue
            if dia > best_dia:
                best, best_dia = i, dia
        if best != wx.NOT_FOUND:
            self.m_ViaSelection.SetSelection(best)
            self.OnViaSelection(None)

    def OnPatternChange(self, event):
        pat = event.GetString() if event else self.m_cbFillType.GetStringSelection()
        is_fence = pat == "Track Fencing"
        self.m_FenceOffsetLabel.Show(is_fence)
        self.m_FenceOffset.Show(is_fence)
        self.RefreshLayout()

    def OnFreqChange(self, event):
        self.CalculateRFGrid()

    def CalculateRFGrid(self):
        if self.m_Profile.GetStringSelection() != "RF / High-Speed":
            return
        try:
            freq_ghz = _float(self.m_Frequency.GetValue())
            er = _float(self.m_Er.GetValue())
            if freq_ghz > 0 and er >= 1:
                wavelength_mm = 299.792458 / (freq_ghz * math.sqrt(er))
                self.m_StepMM.SetValue(f"{wavelength_mm / 20.0:.2f}")
        except ValueError:
            pass

    def OnViaSelection(self, event):
        sel = event.GetString() if event else self.m_ViaSelection.GetStringSelection()
        parts = sel.split("/")
        if len(parts) == 2:
            self.m_SizeMM.SetValue(parts[0].strip())
            self.m_DrillMM.SetValue(parts[1].strip())

    def Validate_(self):
        """Returns an error message, or None if all inputs are usable."""
        def num(ctrl, name, allow_zero=False):
            try:
                v = _float(ctrl.GetValue())
            except ValueError:
                return "'{}' is not a number.".format(name), ctrl
            if v < 0 or (v == 0 and not allow_zero):
                return "'{}' must be greater than zero.".format(name), ctrl
            return None, v

        if self.m_cbNet.GetSelection() == wx.NOT_FOUND:
            return "Select a net to stitch.", self.m_cbNet
        checks = [(self.m_SizeMM, "Outer Diameter", False), (self.m_DrillMM, "Hole Diameter", False),
                  (self.m_ClearanceMM, "Via Clearance", True), (self.m_ExtraClearance, "Extra Safe Clearance", True),
                  (self.m_StepMM, "Via Grid / Pitch", False)]
        if self.m_cbFillType.GetStringSelection() == "Track Fencing":
            checks.append((self.m_FenceOffset, "Fence Offset", True))
        values = {}
        for ctrl, name, allow_zero in checks:
            err, v = num(ctrl, name, allow_zero=allow_zero)
            if err:
                return err, ctrl
            values[name] = v
        if values["Hole Diameter"] >= values["Outer Diameter"]:
            return "Hole diameter must be smaller than the outer diameter.", self.m_DrillMM
        return None, None

    def OnOK(self, event):
        err, ctrl = self.Validate_()
        if err:
            wx.MessageBox(err, "Via Stitching", wx.OK | wx.ICON_WARNING, self)
            if ctrl is not None:
                ctrl.SetFocus()
            return
        event.Skip()


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
        try:
            self._Run(a, pcb_frame)
        finally:
            a.Destroy()

    def _Run(self, a, pcb_frame):
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
            # ChangeValue() does not emit EVT_TEXT, so restoring the frequency
            # no longer overwrites the saved pitch with a recalculated RF value.
            if 'frequency' in cfg: a.m_Frequency.ChangeValue(cfg['frequency'])
            if 'er' in cfg: a.m_Er.ChangeValue(cfg['er'])
            if 'profile' in cfg:
                idx = a.m_Profile.FindString(cfg['profile'])
                if idx >= 0:
                    a.m_Profile.SetSelection(idx)
                    a.OnProfileChange(None)
            if 'size' in cfg: a.m_SizeMM.SetValue(cfg['size'])
            if 'drill' in cfg: a.m_DrillMM.SetValue(cfg['drill'])
            sel = "{} / {}".format(a.m_SizeMM.GetValue(), a.m_DrillMM.GetValue())
            a.m_ViaSelection.SetSelection(a.m_ViaSelection.FindString(sel))  # NOT_FOUND clears it
            if 'step' in cfg: a.m_StepMM.SetValue(cfg['step'])
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
            if 'optimize_alignment' in cfg: a.m_OptimizeAlignment.SetValue(cfg['optimize_alignment'])
        except Exception:
            pass

        if a.ShowModal() != wx.ID_OK:
            return

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
                'optimize_alignment': a.m_OptimizeAlignment.IsChecked(),
                'profile': a.m_Profile.GetStringSelection(),
                'frequency': a.m_Frequency.GetValue(),
                'er': a.m_Er.GetValue(),
            }
            with open(config_file, 'w') as f:
                json.dump(cfg, f)
        except Exception as e:
            print("Failed to save configuration:", e)

        fill = FillArea.FillArea()
        fill.SetStepMM(_float(a.m_StepMM.GetValue()))
        fill.SetSizeMM(_float(a.m_SizeMM.GetValue()))
        fill.SetDrillMM(_float(a.m_DrillMM.GetValue()))
        fill.SetClearanceMM(_float(a.m_ClearanceMM.GetValue()))
        fill.SetExtraClearanceMM(_float(a.m_ExtraClearance.GetValue()))
        if a.m_cbFillType.GetStringSelection() == "Track Fencing":
            fill.SetFenceOffsetMM(_float(a.m_FenceOffset.GetValue()))
        fill.SetNetname(a.m_cbNet.GetStringSelection())
        fill.SetViaThroughAreas(a.m_viaThroughAreas.IsChecked())
        fill.SetType(a.m_cbFillType.GetStringSelection())
        fill.SetSameNetTracks(a.m_sameNetTracks.IsChecked())
        fill.SetAvoidSameNetPads(a.m_avoidSameNetPads.IsChecked())
        fill.SetAutoRefill(a.m_AutoRefill.IsChecked())
        fill.SetOptimizeAlignment(a.m_OptimizeAlignment.IsChecked())
        if a.m_only_selected.IsChecked():
            fill.OnlyOnSelectedArea()

        a.Hide()
        fill.Run()

        icon = wx.ICON_ERROR if fill.error else (wx.ICON_INFORMATION if fill.placed else wx.ICON_WARNING)
        wx.MessageBox(fill.Summary(), "Via Stitching", wx.OK | icon, pcb_frame)


FillAreaAction().register()
