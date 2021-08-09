import ipdb, time

from ThorlabsPM100 import ThorlabsPM100, USBTMC
inst = USBTMC(device="/dev/usbtmc1")
power_meter = ThorlabsPM100(inst=inst)
print(power_meter.read) # Read-only property
print(power_meter.sense.average.count) # read property
#power_meter.sense.average.count = 10 # write property
#power_meter.system.beeper.immediate() # method

while True:
    print(power_meter.read) # Read-only property
    time.sleep(1)

# pyvisa doesn't seem to work...
#import pyvisa
#from ThorlabsPM100 import ThorlabsPM100
#rm = pyvisa.ResourceManager()
#print(rm.list_resources())
##inst = rm.open_resource('ASRL/dev/ttyUSB0::INST')
#inst = rm.open_resource('ASRL/dev/ttyUSB1::INST')
#                        term_chars='\n', timeout=1)

#ipdb.set_trace()
#power_meter = ThorlabsPM100(inst=inst)


#print(power_meter.read) # Read-only property
#print(power_meter.sense.average.count) # read property

#ipdb.set_trace()
