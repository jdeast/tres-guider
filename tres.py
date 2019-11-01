from astropy.io import fits
from pyAndorSDK3 import AndorSDK3
import numpy as np
import socket
import os, sys
import utils
from configobj import ConfigObj
import ipdb
import logging
import datetime
import pid
from get_all_centroids import *
import threading

class tres:

    def __init__(self, base_directory, config_file, logger=None):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'tres')
        else: self.logger = logger

        # read the config file
        config = ConfigObj(self.config_file)

        # read the config file
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + self.config_file + ')')
            sys.exit()

        # set up the devices
        self.guider = imager(base_directory, 'zyla.ini', logger=self.logger)
        self.calstage = calstage(base_directory, 'calstage.ini', logger=self.logger)
        self.tiptilt = tiptilt(base_directory, 'tiptilt.ini', logger=self.logger)
        
    # this assumes there are is no confusion (within tolerance) and each offset is small (< tolerance)
    # annulus guiding (pick star closest to fiber and guide)                     -- done
    # offset guiding (pick star closest to position offset from fiber and guide) -- done
    # platesolve and guide to RA/Dec -- TODO (enough stars?)
    # platesolve and guide to Star closest to RA/Dec -- TODO (enough stars?)
    def guide(self, exptime, offset=(0.0,0.0), tolerance=3.0):

        # load the PID servo parameters
        p=pid.PID(P=np.array([self.guider.KPx, self.guider.KPy]),
                  I=np.array([self.guider.KIx, self.guider.KIy]),
                  D=np.array([self.guider.KDx, self.guider.KDy]),
                  Integrator_max = self.guider.Imax,
                  Deadband = self.guider.Dband,
                  Correction_max = self.guider.Corr_max)

        # TODO: refine fiber position on the chip (does it change?)

        # load the PID set point
        p.setPoint((self.guider.xfiber, self.guider.yfiber))
        
        # TODO: pick guide star, move it to fiber via telescope (pre-load tip/tilt?)
        # requires TCS communication (current functionality requires observer to do this)
        
        # main loop
        while self.guider.guiding:

            self.guider.take_image(exptime)
            stars = self.guider.get_stars()
            # TODO: save guide image?

            # find the closest star to the desired position                            
            dx = stars[:,0] - (self.guider.x_science_fiber-offset[0])
            dy = stars[:,1] - (self.guider.y_science_fiber-offset[1])
            dist = np.sqrt(dx^2 + dy^2)*self.guider.platescale
            ndx = np.argmin(dist)

            # if the star disappears, don't correct to a different star
            # magnitude tolerance, too? (probably not)
            if dist < tolerance:
                p.setPoint((self.guider.xfiber+offset[0],self.guider.yfiber+offset[1]))

                # calculate the X & Y pixel offsets
                dx,dy = p.update(np.array([stars[ndx,0],stars[ndx,1]]))
                
                # convert X & Y pixel to North & East arcsec offset
                # don't need cos(dec) term unless we send via mount
                PA = 0.0 # get from Telescope? Config file? user?
                north = self.guider.platescale*(dx*math.cos(PA) - dy*math.sin(PA))
                east  = self.guider.platescale*(dx*math.sin(PA) + dy*math.cos(PA))

                # TODO: make sure the move is within range
                move_in_range = True
                
                # send correction to tip/tilt
                if move_in_range:
                    self.tiptilt.move_north_east(north,east)
                else:
                    # TODO: move telescope, recenter tip/tilt
                    self.logger.error("Tip/tilt out of range. Must manually recenter")

    def take_image(self, filename, exptime):

        # expose while we get the header info
        expose_thread = threading.Thread(target=self.guider.take_image, args=(exptime,))
        expose_thread.name = 'guider thread'
        expose_thread.start()

        # get the header info
        hdr = self.get_header()

        # wait for the exposure to complete
        expose_thread.join()
        
        # save the image
        self.guider.save_image(filename, hdr=hdr)
        
    def get_header(self):

        hdr = fits.Header()

        # placeholders might be wrong if we populated them now. let guider.save_image populate them
        hdr['DATE-OBS'] = ('','YYYY-MM-DDThh:mm:ss.ssssss (UTC)') # placeholder
        hdr['EXPTIME'] = ('','Exposure time (s)') # placeholder
        hdr['PIXSCALE'] = (self.guider.platescale,'arcsec/pixel')
        hdr['GAIN'] = (self.guider.gain,'electrons/ADU')
        hdr['DATASEC'] = ('',"Region of CCD read") # placeholder
        hdr['CCDSUM'] = ('','CCD on-chip summing') # placeholder

        hdr['INSTRUME'] = ('TRES','Name of the instrument')
        hdr['OBSERVER'] = ('',"Observer") # do we have this info?

        # Camera info
        hdr['CAMMOD'] = (self.guider.model,'Model of the acquisition camera')
        hdr['CAMERASN'] = (self.guider.sn,'Serial number of the acquisition camera')
        hdr['CCD-TEMP'] = (-999,'CCD Temperature (C)') # do we have this?

        # Calibration stage info
        hdr['CSPOS'] = (self.calstage.get_position_string(),"Position of the calibration stage (string)")
        hdr['CSPOSN'] = (self.calstage.get_position(),"Position of the calibration stage (mm)")
        hdr['CSMODEL'] = (self.calstage.model,"Model Number of the calibration stage")
        hdr['CSSN'] = (self.calstage.sn,"Serial number of the calibration stage")
        hdr['CSCMODEL'] = (self.calstage.model_controller,"Model Number of the calibration stage controller")
        hdr['CSCSN'] = (self.calstage.sn_controller,"Serial number of the calibration stage controller")

        # Tip/Tilt stage info
        ttpos = self.tiptilt.getpos()
        hdr['TTTIPPOS'] = (ttpos[0],"Tip Position of the tip/tilt stage (urad)")
        hdr['TTTILPOS'] = (ttpos[1],"Tilt Position of the tip/tilt stage (urad)")
        hdr['TTMODEL'] = (self.tiptilt.model,"Model number of the tip/tilt stage")
        hdr['TTSN'] = (self.tiptilt.sn,"Serial number of the tip/tilt stage")
        hdr['TTCMODEL'] = (self.tiptilt.model_controller,"Model number of the tip/tilt stage controller")
        hdr['TTCSN'] = (self.tiptilt.sn_controller,"Serial number of the tip/tilt stage controller")

        # Fiber info
        hdr['XSCIFIB'] = (self.guider.x_science_fiber,'X pixel of science fiber centroid')
        hdr['YSCIFIB'] = (self.guider.y_science_fiber,'Y pixel of science fiber centroid')
        hdr['XSKYFIB'] = (self.guider.x_sky_fiber,'X pixel of sky fiber centroid')
        hdr['YSKYFIB'] = (self.guider.y_sky_fiber,'Y pixel of sky fiber centroid')
        hdr['GUIDSTAT'] = (self.guider.guidestatus,'Status of the guiding loop')

        # telescope information (requires communication with TCS)
        #hdr['SITELAT'] = (latitude,"Site Latitude (deg)")
        #hdr['SITELONG'] = (longitude,"Site East Longitude (deg)")
        #hdr['SITEALT'] = (elevation,"Site Altitude (m)")
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
        
        # WCS solution
        #hdr['EPOCH'] = (2000,'Epoch of coordinates')
        #hdr['SECPIX'] = (self.platescale,'arcsec/pixel')
        #hdr['CTYPE1'] = ("RA---TAN","TAN projection")
        #hdr['CTYPE2'] = ("DEC--TAN","TAN projection")
        #hdr['CUNIT1'] = ("deg","X pixel scale units")
        #hdr['CUNIT2'] = ("deg","Y pixel scale units")
        #hdr['CRVAL1'] = (ra,"RA of reference point")
        #hdr['CRVAL2'] = (dec,"DEC of reference point")
        #hdr['CRPIX1'] = (self.x_science_fiber,"X reference pixel")
        #hdr['CRPIX2'] = (self.y_science_fiber,"Y reference pixel")
        #hdr['CD1_1'] = (-self.platescale*math.cos(skypa),"DL/DX")
        #hdr['CD1_2'] = (self.platescale*math.sin(skypa),"DL/DY")
        #hdr['CD2_1'] = (self.platescale*math.sin(skypa),"DM/DX")
        #hdr['CD2_2'] = (self.platescale*math.cos(skypa),"DM/DY")

        # target information (do we have this?)
        #hdr['TARGRA'] = (ra, "Target RA (J2000 deg)")
        #hdr['TARGDEC'] = (dec,"Target Dec (J2000 deg)")
        #hdr['PMRA'] = (pmra, "Target Proper Motion in RA (mas/yr)")
        #hdr['PMDEC'] = (pmdec, "Target Proper Motion in DEC (mas/yr)")
        #hdr['PARLAX'] = (parallax, "Target Parallax (mas)")
        #hdr['RV'] = (rv, "Target RV (km/s)")
        
if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    elif socket.gethostname() == 'Jason-THINK':
        base_directory = 'C:/tres-guider/'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'tres.ini'
    tres = imager(base_directory, config_file)

    ipdb.set_trace()



