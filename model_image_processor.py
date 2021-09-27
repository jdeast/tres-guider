#!/usr/bin/python3
#from __future__ import division
from scipy.optimize import least_squares
from scipy.optimize import minimize
import numpy as np
import pyds9
import ipdb
import datetime
from astropy.io import fits as pyfits
from scipy.ndimage.filters import gaussian_filter

################################################################################
class ImageProcessor():
    '''Manage image processing to compute guiding feedback'''
    def __init__(self,config,logger=None):
        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger('./log/','image_processor')
        else:
            self.logger = logger

#-------------------------------------------------------------------------------
    def populate_header(self,hdr):
        '''
        Populate FITS header passed in to set current Image processing state
        '''
        # WCS solution
        #hdr['EPOCH'] = (2000,'Epoch of coordinates')
        #hdr['SECPIX'] = (self.platescale,'arcsec/pixel')
        #hdr['CTYPE1'] = ("RA---TAN","TAN projection")
        #hdr['CTYPE2'] = ("DEC--TAN","TAN projection")
        #hdr['CUNIT1'] = ("deg","X pixel scale units")
        #hdr['CUNIT2'] = ("deg","Y pixel scale units")
        #hdr['CRVAL1'] = (ra,"RA of reference point")
        #hdr['CRVAL2'] = (dec,"DEC of reference point")
        #hdr['CRPIX1'] = (self.x_sci_fiber,"X reference pixel")
        #hdr['CRPIX2'] = (self.y_sci_fiber,"Y reference pixel")
        #hdr['CD1_1'] = (-self.platescale*math.cos(skypa),"DL/DX")
        #hdr['CD1_2'] = (self.platescale*math.sin(skypa),"DL/DY")
        #hdr['CD2_1'] = (self.platescale*math.sin(skypa),"DM/DX")
        #hdr['CD2_2'] = (self.platescale*math.cos(skypa),"DM/DY")
        pass
    
#-------------------------------------------------------------------------------
    def model_annulus(self,pars, image, err, save=False):    
        x_center = pars[0]
        y_center = pars[1]
        sigma = pars[2]
        background = pars[3]
        amplitude = pars[4]
        x_hole = pars[5]
        y_hole = pars[6]
        hole_size = pars[7]
        ylen,xlen = image.shape

        # follow FITS convention that the first pixel is 1,1
        xmin = 1
        xmax = xlen

        ymin = 1
        ymax = ylen

        # boundary checking
        if hole_size  <  0.0: return [np.Infinity]
        if sigma      <= 0.0: return [np.Infinity]
        if amplitude  <= 0.0: return [np.Infinity]
        #    if background <  0.0: return [np.Infinity]

        if x_hole   < (xmin-hole_size) or x_hole   > (xmax+hole_size):
            return [np.Infinity]
        if y_hole   < (ymin-hole_size) or y_hole   > (ymax+hole_size):
            return [np.Infinity]
        if x_center < (xmin-3.0*sigma) or x_center > (xmax+3.0*sigma):
            return [np.Infinity] 
        if y_center < (ymin-3.0*sigma) or y_center > (ymax+3.0*sigma):
            return [np.Infinity]

        xgrid,ygrid = np.meshgrid(np.linspace(xmin-x_center,xmax-x_center,xlen),
                                  np.linspace(ymin-y_center,ymax-y_center,ylen))
        
        xgridhole,ygridhole = np.meshgrid(np.linspace(xmin-x_hole,
                                                      xmax-x_hole,xlen),
                                          np.linspace(ymin-y_hole,
                                                      ymax-y_hole, ylen))

        dhole = np.sqrt(xgridhole*xgridhole+ygridhole*ygridhole)
        hole = np.where(dhole < hole_size)

        hole_mask = np.zeros((ylen,xlen),dtype=np.float64) + 1.0

        hole_mask[hole[0],hole[1]] = 0.0
        hole_mask = gaussian_filter(hole_mask,sigma=1.0)
    
        mu = 0.0
        d = np.sqrt(xgrid*xgrid+ygrid*ygrid)
        g = (hole_mask*amplitude*np.exp(-( (d-mu)**2 / ( 2.0 * sigma**2 ) ) ) +
             background)
        
        return ((image - g)/err).flatten()


#-------------------------------------------------------------------------------
    def fit_annulus(self,image, pars=None, scale=None):

        if pars==None:
            x_center = 0.1
            y_center = 0.3
            sigma = 7.0
            background = np.median(image)
            amplitude = np.amax(image)-background
            x_hole = x_center
            y_hole = y_center
            hole_size = 7.0
            pars = [x_center,y_center,sigma,background,amplitude,
                    x_hole,y_hole,hole_size]

        err = image*0.0 + 1.0

        result = least_squares(self.model_annulus, pars, args=([image,err]),
                               x_scale=scale)
        return result

    
#-------------------------------------------------------------------------------
    def get_stars(self,image):
        t0 = datetime.datetime.utcnow()        
        data_sub = image
        ylen,xlen=image.shape
        x_center = xlen/2.0
        x_hole = x_center
        y_center = xlen/2.0
        y_hole = y_center
        sigma = 7.0
        #    background = 0.0
        background = np.median(data_sub)
        amplitude = np.amax(data_sub) - background
        hole_size = 9.8
        pars  = [x_center,y_center,sigma,background,amplitude,
                 x_hole,y_hole,hole_size]
        scale = [10.0,10.0,3.0,10.0,5000.0,10.00,10.00,5.0]

        best = self.fit_annulus(data_sub,pars,scale=scale)
        if self.logger != None:
            self.logger.info('x_center='  + str(best.x[0]) +
                             ', x_center='   + str(best.x[1]) +
                             'FHWM='      + str(best.x[2]) +
                             ', background=' + str(best.x[3]) +
                             'amplitude=' + str(best.x[4]) +
                             ', x_hole='     + str(best.x[5]) +
                             'y_hole='    + str(best.x[6]) +
                             ', hole_size='  + str(best.x[7]))
        tf = datetime.datetime.utcnow()
        print((tf-t0).total_seconds())
        return(np.transpose(np.vstack((best.x[0], best.x[1], best.x[4]))))

################################################################################
