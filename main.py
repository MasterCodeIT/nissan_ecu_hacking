# Welcome to Nissan_USB2CAN (AKA usb2can2py) by Liam Goss
# I wrote this because I could not find any decent software to work with the Korlan usb2can device I bought
# The usb2can drivers for windows are much easier so I am writing this code for use on windows (via bootcamp on my mac)
# Resources
# https://python-can.readthedocs.io/en/master/api.html
# https://python-obd.readthedocs.io/en/latest/
import sys
import math
import can
import obd
import usb.core
import usb.backend.libusb1

from can.interfaces.usb2can.usb2canabstractionlayer import *
from can.interfaces.usb2can import Usb2canBus

# SYS_DEBUG can be set to True if you want to use the logging library to have a very verbose output
# FUNC_DEBUG is a variable that will be checked in functions and then *certain* tracebacks andprint statements will
#               be executed accordingly

SYS_DEBUG = False
FUNC_DEBUG = True

if SYS_DEBUG:
    import logging
    logging.basicConfig(level=logging.DEBUG)


# The korlan usb2can doesn't like to be detected by this code on Windows 10
#           Could be a driver issue on my end (it shows up as USB and not a COM port like I would prefer, but that
#           likely is a feature not an error)
# Right now this code is being written for Windows 10, but I plan on making this work on Linux as well (i.e. raspbian)
# UPDATE: It seems that our prayers have been answered and we should be able to use usb2can cross-platform
#           by using https://github.com/hardbyte/python-can/pull/979

# ID for speed is (maybe) 354, 355, or 280 and ID for RPM is 1F9
# TODO: figure out live torque/horsepower calculation --- can we get crankshaft position and do some angular velocity type physics?

def send_msg(id, data, interface=None):
    '''
    send_msg() uses the 'can' library to send a message to the can bus
    :param id:
    :param data:
    :param interface:
    :return:
    '''
    # NOTE: it's possible that this wont find the usb because of the following, non-fatal errors:
    '''
    Kvaser canlib is unavailable.
    fcntl not available on this platform
    libc is unavailable
    '''
    # As for the above issue, it could also be due to the library looking for COM ports and not USB
    interfaces = can.interface.detect_available_configs()
    print(interfaces)
    channel = interfaces[0]['channel']
    # TODO: add interface selection code
    # TODO: https://github.com/hardbyte/python-can/pull/979 for drivers to use usb2can easily
    if type(data) == list:
        print("Type is list")
    # print(interfaces)
    # Running on a virtual CAN bus for now since that allows at least a basic test of functionality
    with can.interface.Bus(bustype='virtual', channel=channel, bitrate=500000) as bus:
        # data = [0x20, 0x00, 0x1f, 0xbd, 0x00, 0x00, 0x00, 0x00]
        arbitration_id = id
        msg = can.Message(arbitration_id=arbitration_id, data=data, is_extended_id=True)
        try:
            bus.send(msg)
            print(f"Message sent on virtual {bus.channel_info}")
        except can.CanError:
            print("Message NOT sent")
            return
    print("__{0}/{1} Data__".format('0x' + str(hex(arbitration_id))[2:].zfill(8), arbitration_id))
    print(f"hex: {hex(data[0])}, {hex(data[1])}, {hex(data[2])}, {hex(data[3])}, {hex(data[4])}, {hex(data[5])}, "
          f"{hex(data[6])}, {hex(data[7])}")
    print(f"dec: {data[0]}, {data[1]}, {data[2]}, {data[3]}, {data[4]}, {data[5]}, {data[6]}, {data[7]}")

def calculate_horsepower(final_speed, delta_time, init_speed=0.00):
    '''
    :param speed: in MPH
    :param time: in seconds
    :param mass: in kg
    :return:
    '''
    mass = 1505.9267  # Mass (kg) of a base 2008 Nissan 350z, change accordingly if needed
    # An alternative formula for calculating horsepower is (torque [lb-ft] * RPM) / 5252 but I don't know how to
    #               reliably get live torque data. Maybe I'll introduce another function with some basic estimates?
    # Google says that 90% of the Z's torque (268 lb-ft) is available between 2,000 and 7,000 RPM and that it gets
    #               306 HP @ 6,800 RPM; from there we can probably reverse engineer some values, but either way we are
    #               guessing without a dyno
    # Or you could also do: (Force [lbs] * Radius of rear wheel+tire [feet] * RPM) / 5252
    # But I figured with tire and rim size variations, it isn't the best standard use case, but the formula is here
    #               in case you'd like to implement it
    # If you REALLY want to get fancy, the coefficient of drag is 0.3 (0.29 for grand tourismo? don't quote me on that)
    #               so feel free to do some wicked math and submit a pull request :)

    # The math here, although I think checks out (grade wise I did amazing in physics but my gosh my understanding of
    #                          it is much much less), but it seems off. I think I need to set it up to handle taking the
    #                          time between 2 speeds and not just assuming it starts at 0

    # If you can weigh your own car and change this value, that would be ideal, but I cannot so I am using the internet
    init_speed = init_speed / 2.237  # MPH to m/s: divide MPH by 2.237
    final_speed = final_speed / 2.237
    # time will be in the correct units [seconds]
    # Avg. HP = (((1/2)mv^2)/t)/746
    # 1/2mv^2 is the kinetic energy of an object; m in kg, v in m/s
    # t is time (in seconds) it takes to achieve v (in this theory, from zero - we can do some algebra and physics
    #                                  to get it from a nonzero start)
    # Gives us a the expression so far (in parentheses) gives us Joules/second which is equivalent to Watts
    # 1 HP = 746 Watts so we divide by 746 to cancel out watts and solve for HP

    init_kinetic_energy = 0.5 * mass * (init_speed * init_speed)
    final_kinetic_energy = 0.5 * mass * (final_speed * final_speed)
    delta_kinetic_energy = final_kinetic_energy - init_kinetic_energy
    #print(f"Kinetic energy: {delta_kinetic_energy} Joules (J)")
    watts = delta_kinetic_energy / float(delta_time)
    horsepower = watts / 746.00
    horsepower = int(math.ceil(horsepower)) # round up to nearest whole number - could round down but I mean it's an ego thing at this point
    print(f"Horsepower: {horsepower} HP")

    # After I get the math down solid I will add code to generate graphs and then later on these can be placed on a GUI

    return horsepower

def get_metrics():
    # This function will get the current speed of the car and start a stopwatch at t=0
    # Then it will go X amount of seconds and grab the final speed, then return this to be fed into calculate_horsepower()
    # Using ID 280
    final_speed = 60.0
    init_speed = 0.0
    delta_time = 5.0
    return final_speed, delta_time, init_speed

# Arbitration ID and data must be in the following (hex) format
id = 0x0000060D
data = [0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED, 0x69, 0x69] # placeholder hex values
#send_msg(id, data, 'vcan0')

final_speed, delta_time, initial_speed, = get_metrics()
hp = calculate_horsepower(final_speed, delta_time, initial_speed) # final speed, delta time, init speed

# The following code is deprecated code but I am keeping it here in case you find it useful :)
'''
# The vendor and Product ID correspond to the ID's of the usb2can found  in W10 device manager or various linux commands 
VENDOR_ID = '0483'
PRODUCT_ID = 1234

device = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)

if device is None:
    raise ValueError("No matching USB device found!")
print("Device found!")
usb.core.util.claim_interface(device, 0)
'''
'''
dev = usb.core.find(find_all=True)
# loop through devices, printing vendor and product ids in decimal and hex
for cfg in dev:
  print('Decimal VendorID=' + str(cfg.idVendor) + ' & ProductID=' + str(cfg.idProduct) + '\n')
  print('Hexadecimal VendorID=' + hex(cfg.idVendor) + ' & ProductID=' + hex(cfg.idProduct) + '\n\n')
'''
'''
ports = obd.scan_serial()
print(ports)
obd.logger.setLevel(obd.logging.DEBUG)

connection = obd.OBD()

if connection.is_connected():
    print("OBD2 connected on {0} using {1}".format(connection.port_name()), connection.protocol_name())
    print("RPM Reads:")

    rpm = obd.commands.RPM
    print(rpm)
else:
    print("OBD2 not connected...")
print("Closing connection (if any)")
connection.close()
'''


