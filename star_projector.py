# zaber_motion doesn't support T-series!!!
# py -3 -m pip install --user zaber_motion
#from zaber_motion import Library
#from zaber_motion.ascii import Connection
#from zaber_motion import Units

# py -3 -m pip install --user zaber.serial
from zaber.serial import BinarySerial, BinaryCommand, BinaryDevice
#https://www.zaber.com/wiki/Software/Zaber_Console/Python

from configobj import ConfigObj
import utils
import socket, sys, os
import ipdb

import threading

class star_projector:

    def __init__(self, base_directory, config_file, logger=None, simulate=False):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file
        self.simulate=simulate

        # set up the log file                                                                 
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'star_simulator')
        else: self.logger = logger

        # read the config file                                                                
        config = ConfigObj(self.config_file)

        # read the config file                                                                
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + self.config_file + ')')
            sys.exit()

        self.port = config['PORT']
        self.mm_per_step_x = float(config['MM_PER_STEP_X'])
        self.mm_per_step_y = float(config['MM_PER_STEP_Y'])
        self.deg_per_step = float(config['DEG_PER_STEP'])
        self.arcsec_per_mm_x = float(config['ARCSEC_PER_MM_X'])
        self.arcsec_per_mm_y = float(config['ARCSEC_PER_MM_Y'])

        self.theta = float(config['THETA'])
        self.flip = (config['FLIP'] == 'True')

        # in mm
        self.min_x = float(config['MIN_X'])
        self.min_y = float(config['MIN_Y'])
        self.max_x = float(config['MAX_X'])
        self.max_y = float(config['MAX_Y'])

        # convert to step coordinates
        self.min_x_steps = self.min_x/self.mm_per_step_x
        self.min_y_steps = self.min_y/self.mm_per_step_y
        self.max_x_steps = self.max_x/self.mm_per_step_x
        self.max_y_steps = self.max_y/self.mm_per_step_y

        # derive arcsec/step
        self.arcsec_per_step_x = self.mm_per_step_x*self.arcsec_per_mm_x
        self.arcsec_per_step_y = self.mm_per_step_y*self.arcsec_per_mm_y
        
        if not self.simulate:
            self.connect()
#            self.home()
#            self.move_absolute(x=0.0, y=0.0)

    # Helper to check that commands succeeded.
    def check_command_succeeded(reply):
        """
        Return true if command succeeded, print reason and return false if command
        rejected

        param reply: BinaryReply

        return: boolean
        """
        if reply.command_number == 255: # 255 is the binary error response code.
            print ("Danger! Command rejected. Error code: " + str(reply.data))
            return False
        else: # Command was accepted
            return True

    def get_position(self):
        return (self.x_axis.get_position(), 
                self.y_axis.get_position(),
                self.rot_axis.get_position())
    
    def connect(self):
        self.comport = BinarySerial(self.port)
        self.x_axis = BinaryDevice(self.comport,1)
        self.y_axis = BinaryDevice(self.comport,2)
        self.rot_axis = BinaryDevice(self.comport,3)

    def home(self):
        # this always times out if at the end of range
        self.x_axis.home()
        self.y_axis.home()
        #self.rot_axis.home() # broken

    ''' X/Y motion in arcsec, angle in degrees ''' 
    # TODO: error handling
    def move_relative(self, x=0, y=0, degrees=0, wait=True, mm=False):
        
        if mm:
            x_move = int(round(x/self.mm_per_step_x))
            y_move = int(round(y/self.mm_per_step_y))
        else:
            x_move = int(round(x/self.arcsec_per_step_x))
            y_move = int(round(y/self.arcsec_per_step_y))

        self.x_axis.move_rel(x_move)
        self.y_axis.move_rel(y_move)
        # self.rot_axis.move_rel(degrees/self.deg_per_step)

        # doesn't work for binary library
#        if wait:
#            self.x_axis.poll_until_idle()
#            self.y_axis.poll_until_idle()
#            self.rot_axis.poll_until_idle()

    ''' X/Y motion in arcsec, angle in degrees ''' 
    # TODO: error handling
    def move_absolute(self, x=0.0, y=0.0, degrees=0.0, wait=True, mm=False):

        if mm:
            x_move = int(round((self.min_x_steps + self.max_x_steps)/2.0 + x/self.mm_per_step_x))
            y_move = int(round((self.min_y_steps + self.max_y_steps)/2.0 + y/self.mm_per_step_y))
        else:
            x_move = int(round((self.min_x_steps + self.max_x_steps)/2.0 + x/self.arcsec_per_step_x))
            y_move = int(round((self.min_x_steps + self.max_x_steps)/2.0 + y/self.arcsec_per_step_y))

        if x_move > self.max_x_steps or x_move < self.min_x_steps or y_move > self.max_y_steps or y_move < self.min_y_steps:
            self.logger.error("Requested move beyond bounds")

        self.x_axis.move_abs(x_move)
        self.y_axis.move_abs(y_move)
        #self.rot_axis.move_abs(int(round(degrees/self.deg_per_step)))

        # doesn't work for binary library
#        if wait:
#            self.x_axis.poll_until_idle()
#            self.y_axis.poll_until_idle()
#            self.rot_axis.poll_until_idle()


    ''' 
        impose an asynchronous drift with optional periodic error terms 
        drift_x     -- x drift, in arcsec/sec (or mm/sec if mm=True)
        drift_y     -- y drift, in arcsec/sec (or mm/sec if mm=True)
        drift_rot   -- rotation drift, in deg/sec
        period      -- an array of periods for periodic error, in seconds
                       must be length 1 or match length of amplitude_x
        x_amplitude -- an array of x amplitudes for periodic error, in arcsec
                       must be length 1 or match length of period
        y_amplitude -- an array in y amplitudes for periodic error, in arcsec
                       must be length 1 or match length of period
        t0          -- an array of times, in seconds relative to the start, to start the 
                       periodic error term. 
                       must be length 1 or match length of period        
        this function will also read a correction file (base_directory/guide_correction.txt) 
             to accept corrections (e.g., from the "guider") on top of the drifts
    '''
    def drift(self, drift_x=0.0, drift_y=0.0, drift_rot=0.0, period=[None], amplitude_x=[0.0], amplitude_y=[0.0], t0=[0.0], mm=False):

        if mm:
            x_vel = int(round(drift_x/self.mm_per_step_x))
            y_vel = int(round(drift_y/self.mm_per_step_y))
        else:
            x_vel = int(round(drift_x/self.arcsec_per_step_x))
            y_vel = int(round(drift_y/self.arcsec_per_step_y))

        self.x_axis.move_vel(x_vel)
        self.y_axis.move_vel(y_vel)

        # you wish!
        # but these functions will likely form the basis of the code... 
        #self.x_axis.get_max_speed(unit = Units.NATIVE)
        #self.y_axis.stop()


    '''
        Impose an asycronous drift with a random jitter imposed on top
    '''
    def jitter_drift(self, jitter, drift_x=0.0, drift_y=0.0, mm=False):

        while True:
            if mm:
                x_vel = int(round(np.random.normal(drift_x, jitter)/self.mm_per_step_x))
                y_vel = int(round(np.random.normal(drift_y, jitter)/self.mm_per_step_y))
            else:
                x_vel = int(round(np.random.normal(drift_x,jitter)/self.arcsec_per_step_x))
                y_vel = int(round(np.random.normal(drift_y,jitter)/self.arcsec_per_step_y))

            self.x_axis.move_vel(x_vel)
            self.y_axis.move_vel(y_vel)

            if self.queued_move_x != 0.0 or self.queued_move_y != 0.0:
                self.move_relative(x=self.queued_move_x, y=self.queued_move_y, mm=False)
                self.queued_move_x = 0.0
                self.queued_move_y = 0.0

    '''
        this is meant to be run asynchronously with drift or jitter_drift
    '''
    def guide_xy(self, x=0.0, y=0.0, degrees=0, mm=False):

        # convert to arcsec if necessary, then add to queued move
        if mm:
            self.queued_move_x += x/self.mm_per_step_x*self.arcsec_per_step_x
            self.queued_move_y += y/self.mm_per_step_y*self.arcsec_per_step_y
        else:
            self.queued_move_x += x
            self.queued_move_y += y


#-------------------------------------------------------------------------------
    # these function names emulate dfm_telescope so it can be used as a telescope replacement
    def offset_target_object(self, east, north):
        x = north*math.cos(self.theta*math.pi()/180.0) - east*math.sin(self.theta*math.pi()/180.0)
        y = north*math.sin(self.theta*math.pi()/180.0) + east*math.cos(self.theta*math.pi()/180.0)
        if self.flip: y = -y
        guide_xy(x=x,y=y,mm=False)
        
    def populate_header(self,hdr):

        hdr['TELESCOP'] = ("Star projector","Telescope")
        hdr['SITELAT'] = (42.398067,"Site Latitude (deg)") # CDP
        hdr['SITELONG'] = (-71.149436,"Site East Longitude (deg)") # CDP
        hdr['SITEALT'] = (0.0,"Site Altitude (m)")
        #hdr['RA'] = (ra, "Solved RA (J2000 deg)")
        #hdr['DEC'] = (dec,"Solved Dec (J2000 deg)")
        #hdr['ALT'] = (alt,'Telescope altitude (deg)')
        #hdr['AZ'] = (az,'Telescope azimuth (deg E of N)')
        #hdr['AIRMASS'] = (airmass,"airmass (plane approximation)")
        #hdr['HOURANG'] = (hourang,"Hour angle")
        #hdr['PMODEL'] = ('',"Pointing Model File")
        #hdr['FOCPOS'] = (focus,"Focus Position (microns)")
        #hdr['ROTPOS'] = (rotpos,"Mechanical rotator position (degrees)")
        #hdr['PARANG'] = (parang,"Parallactic Angle (degrees)")
        #hdr['SKYPA' ] = (skypa,"Position angle on the sky (degrees E of N)")

        #hdr['MOONRA'] = (moonra, "Moon RA (J2000 deg)")
        #hdr['MOONDEC'] =  (moondec, "Moon Dec (J2000 deg)")
        #hdr['MOONPHAS'] = (moonphase, "Moon Phase (Fraction)")
        #hdr['MOONDIST'] = (moonsep, "Distance between pointing and moon (deg)")
    
        pass

    def get_objname(self, mask='grid'):
        return "star_projector_mask_" + mask
#-------------------------------------------------------------------------------

if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        # guider machine (linux)
        base_directory = '/home/tres/tres-guider'
    elif socket.gethostname() == 'Jason-THINK':
        # Jason's computer (Windows 7)
        base_directory = 'C:/tres-guider/'
    elif socket.gethostname() == 'DTHINK':
        # Joe's computer (Windows 10)
        base_directory = 'C:/tres-guider/'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'star_projector.ini'
    star_proj = star_projector(base_directory, config_file)


    ipdb.set_trace()

    star_proj.move_absolute(x=0.0, y=10.0)

    
    kwargs = {'drift_x': 0.01, 'drift_y':0.01, 'mm':True}
    thread = threading.Thread(target=star_proj.jitter_drift,args=(0.01,),kwargs=kwargs)
    thread.name = 'Jitter Drift'
    thread.start()

    

    ipdb.set_trace()

