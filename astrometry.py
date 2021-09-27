from astropy.io import fits as fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import astropy.units as u
import subprocess, os
import datetime
import numpy as np
import ipdb
import csv
import ipdb

# use Gaia index files here:
# http://data.astrometry.net/5000/
# copied to /home/tres/gaia_index_files/
# configured in /usr/etc/astrometry.cfg

def astrometry(imagename,rakey='RA',deckey='DEC',pixscalekey='PIXSCALE',
               pixscale=None,quadlimit=[0.45,0.55],radius=None,logger=None,
               verbose=False):

    t0 = datetime.datetime.utcnow()    
    hdr = fits.getheader(imagename)

    basename = os.path.splitext(imagename)[0]

    filearg = imagename
        
    # This is the base command.
    # we're going to build it up according to the options specified
    cmd = 'solve-field'
        
    try:
        if pixscale == None:
            pixscale = float(hdr[pixscalekey])
    except:
        pass

    # limiting the pixel scale dramatically speeds up the solution
    # because it limits the index files searched (which are big and expensive to load)
    if pixscale != None:
        cmd += ' --scale-units arcsecperpix' + \
               ' --scale-low ' + str(0.99*pixscale) + \
               ' --scale-high ' + str(1.01*pixscale)
    
    # giving it an initial guess mildly speeds up the solution
    if radius != None:
        try:
            ra = float(hdr[rakey])
        except:
            ra = ten(hdr[rakey])*15.0
        
        try:
            dec = float(hdr[deckey])
        except:
            dec = ten(hdr[deckey])

        # negative numbers are interpreted as multiples of the FOV
        if radius < 0:
            radius0 = -radius*pixscale*float(hdr['NAXIS1'])/3600.0
        else: radius0 = radius
            
        cmd += ' --ra ' + str(ra) + \
            ' --dec ' + str(dec) + \
            ' --radius ' + str(radius0)

    # limiting the quad sizes limits the index files searched
    if quadlimit[0] != None:
        cmd += ' --quad-size-min ' + str(quadlimit[0])
    if quadlimit[1] != None:
        cmd += ' --quad-size-max ' + str(quadlimit[1])

    # more options to optimize solving time
    cmd += ' --cpulimit 30' + \
           ' --no-verify' + \
           ' --crpix-center' + \
           ' --no-plots' + \
           ' --overwrite ' +\
           filearg
        
    # dump output if verbose not set
    if not verbose:
        cmd += ' >/dev/null 2>&1'
    print(cmd)
#    ipdb.set_trace()
    os.system(cmd)
    
    # insert the solution into the original image
    f = fits.open(imagename, mode='update')
    if os.path.exists(basename + '.new'):

        # preserve original solution
        try:
            f[0].header['WCD1_1'] = float(f[0].header['CD1_1'])
            f[0].header['WCD1_2'] = float(f[0].header['CD1_2'])
            f[0].header['WCD2_1'] = float(f[0].header['CD2_1'])
            f[0].header['WCD2_2'] = float(f[0].header['CD2_2'])
            f[0].header['WCRVAL1'] = float(f[0].header['CRVAL1'])
            f[0].header['WCRVAL2'] = float(f[0].header['CRVAL2'])
        except:
            pass

        # copy the WCS solution to the file
        newhdr = fits.getheader(basename + '.new')
        f[0].header['WCSSOLVE'] = 'True'
        f[0].header['WCSAXES'] = newhdr['WCSAXES']
        f[0].header['CTYPE1'] = newhdr['CTYPE1']
        f[0].header['CTYPE2'] = newhdr['CTYPE2']
        f[0].header['EQUINOX'] = newhdr['EQUINOX']
        f[0].header['LONPOLE'] = newhdr['LONPOLE']
        f[0].header['LATPOLE'] = newhdr['LATPOLE']
        f[0].header['CRVAL1'] = newhdr['CRVAL1']
        f[0].header['CRVAL2'] = newhdr['CRVAL2']
        f[0].header['CRPIX1'] = newhdr['CRPIX1']
        f[0].header['CRPIX2'] = newhdr['CRPIX2']
        f[0].header['CUNIT1'] = newhdr['CUNIT1']
        f[0].header['CUNIT2'] = newhdr['CUNIT2']
        f[0].header['CD1_1'] = newhdr['CD1_1']
        f[0].header['CD1_2'] = newhdr['CD1_2']
        f[0].header['CD2_1'] = newhdr['CD2_1']
        f[0].header['CD2_2'] = newhdr['CD2_2']
        f[0].header['IMAGEW'] = newhdr['IMAGEW']
        f[0].header['IMAGEH'] = newhdr['IMAGEH']
        f[0].header['A_ORDER'] = newhdr['A_ORDER']
        f[0].header['A_0_2'] = newhdr['A_0_2']
        f[0].header['A_1_1'] = newhdr['A_1_1']
        f[0].header['A_2_0'] = newhdr['A_2_0']
        f[0].header['B_ORDER'] = newhdr['B_ORDER']
        f[0].header['B_0_2'] = newhdr['B_0_2']
        f[0].header['B_1_1'] = newhdr['B_1_1']
        f[0].header['B_2_0'] = newhdr['B_2_0']
        f[0].header['AP_ORDER'] = newhdr['AP_ORDER']
        f[0].header['AP_0_1'] = newhdr['AP_0_1']
        f[0].header['AP_0_2'] = newhdr['AP_0_2']
        f[0].header['AP_1_0'] = newhdr['AP_1_0']
        f[0].header['AP_1_1'] = newhdr['AP_1_1']
        f[0].header['AP_2_0'] = newhdr['AP_2_0']
        f[0].header['BP_ORDER'] = newhdr['BP_ORDER']
        f[0].header['BP_0_1'] = newhdr['BP_0_1']
        f[0].header['BP_0_2'] = newhdr['BP_0_2']
        f[0].header['BP_1_0'] = newhdr['BP_1_0']
        f[0].header['BP_1_1'] = newhdr['BP_1_1']
        f[0].header['BP_2_0'] = newhdr['BP_2_0']
        
        wcs_hdr_dict = {'WCSSOLVE':'True',
                        'WCSAXES': newhdr['WCSAXES'],
                        'CTYPE1': newhdr['CTYPE1'],
                        'CTYPE2': newhdr['CTYPE2'],
                        'EQUINOX': newhdr['EQUINOX'],
                        'LONPOLE': newhdr['LONPOLE'],
                        'LATPOLE': newhdr['LATPOLE'],
                        'CRVAL1': newhdr['CRVAL1'],
                        'CRVAL2': newhdr['CRVAL2'],
                        'CRPIX1': newhdr['CRPIX1'],
                        'CRPIX2': newhdr['CRPIX2'],
                        'CUNIT1': newhdr['CUNIT1'],
                        'CUNIT2': newhdr['CUNIT2'],
                        'CD1_1': newhdr['CD1_1'],
                        'CD1_2': newhdr['CD1_2'],
                        'CD2_1': newhdr['CD2_1'],
                        'CD2_2': newhdr['CD2_2'],
                        'IMAGEW': newhdr['IMAGEW'],
                        'IMAGEH': newhdr['IMAGEH'],
                        'A_ORDER': newhdr['A_ORDER'],
                        'A_0_2': newhdr['A_0_2'],
                        'A_1_1': newhdr['A_1_1'],
                        'A_2_0': newhdr['A_2_0'],
                        'B_ORDER': newhdr['B_ORDER'],
                        'B_0_2': newhdr['B_0_2'],
                        'B_1_1': newhdr['B_1_1'],
                        'B_2_0': newhdr['B_2_0'],
                        'AP_ORDER': newhdr['AP_ORDER'],
                        'AP_0_1': newhdr['AP_0_1'],
                        'AP_0_2': newhdr['AP_0_2'],
                        'AP_1_0': newhdr['AP_1_0'],
                        'AP_1_1': newhdr['AP_1_1'],
                        'AP_2_0': newhdr['AP_2_0'],
                        'BP_ORDER': newhdr['BP_ORDER'],
                        'BP_0_1': newhdr['BP_0_1'],
                        'BP_0_2': newhdr['BP_0_2'],
                        'BP_1_0': newhdr['BP_1_0'],
                        'BP_1_1': newhdr['BP_1_1'],
                        'BP_2_0': newhdr['BP_2_0']}
        success = True
        if logger != None:
            logger.info("WCS Solution succeeded")
    else:
        f[0].header['WCSSOLVE'] = 'False'
        wcs_hdr_dict = {'WCSSOLVE': 'False'}
        success = False
        if logger != None:
            logger.info("WCS Solution failed")

    # save the changes
    f.flush()
    f.close()
    
    # clean up extra files
    extstodelete = ['-indx.png','-indx.xyls','-ngc.png','-objs.png','.axy',
                    '.corr','.match','.new','.rdls','.solved','.wcs']
    for ext in extstodelete:
        if os.path.exists(basename + ext):
            os.remove(basename + ext)

    if logger != None:
        logger.info("Done in " + str((datetime.datetime.utcnow()-t0).total_seconds()) + " seconds")
    return (success,wcs_hdr_dict)

'''
return x/y based on ICRS RA/Dec (decimal degrees) for imagename with a WCS solution in the header 

If motion is supplied, coordinates will be 
ra = ICRS RA (J2000 epoch) 
dec = ICRS dec (J2000 epoch)
pmra = proper motion in RA (mas/yr * cos(dec))
pmdec = proper motion in Dec (mas/yr)
rv = radial velocity (km/s)

The units are all the default outputs from the Gaia catalogs

TODO: sort out equinox of input vs output. input is probably current, output probably should be J2000?
TODO: test on sky with high proper motion star!
'''
def sky2pixels(wcs_hdr_dict, ra, dec, pmra=0.0, pmdec=0.0, rv=0.0, equinox=2000.0):
#    f = fits.open(imagename)
#    ipdb.set_trace()
    w = WCS(wcs_hdr_dict)
    sky = SkyCoord(ra, dec, unit="deg", frame="icrs", radial_velocity=rv*u.km/u.s, \
                   pm_ra_cosdec=pmra*u.mas/u.yr, pm_dec=pmdec*u.mas/u.yr)
    xy = w.world_to_pixel(sky)
    return (float(xy[1]),float(xy[0]))

def pixels2sky(wcs_hdr_dict,y,x):
    w = WCS(wcs_hdr_dict)
    sky = w.pixel_to_world(x,y)
    return(sky)

if __name__ == '__main__':

    filename = 'projector_star_field_center.fits'
    astrometry(filename,use_sep=True, verbose=True)


    ipdb.set_trace()
    

    
