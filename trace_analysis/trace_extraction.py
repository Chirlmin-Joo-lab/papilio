import sys

import numpy as np
import xarray as xr

# def make_gaussian(size, fwhm = 3, center=None):
#     # From https://stackoverflow.com/questions/7687679/how-to-generate-2d-gaussian-with-python
#     """ Make a square gaussian kernel.
#
#     size is the length of a side of the square
#     fwhm is full-width-half-maximum, which
#     can be thought of as an effective radius.
#     """
#
#     x = np.arange(0, size, 1, float)
#     y = x[:,np.newaxis]
#
#     if center is None:
#         x0 = y0 = size // 2
#     else:
#         x0 = center[0]
#         y0 = center[1]
#
#     return np.exp(-4*np.log(2) * ((x-x0)**2 + (y-y0)**2) / fwhm**2)


def make_gaussian_mask_old(size, center=None, offset=(0, 0), sigma=1.291):
    # TODO: Explain calculation in docstring
    # It is to keep the photon number the same after applying the mask.
    # If there is a PSF of N photons, which is nothing but a 2D Gauss function with given sigma and amplitude,
    # the sum of the pixel is N. The idea is that the pixel sum should be the same after applying the mask.
    # The normalization factor is calculated to compensate the amplitude of 2D Gaussian after applying the mask.
    # The normalization factor should be different for different PSF size (i.e. different magnification or setup).
    # So N = sum(mask * (psf_single_photon*N)), and so sum(mask*psf_single_photon)
    # Both the mask and the psf are 2d Gaussians

    x = np.arange(0, size, 1, float)
    y = x[:, np.newaxis]

    if center is None: center = [size // 2, size //2]
    #
    # mask_IDL = 2.0 * np.exp(- 0.3 * ((x - center[0] - offset[0]) ** 2 + (y - center[0] - offset[1]) ** 2))
    mask = np.exp(-((x - center[0] - offset[0]) ** 2 + (y - center[0] - offset[1]) ** 2) / sigma**2 / 2)
    psf_single_photon = mask/np.sum(mask)
    norm_factor = np.sum(np.multiply(mask, psf_single_photon))
    mask = np.divide(mask, norm_factor)

    ### SHK to del. for debug
    # print(np.sum(np.multiply(mask, psf_single_photon)))
    # import matplotlib.pyplot as plt
    # from mpl_toolkits.mplot3d import Axes3D
    #
    # fig = plt.figure(1101)
    # fig.clf()
    # ax = plt.axes(projection='3d')
    # ax.plot_surface(x, y, mask_IDL)
    # fig = plt.figure(1102)
    # ax = plt.axes(projection='3d')
    # ax.plot_surface(x, y, mask)
    # xx, yy = np.meshgrid(x,y)
    # ax.scatter(xx, yy, mask_IDL, c='k', depthshade=False, alpha=1, s=30)
    # plt.show()
    # fig = plt.figure(1103)
    # ax = plt.axes(projection='3d')
    # ax.plot_surface(x, y, np.subtract(mask_IDL, mask))
    # plt.show()
    ### END of SHK del

    return mask

def make_gaussian_mask(size, offsets, sigma=1.291):
    # TODO: Explain calculation in docstring
    # It is to keep the photon number the same after applying the mask.
    # If there is a PSF of N photons, which is nothing but a 2D Gauss function with given sigma and amplitude,
    # the sum of the pixel is N. The idea is that the pixel sum should be the same after applying the mask.
    # The normalization factor is calculated to compensate the amplitude of 2D Gaussian after applying the mask.
    # The normalization factor should be different for different PSF size (i.e. different magnification or setup).
    # So N = sum(mask * (psf_single_photon*N)), and so sum(mask*psf_single_photon)
    # Both the mask and the psf are 2d Gaussians
    import xarray as xr
    roi = xr.DataArray(np.mgrid[0:size,0:size]-size//2, dims=('dimension','y','x'), coords={'dimension': ['y', 'x']})
    masks = np.exp(-((roi - offsets) ** 2).sum('dimension') / sigma**2 / 2).transpose('molecule','channel','y','x')
    psfs_single_photon = masks/masks.sum(dim=('x', 'y'))
    norm_factors = (masks*psfs_single_photon).sum(dim=('x','y'))
    masks = masks/norm_factors
    return masks

def extract_trace_values_from_image_old(image, coordinates, background, twoD_gaussians):  # extract traces
    coordinates = np.atleast_2d(coordinates)

    # Probably indeed better to get this outside of the function, so that it is not redefined every time.
    half_size_Gaussian = len(twoD_gaussians[0]) // 2

    # This should likely be put on a central place in selection of locations
    # coordinates = coordinates[self.is_within_margin(coordinates, edge = None, margin = half_size_Gaussian + 1)]

    coordinates = np.floor(coordinates).astype(int)

    trace_values = np.zeros(len(coordinates))

    for i, coordinate in enumerate(coordinates):
        # First crop around spot, then do multiplication
        intensities = image[(coordinate[1] - half_size_Gaussian):(coordinate[1] + half_size_Gaussian + 1),
                      (coordinate[0] - half_size_Gaussian):(coordinate[0] + half_size_Gaussian + 1)
                      ]

        intensities = intensities - background[i]

        weighted_intensities = intensities * twoD_gaussians[i]
        trace_values[i] = np.sum(weighted_intensities)
        #trace_values[i]=np.sum(intensities) # MD testing
    return trace_values


def extract_trace_values_from_image(image, oneD_indices, background, twoD_gaussians):  # extract traces
    full_size_gaussian = twoD_gaussians.shape[-1]

    intensities = image.take(oneD_indices).reshape(-1, full_size_gaussian, full_size_gaussian)

    intensities = intensities - background[:,np.newaxis,np.newaxis]

    weighted_intensities = intensities * twoD_gaussians
    trace_values = weighted_intensities.sum(axis=(1,2))

    return trace_values

def extract_traces_old(movie, coordinates, background=None, channel='all', mask_size=1.291, neighbourhood_size=11):
    # return donor and acceptor for the full data set
    #     root, name = os.path.split(self.filepath)
    #     traces_fn=os.path.join(root,name[:-4]+'-P.traces')

    # if os.path.isfile(traces_fn):
    # # load if traces file already exist
    #      with open(traces_fn, 'r') as infile:
    #          Nframes = np.fromfile(infile, dtype = np.int32, count = 1).item()
    #          Ntraces = np.fromfile(infile, dtype = np.int16, count = 1).item()
    #          rawData = np.fromfile(infile, dtype = np.int16, count = self.number_of_channels*Nframes * Ntraces)
    #      orderedData = np.reshape(rawData.ravel(), (self.number_of_channels, Ntraces//self.number_of_channels, Nframes), order = 'F')
    #      donor=orderedData[0,:,:]
    #      acceptor=orderedData[1,:,:]
    #      donor=np.transpose(donor)
    #      acceptor=np.transpose(acceptor)
    # else:

    # go through all images, extract donor and acceptor signal

    # This should likely be put on a central place in selection of locations
    # coordinates = coordinates[self.is_within_margin(coordinates, edge = None, margin = self.gauss_width // 2 + 1)]

    # donor=np.zeros(( self.number_of_frames,self.pts_number))
    # acceptor=np.zeros((self.number_of_frames,self.pts_number))
    with movie:
        movie.read_header()
        traces = np.zeros((len(coordinates), movie.number_of_frames))

        if background is None:
            background = np.zeros(len(coordinates))

        # t0 = time.time()

        #twoD_gaussian = make_gaussian(gauss_width, fwhm=3, center=(gauss_width // 2, gauss_width // 2))

        offsets = coordinates % 1
        twoD_gaussians = [make_gaussian_mask_old(size=neighbourhood_size, offset=offsets[i], sigma=mask_size) for i in range(len(coordinates))]

        for frame_number in range(movie.number_of_frames):  # self.number_of_frames also works for pm, len(self.movie_file_object.filelist) not
            # print(frame_number)
            if frame_number % 13 == 0:
                sys.stdout.write(f'\r   Frame {frame_number} of {movie.number_of_frames}')

            image = movie.read_frame(frame_number)
            image = movie.get_channel(image, channel)

            trace_values_in_frame = extract_trace_values_from_image_old(image, coordinates, background, twoD_gaussians)

            traces[:,frame_number] = trace_values_in_frame  # will multiply with gaussian, spot location is not drift compensated
        sys.stdout.write(f'\r   Frame {frame_number+1} of {movie.number_of_frames}\n')
        # t1=time.time()
        # elapsed_time=t1-t0; print(elapsed_time)

        # root, name = os.path.split(self.filepath)

        # if os.path.isfile(trace_fn):

    return traces


def extract_traces(movie, coordinates, background=None, channel='all', mask_size=1.291, neighbourhood_size=11):
    # go through all images, extract donor and acceptor signal

    # This should likely be put on a central place in selection of locations
    # coordinates = coordinates[self.is_within_margin(coordinates, edge = None, margin = self.gauss_width // 2 + 1)]

    # donor=np.zeros(( self.number_of_frames,self.pts_number))
    # acceptor=np.zeros((self.number_of_frames,self.pts_number))
    with movie:
        movie.read_header()
        traces = np.zeros((len(coordinates), movie.number_of_frames))

        if background is None:
            background = np.zeros(len(coordinates))

        # t0 = time.time()

        #twoD_gaussian = make_gaussian(gauss_width, fwhm=3, center=(gauss_width // 2, gauss_width // 2))

        offsets = coordinates % 1
        twoD_gaussians = np.stack([make_gaussian_mask_old(size=neighbourhood_size, offset=offsets[i], sigma=mask_size) for i in range(len(coordinates))])

        half_size_gaussian = len(twoD_gaussians[0]) // 2
        full_size_gaussian = half_size_gaussian * 2 + 1

        # This should likely be put on a central place in selection of locations
        # coordinates = coordinates[self.is_within_margin(coordinates, edge = None, margin = half_size_Gaussian + 1)]

        coordinates = np.atleast_2d(coordinates)
        coordinates = np.floor(coordinates).astype(int)

        # im = np.arange(25).reshape(5, 5)
        # coordinates = np.array([[1, 2], [2, 3]])

        x_indices = (coordinates[:, [0]] - half_size_gaussian) + np.atleast_2d(np.arange(0, full_size_gaussian))
        y_indices = (coordinates[:, [1]] - half_size_gaussian) + np.atleast_2d(np.arange(0, full_size_gaussian))

        y_indices = y_indices[:, :, np.newaxis].repeat(full_size_gaussian, axis=2)
        x_indices = x_indices[:, np.newaxis, :].repeat(full_size_gaussian, axis=1)

        oneD_indices = (y_indices * movie.width + x_indices).reshape(-1, full_size_gaussian ** 2)

        for frame_number in range(movie.number_of_frames):  # self.number_of_frames also works for pm, len(self.movie_file_object.filelist) not
            # print(frame_number)
            if frame_number % 13 == 0:
                sys.stdout.write(f'\r   Frame {frame_number} of {movie.number_of_frames}')

            image = movie.read_frame(frame_number)
            image = movie.get_channel(image, channel)

            trace_values_in_frame = extract_trace_values_from_image(image, oneD_indices, background, twoD_gaussians)

            traces[:,frame_number] = trace_values_in_frame  # will multiply with gaussian, spot location is not drift compensated
        sys.stdout.write(f'\r   Frame {frame_number+1} of {movie.number_of_frames}\n')
        # t1=time.time()
        # elapsed_time=t1-t0; print(elapsed_time)

        # root, name = os.path.split(self.filepath)

        # if os.path.isfile(trace_fn):

    return traces


from tqdm import tqdm
def extract_traces_final(movie, coordinates, background=None, mask_size=1.291, neighbourhood_size=11):
    # go through all images, extract donor and acceptor signal

    with movie:
        movie.read_header()

        intensity = xr.DataArray(np.empty((len(coordinates.molecule), len(coordinates.channel), movie.number_of_frames)),
                                 dims=['molecule', 'channel', 'frame'],
                                 coords=coordinates.drop('dimension').coords, name='intensity')

        # channel_offsets = xr.DataArray(np.vstack([channel.origin for channel in movie.channels]),
        #                                dims=('channel', 'dimension'),
        #                                coords={'channel': [channel.index for channel in movie.channels],
        #                                        'dimension': ['x', 'y']}) # TODO: Move to Movie
        # coordinates = coordinates - channel_offsets

        if background is None:
            background = xr.DataArray(dims=['molecule','channel'], coords={'molecule': coordinates.molecule, 'channel': coordinates.channel})

        offsets = coordinates % 1
        twoD_gaussians = make_gaussian_mask(size=neighbourhood_size, offsets=offsets, sigma=mask_size)

        coordinates_floored = (coordinates // 1).astype(int)

        roi_indices_general = xr.DataArray(np.mgrid[:neighbourhood_size, :neighbourhood_size] - neighbourhood_size // 2,
                                           dims=('dimension', 'y', 'x'),
                                           coords={'dimension': ['y', 'x']})#.transpose()

        roi_indices = coordinates_floored + roi_indices_general


        oneD_indices = (roi_indices.sel(dimension='y')*movie.width+roi_indices.sel(dimension='x')).stack(peak=('molecule','channel')).stack(i=('y','x'))
        for frame_number in tqdm(range(movie.number_of_frames), desc=movie.name, position=0, leave=True):  # self.number_of_frames also works for pm, len(self.movie_file_object.filelist) not
            # print(frame_number)
            # if frame_number % 13 == 0:
            #     sys.stdout.write(f'\r   Frame {frame_number} of {movie.number_of_frames}')

            image = movie.read_frame(frame_number)
            frame = xr.DataArray(image, dims=('y','x'))

            #intensity[:, :, frame_number] = extract_intensity_from_frame(frame, background, roi_indices, twoD_gaussians)
            intensity[:, :, frame_number] = extract_intensity_from_frame(frame, background, oneD_indices, twoD_gaussians)

        # sys.stdout.write(f'\r   Frame {frame_number+1} of {movie.number_of_frames}\n')

    return intensity

# def extract_intensity_from_frame(frame, background, roi_indices, twoD_gaussians):
#     intensities = frame.sel(x=roi_indices.sel(dimension='x'), y=roi_indices.sel(dimension='y'))
#     intensities = intensities - background
#     weighted_intensities = intensities * twoD_gaussians
#     intensity_in_frame = weighted_intensities.sum(dim=('x', 'y'))
#     return intensity_in_frame

# A ufunc is probably better here
# def extract_intensity_from_frame(frame, background, roi_indices, twoD_gaussians):
#     intensities = frame.values[roi_indices.values[:,:,1,:,:], roi_indices.values[:,:,0,:,:]]
#     intensities = intensities - background.values[:,:,None,None]
#     weighted_intensities = intensities * twoD_gaussians.values
#     intensity_in_frame = weighted_intensities.sum(axis=(2,3))
#     return intensity_in_frame

def extract_intensity_from_frame(frame, background, oneD_indices, twoD_gaussians):  # extract traces
    intensities = frame.values.take(oneD_indices.values).reshape(twoD_gaussians.shape)
    intensities = intensities - background.values[:,:,None,None]
    weighted_intensities = intensities * twoD_gaussians.values
    intensity_in_frame = weighted_intensities.sum(axis=(2,3))
    return intensity_in_frame



def extract_traces2(frames, coordinates, background=0, mask_size=1.291, neighbourhood_size=11):
    # go through all images, extract donor and acceptor signal

    # This should likely be put on a central place in selection of locations
    # coordinates = coordinates[self.is_within_margin(coordinates, edge = None, margin = self.gauss_width // 2 + 1)]

    # donor=np.zeros(( self.number_of_frames,self.pts_number))
    # acceptor=np.zeros((self.number_of_frames,self.pts_number))
    # movie.read_header()
    # frames = movie.read_frames()


    # traces = np.zeros((len(coordinates), movie.number_of_frames))

    # if background is None:
    #     background = np.zeros(len(coordinates)) # TODO: make xarray

    # t0 = time.time()

    #twoD_gaussian = make_gaussian(gauss_width, fwhm=3, center=(gauss_width // 2, gauss_width // 2))

    # coordinates = coordinates.stack(peaks=('molecule', 'channel')).T

    offsets = coordinates % 1
    twoD_gaussians = make_gaussian_mask(size=neighbourhood_size, offsets=offsets, sigma=mask_size)

    half_size_gaussian = neighbourhood_size // 2
    full_size_gaussian = neighbourhood_size

    # This should likely be put on a central place in selection of locations
    # coordinates = coordinates[self.is_within_margin(coordinates, edge = None, margin = half_size_Gaussian + 1)]

    # coordinates = np.atleast_2d(coordinates)
    coordinates_floored = (coordinates // 1).astype(int)
    # channel_offsets = xr.DataArray(np.vstack([channel.origin for channel in movie.channels]),
    #                                dims=('channel','dimension'),
    #                                coords={'channel': [channel.index for channel in movie.channels], 'dimension': ['x','y']})
    # coordinates_floored -= channel_offsets

    roi_indices_general = xr.DataArray(np.mgrid[:neighbourhood_size, :neighbourhood_size] - neighbourhood_size // 2,
                       dims=('dimension', 'y', 'x'),
                       coords={'dimension': ['x', 'y']}).transpose()

    roi_indices = coordinates_floored + roi_indices_general


    # frames.loc[roi_indices.sel(dimension='x'), roi_indices.sel(dimension='y')]
    intensities = frames.sel(x=roi_indices.sel(dimension='x'), y=roi_indices.sel(dimension='y'))

    intensities = intensities - background

    weighted_intensities = intensities * twoD_gaussians
    traces = weighted_intensities.sum(dim=('x','y'))

    return traces
