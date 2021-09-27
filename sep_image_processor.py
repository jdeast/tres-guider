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
    def get_stars(self,image):
        t0 = datetime.datetime.utcnow()
        image0 = image.astype('float32')
        
        bkg = sep.Background(image0, bw=64, bh=64, fw=3, fh=3)
        #bkg_rms = bkg.rms()

        data_sub = image0 - bkg
        try:
            stars = sep.extract(data_sub,5.0,err=bkg.globalrms,
                                minarea=100, deblend_nthresh=2)
        except:
            return []
        tf = datetime.datetime.utcnow()
        print((tf-t0).total_seconds())
        # add one to X & Y for FITS convention
        return(np.transpose(np.vstack((stars['x']+1,
                                       stars['y']+1,
                                       stars['flux']))))

################################################################################
