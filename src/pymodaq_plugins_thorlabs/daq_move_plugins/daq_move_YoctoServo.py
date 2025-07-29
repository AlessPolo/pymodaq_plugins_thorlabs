from typing import Union, List, Dict
from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun,
                                                          main, DataActuatorType, DataActuator)

from pymodaq_utils.utils import ThreadCommand  # object used to send info back to the main thread
from pymodaq_gui.parameter import Parameter

from yoctopuce.yocto_api import YAPI, YRefParam
from yoctopuce.yocto_servo import YServo


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


class DAQ_Move_YoctoServo(DAQ_Move_base):
    is_multiaxes = False
    _axis_names: Union[List[str], Dict[str, int]] = ['Servo1']
    _controller_units: Union[str, List[str]] = 'units'
    _epsilon: Union[float, List[float]] = 10.0
    data_actuator_type = DataActuatorType.DataActuator

    params = [] + comon_parameters_fun(is_multiaxes, axis_names=_axis_names, epsilon=_epsilon)

    def ini_attributes(self):
        # Initialize attributes of the class
        self.controller: YoctoServoWrapper = None
        self.axis_unit = self._controller_units
        self.target_value = DataActuator(data=0, units=self._controller_units)
        self.current_position = 0

    def get_actuator_value(self):
        """Get the current value from the hardware with scaling conversion.

        Returns
        -------
        DataActuator: The position obtained after scaling conversion.
        """
        position = self.controller.get_position() if self.controller is not None else None
        if position is None:
            return DataActuator(data=0, units=self.axis_unit)
        return DataActuator(data=position, units=self.axis_unit)

    def close(self):
        """Terminate the communication protocol"""
        if self.controller is not None:
            self.controller.stop()
        YAPI.FreeAPI()

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings"""
        if param.name() == 'axis':
            pass
        else:
            pass

    def ini_stage(self, controller=None):
        """Actuator communication initialization

        Parameters
        ----------
        controller: (object)
            custom object of a PyMoDAQ plugin (Slave case). None if only one actuator by controller (Master case)

        Returns
        -------
        info: str
        initialized: bool
            False if initialization failed otherwise True
        """
        if self.is_master:
            try:
                self.controller = YoctoServoWrapper()
                initialized = True
                info = "Yocto-Servo initialized."
            except Exception as e:
                info = f"Erreur when initialisation : {e}"
                initialized = False
        print("YOCTO INIZIAL")
        return info, initialized


    def move_abs(self, value: DataActuator):
        """
        Move the actuator to the absolute position specified by `value`.

        Parameters
        ----------
        value: DataActuator
            Target position with units.
        """
        value_checked = self.check_bound(value)
        self.target_value = value_checked
        pos_to_set = value_checked.value(self.axis_unit)

        try:
            self.controller.move_absolute(pos_to_set)
            self.emit_status(ThreadCommand('Update_Status', [f"Displacement to {pos_to_set} {self.axis_unit}"]))
        except Exception as e:
            self.emit_status(ThreadCommand('Update_Status', [f"Erreur : {e}"]))

    def move_rel(self, value: DataActuator):
        """
        Move the actuator to the relative target actuator value defined by value.

        Parameters
        ----------
        value: DataActuator
            Value of the relative target positioning.
        """
        current_pos = self.get_actuator_value().value(self.axis_unit)
        rel_value = value.value(self.axis_unit)
        new_pos = current_pos + rel_value
        new_pos_data = DataActuator(data=new_pos, units=self.axis_unit)
        self.move_abs(new_pos_data)

    def move_home(self):
        """Call the reference method of the controller"""
        self.emit_status(ThreadCommand('Update_Status', ['Move home non implémenté']))

    def stop_motion(self):
        """Stop the actuator and emits move_done signal"""
        self.controller.stop()
        self.emit_status(ThreadCommand('Update_Status', ['Mouvement stopped']))
        self.emit_status(ThreadCommand('done_moving', self.get_actuator_value()))


if __name__ == '__main__':
    main(__file__)
