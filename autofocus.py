import numpy as np

def autofocus(telescope, camera, maxfocus=0.0, minfocus=-3000.0, nsteps=6, exptime=5.0, logger=None):

    stepsize = (maxfocus-minfocus)/(nsteps-1)
    focpos = minfocus + stepsize*np.nsteps
    fwhm = np.array(nsteps)
    nstars = np.array(nsteps)
    startfocus = telescope.read_focuser_position()
    
    for i in range(nsteps):
        
        # move focuser
        if logger != None: logger.info('Moving focus to ' + str(focpos[i]))
        telescope.move_focus_and_check(focpos[i])

        # take exposure           
        if logger != None: logger.info('Taking ' + str(exptime) + ' second exposure')
        camera.take_image(exptime)

        # save image
        filename = path + 'autofocus.' + str(i).zfill(4) + '.fits'
        camera.save_image(filename)
        
        # analyze image to get average spot size
        if logger != None: logger.info('Analyzing image (' + filename + ')')
        fwhm[i] = 0.0
        nstars[i] = 1
        if logger != None: logger.info('Detected ' + str(nstars[i]) +\
                                       ' stars, with an average of ' +\
                                       str(fwhm[i]) + '" FWHM')


    bestfound = min(fhwm)

        
    good = where(np.finite(fwhm))
    if len(good) == 0:
        if logger != None: logger.error('No good focus points. Returning to starting value')
        setfocus = startfocus      
    if len(good) < 3:
        if logger != None: logger.error('Not enough points (' + str(len(good)) + ') to fit a quadratic; using minimum found')
        setfocus = bestfound
    else:
        # now fit the spot sizes to find the best focus
        focpos = focpos[good]
        fwhm = fwhm[good]
        
        coeffs = np.polyfit(focpos, fwhm, 2)
#        fitfwhm = coeffs[0]*focpos**2 + coeffs[1]*focpos + coeffs[2]

        # solve for the minimum of the quadratic
        bestfocus = -coeffs[1]/(2.0*coeffs[0]) 
        bestfwhm = coeffs[0]*bestfocus**2 + coeffs[1]*bestfocus + coeffs[2]
        
        if bestfocus > maxfocus:
            # best fit focus is beyond the maximum range -- don't extrapolate
            if logger != None: logger.error('Best-fit focus (' + str(bestfocus) +\
                                            ') exceeds maximum range (' + str(maxfocus) +\
                                            '; setting focus to the minimum found')
            setfocus = bestfound
        elif bestfocus < minfocus:
            # best fit focus is beyond the minimum range -- don't extrapolate
            if logger != None: logger.error('Best-fit focus (' + str(bestfocus) +\
                                            ') exceeds minimum range (' + str(minfocus) +\
                                            '); setting focus to the minimum found')
            setfocus = bestfound
        elif coeffs[0] < 0.0:
            # best fit focus is clearly wrong
            if logger != None: logger.error('Autofocus fit an upside down quadratic; '+\
                                            'setting focus to the minimum found')
            setfocus = bestfound
        else:
            # autofocus seems to have worked well
            if logger != None: logger.info('Best-fit focus is ' + str(bestfhwm) + '" at ' + str(bestfocus))
            setfocus = bestfocus

    if logger != None: logger.info('Moving focuser to ' + str(setfocus))        
    telescope.move_focus_and_check(setfocus)

if __name__ == 'main':

    base_directory = '/home/observer/tres-guider/'
    telescope = Telescope(base_directory, 'telescope.ini')
    camera = imager(base_directory, 'zyla.ini')

    ipdb.set_trace()
    
    autofocus(telescope,camera)
    
    
        
            
        
