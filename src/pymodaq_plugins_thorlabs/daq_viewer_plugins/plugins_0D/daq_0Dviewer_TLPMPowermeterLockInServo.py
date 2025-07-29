"""
PyMoDAQ plugin for thorlabs instruments based on the TLPM library allowing
remote control and monitoring of up to eight power and energy meters.
This software is compatible with our Power Meter Consoles and Interfaces (PM100A and PM101 Series),
Power and Energy Meter Consoles and Interfaces (PM100D, PM400, PM100USB, PM103 Series, and legacy PM200),
Position & Power Meter Interfaces (PM102 Series),
Wireless Power Meters (PM160, PM160T, and PM160T-HP),
and USB-Interface Power Meters (PM16 Series)

you have to install the Optical Monitor Software from Thorlabs to obtain the library

The installation should create (following the manual) an environment variable called either VXIPNPPATH64 or
VXIPNPPATH depending on your platform (32 or 64 bits) pointing to where the TLPM library is
(usually C:\Program Files\IVI Foundation\VISA)

This plugin is making use of the TLPM.py script provided by thorlabs. An alternative is to use the TLPMPowermeterInst
plugin using the Instrumental_lib package directly interfacing the C library with the nice Instrument wrapper
"""
from easydict import EasyDict as edict
from future.utils import raise_
from pymodaq.utils.daq_utils import ThreadCommand, getLineInfo
from pymodaq.utils.data import DataFromPlugins
from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, main
import time
import numpy as np
from pymodaq.control_modules.viewer_utility_classes import comon_parameters
from pymodaq_plugins_thorlabs.hardware.powermeter import CustomTLPM, DEVICE_NAMES
from typing import Union, List, Dict
from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun,
                                                          main, DataActuatorType, DataActuator)

from pymodaq_utils.utils import ThreadCommand  # object used to send info back to the main thread
from pymodaq_gui.parameter import Parameter

from yoctopuce.yocto_api import YAPI, YRefParam
from yoctopuce.yocto_servo import YServo

#from pymodaq_plugins_thorlabs.daq_move_plugins.daq_move_YoctoServo import DAQ_Move_YoctoServo
from pymodaq.utils.data import Axis


class YoctoServoWrapper:
    def __init__(self):
        errmsg = YRefParam()
        if YAPI.RegisterHub("usb", errmsg) != YAPI.SUCCESS:
            raise RuntimeError("Cannot initialize YoctoPuce : " + errmsg.value)
        self.servo = YServo.FirstServo()
        if self.servo is None:
            raise RuntimeError("YoctoPuce not found.")
        self.servo.set_enabled(True)

    def move_absolute(self, position, duration=100):
        self.servo.move(position, duration)

    def get_position(self):
        pos = self.servo.get_position()
        if pos == YServo.POSITION_INVALID:
            return None
        return pos

    def stop(self):
        self.servo.set_enabled(False)



class DAQ_0DViewer_TLPMPowermeterLockInServo(DAQ_Viewer_base):

    _controller_units = 'W'
    devices = DEVICE_NAMES
    servo: YoctoServoWrapper = None

    params = comon_parameters + [
        {'title': 'Devices:', 'name': 'devices', 'type': 'list', 'limits': devices},
        {'title': 'Info:', 'name': 'info', 'type': 'str', 'value': '', 'readonly': True},
        {'title': 'Wavelength:', 'name': 'wavelength', 'type': 'float', 'value': 532.,},
        {'title': 'Nb of cycle:', 'name': 'nb_of_cycle', 'type': 'int', 'value':1, 'limits': (1, 300)},
        {'title': 'Servo time:', 'name': 'servo_time', 'type': 'float', 'value': 1.0, 'limits': (1.1, 30)},
        ]

    def __init__(self, parent=None, params_state=None):
        super().__init__(parent, params_state)


    def ini_detector(self, controller=None):
        """
            Initialisation procedure of the detector.

            Returns
            -------

                The initialized status.

            See Also
            --------
            daq_utils.ThreadCommand
        """
        print("ini detector called")
        self.status.update(edict(initialized=False, info="", x_axis=None, y_axis=None, controller=None))
        try:

            if self.settings.child(('controller_status')).value() == "Slave":
                if controller is None:
                    raise Exception('no controller has been defined externally while this detector is a slave one')
                else:
                    self.controller = controller
            else:
                index = DEVICE_NAMES.index(self.settings['devices'])
                self.controller = CustomTLPM()
                info = self.controller.infos.get_devices_info(index)
                print('Trying to open device')
                self.controller.open_by_index(index)
                print('Device opened')

                self.settings.child('info').setValue(str(info))

            self.settings.child('wavelength').setOpts(limits=self.controller.wavelength_range)
            self.controller.wavelength = self.settings.child('wavelength').value()
            self.settings.child('wavelength').setValue(self.controller.wavelength)

            if self.is_master:
                try:
                    self.servo = YoctoServoWrapper()
                    print("Yocto Servo Initialized")
                except Exception as e:
                    print(f"Error with initialization servo: {e}")

            self.status.initialized = True
            self.status.controller = self.controller
            self.status.info = str(info)
            return self.status

        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [getLineInfo() + str(e), 'log']))
            self.status.info = getLineInfo() + str(e)
            self.status.initialized = False
            print("INITIALIZATION OK")
            return self.status


    def commit_settings(self, param):
        """
        """
        if param.name() == 'wavelength':
            self.controller.wavelength = self.settings.child('wavelength').value()
            self.settings.child('wavelength').setValue(self.controller.wavelength)

    def close(self):
        """
            close the current instance of Keithley viewer.
        """
        self.controller.close()

    def grab_data(self, Naverage=1, **kwargs):
        try:
            print("grab_data started")
            n_cycles = self.settings['nb_of_cycle']
            servo_time = self.settings['servo_time']
            half_cycle = servo_time / 2

            on_powers = []
            off_powers = []
            trace_times = []
            trace_powers = []

            t0 = time.time()

            for i in range(n_cycles):
                print(f"Cycle {i + 1} / {n_cycles} - Moving servo to 1000")
                self.servo.move_absolute(1000)
                time.sleep(0.1)

                start = time.time()
                print(f"Cycle {i + 1} - Reading ON powers")
                while time.time() - start < half_cycle:
                    try:
                        power = self.controller.get_power()
                        print(f"Power ON: {power}")
                        on_powers.append(power)
                        trace_times.append(time.time() - t0)
                        trace_powers.append(power)
                    except Exception as e:
                        print(f"Error while reading power: {e}")
                    time.sleep(0.01)

                print(f"Cycle {i + 1} - Moving servo to -1000")
                self.servo.move_absolute(-1000)

                start = time.time()
                print(f"Cycle {i + 1} - Reading OFF powers")
                while time.time() - start < half_cycle:
                    power = self.controller.get_power()
                    print(f"Power OFF: {power}")
                    off_powers.append(power)
                    trace_times.append(time.time() - t0)
                    trace_powers.append(power)
                if len(on_powers) == 0 or len(off_powers) == 0:
                    raise ValueError(
                        f"No power data acquired. on_powers={len(on_powers)}, off_powers={len(off_powers)}. "
                        "Cycle time may be too short, or sensor may not be ready.")

            print("Calculating lock-in signal")
            lockin_signal = np.mean(on_powers) - np.mean(off_powers)

            x_axis = Axis(label='Time', units='s', data=np.array(trace_times))
            y_data = np.array(trace_powers)
            print(f"x_axis length: {len(x_axis)}, y_data length: {len(y_data)}")
            assert x_axis.get_data().shape == y_data.shape, f"x={x_axis.get_data().shape}, y={y_data.shape}"

            data_trace = DataFromPlugins(name='Power trace',
                                         data=[y_data],
                                         dim='Data1D',
                                         x_axis=x_axis,
                                         labels=['Power (W)'])

            data_lockin = DataFromPlugins(name='Lock-in power',
                                          data=[np.array([lockin_signal])],
                                          dim='Data0D',
                                          labels=['ΔPower (W)'])

            print(f"Emitting {len(trace_times)} points")
            self.data_grabed_signal.emit([data_trace, data_lockin])
            print("Data emitted successfully")

        except Exception as e:
            print(f"[ERROR in grab_data]: {e}")
            self.emit_status(ThreadCommand('Update_Status', [getLineInfo() + str(e), 'log']))

    def stop(self):
        """
        """
        return ""

if __name__ == '__main__':
    main(__file__)

