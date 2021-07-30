from astropy.io import fits as pyfits
import subprocess, os
import datetime
import centroid
import numpy as np
import ipdb
import csv

# use Gaia index files here:
# http://data.astrometry.net/5000/
# copied to /home/tres/gaia_index_files/
# configured in /usr/etc/astrometry.cfg

# native version of xylist2fits
# basename.xy is a two-column ascii file of XY positions sorted by brightness
# cmd = 'xylist2fits ' + basename '.xy ' + basename + '.xyls' 
def stars_to_xyls(stars, filename):

    basename = os.path.splitext(filename)[0]
    
    sorted = stars[:,2].argsort()
    x = stars[sorted[::-1],0]
    y = stars[sorted[::-1],1]   
#    np.savetxt(basename + '.xy', zip(x,y))

    with open(basename + '.xy', 'w') as f:
        writer = csv.writer(f,delimiter='\t')
        writer.writerow(['x','y'])
        writer.writerows(zip(x,y))

#    f = open(basename + '.xy', "w")
#    for i in range(len(x)):
#        f.write(str(x[i]) + ' ' + str(y[i]))
#        print(str(x[i]) + ' ' + str(y[i]))
#    f.close1

#    ipdb.set_trace()
    
    # convert ascii xy list to fits binary table
#    cmd = 'xylist2fits ' + basename + '.xy ' + basename + '.xyls' 
    cmd = 'text2fits ' + basename + '.xy ' + basename + '.xyls' 
    os.system(cmd)
    return
    
    # it must be possible to write my own pretty quickly...
    colx = pyfits.Column(name='x', format='10E', array=x)
    coly = pyfits.Column(name='y', format='10E', array=y)
    coldefs = pyfits.ColDefs([colx,coly])
    hdu = pyfits.BinTableHDU.from_columns([colx,coly])
    hdu.writeto(filename,overwrite=True)


def astrometry(imagename, rakey='RA', deckey='DEC',pixscalekey='PIXSCALE', pixscale=None, quadlimit=[0.45,0.55], radius=None, sextractor=False, verbose=False, use_sep=False):

    t0 = datetime.datetime.utcnow()    
    hdr = pyfits.getheader(imagename)

    basename = os.path.splitext(imagename)[0]

    if use_sep:
        # this doesn't actually work, but in principle would give us more flexibility and could be a significant improvement
        print("must use built-in source extraction")
        return
        xyfile = basename + '.xyls' 
        stars = centroid.get_stars_sep('',imagename)
        stars_to_xyls(stars, xyfile)
        filearg = xyfile
    else: filearg = imagename
        
    # This is the base command.
    # we're going to build it up according to the options specified
    cmd = 'solve-field'
        
    try:
        if pixscale == None: pixscale = float(hdr[pixscalekey])
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
    if quadlimit[0] != None: cmd += ' --quad-size-min ' + str(quadlimit[0])
    if quadlimit[1] != None: cmd += ' --quad-size-max ' + str(quadlimit[1])

    # need sextractor to be installed
    if sextractor: cmd += ' --use-sextractor' 
        
    # more options to optimize solving time
    cmd += ' --cpulimit 30' + \
           ' --no-verify' + \
           ' --crpix-center' + \
           ' --no-plots' + \
           ' --overwrite ' +\
           filearg
        
#           ' --no-fits2fits' + \


    #cmd = r'/usr/local/astrometry/bin/' + cmd + ' >/dev/null 2>&1'
    # assume solve-field is in the path; dump output

    # dump output if verbose not set
    if not verbose: cmd += ' >/dev/null 2>&1'
    #subprocess(cmd.split())
    print(cmd)
    ipdb.set_trace()
    os.system(cmd)
    
    # insert the solution into the original image
    f = pyfits.open(imagename, mode='update')
    if os.path.exists(basename + '.new'):

        # preserve original solution
        orighdr = pyfits.getheader(imagename)
        f[0].header['WCD1_1'] = float(f[0].header['CD1_1'])
        f[0].header['WCD1_2'] = float(f[0].header['CD1_2'])
        f[0].header['WCD2_1'] = float(f[0].header['CD2_1'])
        f[0].header['WCD2_2'] = float(f[0].header['CD2_2'])
        f[0].header['WCRVAL1'] = float(f[0].header['CRVAL1'])
        f[0].header['WCRVAL2'] = float(f[0].header['CRVAL2'])

        # copy the WCS solution to the file
        newhdr = pyfits.getheader(basename + '.new')
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
        success = True
    else:
        f[0].header['WCSSOLVE'] = 'False'
        success = False

    # save the changes
    f.flush()
    f.close()

    
#    # clean up extra files
#    extstodelete = ['-indx.png','-indx.xyls','-ngc.png','-objs.png','.axy',
#                    '.corr','.match','.new','.rdls','.solved','.wcs']
#    for ext in extstodelete:
#        if os.path.exists(basename + ext):
#            os.remove(basename + ext)

    if verbose: print("Done in " + str((datetime.datetime.utcnow()-t0).total_seconds()) + " seconds")
    return success
