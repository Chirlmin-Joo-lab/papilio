from pathlib import Path # For efficient path manipulation
import numpy as np #scientific computing with Python
import pandas as pd
import matplotlib.pyplot as plt #Provides a MATLAB-like plotting framework
import skimage.io as io
import skimage as ski
from trace_analysis.molecule import Molecule
from trace_analysis.image_adapt.sifx_file import SifxFile
from trace_analysis.image_adapt.pma_file import PmaFile
from trace_analysis.image_adapt.tif_file import TifFile
from trace_analysis.plotting import histogram
from trace_analysis.mapping.mapping import Mapping2
from trace_analysis.peak_finding import find_peaks
from trace_analysis.coordinate_optimization import coordinates_within_margin, coordinates_after_gaussian_fit, coordinates_without_intensity_at_radius
from trace_analysis.trace_extraction import extract_traces
from trace_analysis.coordinate_transformations import translate, transform # MD: we don't want to use this anymore I think, it is only linear
                                                                           # IS: We do! But we just need to make them usable with the nonlinear mapping

from trace_analysis.mapping.icp import nearest_neighbor_pair, scatter_coordinates, show_point_connections


class File:
    def __init__(self, relativeFilePath, experiment):
        relativeFilePath = Path(relativeFilePath)
        self.experiment = experiment

        self.relativePath = relativeFilePath.parent
        self.name = relativeFilePath.name
        self.extensions = list()

        self.molecules = list()

        self.exposure_time = 0.1  # Found from log file or should be inputted
        self.number_of_frames = 0
        self.log_details = None  # a string with the contents of the log file
        self.number_of_frames = None

        self.background = np.array([0, 0])

        self.isSelected = False
        self.is_mapping_file = False

        self.movie = None
        self.mapping = None
        self._average_image = None
        self._maximum_projection_image = None

        if self.experiment.import_all is True:
            self.findAndAddExtensions()


    def __repr__(self):
        return (f'{self.__class__.__name__}({self.relativePath.joinpath(self.name)})')

    @property
    def relativeFilePath(self):
        return self.relativePath.joinpath(self.name)

    @property
    def absoluteFilePath(self):
        return self.experiment.mainPath.joinpath(self.relativeFilePath)

    @property
    def number_of_molecules(self):
        return len(self.molecules)

    @number_of_molecules.setter
    def number_of_molecules(self, number_of_molecules):
        if not self.molecules:
            for molecule in range(0, number_of_molecules):
                self.addMolecule()
        elif number_of_molecules != self.number_of_molecules:
            raise ValueError('Requested number of molecules differs from existing number of molecules')

    @property
    def number_of_colours(self):
        return self.experiment.Ncolours

    @property
    def selectedMolecules(self):
        return [molecule for molecule in self.molecules if molecule.isSelected]

    @property
    def average_image(self):
        if self._average_image is None:
            self._average_image = self.movie.average_image
        return self._average_image
    
    @property
    def maximum_projection_image(self):
        if self._maximum_projection_image is None:
            self._maximum_projection_image = self.movie.maximum_projection_image
        return self._maximum_projection_image

    @property
    def coordinates(self):
        # if not self._pks_file:
        #     _pks_file = PksFile(self.absoluteFilePath.with_suffix('.pks'))

        #return np.concatenate([[molecule.coordinates[0, :] for molecule in self.molecules]])
        coordinates = [molecule.coordinates for molecule in self.molecules]
        if coordinates: return np.concatenate(coordinates)
        else: return None


    @coordinates.setter
    def coordinates(self, coordinates, number_of_colours = None):
        if number_of_colours is None:
            number_of_colours = self.number_of_colours
        self.number_of_molecules = np.shape(coordinates)[0]//number_of_colours

        for i, molecule in enumerate(self.molecules):
            molecule.coordinates = coordinates[(i * number_of_colours):((i + 1) * number_of_colours), :]

    def coordinates_from_channel(self, channel):
        # if not self._pks_file:
        #     _pks_file = PksFile(self.absoluteFilePath.with_suffix('.pks'))

        #return np.concatenate([[molecule.coordinates[0, :] for molecule in self.molecules]])
        if type(channel) is str:
            channel = {'d': 0, 'a': 1, 'g':0, 'r':1}[channel]

        return np.vstack([molecule.coordinates[channel] for molecule in self.molecules])

    @property
    def time(self):  # the time axis of the experiment, if not found in log it will be asked as input
        if self.exposure_time is None:
            self.exposure_time = float(input(f'Exposure time for {self.name}: '))
        return np.arange(0, self.number_of_frames)*self.exposure_time

    @property
    def traces(self):
        return np.dstack([molecule.intensity for molecule in self.molecules]).swapaxes(1, 2) # 3d array of traces
        # np.concatenate([molecule.intensity for molecule in self.molecules]) # 2d array of traces

    @traces.setter
    def traces(self, traces):
        for i, molecule in enumerate(self.molecules):
            molecule.intensity = traces[:, i, :] # 3d array of traces
            # molecule.intensity = traces[(i * self.number_of_colours):((i + 1) * self.number_of_colours), :] # 2d array of traces
        self.number_of_frames = traces.shape[2]

    def findAndAddExtensions(self):
        foundFiles = [file.name for file in self.experiment.mainPath.joinpath(self.relativePath).glob(self.name + '*')]
        foundExtensions = [file[len(self.name):] for file in foundFiles]

        # For the special case of a sifx file, which is located inside a folder
        if '' in foundExtensions: foundExtensions[foundExtensions.index('')] = '.sifx'

        newExtensions = [extension for extension in foundExtensions if extension not in self.extensions]
        # self.extensions = self.extensions + newExtensions
        for extension in newExtensions: self.importExtension(extension)

    def importExtension(self, extension):

        # print(f.relative_to(self.experiment.mainPath))

        # if extension not in self.extensions:
        #     self.extensions.append(extension)

        # print(extension)
        importFunctions = { '.sifx': self.import_sifx_file,
                            '.pma': self.import_pma_file,
                            '.tif': self.import_tif_file,
                            '_ave.tif': self.import_average_tif_file,
                            '_max.tif': self.import_maximum_projection_tif_file,
                            '.coeff': self.import_coeff_file,
                            '.map': self.import_map_file,
                            '.pks': self.import_pks_file,
                            '.traces': self.import_traces_file,
                            '.log' : self.import_log_file
                            }

        importFunctions.get(extension, self.noneFunction)()
        if extension in importFunctions.keys(): self.extensions.append(extension)

    def noneFunction(self):
        return

    def import_log_file(self):
        self.exposure_time = np.genfromtxt(f'{self.relativeFilePath}.log', max_rows=1)[2]
        self.log_details = open(f'{self.relativeFilePath}.log').readlines()
        self.log_details = ''.join(self.log_details)

    def import_sifx_file(self):
        imageFilePath = self.absoluteFilePath.joinpath('Spooled files.sifx')
        self.movie = SifxFile(imageFilePath)
        self.number_of_frames = self.movie.number_of_frames

    def import_pma_file(self):
        imageFilePath = self.absoluteFilePath.with_suffix('.pma')
        self.movie = PmaFile(imageFilePath)
        self.number_of_frames = self.movie.number_of_frames

    def import_tif_file(self):
        imageFilePath = self.absoluteFilePath.with_suffix('.tif')
        self.movie = TifFile(imageFilePath)
        self.number_of_frames = self.movie.number_of_frames

    def import_average_tif_file(self):
        averageTifFilePath = self.absoluteFilePath.with_name(self.name+'_ave.tif')
        self._average_image = io.imread(averageTifFilePath, as_gray=True)
        
    def import_maximum_projection_tif_file(self):
        maxTifFilePath = self.absoluteFilePath.with_name(self.name+'_max.tif')
        self._maximum_projection_image = io.imread(maxTifFilePath, as_gray=True)

    def import_coeff_file(self):
        if self.mapping is None: # the following only works for 'linear'transformation_type
            file_content=np.genfromtxt(str(self.relativeFilePath) + '.coeff')
            if len(file_content)==12:  [coefficients, coefficients_inverse] = np.split(file_content,2)
            elif len(file_content)==6: coefficients = file_content
            else: raise TypeError('Error in importing coeff file, wrong number of lines')
            
            self.mapping = Mapping2(transformation_type='linear')
            self.mapping.transformation = np.zeros((3,3))
            self.mapping.transformation[2,2] = 1
            self.mapping.transformation[[0,0,0,1,1,1],[2,0,1,2,0,1]] = coefficients
            
            if len(file_content)==6:
                self.mapping.transformation_inverse=np.linalg.inv(self.mapping.transformation)
            else:
                self.mapping.transformation_inverse = np.zeros((3,3))
                self.mapping.transformation_inverse[2,2] = 1
                self.mapping.transformation_inverse[[0,0,0,1,1,1],[2,0,1,2,0,1]] = coefficients_inverse
                    
            self.mapping.file = self

    def export_coeff_file(self):
        if self.mapping.transformation_type == 'linear':
            coeff_filepath = self.absoluteFilePath.with_suffix('.coeff')
            coefficients = self.mapping.transformation[[0, 0, 0, 1, 1, 1], [2, 0, 1, 2, 0, 1]]
           # np.savetxt(coeff_filepath, coefficients, fmt='%13.6g') # Same format used as in IDL code
            coefficients_inverse = self.mapping.transformation_inverse[[0, 0, 0, 1, 1, 1], [2, 0, 1, 2, 0, 1]]
            np.savetxt(coeff_filepath,  np.concatenate((coefficients,coefficients_inverse)), fmt='%13.6g') # Same format used as in IDL code
        else:
            raise TypeError('Mapping is not of type linear')

    def import_map_file(self):
        #coefficients = np.genfromtxt(self.relativeFilePath.with_suffix('.map'))
        file_content=np.genfromtxt(self.relativeFilePath.with_suffix('.map'))
        if len(file_content) == 64:
            [coefficients, coefficients_inverse] = np.split(file_content, 2)
        elif len(file_content) == 32:
            coefficients = file_content
        else:
            raise TypeError('Error in import map file, incorrect number of lines')
        
        degree = int(np.sqrt(len(coefficients) // 2) - 1)
        P = coefficients[:len(coefficients) // 2].reshape((degree + 1, degree + 1))
        Q = coefficients[len(coefficients) // 2 : len(coefficients)].reshape((degree + 1, degree + 1))

        self.mapping = Mapping2(transformation_type='nonlinear')
        self.mapping.transformation = (P,Q) #{'P': P, 'Q': Q}
        #self.mapping.file = self
        if len(file_content)==64:
            degree = int(np.sqrt(len(coefficients_inverse) // 2) - 1)
            Pi = coefficients_inverse[:len(coefficients_inverse) // 2].reshape((degree + 1, degree + 1))
            Qi = coefficients_inverse[len(coefficients_inverse) // 2 : len(coefficients_inverse)].reshape((degree + 1, degree + 1))
        else :
            image_height = self._average_image.shape[0]
            # Can't we make this independent of the image?
            # (Can't we just take the whole image here [IS 26-03-2020])
            grid_coordinates = np.array([(a,b) for a in range(20, image_height/2-20, 10) for b in range(20, image_height-20, 10)])
            ##still the question whether range a & B should be swapped
            # I think so, but does the precies  [IS
            from trace_analysis.image_adapt.polywarp import polywarp, polywarp_apply
            transformed_grid_coordinates = polywarp_apply(P, Q, grid_coordinates)
            plt.scatter(transformed_grid_coordinates[:,0],transformed_grid_coordinates[:,1],'.')
            Pi, Qi = polywarp(transformed_grid_coordinates[:,0],transformed_grid_coordinates[:,1],grid_coordinates[:,0],grid_coordinates[:,1])

       # self.mapping = Mapping2(transformation_type='nonlinear')
        self.mapping.transformation_inverse = (Pi, Qi) # {'P': Pi, 'Q': Qi}
        self.mapping.file = self
        
    def export_map_file(self):
        #saving kx,ky, still need to see how to read it in again
        map_filepath = self.absoluteFilePath.with_suffix('.map')
        PandQ = self.mapping.transformation
        coefficients = np.concatenate((PandQ[0].flatten(),PandQ[1].flatten()),axis=None)
        #np.savetxt(map_filepath, coefficients, fmt='%13.6g') # Same format used as in IDL code
        PiandQi = self.mapping.transformation_inverse
        coefficients_inverse = np.concatenate((PiandQi[0].flatten(),PiandQi[1].flatten()),axis=None)
        np.savetxt(map_filepath, np.concatenate((coefficients,coefficients_inverse)), fmt='%13.6g') # Same format used as in IDL code

    def import_pks_file(self):
        # Background value stored in pks file is not imported yet
        coordinates = np.genfromtxt(str(self.relativeFilePath) + '.pks')
        coordinates = np.atleast_2d(coordinates)[:,1:3]

        self.coordinates = coordinates

    def find_coordinates(self, configuration = None):
        # Refresh configuration
        if not configuration:  self.experiment.import_config_file() # is this usefull, look at next line of code

        if configuration is None: configuration = self.experiment.configuration['find_coordinates'] 
        channel = configuration['channel']
        configuration['image']
        if configuration['image'] == 'average_image':
            full_image = self.average_image
        elif configuration['image'] == 'maximum_image':
            full_image = self.maximum_projection_image
       # plt.figure(30), plt.subplot(1,2,1), plt.imshow(self.average_image)
       # plt.figure(30), plt.subplot(1,2,2), plt.imshow(self.maximum_projection_image)

        if channel in ['d','a']:
            image = self.movie.get_channel(image=full_image, channel=channel)
        elif channel in ['da']:
            donor_image = self.movie.get_channel(image=full_image, channel='d')
            #acceptor_image = self.movie.get_channel(image=full_image, channel='a')

            #image_transformation = translate([-self.movie.width / 2, 0]) @ self.mapping.transformation #$$
            #acceptor_image_transformed = ski.transform.warp(acceptor_image, image_transformation, preserve_range=True) #$$
            #MD: ski.transfrom.PolynomialTransform
            tform = ski.transform.PolynomialTransform()
            tform.estimate(source[source_indices, :2],destination[destination_indices, :2],order=4)
            acceptor_image_transformed = ski.transform.warp(full_image, tform,preserve_range=True)
            image = (donor_image + acceptor_image_transformed) / 2

            plt.imshow(np.stack([donor_image.astype('uint8'),
                                 acceptor_image_transformed.astype('uint8'),
                                 np.zeros((self.movie.height, self.movie.width//2)).astype('uint8')], axis=-1))



        coordinates = find_peaks(image=image, **configuration['peak_finding'])

        coordinate_optimization_functions = \
            {'coordinates_within_margin': coordinates_within_margin,
             'coordinates_after_gaussian_fit': coordinates_after_gaussian_fit,
             'coordinates_without_intensity_at_radius': coordinates_without_intensity_at_radius}

        for f, kwargs in configuration['coordinate_optimization'].items():
            coordinates = coordinate_optimization_functions[f](coordinates, image, **kwargs)


        if channel == 'a':
            coordinates = transform(coordinates, translation=[self.movie.width//2,0]) #$$
            # MD:here a simple transform is necessary, to move from found points in left channel to right side
            # why: because you detect in a cropped image size 1024x2048, 

        if self.number_of_colours == 2:
            if channel in ['d','da']:
                donor_coordinates=coordinates
                acceptor_coordinates = self.mapping.transform_coordinates(donor_coordinates, direction='source2destination')
                print(np.shape(acceptor_coordinates), np.shape(coordinates))
            if channel == 'a':
                acceptor_coordinates=coordinates
                donor_coordinates = self.mapping.transform_coordinates(acceptor_coordinates, direction='destination2source')
            coordinates = np.hstack([donor_coordinates,acceptor_coordinates]).reshape((-1,2))
            
        self.molecules = [] # Should we put this here?
        self.coordinates = coordinates
        self.export_pks_file()
        
        plt.figure(44), plt.imshow(full_image)
        scatter_coordinates(donor_coordinates,marker='+', c='w')
        scatter_coordinates(acceptor_coordinates,marker='x', c='w')
        if channel=='a': plt.title('#acceptor='+str(len(acceptor_coordinates)))
        else:            plt.title('#donor='+str(len(donor_coordinates)))
                                       
    def export_pks_file(self):
        pks_filepath = self.absoluteFilePath.with_suffix('.pks')
        with pks_filepath.open('w') as pks_file:
            for i, coordinate in enumerate(self.coordinates):
                # outfile.write(' {0:4.0f} {1:4.4f} {2:4.4f} {3:4.4f} {4:4.4f} \n'.format(i, coordinate[0], coordinate[1], 0, 0, width4=4, width6=6))
                pks_file.write('{0:4.0f} {1:4.4f} {2:4.4f} \n'.format(i + 1, coordinate[0], coordinate[1]))

    def import_traces_file(self):
        traces_filepath = self.absoluteFilePath.with_suffix('.traces')
        with traces_filepath.open('r') as traces_file:
            self.number_of_frames = np.fromfile(traces_file, dtype=np.int32, count=1).item()
            number_of_traces = np.fromfile(traces_file, dtype=np.int16, count=1).item()
            self.number_of_molecules = number_of_traces // self.number_of_colours
            rawData = np.fromfile(traces_file, dtype=np.int16, count=self.number_of_frames * number_of_traces)
        self.traces = np.reshape(rawData.ravel(), (self.number_of_colours, self.number_of_molecules, self.number_of_frames), order='F')  # 3d array of traces
        #self.traces = np.reshape(rawData.ravel(), (self.number_of_colours * self.number_of_molecules, self.number_of_frames), order='F') # 2d array of traces

    def extract_traces(self):
        # Refresh configuration
        self.experiment.import_config_file()

        if self.movie is None: raise FileNotFoundError('No movie file was found')
        self.traces = extract_traces(self.movie, self.coordinates, channel='all', gauss_width = 11)
        self.export_traces_file()
        if '.traces' not in self.extensions: self.extensions.append('.traces')

    def export_traces_file(self):
        traces_filepath = self.absoluteFilePath.with_suffix('.traces')
        with traces_filepath.open('w') as traces_file:
            np.array([self.traces.shape[2]], dtype=np.int32).tofile(traces_file)
            np.array([self.traces.shape[0]*self.traces.shape[1]], dtype=np.int16).tofile(traces_file)
            # time_tr = np.zeros((self.number_of_frames, 2 * self.pts_number))
            # Ncolours=2
            # for jj in range(2*self.pts_number//Ncolours):
            #     time_tr[:,jj*2] = donor[:,jj]
            #     time_tr[:,jj*2+1]=  acceptor[:,jj]
            np.array(self.traces.T, dtype=np.int16).tofile(traces_file)

    #    def importSimFile(self):
    #        file = open(str(self.relativeFilePath) + '.sim', 'rb')
    #        self.data = pickle.load(file)
    #        red, green  = self.data['red'], self.data['green']
    #        Ntraces = red.shape[0]
    #        self.Nframes = red.shape[1]
    #
    #        if not self.molecules:
    #            for molecule in range(0, Ntraces):
    #                self.addMolecule()
    #
    #        for i, molecule in enumerate(self.molecules):
    #            molecule.intensity = np.vstack((green[i], red[i]))
    #        file.close()

    def addMolecule(self):
        index = len(self.molecules) # this is the molecule number
        self.molecules.append(Molecule(self))
        self.molecules[-1].index = index

    def histogram(self, axis = None, bins = 100, parameter = 'E', molecule_averaging = False, makeFit=False, export=False, **kwargs):
        histogram(self.molecules, axis=axis, bins=bins, parameter=parameter, molecule_averaging=molecule_averaging, makeFit=makeFit, collection_name=self, **kwargs)
        if export: plt.savefig(self.absoluteFilePath.with_name(f'{self.name}_{parameter}_histogram').with_suffix('.png'))

    def importExcel(self, filename=None):
        if filename is None:
            filename = self.name+'_steps_data.xlsx'
        try:
            steps_data = pd.read_excel(filename, index_col=[0,1],
                                            dtype={'kon':np.str})       # reads from the 1st excel sheet of the file
        except FileNotFoundError:
            print(f'No saved analysis for {self.name}')
            return
        molecules = steps_data.index.unique(0)
        indices = [int(m.split()[-1]) for m in molecules]
        for mol in self.molecules:
            if mol.index not in indices:
                continue
            mol.steps = steps_data.loc[f'mol {mol.index}']
            if 'kon' in mol.steps.columns:
                k = [int(i) for i in mol.steps.kon[0]]
                mol.kon_boolean = np.array(k).astype(bool).reshape((3,3))
        return steps_data

    def savetoExcel(self, filename=None, save=True):
        if filename is None:
            filename = self.name+'_steps_data.xlsx'
        # Concatenate all steps dataframes that are not None
        mol_data = [mol.steps for mol in self.molecules if mol.steps is not None]
        if not mol_data:
            print(f'no data to save for {self.name}')
            return
        keys = [f'mol {mol.index}' for mol in self.molecules if mol.steps is not None]
        steps_data = pd.concat(mol_data, keys=keys, sort=False)
        if save:
            print("data saved in: " + filename)
            writer = pd.ExcelWriter(filename)
            steps_data.to_excel(writer, self.name)
            writer.save()
        return steps_data

    def autoThreshold(self, trace_name, threshold=100, max_steps=20,
                      only_selected=False, kon_str='000000000'):
        nam = trace_name
        for mol in self.molecules:

            trace = mol.I(0)*int((nam == 'green')) + \
                    mol.I(1)*int((nam == 'red')) +\
                     mol.E()*int((nam == 'E'))  # Here no offset corrections are applied yet

            d = mol.find_steps(trace)
            frames = d['frames']
            times = frames*self.exposure_time
            times = np.sort(times)
            mol.steps = pd.DataFrame({'time': times, 'trace': nam,
                                  'state': 1, 'method': 'thres',
                                'thres': threshold, 'kon': kon_str})
        filename = self.name+'_steps_data.xlsx'
        data = self.savetoExcel(filename)
        return data

    def select(self, figure=None):
        plt.ion()
        for index, molecule in enumerate(self.molecules):
            molecule.plot(figure=figure)
            plt.title('Molecule ' + str(index), y=-0.01)
            plt.show()
            plt.pause(0.001)
            print('Molecule ' + str(index))
            input("Press enter to continue")

    def perform_mapping(self, configuration = None):
        # Refresh configuration
        if not configuration: self.experiment.import_config_file()

        image = self.average_image
        if configuration is None: configuration = self.experiment.configuration['mapping']
        
        transformation_type = configuration['transformation_type']
        print(transformation_type)

        donor_image = self.movie.get_channel(image=image, channel='d')
        acceptor_image = self.movie.get_channel(image=image, channel='a')
        donor_coordinates = find_peaks(image=donor_image, **configuration['peak_finding']['donor'])
        if donor_coordinates.size == 0: #should throw a error message to warm no acceptor molecules found
            print('No donor molecules found')
        acceptor_coordinates = find_peaks(image=acceptor_image, **configuration['peak_finding']['acceptor'])
        if acceptor_coordinates.size == 0: #should throw a error message to warm no acceptor molecules found
            print('No acceptor molecules found')
        acceptor_coordinates = transform(acceptor_coordinates, translation=[image.shape[0]//2, 0])
        coordinates = np.append(donor_coordinates, acceptor_coordinates, axis=0)

        coordinate_optimization_functions = \
            {'coordinates_within_margin': coordinates_within_margin,
             'coordinates_after_gaussian_fit': coordinates_after_gaussian_fit,
             'coordinates_without_intensity_at_radius': coordinates_without_intensity_at_radius}

        for f, kwargs in configuration['coordinate_optimization'].items():
            coordinates = coordinate_optimization_functions[f](coordinates, image, **kwargs)
            
 #       coordinates = coordinates_after_gaussian_fit(coordinates, image)
#        coordinates = coordinates_without_intensity_at_radius(coordinates, image,
#                                                              **configuration['coordinate_optimization']['coordinates_without_intensity_at_radius'])
#                                                              # radius=4,
#                                                              # cutoff=np.median(image),
#                                                              # fraction_of_peak_max=0.35) # was 0.25 in IDL code
#
        margin = configuration['coordinate_optimization']['coordinates_within_margin']['margin']
        donor_coordinates = coordinates_within_margin(coordinates, bounds=self.movie.channel_boundaries('d'), margin=margin)
        acceptor_coordinates = coordinates_within_margin(coordinates, bounds=self.movie.channel_boundaries('a'), margin=margin)
        if (len(donor_coordinates)<16) | (len(acceptor_coordinates)<16):
            print('Error in mapping, need at least 16 points in acceptor and donor channel') # should we iterate config settings
        self.mapping = Mapping2(source=donor_coordinates,
                                destination=acceptor_coordinates,
                                transformation_type=transformation_type,
                                initial_translation=translate([image.shape[0]//2,0]))
        self.mapping.file = self
        self.is_mapping_file = True

        if self.mapping.transformation_type == 'linear':
            self.export_coeff_file()
        elif self.mapping.transformation_type == 'nonlinear':
            self.export_map_file()

    def copy_coordinates_to_selected_files(self):
        for file in self.experiment.selectedFiles:
            if file is not self:
                file.coordinates = self.coordinates
                file.export_pks_file()

    def use_mapping_for_all_files(self):
        self.is_mapping_file = True
        #mapping = self.movie.use_for_mapping()
        for file in self.experiment.files:
            if file is not self:
                file.mapping = self.mapping
                file.is_mapping_file = False
                
    def show_image(self, image_type='default', mode='2d', figure=None):
        # Refresh configuration
        if image_type is 'default':
            self.experiment.import_config_file()
            image_type = self.experiment.configuration['find_coordinates']['image']
        
        if figure is None: figure = plt.figure() # Or possibly e.g. plt.figure('Movie')
        axis = figure.gca()
        
        # Choose method to plot 
        if image_type == 'average_image':
            image = self.average_image
            axis.set_title('Average image')
        elif image_type == 'maximum_image':
            image = self.maximum_projection_image
            axis.set_title('Maximum projection')
            
        if mode == '2d':
            vmax = np.percentile(image, 99.99)
            axis.imshow(image, vmax=vmax)
        if mode == '3d':
            from matplotlib import cm
            axis = figure.gca(projection='3d')
            X = np.arange(image.shape[1])
            Y = np.arange(image.shape[0])
            X, Y = np.meshgrid(X, Y)
            axis.plot_surface(X,Y,image, cmap=cm.coolwarm,
                                   linewidth=0, antialiased=False)

    def show_average_image(self, mode='2d', figure=None):
        self.show_image(image_type='average_image', mode=mode, figure=figure)

    def show_coordinates(self, figure=None, annotate=False, **kwargs):
        if not figure: figure = plt.figure()

        if self.coordinates is not None:
            axis = figure.gca()
            axis.scatter(self.coordinates[:,0],self.coordinates[:,1], facecolors='none', edgecolors='r', **kwargs)
            if annotate:
                for molecule in self.molecules:
                    for i in np.arange(self.number_of_colours):
                        axis.annotate(molecule.index, molecule.coordinates[i], color='white')
