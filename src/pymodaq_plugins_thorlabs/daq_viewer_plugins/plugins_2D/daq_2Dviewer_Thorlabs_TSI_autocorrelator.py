from qtpy.QtCore import QThread, Slot, QRectF
from qtpy import QtWidgets
import numpy as np
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, main, comon_parameters

from pymodaq.utils.daq_utils import ThreadCommand
from pymodaq.utils.data import DataFromPlugins, Axis, DataToExport
from pymodaq.utils.parameter import Parameter
from pymodaq.utils.parameter.utils import iter_children

import laserbeamsize as lbs
import numba
from pymodaq_plugins_thorlabs.daq_viewer_plugins.plugins_2D.daq_2Dviewer_Thorlabs_TSI import DAQ_2DViewer_Thorlabs_TSI, main


from scipy.optimize import curve_fit

from pylablib.devices import Thorlabs
from qtpy import QtWidgets, QtCore
class DAQ_2DViewer_Thorlabs_TSI_autocorrelator(DAQ_2DViewer_Thorlabs_TSI):

    serialnumbers = Thorlabs.list_cameras_tlcam()
    params = comon_parameters + [
        {'title': 'Camera name:', 'name': 'camera_name', 'type': 'str', 'value': '', 'readonly': True},
        {'title': 'Serial number:', 'name': 'serial_number', 'type': 'list', 'limits': serialnumbers},
        #{'title': 'Sensor type:', 'name': 'sensor', 'type': 'str', 'value': '', 'readonly': True},
        #this will be used once pylablib accepts PR52
        {'title': 'Sensor type:', 'name': 'sensor', 'type': 'list', 'limits': ['Monochrome', 'Bayer']},
        {'title': 'Ouput Color:', 'name': 'output_color', 'type': 'list', 'limits': ['RGB', 'MonoChrome']},
        {'title': 'Update ROI', 'name': 'update_roi', 'type': 'bool_push', 'value': False},
        {'title': 'Clear ROI+Bin', 'name': 'clear_roi', 'type': 'bool_push', 'value': False},
        {'title': 'X binning', 'name': 'x_binning', 'type': 'int', 'value': 1},
        {'title': 'Y binning', 'name': 'y_binning', 'type': 'int', 'value': 1},
        {'title': 'Image width', 'name': 'hdet', 'type': 'int', 'value': 1, 'readonly': True},
        {'title': 'Image height', 'name': 'vdet', 'type': 'int', 'value': 1, 'readonly': True},
        {'title': 'Timing', 'name': 'timing_opts', 'type': 'group', 'children':
            [{'title': 'Exposure Time (ms)', 'name': 'exposure_time', 'type': 'int', 'value': 1},
            {'title': 'Compute FPS', 'name': 'fps_on', 'type': 'bool', 'value': True},
            {'title': 'FPS', 'name': 'fps', 'type': 'float', 'value': 0.0, 'readonly': True}]
        },
        {'title': 'Autocorrelation parameters', 'name': 'ac_param', 'type': 'group', 'children':
            [{'title': 'Gaussian', 'name': 'GS', 'type': 'bool', 'value': True},
             {'title': 'Sech²', 'name': 'Sec2', 'type': 'bool', 'value': False},
             {'title': 'Vertical average', 'name': 'av_axis_v', 'type': 'bool', 'value': True},
             {'title': 'Horizontal average', 'name': 'av_axis_h', 'type': 'bool', 'value': False},
             {'title': 'Pixel to femtosecond conversion', 'name': 'PxFs', 'type': 'float', 'value': 0.764, 'readonly': False}]
         }
    ]

    callback_signal = QtCore.Signal()
    def gaus(self, x, a, x0, dx):
        return a * np.exp(-(x - x0) ** 2 / (dx ** 2))
    #def grab_data(self, Naverage=1, **kwargs):

    def ini_attributes(self):
        self.controller: Thorlabs.ThorlabsTLCamera = None

        self.x_axis = None
        self.y_axis = None
        self.last_tick = 0.0  # time counter used to compute FPS
        self.fps = 0.0

        self.data_shape: str = ''
        self.callback_thread = None

        self.factor = 1/1.41
        self.avaxis = 0

        # Disable "use ROI" option to avoid confusion with other buttons
        #self.settings.child('ROIselect', 'use_ROI').setOpts(visible=False)


    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() == "exposure_time":
            self.controller.set_exposure(param.value()/1000)

        if param.name() == "fps_on":
            self.settings.child('timing_opts', 'fps').setOpts(visible=param.value())

        if param.name() == "update_roi":
            if param.value():   # Switching on ROI

                # We handle ROI and binning separately for clarity
                (old_x, _, old_y, _, xbin, ybin) = self.controller.get_roi() # Get current binning

                # Values need to be rescaled by binning factor and shifted by current x0,y0 to be correct.
                new_x = (old_x + self.settings.child('ROIselect', 'x0').value())*xbin
                new_y = (old_y + self.settings.child('ROIselect', 'y0').value())*xbin
                new_width = self.settings.child('ROIselect', 'width').value()*ybin
                new_height = self.settings.child('ROIselect', 'height').value()*ybin

                new_roi = (new_x, new_width, xbin, new_y, new_height, ybin)
                self.update_rois(new_roi)
                # recenter rectangle
                self.settings.child('ROIselect', 'x0').setValue(0)
                self.settings.child('ROIselect', 'y0').setValue(0)
                param.setValue(False)

        if param.name() in ['x_binning', 'y_binning']:
            # We handle ROI and binning separately for clarity
            (x0, w, y0, h, *_) = self.controller.get_roi()  # Get current ROI
            xbin = self.settings.child('x_binning').value()
            ybin = self.settings.child('y_binning').value()
            new_roi = (x0, w, xbin, y0, h, ybin)
            self.update_rois(new_roi)

        if param.name() == "clear_roi":
            if param.value():   # Switching on ROI
                wdet, hdet = self.controller.get_detector_size()
                # self.settings.child('ROIselect', 'x0').setValue(0)
                # self.settings.child('ROIselect', 'width').setValue(wdet)
                self.settings.child('x_binning').setValue(1)
                #
                # self.settings.child('ROIselect', 'y0').setValue(0)
                # new_height = self.settings.child('ROIselect', 'height').setValue(hdet)
                self.settings.child('y_binning').setValue(1)

                new_roi = (0, wdet, 1, 0, hdet, 1)
                self.update_rois(new_roi)
                param.setValue(False)

        if param.name() == "GS":
            self.settings.child('ac_param', 'Sec2').setValue(not param.value())

        if param.name() == 'Sec2':
            self.settings.child('ac_param', 'GS').setValue(not param.value())

        if param.name() == "av_axis_v":
            self.settings.child('ac_param', 'av_axis_h').setValue(not param.value())

        if param.name() == 'av_axis_h':
            self.settings.child('ac_param', 'av_axis_v').setValue(not param.value())


    def _prepare_view(self):
        """Preparing a data viewer by emitting temporary data. Typically, needs to be called whenever the
        ROIs are changed"""
        # wx = self.settings.child('rois', 'width').value()
        # wy = self.settings.child('rois', 'height').value()
        # bx = self.settings.child('rois', 'x_binning').value()
        # by = self.settings.child('rois', 'y_binning').value()
        #
        # sizex = wx // bx
        # sizey = wy // by
        height, width = self.controller.get_data_dimensions()

        self.settings.child('hdet').setValue(width)
        self.settings.child('vdet').setValue(height)
        mock_data = np.zeros((height, width))

        if width != 1 and height != 1:
            data_shape = 'Data2D'
        else:
            data_shape = 'Data1D'

        if data_shape != self.data_shape:
            self.data_shape = data_shape
            # init the viewers


            data = [np.squeeze(mock_data)]
            dwa2D = DataFromPlugins(name='Thorlabs Camera',
                                                               data=data,
                                                               dim=self.data_shape,
                                                               labels=[f'ThorCam_{self.data_shape}'])
            data_mean = np.mean(data[0], axis=0)
            data_fit = data_mean

            dwa1D = DataFromPlugins(name='Autoccorelation trace',
                                                      data=[data_mean, data_fit],
                                                      dim='Data1D',
                                                      labels=['Trace', 'Gaussian fit'])


            dwa0D = DataFromPlugins(name='Pulse duration',
                                                      data=[np.array([0])],
                                                      dim='Data0D',
                                                      labels=['Pulse duration (fs)'],
                                                        unit='fs')

            dataa = DataToExport('Autocorrelator', data=[dwa2D, dwa1D, dwa0D])
            self.dte_signal.emit(dataa)

            QtWidgets.QApplication.processEvents()

    def emit_data(self):
        """ Function used to emit data obtained by callback.

        Parameter
        ---------
        status: bool
            If True a frame is available, If False, a Timeout occured while waiting for the frame

        See Also
        --------
        daq_utils.ThreadCommand
        """
        try:
            # Get  data from buffer
            frame = self.controller.read_newest_image()
            # Emit the frame.
            if frame is not None:       # happens for last frame when stopping camera
                if self.settings['output_color'] == 'RGB':

                    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BAYER_BG2RGB)
                    data = [np.squeeze(rgb_image[..., ind]) for ind in range(3)]


                    dwa2D = DataFromPlugins(name='Thorlabs Camera',
                                                                  data=data,
                                                                  dim='Data2D',
                                                                  labels=[f'ThorCam_{self.data_shape}'])



                else:
                    if 'monochrome' in self.settings['sensor'].lower():
                        data = [np.squeeze(frame)]
                        dwa2D = DataFromPlugins(name='Thorlabs Camera',
                                                data=data,
                                                dim='Data2D',
                                                labels=[f'ThorCam_{self.data_shape}'])
                    else:
                        grey_image = cv2.cvtColor(frame, cv2.COLOR_BAYER_BG2GRAY)
                        data = [np.squeeze(grey_image)]
                        dwa2D = DataFromPlugins(name='Thorlabs Camera',
                                                data=data,
                                                dim='Data2D',
                                                labels=[f'ThorCam_{self.data_shape}'])

                if self.settings.child('ac_param', 'av_axis_v').value() == True:
                    self.avaxis = 0
                else:
                    self.avaxis = 1

                data_mean = np.mean(data[0], axis=self.avaxis)
                x = np.linspace(0, len(data_mean)-1, len(data_mean))
                popt, pcov = curve_fit(self.gaus, x, data_mean, p0=[1, 1, 1])
                data_fit = self.gaus(x, popt[0],popt[1], popt[2] )

                dwa1D = DataFromPlugins(name='Autoccorelation trace',
                                                          data=[data_mean, data_fit],
                                                          dim='Data1D',
                                                          labels=['Trace', 'Gaussian fit'])


                if self.settings.child('ac_param', 'GS').value() == True:
                    self.factor = 1/1.41
                else:
                    self.factor = 0.65

                PxFs = self.settings.child('ac_param', 'PxFs').value()
                dwa0D = DataFromPlugins(name='Pulse duration',
                                                          data=[np.array([popt[2]*PxFs*self.factor])],
                                                          dim='Data0D',
                                                          labels=['Pulse duration (fs)'],
                                                            unit='fs')

            dataa = DataToExport('Autocorrelator', data=[dwa2D, dwa1D, dwa0D])
            self.dte_signal.emit(dataa)


            if self.settings.child('timing_opts', 'fps_on').value():
                self.update_fps()

            # To make sure that timed events are executed in continuous grab mode
            QtWidgets.QApplication.processEvents()

        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [str(e), 'log']))












if __name__ == '__main__':
    main(__file__)
