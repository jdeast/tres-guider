from configobj import ConfigObj
from PIPython import pipython.GCSDevice
import ipdb

class calstage:

    def __init__(self, base_directory, config_file):
        self.base_directory=base_directory

        # read the config file
        config = ConfigObj(self.base_directory + '/config/' + self.config_file)
        self.science_position = float(config['SCIENCEPOS'])
        self.sky_position = float(config['SKYPOS'])
        self.out_position = float(config['OUTPOS'])

        # use the PI python library to initialize the device
        self.calstage = GCSDevice()

    def connect(self):
        self.calstage.ConnectUSB('123456789')

    def move(self, position):
        # make sure we're connected

        # move the stage
        self.calstage.MOV('A',position)

        # make sure it moved where we wanted
        if position != self.get_position():
            pass

        return

    def get_position(self):
        return self.calstage.qPOS('A')

    def move_to_science(self):
        return move(self,self.science_position)

    def move_to_sky(self):
        return move(self,self.sky_position)

    def move_to_out(self):
        return move(self,self.out_position)

if __name__ == '__main__':

    base_directory = '/h/onion0/tres/'
    config_file = 'calstage.ini'
    calstage = calstage(base_directory, config_file)

    ipdb.set_trace()
