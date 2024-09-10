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
class DAQ_2DViewer_Thorlabs_TSI_autocorrelator(DAQ_2DViewer_Thorlabs_TSI):

    def gaus(self, x, a, x0, dx):
        return a * np.exp(-(x - x0) ** 2 / (dx ** 2))
    #def grab_data(self, Naverage=1, **kwargs):

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

            self.data_grabed_signal_temp.emit([DataFromPlugins(name='Thorlabs Camera',
                                                               data=[np.squeeze(mock_data)],
                                                               dim=self.data_shape,
                                                               labels=[f'ThorCam_{self.data_shape}'])])




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

                data_mean = np.mean(data[0], axis=0)
                x = np.linspace(0, len(data_mean)-1, len(data_mean))
                popt, pcov = curve_fit(self.gaus, x, data_mean, p0=[1, 1, 1])
                data_fit = self.gaus(x, popt[0],popt[1], popt[2] )

                dwa1D = DataFromPlugins(name='Autoccorelation trace',
                                                          data=[data_mean, data_fit],
                                                          dim='Data1D',
                                                          labels=['Trace', 'Gaussian fit'])

                factor = 1/1.41
                PxFs = 0.764
                dwa0D = DataFromPlugins(name='Pulse duration',
                                                          data=[np.array([popt[2]*PxFs*factor])],
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
