from pymodaq.control_modules.move_utility_classes import DAQ_Move_base, comon_parameters_fun, main, DataActuatorType, \
    DataActuator  # common set of parameters for all actuators
from pymodaq.utils.daq_utils import ThreadCommand  # object used to send info back to the main thread
from pymodaq.utils.parameter import Parameter

from pylablib.devices import Thorlabs



# TODO:
# (1) change the name of the following class to DAQ_Move_TheNameOfYourChoice
# (2) change the name of this file to daq_move_TheNameOfYourChoice ("TheNameOfYourChoice" should be the SAME
#     for the class name and the file name.)
# (3) this file should then be put into the right folder, namely IN THE FOLDER OF THE PLUGIN YOU ARE DEVELOPING:
#     pymodaq_plugins_my_plugin/daq_move_plugins
class DAQ_Move_LTS150(DAQ_Move_base):
    """ Instrument plugin class for an actuator.

    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Move module through inheritance via
    DAQ_Move_base. It makes a bridge between the DAQ_Move module and the Python wrapper of a particular instrument.

    TODO Complete the docstring of your plugin with:
        * The set of controllers and actuators that should be compatible with this instrument plugin.
        * With which instrument and controller it has been tested.
        * The version of PyMoDAQ during the test.
        * The version of the operating system.
        * Installation instructions: what manufacturer’s drivers should be installed to make it run?

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.

    # TODO add your particular attributes here if any

    """


    _controller_units = 'mm'  # TODO for your plugin: put the correct unit here
    is_multiaxes = False  # TODO for your plugin set to True if this plugin is controlled for a multiaxis controller
    _axis_names = ['Axis1']  # TODO for your plugin: complete the list
    _epsilon = 1/409600  # TODO replace this by a value that is correct depending on your controller
    data_actuator_type = DataActuatorType[
        'DataActuator']  # wether you use the new data style for actuator otherwise set this
    # as  DataActuatorType['float']  (or entirely remove the line)


    params = [{'title': 'Serial number:', 'name': 'serial_number', 'type': 'str', 'value': '45922740', 'readonly': True},
              {'title': 'Home Position:', 'name': 'home_position', 'type': 'float', 'value': 0.0},
              {'title': 'Speed:', 'name': 'speed', 'type': 'float', 'value': 0.0}
             ] + comon_parameters_fun(is_multiaxes, axis_names=_axis_names, epsilon=_epsilon)

    # _epsilon is the initial default value for the epsilon parameter allowing pymodaq to know if the controller reached
    # the target value. It is the developer responsibility to put here a meaningful value

    def ini_attributes(self):
        #  TODO declare the type of the wrapper (and assign it to self.controller) you're going to use for easy
        #  autocompletion
        self.controller: Thorlabs.KinesisMotor(self.settings.child('serial_number').value()) = None

        # TODO declare here attributes you want/need to init with a default value
        pass

    def get_actuator_value(self):
        """Get the current value from the hardware with scaling conversion.

        Returns
        -------
        float: The position obtained after scaling conversion.
        """

        #pos = DataActuator(
         #   data=self.controller.get_position(scale=True))
        pos = self.controller.get_position(scale=True)
        pos = self.get_position_with_scaling(pos)
        #print(pos)
        return pos

    def close(self):
        """Terminate the communication protocol"""
        self.controller.close()

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        ## TODO for your custom plugin
        if param.name() == "a_parameter_you've_added_in_self.params":
            self.controller.your_method_to_apply_this_param_change()
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
        ratio = 61440000/150 #steps to mm
        #raise NotImplemented  # TODO when writing your own plugin remove this line and modify the one below

        sscale = (409600, 21987328, 4506)
        self.controller = self.ini_stage_init(old_controller=controller,
                                              new_controller=Thorlabs.KinesisMotor(self.settings.child('serial_number').value(), scale=sscale))

        info = self.controller.get_device_info()
        initialized = True
        #initialized = self.controller.a_method_or_atttribute_to_check_if_init()  # todo
        #print("bla")
        print("vel param", self.controller.get_velocity_parameters(channel=None, scale=True))
        print("scale", self.controller.get_scale())
        print("stage", self.controller.get_stage())
        print("homing param ", self.controller.get_homing_parameters(channel=None, scale=True))
        return info.notes, initialized

    def move_abs(self, value: DataActuator):
        """ Move the actuator to the absolute target defined by value

        Parameters
        ----------
        value: (float) value of the absolute target positioning
        """
        value = value.value()
        value = self.check_bound(value)  # if user checked bounds, the defined bounds are applied here
        self.target_value = value
        value = self.set_position_with_scaling(value)  # apply scaling if the user specified one
        print(value)
        #self.controller.move_to(
        #    value, scale=True)
        currentpos = self.get_actuator_value()
        self.controller.move_by(distance=value-currentpos , channel=None, scale=True)

        self.emit_status(ThreadCommand('Update_Status', ['moving']))
        self.emit_status(ThreadCommand('Update_Status', [f'Moving to position: {value}']))

    def move_rel(self, value: DataActuator):
        """ Move the actuator to the relative target actuator value defined by value

        Parameters
        ----------
        value: (float) value of the relative target positioning
        """
        value = self.check_bound(self.current_position + value) - self.current_position
        self.target_value = value + self.current_position
        value = self.set_position_relative_with_scaling(value)


        self.controller.move_by(distance=value.value() , channel=None, scale=True)

        #self.emit_status(ThreadCommand('Update_Status', ['moved']))

    def move_home(self):
        """Call the reference method of the controller"""


        #self.controller.home(sync=True)  # when writing your own plugin replace this line
        #self.controller.home()
        #self.controller.move_to(self.settings.child('home_position').value())
        #self.emit_status(ThreadCommand('Update_Status', ['Home']))

        '''  
        #get current value
        pos = self.get_actuator_value()

        #home = DataActuator(data=self.settings.child('home_position').value())

        self.controller.move_by(distance=-pos , channel=None, scale=True)
        '''
        self.controller.home(force=True)
        self.controller.wait_for_home(channel=None, timeout=None)
        self.emit_status(ThreadCommand('Update_Status', ['Home']))
        #print("home " , home)

    def stop_motion(self):

        self.controller.stop(immediate=False, sync=True, channel=None, timeout=None)  # when writing your own plugin replace this line
        self.emit_status(ThreadCommand('Update_Status', ['Stop']))


if __name__ == '__main__':
    main(__file__, init=False)