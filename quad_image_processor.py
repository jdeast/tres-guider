#!/usr/bin/python3
#from __future__ import division

import datetime
import numpy as np
import sep

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
    def get_quad_annulus(self,image):
        ''' determine the centroid in the presence of a hole using
        the power in 4 quadrants plus an empirical correction
        the input image should be a postage stamp around the fiber hole with one
        star'''
        t0 = datetime.datetime.utcnow()
        image0 = image.astype('float64')
        bkg = sep.Background(image0, bw=64, bh=64, fw=3, fh=3)
        data_sub = image0 - bkg

        ylen,xlen = image0.shape
        x1 = 0
        x2 = np.floor(xlen/2).astype(int)
        x3 = x2+1
        x4 = xlen
        y1 = 0
        y2 = np.floor(ylen/2).astype(int)
        y3 = y2+1
        y4 = ylen

        intensity_left = np.sum(data_sub[:,x1:x2])
        intensity_right = np.sum(data_sub[:,x3:x4])
        intensity_bottom = np.sum(data_sub[y1:y2,:])
        intensity_top = np.sum(data_sub[y3:y4,:])
        total_inten = (intensity_left + intensity_right + 
                       intensity_top + intensity_bottom)
        
        xquad = ((intensity_right - intensity_left)/
                 (intensity_left+intensity_right)*(xlen/2.0)+x3)
        yquad = ((intensity_top - intensity_bottom)/
                 (intensity_bottom+intensity_top)*(ylen/2.0)+y3)

        tf = datetime.datetime.utcnow()
#        print((tf-t0).total_seconds())
    
        return xquad,yquad,total_inten
    
#-------------------------------------------------------------------------------
    def annulus2cen(self,xin,yin,com=False,quad=False,sep=False):
        ''' function to translate measured centroid to true centroid
         empirically calibrated using calibrate_annulus.py '''

        # these are just temporary passthroughs that return xin, yin
        if com:
            xcoeffs = [1.0,0.0]
            ycoeffs = [1.0,0.0]
        elif quad:
            xcoeffs = [1.0,0.0]
            ycoeffs = [1.0,0.0]
        elif sep:        
            xcoeffs = [1.0,0.0]
            ycoeffs = [1.0,0.0]
        else:
            print("one of com, quad, sep must be True")
        
        x = np.polyval(xcoeffs,xin)
        y = np.polyval(ycoeffs,yin)
        
        return x, y
    
#-------------------------------------------------------------------------------
    def get_stars(self,image):
        ''' determine the centroid in the presence of a hole using
        the power in 4 quadrants plus an empirical correction
        the input image should be a postage stamp around the fiber hole with one
        star '''    
        xquad,yquad,inten = self.get_quad_annulus(image)
        #t0 = datetime.datetime.utcnow()
        x,y = self.annulus2cen(xquad,yquad,quad=True)
        #tf = datetime.datetime.utcnow()
        #print((tf-t0).total_seconds())
        return np.transpose(np.vstack((x,y,inten,0.0)))
    
################################################################################
