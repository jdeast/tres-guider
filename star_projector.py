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
import pdu
import threading
import math
import time
import datetime
import ephem
import numpy as np

class StarProjector:

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
        self.arcsec_per_mm_x = float(config['ARCSEC_PER_MM'])
        self.arcsec_per_mm_y = float(config['ARCSEC_PER_MM'])
        self.nfail = 0

        # translate from axis1/axis2 on the star projector
        # to X/Y on the ccd
        self.sptheta = float(config['SPTHETA'])*math.pi/180.0
        if config['SPFLIP'] == 'True': self.spsign = -1.0
        else: self.spsign = 1.0

        self.sitename = config['SITENAME']
        self.sitelat = float(config['SITELAT'])
        self.sitelong = float(config['SITELONG'])
        self.siteelev = float(config['SITEELEV'])
        self.obs = ephem.Observer()
        self.obs.lat = ephem.degrees(str(self.sitelat)) # N
        self.obs.lon = ephem.degrees(str(self.sitelong)) # E
        self.obs.elevation = self.siteelev # meters
        
        # this translates from X/Y on the CCD to north/east on the sky
        self.cd11 = float(config['CD11'])
        self.cd12 = float(config['CD12'])
        self.cd21 = float(config['CD21'])
        self.cd22 = float(config['CD22'])

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
            success = False
            while not success:
                try:
                    self.get_position()
                    success = True
                except:
                    self.logger.error("connection timed out, connecting again")
                    self.connect()
                    time.sleep(2.0)
                
                
#            time.sleep(15.0)
#            self.connect()
#            print('connected!')
#            ipdb.set_trace()
#            self.get_position()
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

    def get_position(self, mm=False, arcsec=False, native=False):

        xpos = self.x_axis.get_position()
        ypos = self.y_axis.get_position()
        thetapos = self.rot_axis.get_position()
        
        if mm:
            return ((xpos - (self.min_x_steps + self.max_x_steps)/2.0)*self.mm_per_step_x,
                    (ypos - (self.min_y_steps + self.max_y_steps)/2.0)*self.mm_per_step_y,
                    thetapos*self.deg_per_step)
        if arcsec:
            return ((xpos - (self.min_x_steps + self.max_x_steps)/2.0)*self.arcsec_per_step_x,
                    (ypos - (self.min_y_steps + self.max_y_steps)/2.0)*self.arcsec_per_step_y,
                    thetapos*self.deg_per_step)
        else:
            return (xpos,ypos,thetapos)
    
    def connect(self):
        self.comport = BinarySerial(self.port)
        self.x_axis = BinaryDevice(self.comport,1)
        self.y_axis = BinaryDevice(self.comport,2)
        self.rot_axis = BinaryDevice(self.comport,3)
#        time.sleep(10)

        
    def home(self):
        # this always times out if at the end of range
        self.x_axis.home()
        self.y_axis.home()
        #self.rot_axis.home() # broken

    ''' X/Y motion in arcsec, angle in degrees ''' 
    # TODO: error handling
    # this is moving the star projector hardware axis1=x, axis2=y
    def move_relative(self, x=0, y=0, degrees=0, wait=True, mm=False):
        
        if mm:
            x_move = int(round(x/self.mm_per_step_x))
            y_move = int(round(y/self.mm_per_step_y))
        else:
            x_move = int(round(x/self.arcsec_per_step_x))
            y_move = int(round(y/self.arcsec_per_step_y))

        x0,y0,theta0 = self.get_position(native=True)
            
        self.logger.info("moving " + str(x_move) + " relative steps in x and " + str(y_move) + " in y")
        self.x_axis.move_rel(x_move)
        self.y_axis.move_rel(y_move)

        xf,yf,thetaf = self.get_position(native=True)

        if (x0+x_move) != xf or (y0+y_move) != yf:
            self.nfail += 1
            if self.nfail > 3:
                self.logger.error("Did not go to requested position after 3 attempts; giving up!")
                return False
            self.logger.warning("Did not go to requested position; trying again")
            self.logger.warning("x0,xf,x_move=" + str(x0) + ',' + str(xf) + ',' + str(x_move))
            self.logger.warning("y0,yf,y_move=" + str(y0) + ',' + str(yf) + ',' + str(y_move))
            self.move_absolute(x=x0+x_move,y=y0+y_move,native=True)
        else: self.nfail=0

        # self.rot_axis.move_rel(degrees/self.deg_per_step)

        # doesn't work for binary library
#        if wait:
#            self.x_axis.poll_until_idle()
#            self.y_axis.poll_until_idle()
#            self.rot_axis.poll_until_idle()

    ''' X/Y motion in arcsec, angle in degrees ''' 
    # TODO: error handling
    def move_absolute(self, x=0.0, y=0.0, degrees=0.0, wait=True, mm=False, native=False):

        if mm:
            x_move = int(round((self.min_x_steps + self.max_x_steps)/2.0 + x/self.mm_per_step_x))
            y_move = int(round((self.min_y_steps + self.max_y_steps)/2.0 + y/self.mm_per_step_y))
        elif native:
            x_move = int(round(x))
            y_move = int(round(y))
        else:
            x_move = int(round((self.min_x_steps + self.max_x_steps)/2.0 + x/self.arcsec_per_step_x))
            y_move = int(round((self.min_x_steps + self.max_x_steps)/2.0 + y/self.arcsec_per_step_y))

        self.logger.info("moving " + str(x_move) + " steps in x and " + str(y_move) + " in y")

        if x_move > self.max_x_steps or x_move < self.min_x_steps or y_move > self.max_y_steps or y_move < self.min_y_steps:
            self.logger.error("Requested move beyond bounds")
            self.nfail += 3
            return False
            
        self.x_axis.move_abs(x_move)
        self.y_axis.move_abs(y_move)
        #self.rot_axis.move_abs(int(round(degrees/self.deg_per_step)))

        x,y,theta = self.get_position(native=True)
        if x != x_move or y != y_move:
            self.nfail += 1
            if self.nfail > 3:
                self.logger.error("Did not go to requested position after 3 attempts; giving up!")
                return False
            self.logger.warning("Did not go to requested position; trying again")
            self.move_absolute(x=x_move, y=y_move)
        else: self.nfail=0


            
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

    def east_north_to_ccdx_ccdy(self,east,north):

        # cd matrix is deg/pix, east/north in arcsec
        det = 1.0/(self.cd11*self.cd22 - self.cd12*self.cd21)
        ccdx = ( east*det*self.cd22 - north*det*self.cd12)/3600.0 # arcsec
        ccdy = (-east*det*self.cd21 + north*det*self.cd11)/3600.0 # arcsec

        east2  = (ccdx*self.cd11 + ccdy*self.cd12)*3600.0 # arcsec
        north2 = (ccdx*self.cd21 + ccdy*self.cd22)*3600.0 # arcsec

#        ipdb.set_trace()
        
        self.logger.info('east,north = (' + str(east) + ',' + str(north) + '), ccdx,ccdy = (' + str(ccdx) + ',' + str(ccdy) + ')')

        return ccdx,ccdy

    def ccdx_ccdy_to_projx_projy(self,ccdx,ccdy):

#        projx =  self.spsign*(ccdx*math.cos(self.sptheta) - ccdy*math.sin(self.sptheta))
#        projy =               ccdx*math.sin(self.sptheta) + ccdy*math.cos(self.sptheta)
        
        # This is what worked with the WCS!! Don't change without re-testing star mask
        projx =  self.spsign*ccdx*math.cos(self.sptheta) + ccdy*math.sin(self.sptheta) # arcsec
        projy = -self.spsign*ccdx*math.sin(self.sptheta) + ccdy*math.cos(self.sptheta) # arcsec

        self.logger.info('ccdx,ccdy = (' + str(ccdx) + ',' + str(ccdy) + '), projx,projy = (' + str(projx) + ',' + str(projy) + ')')
        return projx,projy

    def east_north_to_projx_projy(self,east,north):
#        return self.ccdx_ccdy_to_projx_projy(self.east_north_to_ccdx_ccdy(east,north))

        ccdx,ccdy = self.east_north_to_ccdx_ccdy(east,north)
        projx,projy = self.ccdx_ccdy_to_projx_projy(ccdx,ccdy)

        self.logger.info('east,north = (' + str(east) + ',' + str(north) + '), projx,projy = (' + str(projx) + ',' + str(projy) + ')')

        return projx,projy
    
    def move_xy(self,ccdx,ccdy):
        projx,projy = self.ccdx_ccdy_to_projx_projy(ccdx,ccdy)
        self.move_relative(x=projx,y=projy)

#-------------------------------------------------------------------------------
    # these function names emulate dfm_telescope
    # so it can be used as a telescope replacement
    # I'm going to assume that North is up, East is left as seen on the Andor
    # I want to translate that into pixels
    def jog(self, east, north):

        self.logger.info('Moving ' + str(east) + '" east, ' + str(north) + '" North')
        x,y = self.east_north_to_projx_projy(east,north) # arcsec
        
#        # apply the rotation matrix from axis1/axis2 on the projector to x/y on the CCD
#        # so we use the transpose rotation matrix for the reverse
#        x =  self.spsign*(east*math.cos(self.sptheta) - north*math.sin(self.sptheta))
#        y =               east*math.sin(self.sptheta) + north*math.cos(self.sptheta)
        self.move_relative(x=x,y=y)
        
    def read_mount_coordinates(self):
        coords = {'HA':0.0,
#                  # coordinates of our star projector mask center
#                  'RA':266.41/15.0, 
#                  'Dec':-28.94,
                  # coordinates of a star to acquire in our projector mask
                  'RA':266.5326662/15.0, 
                  'Dec':-28.90536313,     
                  'RA':266.4979902/15.0, 
                  'Dec':-29.01741801,     
                  'equinox':2000,   # not sure this is right (or relevant)
                  'airmass':1.0,
                  'zenith_distance':0.0,
                  'azimuth': 0.0,
                  'sidereal_time':'??',
                  'date': datetime.datetime.utcnow()}

        return coords

    def read_target_object_coordinates(self):
        coords = {'elapsed_track_time':0.0,
                  'apparent_ha':0.0,
#                  # coordinates of our star projector mask center
#                  'mean_ra':266.41/15.0,
#                  'mean_dec':-28.94,
                  # coordinates of a star to acquire in our projector mask
                  'mean_ra':266.534479167/15.0, 
                  'mean_dec':-28.9247611111,     
                  'equinox':2000,          # not sure this is right (or relevant)
                  'mean_ra_velocity':0.0,
                  'mean_dec_velocity':0.0,
                  'airmass':1.0,
                  'zenith_distance':0.0,
                  'azimuth': 0.0}
        return coords
        
    def populate_header(self,hdr):

        # Site keywords
        hdr['TELESCOP'] = (self.sitename,"Telescope")
        hdr['SITELAT'] = (self.sitelat,"Site Latitude (deg)")
        hdr['SITELONG'] = (-self.sitelong,"Site longitude (deg W of zero)")
        hdr['SITEELEV'] = (self.siteelev,"Site Elevation (m)")

        # Positional keywords
        coords = self.read_mount_coordinates()
        hdr['HA'] = (coords['HA'], "Hour angle (hrs)")
        hdr['RA'] = (coords['RA']*15.0, "Mount RA (J2000 deg)")
        hdr['DEC'] = (coords['Dec'], "Mount Dec (J2000 deg)")
        hdr['EQUINOX'] = (coords['equinox'],"Equinox of coordinates")

        #stolen from parangle.pro written by Tim Robinshaw
        parang = -180.0/math.pi*math.atan2(-math.sin(coords['HA']*math.pi/12.0),
                                           math.cos(coords['Dec']*math.pi/180.0)*math.tan(float(self.sitelat)*math.pi/180.0)-
                                           math.sin(coords['Dec']*math.pi/180.0)*math.cos(coords['HA']*math.pi/12.0))
        
        hdr['PARANG'] = (parang, "Parallactic Angle (deg)")
        hdr['AIR'] = (coords['airmass'],'Airmass')
        hdr['ZENITH'] = (coords['zenith_distance'],'Zenith Distances (deg)')
        hdr['AZIMUTH'] = (coords['azimuth'],'Telescope Azimuth (Deg E of N)')
        hdr['ALTITUDE'] = (90 - coords['zenith_distance'],'Telescope Altitude (Deg)')
        hdr['ST'] = (coords['sidereal_time'],'Sidereal Time (HH:MM:SS.fff)')       
        hdr['FOCPOS'] = (self.read_focuser_position(),"Focus Position (mm?)")
        #hdr['PMODEL'] = ('',"Pointing Model File")
        #hdr['ROTPOS'] = (rotpos,"Mechanical rotator position (degrees)")

        sign = np.sign(self.cd11*self.cd22-self.cd12*self.cd21)
        skypa = math.atan2(sign*self.cd21,self.cd11)*180.0/math.pi
        hdr['SKYPA' ] = (skypa,"Position angle on the sky (degrees E of N)")

        # add moon keywords
        moon = ephem.Moon()
        moon.compute(datetime.datetime.utcnow())
        moonpos = (moon.ra,moon.dec)
        moonsep = ephem.separation((coords['RA']*math.pi/180.0,coords['Dec']*math.pi/180.0),(moon.ra,moon.dec))*180.0/math.pi
        hdr['MOONRA'] = (moon.ra*180.0/math.pi, "Moon RA (J2000 deg)")
        hdr['MOONDEC'] =  (moon.dec*180.0/math.pi, "Moon Dec (J2000 deg)")
        hdr['MOONPHAS'] = (moon.phase/100.0, "Moon Phase (Fraction)")
        hdr['MOONDIST'] = (moonsep, "Distance between pointing and moon (deg)")
    
        # add Sun keywords
        self.obs.date = datetime.datetime.utcnow()
        sun = ephem.Sun()
        sun.compute(self.obs) # needs lat/lon/date
        hdr['SUNALT'] = (sun.alt*180.0/math.pi, "Sun Alt (Deg)")
        hdr['SUNAZ'] =  (sun.az*180.0/math.pi, "Sun Az (Deg E of N)")

        # Weather keywords ?
        
        pass

    def read_focuser_position(self):
        return 0.0
    
    def get_objname(self, mask='grid'):
        return "star_projector_mask_" + mask
    
#-------------------------------------------------------------------------------

if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        # guider machine (linux)
        base_directory = '/home/tres/jan/tres-guider'
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
    star_proj = StarProjector(base_directory, config_file)
    apc = pdu.PDU(base_directory, 'pdu.ini', logger=star_proj.logger)
    if not apc.starprojector.status():
        apc.starprojector.on()
    
#    ipdb.set_trace()

#    star_proj.move_absolute(x=0.0, y=0.0)

    star_proj.move_absolute(x=-70.0, y=-7.6)
    

    
#    kwargs = {'drift_x': 0.01, 'drift_y':0.01, 'mm':True}
#    thread = threading.Thread(target=star_proj.jitter_drift,args=(0.01,),kwargs=kwargs)
#    thread.name = 'Jitter Drift'
#    thread.start()


#    ipdb.set_trace()

