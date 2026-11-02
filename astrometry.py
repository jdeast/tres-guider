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
import sep_image_processor

# use Gaia index files here:
# http://data.astrometry.net/5000/
# copied to /home/tres/gaia_index_files/
# configured in /usr/etc/astrometry.cfg

# native version of xylist2fits
# basename.xy is a two-column ascii file of XY positions sorted by brightness
# cmd = 'xylist2fits ' + basename '.xy ' + basename + '.xyls'
def stars_to_xyls(stars, basename):
    xylsfile = basename + '.xyls'

    sorted = stars[:,2].argsort()
    x = stars[sorted[::-1],0]
    y = stars[sorted[::-1],1]

    # write my own xyls file (20x faster than using built-in tool, no known downside)
    colx = fits.Column(name='X', format='E', array=x)
    coly = fits.Column(name='Y', format='E', array=y)
    coldefs = fits.ColDefs([colx,coly])
    hdu = fits.BinTableHDU.from_columns([colx,coly])
    hdu.writeto(xylsfile,overwrite=True)

def astrometry(imagename,rakey='RA',deckey='DEC',pixscalekey='PIXSCALE',\
               pixscale=None,quadlimit=[0.45,0.55],parity=None,\
               downsample=None,radius=None,use_sep=False,\
               logger=None,verbose=False,vverbose=False):

    t0 = datetime.datetime.utcnow()    
    hdr = fits.getheader(imagename)
    basename = os.path.splitext(imagename)[0]

    # This is the base command.
    # we're going to build it up according to the options specified
    cmd = 'solve-field'

    # use SEP to extract stars and write my own xyls file
    # could avoid writing/reading image to disk if we pass image/star coordinates/xyls file directly...
    if use_sep:
        image_processor = sep_image_processor.ImageProcessor('',logger=logger)
        image = fits.getdata(imagename)
        stars = image_processor.get_stars(image,minarea=25.0,threshold=3.0)
        
        #stars = centroid.get_stars_sep('',imagename,minarea=25,threshold=3.0)
        stars_to_xyls(stars, basename)
        filearg = basename + '.xyls'
        width = float(hdr['NAXIS1'])
        height = float(hdr['NAXIS2'])
        cmd += ' --width ' + str(width) + ' --height ' + str(height)
    else: filearg = imagename

    # extra verbosity
    if vverbose:
        cmd += ' -v'
        verbose=True
        
    try:
        if pixscale == None: pixscale = float(hdr[pixscalekey])
    except:
        pass

    # limiting the pixel scale dramatically speeds up the solution
    # because it limits the index files searched (big and expensive to load)
    if pixscale != None:
        cmd += ' --scale-units arcsecperpix' + \
               ' --scale-low ' + str(0.95*pixscale) + \
               ' --scale-high ' + str(1.05*pixscale)

    if parity != None: cmd += ' --parity ' + parity
    if downsample != None: cmd += ' --downsample ' + str(downsample)
            
    # giving it an initial guess mildly speeds up the solution
    if radius != None and rakey in hdr.keys() and deckey in hdr.keys():
        try: ra = float(hdr[rakey])
        except: ra = ten(hdr[rakey])*15.0
        
        try: dec = float(hdr[deckey])
        except: dec = ten(hdr[deckey])

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
    if logger != None: logger.info("platesolving command is "+cmd)
#    os.system(cmd)  # cpulimit doesn't seem to be respected
    # force timeout using subprocess instead
    try:
        subprocess.check_output(cmd,shell=True,timeout=5)
    except subprocess.TimeoutExpired as e:
        pass

    # insert the solution into the original image
    f = fits.open(imagename, mode='update')
    if os.path.exists(basename + '.wcs'):

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
        newhdr = fits.getheader(basename + '.wcs')
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
        # save the changes
        f.flush()
        f.close()
        success = True
        if logger != None:
            logger.info("WCS Solution succeeded")
    else:
        try:
            f[0].header['WCSSOLVE'] = 'False'
            wcs_hdr_dict = {'WCSSOLVE': 'False'}
            success = False
            if logger != None:
                logger.info("WCS Solution failed")
        except Exception as e:
            print(e)


    try:
        # clean up extra files
        extstodelete = ['-indx.png','-indx.xyls','-ngc.png','-objs.png','.axy',
                        '.corr','.match','.new','.rdls','.solved','.wcs']
        for ext in extstodelete:
            if os.path.exists(basename + ext):
                os.remove(basename + ext)

        if logger != None:
            logger.info("Done in " + str((datetime.datetime.utcnow()-t0).total_seconds()) + " seconds")
    except Exception as e:
        print(e)
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
    

    
