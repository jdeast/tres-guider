import datetime, time
import os
import logging
import subprocess
import ipdb

def setup_logger(path, logger_name):

    fmt = "%(asctime)s.%(msecs).03d [%(filename)s:%(lineno)s - %(funcName)s()] %(levelname)s: %(threadName)s: %(message)s"
    datefmt = "%Y-%m-%dT%H:%M:%S"

    # append a date string to the logger name so each file doesn't get too big
    datestr = datetime.datetime.utcnow().strftime('%Y%m%d')
    logname = path + logger_name + '_' + datestr + '.log'
    if not os.path.exists(path): os.mkdir(path)

    # set up logging to file
    logging.basicConfig(level=logging.DEBUG,
                        format=fmt,
                        datefmt=datefmt,
                        filename=logname,
                        filemode='a')

    # define a Handler which writes INFO messages or higher to sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter(fmt,datefmt=datefmt)
    formatter.converter = time.gmtime
    console.setFormatter(formatter)

    # add the handler to the root logger
    logging.getLogger('').addHandler(console)

    # return the logger
    logger = logging.getLogger(logger_name)
    return logger
    
    
def dateobs2jd(dateobs):
    t0 = datetime.datetime(2000,1,1)
    t0jd = 2451544.5
    ti = datetime.datetime.strptime(dateobs,"%Y-%m-%dT%H:%M:%S.%f")
    return t0jd + (ti-t0).total_seconds()/86400.0

def jd2datetime(jd):
    jd0 = 2451544.5
    t0 = datetime.datetime(2000,1,1)
    date = t0 + datetime.timedelta(days=jd-jd0)
    return date

def datetime2jd(date):
    jd0 = 2451544.5
    t0 = datetime.datetime(2000,1,1)
    jd = jd0 + (date - t0).total_seconds()/86400.0
    return jd

# converts a sexigesimal string to a float
# the string may be delimited by either spaces or colons
def ten(string):
    array = re.split(' |:',string)
    if "-" in array[0]:
        return float(array[0]) - float(array[1])/60.0 - float(array[2])/3600.0
    return float(array[0]) + float(array[1])/60.0 + float(array[2])/3600.0


''' 
sexpath - path where all the .sex, .param, etc. files are
'''
# run sextractor on an image
def sextract(datapath, imagefile, \
             sexfile='/usr/share/sextractor/default.sex', \
             paramfile=None, \
             convfile=None, \
             catfile=None):
    
    # This is the base command we be calling with sextractor.
    # We'll add on other parameters and arguments as they are specified
    sexcommand = 'sextractor ' + datapath+imagefile+ ' -c ' + sexfile

    # If a paramfile was specfied, then we will use that instead of the
    # default param file
    if paramfile != None:
        sexcommand+= ' -PARAMETERS_NAME ' + paramfile

    # Similar to above, but the convolution filter
    if convfile != None:
        sexcommand+= ' -FILTER_NAME ' + convfile

    # if catfile is specified, the output will go to that file
    # otherwise, replace ".fits" with ".cat" in the image filename
    if catfile == None:
        catfile = imagefile.split('.fits')[0] + '.cat'
        sexcommand += ' -CATALOG_NAME ' + datapath+catfile

    # sexcommand has all of its components split by
    # spaces which will allow .split to put in a list for subprocess.call
    subprocess.call(sexcommand.split())

    # return the catalog file name
    return datapath+catfile

# read a source extractor catalog into a python dictionary
def readsexcat(catname):

    data = {}
    if not os.path.exists(catname): return data
    with open(catname,'rb') as filep:
        header = []
        for line in filep:
            # header lines begin with # and are the 3rd item in the line
            line = line.decode('utf-8')
            if line.startswith('#'):
                header.append(line.split()[2])
                for h in header:
                    data[h] = []
            # older sextractor catalogs contain a few nuisance lines; ignore those
            elif not line.startswith('-----') and not line.startswith('Measuring') and \
                    not line.startswith('(M+D)') and not line.startswith('Objects:'):
                # assume all values are floats
                values = [ float(x) for x in line.split() ]
                for h,v in zip(header,values):
                    data[h].append(v)
    for key in data.keys():
        # try and convert to an np.array, and if not possible just pass
        # the try is in case for some reason a non-numerical entry is
        # encountered. may be a l
        try:
            data[key] = np.array(data[key])
        except:
            pass

    return data


