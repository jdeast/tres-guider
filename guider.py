from astropy.io import fits

class imager:

    def __init__(self, base_directory, config_file):
        pass
        
    def take_image(self, exptime):
        pass

    def save_image(self, image, filename, overwrite=False):
        hdu = fits.PrimaryHDU(image)
        hdulist = fits.HDUList([hdu])
        hdulist.writeto(filename, overwrite=overwrite)

    def set_roi(self,x1,y1,x2,y2):
        pass
    
    def calc_offsets(self):
        pass

